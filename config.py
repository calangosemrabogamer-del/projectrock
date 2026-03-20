#!/usr/bin/env python3
"""
Configuration & Constants Module
Centralized configuration for unified_scanner
"""

import os
import sys
from pathlib import Path

# ============= ENVIRONMENT =============
DEBUG_MODE = os.getenv('DEBUG_MODE', 'False').lower() == 'true'
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# ============= PATHS (PyInstaller-aware) =============
# When packaged into an executable, PyInstaller unpacks resources into sys._MEIPASS
IS_FROZEN = getattr(sys, 'frozen', False)

if IS_FROZEN:
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent

# Application state directory (persistent between runs)
APP_DIR = Path(os.getenv('PROJECTROCK_HOME', Path.home() / '.projectrock'))
APP_DIR.mkdir(parents=True, exist_ok=True)

DATA_DIR = BASE_DIR / 'data'
LOG_DIR = APP_DIR / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ============= FILE PATHS =============
ROCKYOU_FILE = BASE_DIR / 'rockyou-60.txt'
PROXY_FILE = BASE_DIR / 'proxies.txt'
SAMPLE_PASSWORDS = BASE_DIR / 'sample_passwords.txt'
SAMPLE_URLS = BASE_DIR / 'sample_urls.txt'
MANUAL_URLS = BASE_DIR / 'manual_urls.txt'

# ============= SECURITY =============
# SSL Verification - ALWAYS TRUE for security
VERIFY_SSL = os.getenv('VERIFY_SSL', 'True').lower() == 'true'

# Request timeout (seconds)
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '10'))

# ============= USER AGENTS =============
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

# ============= WORDPRESS DETECTION =============
WP_DETECTION_TIMEOUT = int(os.getenv('WP_DETECTION_TIMEOUT', '10'))
WP_DETECTION_RETRIES = int(os.getenv('WP_DETECTION_RETRIES', '2'))

# ============= SCANNING =============
# Threads for concurrent scanning
SCAN_THREADS = int(os.getenv('SCAN_THREADS', '5'))
MAX_THREADS = int(os.getenv('MAX_THREADS', '20'))

# Password list limits
MAX_PASSWORDS = int(os.getenv('MAX_PASSWORDS', '100'))
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 128

# URL collection
MAX_URLS_BATCH = int(os.getenv('MAX_URLS_BATCH', '100'))
MAX_DISPLAY_URLS = 1000

# ============= ANONYMITY =============
TOR_ENABLED = False  # Default off - user must enable
TOR_SOCKS_HOST = os.getenv('TOR_SOCKS_HOST', '127.0.0.1')
TOR_SOCKS_PORT = int(os.getenv('TOR_SOCKS_PORT', '9050'))

USE_PROXIES = False  # Default off - user must enable
PROXY_TIMEOUT = int(os.getenv('PROXY_TIMEOUT', '5'))
PROXY_TEST_URL = 'https://httpbin.org/get'

# ============= STEALTH OPTIONS =============
STEALTH_DELAYS = {
    'minimal': {'page_load': (2, 4), 'between_requests': (1, 3)},
    'cautious': {'page_load': (4, 8), 'between_requests': (3, 6)},
    'paranoid': {'page_load': (8, 15), 'between_requests': (6, 12)},
}

DEFAULT_STEALTH = 'cautious'

# ============= GOOGLE MAPS DISCOVERY =============
MAPS_DELAY_BETWEEN_LISTINGS = (2, 5)
MAPS_DELAY_BETWEEN_SEARCHES = (10, 20)
MAPS_BROWSER_TIMEOUT = 15

# Cities for discovery
CITIES = {
    'USA': [
        'New York NY', 'Los Angeles CA', 'Chicago IL', 'Houston TX',
        'Phoenix AZ', 'Philadelphia PA', 'San Antonio TX', 'San Diego CA',
    ],
    'Canada': ['Toronto ON', 'Montreal QC', 'Vancouver BC', 'Calgary AB'],
    'Brazil': ['São Paulo SP', 'Rio de Janeiro RJ', 'Brasília DF'],
    'Portugal': ['Lisboa', 'Porto', 'Braga'],
}

# Business types for discovery
BUSINESS_TYPES = {
    'Legal': ['lawyer', 'law firm', 'attorney'],
    'Medical': ['dentist', 'orthodontist', 'doctor'],
    'Healthcare': ['psychologist', 'therapist'],
    'Financial': ['accounting', 'CPA'],
    'Business': ['consulting', 'marketing agency'],
}

# Portuguese business types (for Brazil/Portugal)
BUSINESS_TYPES_PT = {
    'Jurídico': ['advogado', 'escritório de advocacia', 'advogada'],
    'Médico': ['dentista', 'ortodontista', 'médico'],
    'Saúde': ['psicólogo', 'terapeuta'],
    'Financeiro': ['contabilidade', 'contador'],
    'Negócios': ['consultoria', 'agência de marketing'],
}

# ============= VALIDATION LIMITS =============
URL_MIN_LENGTH = 7  # Minimum URL length (http://a)
URL_MAX_LENGTH = 255
USERNAME_MAX_LENGTH = 60
PASSWORD_MAX_LENGTH = 128

# ============= LOGGING =============
LOG_SENSITIVE_DATA = False  # Never log credentials
LOG_FILE_SIZE_MB = 10  # Rotate logs after 10MB
LOG_BACKUP_COUNT = 3  # Keep 3 backup logs

# ============= RATE LIMITING =============
BATCH_DELAY_SECONDS = 0.5  # Small delay between batches to avoid overwhelming servers
MAX_REQUESTS_PER_MINUTE = 60
MIN_DELAY_BETWEEN_TARGETS = 0.1

# ============= MISC =============
AUTO_CLEANUP_ON_EXIT = True  # Removes temp files on exit if enabled

# ============= FILE CONSTRAINTS =============
MAX_FILE_SIZE_MB = 100  # Max file size for import
ALLOWED_IMPORT_EXTENSIONS = ('.txt',)

# ============= REGEX PATTERNS =============
URL_PATTERN = r'^https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
DOMAIN_PATTERN = r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

# ============= RESULTS EXPORT =============
EXPORT_DELAY_BETWEEN_WRITES = 0.1  # seconds
MAX_RESULTS_CSV = 10000  # Max results to export


if __name__ == '__main__':
    # Display config (use for debugging)
    print("Configuration Loaded:")
    print(f"  SSL Verification: {VERIFY_SSL}")
    print(f"  Request Timeout: {REQUEST_TIMEOUT}s")
    print(f"  Scan Threads: {SCAN_THREADS}")
    print(f"  Log Level: {LOG_LEVEL}")
    print(f"  Debug Mode: {DEBUG_MODE}")
    print(f"  Log Directory: {LOG_DIR}")
