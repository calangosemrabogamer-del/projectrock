#!/usr/bin/env python3
"""
Security Module
Security utilities, SSL verification, and secure request handling
"""

import ssl
import urllib3
import requests
from requests.adapters import HTTPAdapter
from typing import Optional, Dict, Any
import config

# Suppress insecure SSL warnings ONLY when explicitly disabled
if not config.VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class SecureRequestSession:
    """
    Secure HTTP session with SSL verification and security best practices
    """
    
    def __init__(self, verify_ssl: bool = True, timeout: int = None, 
                 user_agent: str = None, proxy: Dict[str, str] = None):
        """
        Initialize secure session
        
        Args:
            verify_ssl: Whether to verify SSL certificates (always True recommended)
            timeout: Request timeout in seconds
            user_agent: Custom User-Agent
            proxy: Proxy configuration dict {'http': 'http://...', 'https': 'http://...'}
        """
        self.session = requests.Session()
        self.verify_ssl = verify_ssl
        self.timeout = timeout or config.REQUEST_TIMEOUT
        self.user_agent = user_agent or config.USER_AGENTS[0]
        self.proxy = proxy
        
        # Configure session
        self._configure_session()
    
    def _configure_session(self):
        """Configure session with security best practices"""
        # Set default headers
        self.session.headers.update({
            'User-Agent': self.user_agent,
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'close',
        })
        
        # Set proxy if provided
        if self.proxy:
            self.session.proxies.update(self.proxy)
        
        # Mount HTTPAdapter with timeout and SSL config
        adapter = SecureHTTPAdapter(
            verify_ssl=self.verify_ssl,
            timeout=self.timeout
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
    
    def get(self, url: str, **kwargs) -> Optional[requests.Response]:
        """Safe GET request"""
        try:
            return self.session.get(
                url,
                verify=self.verify_ssl,
                timeout=self.timeout,
                **kwargs
            )
        except Exception as e:
            print(f"GET request failed for {url}: {type(e).__name__}")
            return None
    
    def post(self, url: str, data: Dict = None, json: Dict = None, **kwargs) -> Optional[requests.Response]:
        """Safe POST request"""
        try:
            return self.session.post(
                url,
                data=data,
                json=json,
                verify=self.verify_ssl,
                timeout=self.timeout,
                **kwargs
            )
        except Exception as e:
            print(f"POST request failed for {url}: {type(e).__name__}")
            return None
    
    def close(self):
        """Close session properly"""
        try:
            self.session.close()
        except Exception:
            pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


class SecureHTTPAdapter(HTTPAdapter):
    """
    Custom HTTPAdapter with enforced SSL verification and timeouts
    """
    
    def __init__(self, verify_ssl: bool = True, timeout: int = 10, *args, **kwargs):
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        super().__init__(*args, **kwargs)
    
    def send(self, request, **kwargs):
        """Override send to enforce timeout and SSL"""
        kwargs['timeout'] = self.timeout
        kwargs['verify'] = self.verify_ssl
        return super().send(request, **kwargs)


def get_secure_session(verify_ssl: Optional[bool] = None, 
                       timeout: Optional[int] = None,
                       user_agent: Optional[str] = None,
                       proxy: Optional[Dict[str, str]] = None) -> SecureRequestSession:
    """
    Factory function for creating secure sessions
    
    Args:
        verify_ssl: Override config SSL verification setting
        timeout: Override config timeout
        user_agent: Custom User-Agent string
        proxy: Proxy configuration
    
    Returns:
        SecureRequestSession instance
    """
    verify = verify_ssl if verify_ssl is not None else config.VERIFY_SSL
    timeout_val = timeout or config.REQUEST_TIMEOUT
    
    return SecureRequestSession(
        verify_ssl=verify,
        timeout=timeout_val,
        user_agent=user_agent,
        proxy=proxy
    )


def validate_url(url: str) -> bool:
    """
    Validate URL format and prevent directory traversal attacks
    
    Args:
        url: URL to validate
    
    Returns:
        True if valid, False otherwise
    """
    if not url or not isinstance(url, str):
        return False
    
    if len(url) < config.URL_MIN_LENGTH or len(url) > config.URL_MAX_LENGTH:
        return False
    
    # Check for directory traversal attempts
    if '..' in url or '//' in url.replace('://', ''):
        return False
    
    # Must start with http:// or https://
    if not url.startswith(('http://', 'https://')):
        return False
    
    return True


def validate_domain(domain: str) -> bool:
    """
    Validate domain name format
    
    Args:
        domain: Domain to validate
    
    Returns:
        True if valid, False otherwise
    """
    if not domain or not isinstance(domain, str):
        return False
    
    if len(domain) < 3 or len(domain) > 255:
        return False
    
    # Basic domain validation
    parts = domain.split('.')
    if len(parts) < 2:
        return False
    
    # Each part must be alphanumeric or hyphen
    for part in parts:
        if not part or len(part) > 63:
            return False
        if not all(c.isalnum() or c == '-' for c in part):
            return False
        if part.startswith('-') or part.endswith('-'):
            return False
    
    return True


def sanitize_credentials_from_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove sensitive data from dictionary (in-place safe copy)
    
    Args:
        data: Dictionary potentially containing credentials
    
    Returns:
        New dictionary with sensitive fields removed
    """
    sensitive_keys = ['password', 'passwd', 'pwd', 'secret', 'token', 'key', 'credential']
    
    sanitized = {}
    for key, value in data.items():
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            sanitized[key] = '***REDACTED***'
        else:
            sanitized[key] = value
    
    return sanitized


def normalize_url(url: str) -> str:
    """
    Normalize URL to consistent format
    
    Args:
        url: URL to normalize
    
    Returns:
        Normalized URL
    """
    if not url:
        return ''
    
    url = url.strip()
    
    # Add scheme if missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Remove trailing slash from domain portion
    if url.endswith('/') and url.count('/') == 3:
        url = url.rstrip('/')
    
    return url


if __name__ == '__main__':
    # Test module
    print("Security Module Loaded")
    print(f"SSL Verification Enabled: {config.VERIFY_SSL}")
    
    # Test URL validation
    print("\nURL Validation Tests:")
    test_urls = [
        'https://example.com',
        'http://example.com',
        'example.com',
        '../../../etc/passwd',
        'javascript:alert(1)',
    ]
    for url in test_urls:
        print(f"  {url}: {validate_url(url)}")
