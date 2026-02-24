import time
import threading
from functools import wraps
from core.logger import setup_logger
from core.constants import RATE_LIMIT_MAX_CALLS, RATE_LIMIT_PERIOD_SECONDS, RATE_LIMIT_MAX_WAIT_SECONDS

logger = setup_logger(__name__)

class RateLimiter:
    """Thread-safe rate limiter to prevent API abuse"""
    def __init__(self, max_calls: int = None, period: int = None, max_wait: int = None):
        self.max_calls = max_calls or RATE_LIMIT_MAX_CALLS
        self.period = period or RATE_LIMIT_PERIOD_SECONDS
        self.max_wait = max_wait or RATE_LIMIT_MAX_WAIT_SECONDS  # Maximum wait time to prevent DoS
        self.calls = []
        self.lock = threading.Lock()  # Thread safety
    
    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            obj = args[0] if args else None
            # Check for use_etl attribute to bypass rate limiting for database calls
            ignore_rate_limit = obj and getattr(obj, 'use_etl', False)
            if ignore_rate_limit:
                return func(*args, **kwargs)
            with self.lock:  # Thread-safe access
                now = time.time()
                # Remove old calls outside the time window
                self.calls[:] = [c for c in self.calls if c > now - self.period]
                
                if len(self.calls) >= self.max_calls:
                    wait_time = min(self.period - (now - self.calls[0]), self.max_wait)
                    if wait_time > 0:
                        logger.warning(f"Rate limit reached. Waiting {wait_time:.1f}s")
                        time.sleep(wait_time)
                        # Re-clean after wait
                        now = time.time()
                        self.calls[:] = [c for c in self.calls if c > now - self.period]
                
                self.calls.append(now)
            return func(*args, **kwargs)
        return wrapper

# Default global instance
rate_limiter = RateLimiter(
    max_calls=RATE_LIMIT_MAX_CALLS,
    period=RATE_LIMIT_PERIOD_SECONDS,
    max_wait=RATE_LIMIT_MAX_WAIT_SECONDS
)
