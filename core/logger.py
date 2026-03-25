import logging
from logging.handlers import RotatingFileHandler
import os
import re
from core.config import Config

class SensitiveDataFilter(logging.Filter):
    """Filter to remove sensitive AWS data from logs"""
    
    PATTERNS = [
        (re.compile(r'AKIA[0-9A-Z]{16}'), 'AKIA****************'),
        (re.compile(r'(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{40}(?![A-Za-z0-9+/])'), '****************************************'), # Secret Access Key
        (re.compile(r'\d{12}'), '************'),  # AWS Account ID
        (re.compile(r'arn:aws:[^:]*:[^:]*:\d{12}:[^\s]*'), 'arn:aws:***:***:************:***'),
    ]
    
    def filter(self, record):
        if not isinstance(record.msg, str):
            return True
            
        record.msg = self.sanitize(record.msg)
        if record.args:
            record.args = tuple(self.sanitize(str(arg)) for arg in record.args)
        return True
    
    def sanitize(self, text):
        if not isinstance(text, str):
            return text
        for pattern, replacement in self.PATTERNS:
            text = pattern.sub(replacement, text)
        return text

def setup_logger(name: str = __name__) -> logging.Logger:
    """Configure and return a logger instance with sensitive data filtering"""
    Config.initialize()
    
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers if already configured
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # Add sensitive data filter
        logger.addFilter(SensitiveDataFilter())
        
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # File Handler with rotation (max 10MB, keep 5 backup files)
        file_handler = RotatingFileHandler(
            Config.LOG_FILE,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Stream Handler
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        
        # Set secure permissions on log file
        try:
            if os.path.exists(Config.LOG_FILE):
                os.chmod(Config.LOG_FILE, 0o600)
        except OSError:
            pass
            
    return logger
