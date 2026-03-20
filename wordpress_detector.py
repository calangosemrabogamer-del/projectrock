#!/usr/bin/env python3
"""
WordPress Site Detector
Quickly identifies if a URL is a WordPress site with multiple detection methods
Reusable module for all discovery and scanning scripts
"""

import requests
import logging
import time
from typing import Tuple, Dict, Optional
from urllib.parse import urljoin, urlparse
import functools

import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global cache for WordPress detection results
_wp_cache: Dict[str, Tuple[bool, str]] = {}


class WordPressDetector:
    """Detect if a URL is running WordPress"""
    
    # WordPress detection indicators
    WP_INDICATORS = {
        'wp_content_path': '/wp-content/',
        'wp_includes_path': '/wp-includes/',
        'wp_admin_path': '/wp-admin/',
        'wp_json_path': '/wp-json/',
        'xmlrpc_path': '/xmlrpc.php',
        'wp_login_path': '/wp-login.php',
        'wordpress_version': 'wordpress',
        'wp_generator': 'wordpress',
    }
    
    # Common WordPress paths to check
    WP_PATHS = [
        '/wp-admin/',
        '/wp-login.php',
        '/wp-content/',
        '/wp-includes/',
        '/wp-json/wp/v2/users',
        '/xmlrpc.php',
    ]
    
    def __init__(self, timeout: int = 10, verify_ssl: Optional[bool] = None):
        """Initialize WordPress detector.

        Args:
            timeout: Request timeout in seconds
            verify_ssl: Whether to verify SSL certificates (defaults to project setting)
        """
        self.timeout = timeout
        self.verify_ssl = config.VERIFY_SSL if verify_ssl is None else verify_ssl
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        ]
    
    def is_wordpress(self, url: str) -> Tuple[bool, str]:
        """
        Check if URL is a WordPress site
        
        Args:
            url: URL to check
        
        Returns:
            Tuple of (is_wordpress, reason)
            - is_wordpress (bool): True if site is detected as WordPress
            - reason (str): Detection method used or failure reason
        """
        # Check cache first
        if url in _wp_cache:
            return _wp_cache[url]
        
        try:
            # Normalize URL
            url = self._normalize_url(url)
            if not url:
                result = False, "Invalid URL format"
                _wp_cache[url] = result
                return result
            
            # Try multiple detection methods
            methods = [
                self._check_meta_generator,
                self._check_wp_json_api,
                self._check_wordpress_paths,
                self._check_html_source,
                self._check_wp_admin_access,
            ]
            
            for method in methods:
                result, reason = method(url)
                if result:
                    _wp_cache[url] = (True, reason)
                    return True, reason
            
            result = False, "No WordPress indicators found"
            _wp_cache[url] = result
            return result
        
        except requests.Timeout:
            result = False, "Request timeout"
            _wp_cache[url] = result
            return result
        except requests.ConnectionError:
            result = False, "Connection error"
            _wp_cache[url] = result
            return result
        except Exception as e:
            result = False, f"Error: {str(e)}"
            _wp_cache[url] = result
            return result
    
    def _normalize_url(self, url: str) -> Optional[str]:
        """Normalize URL to standard format"""
        try:
            if not url:
                return None
            
            # Add protocol if missing
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            # Parse and validate
            parsed = urlparse(url)
            if not parsed.netloc:
                return None
            
            # Return base URL
            return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            return None
    
    def _get_response(self, url: str, timeout: int = None) -> Optional[requests.Response]:
        """Make HTTP request with retries"""
        if timeout is None:
            timeout = self.timeout
        
        headers = {'User-Agent': self.user_agents[0]}
        
        for attempt in range(2):
            try:
                response = requests.get(
                    url,
                    timeout=timeout,
                    headers=headers,
                    verify=self.verify_ssl,
                    allow_redirects=True
                )
                return response
            except (requests.Timeout, requests.ConnectionError) as e:
                if attempt == 0:
                    time.sleep(0.5)
                    continue
                return None
            except Exception:
                return None
        
        return None
    
    def _check_meta_generator(self, url: str) -> Tuple[bool, str]:
        """Check for WordPress meta generator tag"""
        try:
            response = self._get_response(url, timeout=self.timeout)
            if not response or response.status_code != 200:
                return False, ""
            
            # Look for WordPress generator meta tag
            if 'wordpress' in response.text.lower():
                if '<meta name="generator"' in response.text.lower():
                    if 'wordpress' in response.text.lower():
                        return True, "Found WordPress meta generator tag"
            
            return False, ""
        except Exception:
            return False, ""
    
    def _check_wp_json_api(self, url: str) -> Tuple[bool, str]:
        """Check for WordPress REST API"""
        try:
            # Check wp-json/wp/v2/users endpoint (more reliable, less strict)
            api_url = urljoin(url, '/wp-json/wp/v2/')
            
            response = self._get_response(api_url, timeout=self.timeout)
            if response and response.status_code == 200:
                try:
                    data = response.json()
                    # Look for WordPress-specific response structure
                    if isinstance(data, dict) and ('routes' in data or 'errors' not in data):
                        return True, "WordPress REST API detected"
                except Exception as e:
                    logger.debug(f"WP JSON parse failed: {type(e).__name__}")
            
            # Also check if the endpoint exists  (any response that's not 404/403)
            if response and response.status_code not in [404, 403, 500]:
                return True, "WordPress REST API endpoint found"
            
            return False, ""
        except Exception:
            return False, ""
    
    def _check_wordpress_paths(self, url: str) -> Tuple[bool, str]:
        """Check for common WordPress directory paths"""
        try:
            indicators_found = []
            
            for path in self.WP_PATHS[:3]:  # Check first 3 paths only
                try:
                    check_url = urljoin(url, path)
                    response = self._get_response(check_url, timeout=self.timeout - 2)
                    
                    # 200, 403, 301 indicate path exists
                    # 404 means path doesn't exist
                    if response and response.status_code != 404:
                        indicators_found.append(path)
                        
                        # If we found 2+ paths, it's definitely WordPress
                        if len(indicators_found) >= 2:
                            return True, f"Found WordPress paths: {', '.join(indicators_found)}"
                except Exception as e:
                    logger.debug(f"WordPress path check failed: {type(e).__name__}")
            
            if len(indicators_found) >= 1:
                return True, f"Found WordPress path: {indicators_found[0]}"
            
            return False, ""
        except Exception:
            return False, ""
    
    def _check_html_source(self, url: str) -> Tuple[bool, str]:
        """Check HTML source for WordPress indicators"""
        try:
            response = self._get_response(url, timeout=self.timeout)
            if not response or response.status_code != 200:
                return False, ""
            
            text = response.text.lower()
            
            # Check for multiple indicators in HTML
            indicators = {
                'wp-content': text.count('/wp-content/'),
                'wp-includes': text.count('/wp-includes/'),
                'wp-json': text.count('/wp-json/'),
                'wordpress': text.count('wordpress'),
                'wp-login': text.count('wp-login'),
            }
            
            # If we found multiple WordPress references, it's likely WordPress
            found_count = sum(1 for v in indicators.values() if v > 0)
            if found_count >= 2:
                found_items = [k for k, v in indicators.items() if v > 0]
                return True, f"Found WordPress indicators in HTML: {', '.join(found_items)}"
            
            return False, ""
        except Exception:
            return False, ""
    
    def _check_wp_admin_access(self, url: str) -> Tuple[bool, str]:
        """Check if /wp-admin/ is accessible (doesn't return 404)"""
        try:
            admin_url = urljoin(url, '/wp-admin/')
            response = self._get_response(admin_url, timeout=self.timeout - 3)
            
            if response:
                # Any response code except 404 suggests WordPress installation
                if response.status_code != 404:
                    return True, f"WordPress admin panel accessible (HTTP {response.status_code})"
            
            return False, ""
        except Exception:
            return False, ""
    
    def batch_check(self, urls: list, progress_callback=None) -> Dict[str, Tuple[bool, str]]:
        """
        Check multiple URLs for WordPress
        
        Args:
            urls: List of URLs to check
            progress_callback: Optional callback function(current, total, url)
        
        Returns:
            Dictionary mapping URLs to (is_wordpress, reason) tuples
        """
        results = {}
        
        for i, url in enumerate(urls):
            if progress_callback:
                progress_callback(i + 1, len(urls), url)
            
            results[url] = self.is_wordpress(url)
            
            # Small delay to avoid overwhelming servers
            time.sleep(0.1)
        
        return results


def detect_and_filter_wordpress(urls: list, timeout: int = 10, verbose: bool = True) -> list:
    """
    Quick function to detect and filter WordPress sites from a list of URLs
    
    Args:
        urls: List of URLs to filter
        timeout: Request timeout
        verbose: Print progress
    
    Returns:
        List of URLs confirmed to be WordPress sites
    """
    detector = WordPressDetector(timeout=timeout)
    wordpress_urls = []
    
    total = len(urls)
    for i, url in enumerate(urls, 1):
        if verbose:
            print(f"[{i}/{total}] Checking {url}...", end=" ", flush=True)
        
        is_wp, reason = detector.is_wordpress(url)
        
        if is_wp:
            wordpress_urls.append(url)
            if verbose:
                print(f"✓ WordPress ({reason})")
        else:
            if verbose:
                print(f"✗ Not WordPress")
    
    return wordpress_urls


if __name__ == "__main__":
    # Example usage
    test_urls = [
        "https://example.com",
        "https://wordpress.com",
    ]
    
    detector = WordPressDetector()
    for url in test_urls:
        is_wp, reason = detector.is_wordpress(url)
        print(f"{url}: {is_wp} ({reason})")
