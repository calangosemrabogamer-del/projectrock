#!/usr/bin/env python3
"""
Scanner Engine Module
Consolidated WordPress scanning logic with proper exception handling
"""

import threading
import queue
import time
from typing import Optional, List, Callable, Dict, Any
from dataclasses import dataclass, field
import config
import security
from logger import get_operation_logger, get_audit_logger


@dataclass
class ScanResult:
    """Result from a single scan"""
    url: str
    method: str
    success: bool
    status_code: Optional[int] = None
    response_time: float = 0.0
    error: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[str] = None


class ScannerEngine:
    """
    Thread-safe WordPress scanner engine
    """
    
    def __init__(self, max_threads: int = 15, verify_wordpress: bool = True):
        """
        Initialize scanner engine
        
        Args:
            max_threads: Number of concurrent threads
            verify_wordpress: Whether to verify WordPress before scanning
        """
        self.max_threads = min(max_threads, config.MAX_THREADS)
        self.verify_wordpress = verify_wordpress
        
        self.work_queue: queue.Queue = queue.Queue()
        self.result_queue: queue.Queue = queue.Queue()
        self.threads: List[threading.Thread] = []
        
        self.running = False
        self.lock = threading.RLock()
        
        self.logger = get_operation_logger()
        self.audit_logger = get_audit_logger()
        
        # Statistics
        self.total_scanned = 0
        self.successful_scans = 0
        self.failed_scans = 0
    
    def add_target(self, url: str, method: str = 'wp_scanner', metadata: Dict = None):
        """
        Add target URL to scan queue
        
        Args:
            url: Target URL
            method: Scanning method identifier
            metadata: Optional metadata dict
        """
        if not security.validate_url(url):
            self.audit_logger.validation_failed("URL", f"Invalid URL: {url}")
            return False
        
        self.work_queue.put({
            'url': url,
            'method': method,
            'metadata': metadata or {}
        })
        return True
    
    def add_targets_batch(self, urls: List[str], method: str = 'wp_scanner'):
        """
        Add batch of targets
        
        Args:
            urls: List of URLs
            method: Scanning method identifier
        
        Returns:
            Number of targets added
        """
        count = 0
        for url in urls:
            if self.add_target(url, method):
                count += 1
        
        self.logger.batch_started(f"batch_{int(time.time())}", count)
        return count
    
    def start(self):
        """Start scanning threads"""
        with self.lock:
            if self.running:
                return
            
            self.running = True
            self.audit_logger.info_event("SCANNER_START", f"Starting {self.max_threads} scanner threads")
            
            # Create worker threads
            for i in range(self.max_threads):
                thread = threading.Thread(target=self._worker, daemon=True)
                thread.start()
                self.threads.append(thread)
    
    def stop(self):
        """Stop scanning threads"""
        with self.lock:
            if not self.running:
                return
            
            self.running = False
            self.audit_logger.info_event("SCANNER_STOP", "Stopping scanner threads")
            
            # Wait for threads to finish
            for thread in self.threads:
                thread.join(timeout=5)
            
            self.threads.clear()
    
    def _worker(self):
        """Worker thread function"""
        while self.running:
            try:
                # Get work with timeout
                try:
                    task = self.work_queue.get(timeout=1)
                except queue.Empty:
                    continue
                
                # Process task
                try:
                    result = self._scan_target(task)
                    self.result_queue.put(result)
                except Exception as e:
                    # Specific exception handling
                    self.audit_logger.error_event("SCAN_WORKER", f"{type(e).__name__}: {str(e)[:100]}")
                finally:
                    self.work_queue.task_done()
            
            except Exception as e:
                # Outer exception handler
                self.audit_logger.error_event("WORKER_EXCEPTION", f"{type(e).__name__}: {str(e)[:100]}")
    
    def _scan_target(self, task: Dict) -> ScanResult:
        """
        Scan single target
        
        Args:
            task: Task dictionary with 'url', 'method', 'metadata'
        
        Returns:
            ScanResult object
        """
        url = task['url']
        method = task['method']
        
        result = ScanResult(
            url=url,
            method=method,
            success=False,
            timestamp=str(time.time())
        )
        
        self.logger.scan_started(url, method)
        
        try:
            # Verify WordPress first if enabled
            if self.verify_wordpress:
                from wordpress_detector import WordPressDetector
                detector = WordPressDetector()
                is_wp = detector.is_wordpress(url)
                
                if not is_wp:
                    self.logger.wordpress_verification_failed(url)
                    result.error = "Not a WordPress site"
                    self.failed_scans += 1
                    return result
            
            # Scan WordPress
            result = self._execute_scan(url, method, result)
            
            if result.success:
                self.successful_scans += 1
                self.logger.scan_completed(url, "SUCCESS")
            else:
                self.failed_scans += 1
                self.logger.scan_failed(url, result.error or "Unknown error")
        
        except ConnectionError as e:
            result.error = f"Connection failed: {str(e)[:50]}"
            result.success = False
            self.failed_scans += 1
            self.logger.scan_failed(url, result.error)
        except TimeoutError as e:
            result.error = f"Request timeout: {str(e)[:50]}"
            result.success = False
            self.failed_scans += 1
            self.logger.scan_failed(url, result.error)
        except ValueError as e:
            result.error = f"Invalid value: {str(e)[:50]}"
            result.success = False
            self.failed_scans += 1
            self.logger.scan_failed(url, result.error)
        except Exception as e:
            # Catch-all with proper type identification
            result.error = f"{type(e).__name__}: {str(e)[:50]}"
            result.success = False
            self.failed_scans += 1
            self.logger.scan_failed(url, result.error)
        
        self.total_scanned += 1
        return result
    
    def _execute_scan(self, url: str, method: str, result: ScanResult) -> ScanResult:
        """
        Execute actual WordPress scan
        This is a placeholder for integration with actual scanning methods
        
        Args:
            url: Target URL
            method: Scanning method
            result: Result object to populate
        
        Returns:
            Populated ScanResult object
        """
        try:
            start_time = time.time()
            
            # Generic WordPress info check
            session = security.get_secure_session()
            response = session.get(url + '/wp-admin/', timeout=config.REQUEST_TIMEOUT)
            session.close()
            
            result.response_time = time.time() - start_time
            result.status_code = response.status_code
            result.success = response.status_code in (200, 302, 401, 403)
            
            return result
        except Exception as e:
            raise
    
    def get_results(self, timeout: float = 0.1) -> Optional[ScanResult]:
        """
        Get next result from queue
        
        Args:
            timeout: Queue timeout in seconds
        
        Returns:
            ScanResult or None if queue empty
        """
        try:
            return self.result_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def get_all_results(self) -> List[ScanResult]:
        """
        Get all results from queue (non-blocking)
        
        Returns:
            List of ScanResult objects
        """
        results = []
        while not self.result_queue.empty():
            try:
                results.append(self.result_queue.get_nowait())
            except queue.Empty:
                break
        
        return results
    
    def wait_completion(self, timeout: Optional[float] = None):
        """
        Wait for all current tasks to complete
        
        Args:
            timeout: Maximum wait time in seconds
        """
        try:
            self.work_queue.join()
        except Exception:
            pass
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get scanning statistics"""
        with self.lock:
            return {
                'total_scanned': self.total_scanned,
                'successful': self.successful_scans,
                'failed': self.failed_scans,
                'pending': self.work_queue.qsize(),
                'threads': len([t for t in self.threads if t.is_alive()]),
            }


class ResultProcessor:
    """
    Process and export scan results
    """
    
    def __init__(self):
        self.audit_logger = get_audit_logger()
    
    def export_csv(self, results: List[ScanResult], filename: str) -> bool:
        """
        Export results to CSV
        
        Args:
            results: List of ScanResult objects
            filename: Output filename
        
        Returns:
            True if successful
        """
        if len(results) > config.MAX_RESULTS_CSV:
            self.audit_logger.validation_failed(
                "CSV_EXPORT",
                f"Too many results: {len(results)} > {config.MAX_RESULTS_CSV}"
            )
            return False
        
        try:
            import csv
            
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=['url', 'method', 'success', 'status_code', 'response_time', 'error']
                )
                writer.writeheader()
                
                for result in results:
                    writer.writerow({
                        'url': result.url,
                        'method': result.method,
                        'success': result.success,
                        'status_code': result.status_code,
                        'response_time': result.response_time,
                        'error': result.error or ''
                    })
            
            self.audit_logger.info_event("CSV_EXPORT", f"Exported {len(results)} results to {filename}")
            return True
        
        except PermissionError as e:
            self.audit_logger.error_event("CSV_EXPORT", f"Permission denied: {filename}")
            return False
        except IOError as e:
            self.audit_logger.error_event("CSV_EXPORT", f"IO error: {str(e)[:100]}")
            return False
        except Exception as e:
            self.audit_logger.error_event("CSV_EXPORT", f"{type(e).__name__}: {str(e)[:100]}")
            return False


if __name__ == '__main__':
    print("Scanner Engine Module Loaded")
    
    # Test scanner engine
    engine = ScannerEngine(max_threads=3)
    engine.add_target("https://example.com")
    
    engine.start()
    print("Scanner started")
    
    time.sleep(2)
    engine.stop()
    print(f"Statistics: {engine.get_statistics()}")
