#!/usr/bin/env python3
"""
Logging Module
Secure audit logging without credential exposure
"""

import logging
import logging.handlers
from pathlib import Path
from datetime import datetime
import config
import security


class SensitiveInfoFilter(logging.Filter):
    """
    Filter to redact sensitive information from log records
    Removes passwords, credentials, tokens, etc.
    """
    
    SENSITIVE_KEYS = ['password', 'passwd', 'pwd', 'secret', 'token', 'key', 'credential', 'auth']
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Redact sensitive data from log message
        
        Args:
            record: Log record to filter
        
        Returns:
            True to allow logging
        """
        if record.msg:
            # Handle string formatting
            try:
                if isinstance(record.msg, str):
                    message = record.msg % record.args if record.args else record.msg
                    message = self._redact(message)
                    record.msg = message
                    record.args = ()
            except (TypeError, ValueError):
                # If formatting fails, just try to redact as-is
                try:
                    record.msg = self._redact(str(record.msg))
                except Exception:
                    pass
        
        return True
    
    @staticmethod
    def _redact(message: str) -> str:
        """Redact sensitive keywords from message"""
        if not message:
            return message
        
        message_lower = message.lower()
        
        # Check for sensitive patterns and redact
        for key in SensitiveInfoFilter.SENSITIVE_KEYS:
            if key in message_lower:
                # Found sensitive keyword, redact value after it
                import re
                # Match patterns like: password="xyz", passwd: xyz, etc.
                pattern = rf'{key}\s*[=:]\s*["\']?([^"\'\s,\]}}]*)["\']?'
                message = re.sub(pattern, f'{key}=***REDACTED***', message, flags=re.IGNORECASE)
        
        return message


class ContextFilter(logging.Filter):
    """Add contextual information to log records"""
    
    def __init__(self, context_name: str = 'app'):
        super().__init__()
        self.context_name = context_name
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add context to record"""
        record.context = self.context_name
        record.timestamp = datetime.now().isoformat()
        return True


class AuditLogger:
    """
    Audit logger for security-relevant events
    """
    
    def __init__(self, name: str = 'audit', log_dir: Path = config.LOG_DIR):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(config.LOG_LEVEL)
        
        # Create log directory
        log_dir.mkdir(exist_ok=True)
        
        # Configure handlers
        self._setup_handlers(log_dir)
        
        # Add filters
        sensitive_filter = SensitiveInfoFilter()
        context_filter = ContextFilter('audit')
        
        for handler in self.logger.handlers:
            handler.addFilter(sensitive_filter)
            handler.addFilter(context_filter)
    
    def _setup_handlers(self, log_dir: Path):
        """Setup logging handlers"""
        
        # File handler with rotation
        log_file = log_dir / f'audit_{datetime.now().strftime("%Y%m%d")}.log'
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=config.LOG_FILE_SIZE_MB * 1024 * 1024,
            backupCount=config.LOG_BACKUP_COUNT
        )
        file_handler.setLevel(logging.INFO)
        
        # Formatter with timestamp
        formatter = logging.Formatter(
            '%(timestamp)s - %(levelname)s - %(context)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
    
    def security_event(self, event_type: str, details: str):
        """Log security-relevant event"""
        self.logger.warning(f"SECURITY_EVENT [{event_type}]: {details}")
    
    def validation_failed(self, validation_type: str, reason: str):
        """Log validation failure"""
        self.logger.warning(f"VALIDATION_FAILED [{validation_type}]: {reason}")
    
    def error_event(self, error_type: str, message: str):
        """Log error event"""
        self.logger.error(f"ERROR [{error_type}]: {message}")
    
    def info_event(self, event_type: str, message: str):
        """Log informational event"""
        self.logger.info(f"{event_type}: {message}")
    
    def debug_event(self, event_type: str, message: str):
        """Log debug event (only in DEBUG mode)"""
        if config.DEBUG_MODE:
            self.logger.debug(f"{event_type}: {message}")


class OperationLogger:
    """
    Logger for operational events during scanning/discovery
    """
    
    def __init__(self, name: str = 'operations', log_dir: Path = config.LOG_DIR):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(config.LOG_LEVEL)
        
        # Create log directory
        log_dir.mkdir(exist_ok=True)
        
        # Setup handlers
        self._setup_handlers(log_dir)
        
        # Add filters
        sensitive_filter = SensitiveInfoFilter()
        context_filter = ContextFilter('operations')
        
        for handler in self.logger.handlers:
            handler.addFilter(sensitive_filter)
            handler.addFilter(context_filter)
    
    def _setup_handlers(self, log_dir: Path):
        """Setup logging handlers"""
        
        # Daily file handler
        log_file = log_dir / f'operations_{datetime.now().strftime("%Y%m%d")}.log'
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=config.LOG_FILE_SIZE_MB * 1024 * 1024,
            backupCount=config.LOG_BACKUP_COUNT
        )
        file_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(timestamp)s - %(levelname)s - %(context)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
    
    def url_discovered(self, url: str, source: str):
        """Log URL discovery"""
        # Sanitize URL for logging
        safe_url = url[:50] + '...' if len(url) > 50 else url
        self.logger.info(f"URL_DISCOVERED [{source}]: {safe_url}")
    
    def wordpress_detected(self, url: str, methods: list):
        """Log WordPress detection"""
        safe_url = url[:50] + '...' if len(url) > 50 else url
        self.logger.info(f"WORDPRESS_DETECTED [{safe_url}]: {', '.join(methods)}")
    
    def wordpress_verification_failed(self, url: str):
        """Log WordPress verification failure"""
        safe_url = url[:50] + '...' if len(url) > 50 else url
        self.logger.info(f"NOT_WORDPRESS: {safe_url}")
    
    def scan_started(self, target: str, method: str):
        """Log scan start"""
        self.logger.info(f"SCAN_STARTED [method={method}]: {target}")
    
    def scan_completed(self, target: str, result: str):
        """Log scan completion"""
        self.logger.info(f"SCAN_COMPLETED: {target} -> {result}")
    
    def scan_failed(self, target: str, reason: str):
        """Log scan failure"""
        self.logger.warning(f"SCAN_FAILED: {target} ({reason})")
    
    def batch_started(self, batch_id: str, count: int):
        """Log batch start"""
        self.logger.info(f"BATCH_STARTED [id={batch_id}]: {count} items")
    
    def batch_completed(self, batch_id: str, count: int, success: int):
        """Log batch completion"""
        self.logger.info(f"BATCH_COMPLETED [id={batch_id}]: {success}/{count} successful")


# Global instances
audit_logger = AuditLogger()
operation_logger = OperationLogger()


def get_audit_logger() -> AuditLogger:
    """Get global audit logger instance"""
    return audit_logger


def get_operation_logger() -> OperationLogger:
    """Get global operation logger instance"""
    return operation_logger


if __name__ == '__main__':
    # Test logging
    print("Logging Module Loaded")
    
    # Test audit logger
    audit = get_audit_logger()
    audit.info_event("TEST", "Audit logger test")
    audit.security_event("LOGIN", "User login attempt")
    audit.validation_failed("URL", "Invalid URL format")
    
    # Test operation logger
    ops = get_operation_logger()
    ops.url_discovered("https://example.com/wp-admin", "Google Maps")
    ops.wordpress_detected("https://example.com", ["meta_tags", "rest_api"])
    ops.scan_started("https://example.com", "WP Scanner")
