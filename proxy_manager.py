#!/usr/bin/env python3
"""
Proxy Manager Module
Consolidated proxy and TOR management
"""

import os
import socks
import socket
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import random
import requests
import config
import security
from logger import get_audit_logger


@dataclass
class Proxy:
    """Proxy configuration"""
    protocol: str  # 'http', 'https', 'socks5'
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    last_tested: Optional[datetime] = None
    working: bool = True
    test_count: int = 0
    success_count: int = 0
    
    def __repr__(self):
        return f"{self.protocol}://{self.host}:{self.port}"
    
    def get_url(self) -> str:
        """Get proxy URL"""
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol}://{self.host}:{self.port}"
    
    def get_requests_dict(self) -> Dict[str, str]:
        """Get proxy dict for requests library"""
        return {
            'http': self.get_url(),
            'https': self.get_url(),
        }
    
    def mark_tested(self, success: bool):
        """Mark proxy as tested"""
        self.last_tested = datetime.now()
        self.test_count += 1
        if success:
            self.success_count += 1
            self.working = True
        else:
            # Mark failed if 3+ consecutive failures
            if self.test_count - self.success_count >= 3:
                self.working = False
    
    def success_rate(self) -> float:
        """Get success rate percentage"""
        if self.test_count == 0:
            return 0.0
        return (self.success_count / self.test_count) * 100


class ProxyManager:
    """
    Manage proxy rotation and testing
    """
    
    def __init__(self, proxy_file: Optional[str] = None):
        """
        Initialize proxy manager
        
        Args:
            proxy_file: Path to proxy file (one per line, format: protocol://host:port)
        """
        self.proxies: List[Proxy] = []
        self.tor_available = False
        self.audit_logger = get_audit_logger()
        
        if proxy_file:
            self.load_proxies_from_file(proxy_file)
        
        self._check_tor_availability()
    
    def load_proxies_from_file(self, proxy_file: str):
        """
        Load proxies from file
        
        Args:
            proxy_file: Path to proxy file
        """
        try:
            if not os.path.exists(proxy_file):
                self.audit_logger.info_event("PROXY_LOAD", f"Proxy file not found: {proxy_file}")
                return
            
            with open(proxy_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    self._parse_and_add_proxy(line)
            
            self.audit_logger.info_event("PROXY_LOAD", f"Loaded {len(self.proxies)} proxies")
        except Exception as e:
            self.audit_logger.error_event("PROXY_LOAD", f"Failed to load proxies: {type(e).__name__}: {str(e)[:100]}")
    
    def _parse_and_add_proxy(self, proxy_line: str):
        """Parse proxy line and add to list"""
        try:
            # Format: protocol://host:port or host:port
            if '://' not in proxy_line:
                proxy_line = 'http://' + proxy_line
            
            protocol = proxy_line.split('://')[0].lower()
            if protocol not in ('http', 'https', 'socks5'):
                protocol = 'http'
            
            host_port = proxy_line.split('://', 1)[1]
            host, port = host_port.rsplit(':', 1)
            
            try:
                port = int(port)
            except ValueError:
                return
            
            proxy = Proxy(protocol=protocol, host=host, port=port)
            self.proxies.append(proxy)
        except Exception:
            pass
    
    def _check_tor_availability(self):
        """Check if TOR is available"""
        try:
            import stem
            self.tor_available = True
        except ImportError:
            self.tor_available = False
    
    def get_random_proxy(self, working_only: bool = True) -> Optional[Proxy]:
        """
        Get random proxy
        
        Args:
            working_only: Only return proxies with working status
        
        Returns:
            Random proxy or None
        """
        if not self.proxies:
            return None
        
        available = self.proxies if not working_only else [p for p in self.proxies if p.working]
        
        if not available:
            return None
        
        return random.choice(available)
    
    def get_best_proxy(self) -> Optional[Proxy]:
        """
        Get proxy with best success rate
        
        Returns:
            Best performing proxy or None
        """
        if not self.proxies:
            return None
        
        working = [p for p in self.proxies if p.working]
        if not working:
            return self.get_random_proxy(working_only=False)
        
        return max(working, key=lambda p: p.success_rate())
    
    def get_next_proxy(self, last_used: Optional[Proxy] = None) -> Optional[Proxy]:
        """
        Get next proxy (rotation)
        
        Args:
            last_used: Previously used proxy to skip
        
        Returns:
            Next proxy in rotation
        """
        if not self.proxies:
            return None
        
        working = [p for p in self.proxies if p.working]
        if not working:
            working = self.proxies
        
        if last_used and last_used in working:
            working.remove(last_used)
        
        if not working:
            return None
        
        return random.choice(working)
    
    def test_proxy(self, proxy: Proxy, timeout: int = 5) -> bool:
        """
        Test proxy connectivity
        
        Args:
            proxy: Proxy to test
            timeout: Timeout in seconds
        
        Returns:
            True if proxy works
        """
        try:
            session = security.get_secure_session(proxy=proxy.get_requests_dict())
            response = session.get(
                config.PROXY_TEST_URL,
                timeout=timeout
            )
            success = response.status_code == 200
            proxy.mark_tested(success)
            session.close()
            return success
        except Exception as e:
            proxy.mark_tested(False)
            return False
    
    def test_all_proxies(self, timeout: int = 5, show_progress=None):
        """
        Test all proxies
        
        Args:
            timeout: Timeout per proxy
            show_progress: Callback function for progress updates
        """
        for i, proxy in enumerate(self.proxies):
            if show_progress:
                show_progress(i + 1, len(self.proxies), proxy)
            
            self.test_proxy(proxy, timeout)
    
    def get_statistics(self) -> Dict:
        """Get proxy statistics"""
        if not self.proxies:
            return {'total': 0, 'working': 0, 'dead': 0}
        
        working = len([p for p in self.proxies if p.working])
        dead = len(self.proxies) - working
        
        return {
            'total': len(self.proxies),
            'working': working,
            'dead': dead,
            'avg_success_rate': sum(p.success_rate() for p in self.proxies) / len(self.proxies) if self.proxies else 0
        }


class TORManager:
    """
    Manage TOR connection
    """
    
    def __init__(self):
        """Initialize TOR manager"""
        self.audit_logger = get_audit_logger()
        self.available = self._check_tor_available()
        self.socks_host = config.TOR_SOCKS_HOST
        self.socks_port = config.TOR_SOCKS_PORT
    
    def _check_tor_available(self) -> bool:
        """Check if TOR is available"""
        try:
            import stem
            return True
        except ImportError:
            self.audit_logger.info_event("TOR_CHECK", "Stem library not available")
            return False
    
    def get_socks_proxy(self) -> Dict[str, str]:
        """
        Get SOCKS proxy dict for TOR
        
        Returns:
            Proxy dict for requests library
        """
        return {
            'http': f'socks5://{self.socks_host}:{self.socks_port}',
            'https': f'socks5://{self.socks_host}:{self.socks_port}',
        }
    
    def configure_socks(self):
        """Configure socket module for SOCKS"""
        try:
            socks.set_default_proxy(
                socks.SOCKS5,
                self.socks_host,
                self.socks_port
            )
            socket.socket = socks.socksocket
            self.audit_logger.info_event("TOR_CONFIG", "SOCKS configured successfully")
            return True
        except Exception as e:
            self.audit_logger.error_event("TOR_CONFIG", str(e)[:100])
            return False
    
    def test_connection(self) -> bool:
        """Test TOR connection"""
        try:
            session = security.get_secure_session(proxy=self.get_socks_proxy())
            response = session.get('https://check.torproject.org', timeout=10)
            session.close()
            return response.status_code == 200
        except Exception:
            return False


# Global manager instances
_proxy_manager: Optional[ProxyManager] = None
_tor_manager: Optional[TORManager] = None


def get_proxy_manager() -> ProxyManager:
    """Get global proxy manager"""
    global _proxy_manager
    if _proxy_manager is None:
        _proxy_manager = ProxyManager(str(config.PROXY_FILE) if config.PROXY_FILE.exists() else None)
    return _proxy_manager


def get_tor_manager() -> TORManager:
    """Get global TOR manager"""
    global _tor_manager
    if _tor_manager is None:
        _tor_manager = TORManager()
    return _tor_manager


if __name__ == '__main__':
    print("Proxy Manager Module Loaded")
    
    # Test proxy manager
    manager = ProxyManager()
    print(f"Loaded proxies: {len(manager.proxies)}")
    print(f"Statistics: {manager.get_statistics()}")
    
    # Test TOR manager
    tor = get_tor_manager()
    print(f"TOR Available: {tor.available}")
