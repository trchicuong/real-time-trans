"""
Adaptive Rate Limiter - Monitor API performance và tự động điều chỉnh request rate
"""
import time
import threading
from collections import deque
from .logger import log_debug, log_error

class AdaptiveRateLimiter:
    """
    Monitor API response times và tự động điều chỉnh capture rate.
    Implement backpressure khi API chậm, exponential backoff khi failures.
    """
    
    def __init__(self, 
                 base_interval=0.2,
                 min_interval=0.1,
                 max_interval=2.0,
                 slow_threshold=2.0,
                 fast_threshold=0.5):
        """
        Args:
            base_interval: Base capture interval (seconds)
            min_interval: Minimum interval (fastest capture rate)
            max_interval: Maximum interval (slowest capture rate)
            slow_threshold: Coi API là "slow" nếu response time > threshold (s)
            fast_threshold: Coi API là "fast" nếu response time < threshold (s)
        """
        self.base_interval = base_interval
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.slow_threshold = slow_threshold
        self.fast_threshold = fast_threshold
        
        # Current state
        self.current_interval = base_interval
        self.is_throttled = False
        
        # Response time tracking (last 20 requests)
        self.response_times = deque(maxlen=20)
        self._lock = threading.RLock()
        
        # Failure tracking cho exponential backoff
        self.consecutive_failures = 0
        self.last_failure_time = None
        self.backoff_multiplier = 1.0
        self.max_backoff_multiplier = 8.0  # Max 8x slowdown
        
        # Statistics
        self.total_requests = 0
        self.total_failures = 0
        self.throttle_events = 0
        self.speedup_events = 0
    
    def record_request_start(self):
        """
        Gọi trước khi bắt đầu API request.
        
        Returns:
            start_time (float) - Timestamp để track duration
        """
        return time.time()
    
    def record_request_success(self, start_time):
        """
        Gọi sau khi API request thành công.
        
        Args:
            start_time: Timestamp từ record_request_start()
        """
        try:
            duration = time.time() - start_time
            
            with self._lock:
                self.total_requests += 1
                self.response_times.append(duration)
                
                # Reset failure tracking khi thành công
                if self.consecutive_failures > 0:
                    log_debug(f"API recovered after {self.consecutive_failures} failures")
                    self.consecutive_failures = 0
                    self.backoff_multiplier = 1.0
                
                # Adaptive adjustment
                self._adjust_rate_based_on_performance()
                
        except Exception as e:
            log_error("Error recording request success", e)
    
    def record_request_failure(self, start_time=None):
        """
        Gọi sau khi API request thất bại.
        Implement exponential backoff.
        
        Args:
            start_time: Optional timestamp từ record_request_start()
        """
        try:
            with self._lock:
                self.total_requests += 1
                self.total_failures += 1
                self.consecutive_failures += 1
                self.last_failure_time = time.time()
                
                # Exponential backoff: 2^failures * base_interval
                # Max 8x slowdown
                self.backoff_multiplier = min(
                    2 ** min(self.consecutive_failures, 3),  # 2^0=1, 2^1=2, 2^2=4, 2^3=8
                    self.max_backoff_multiplier
                )
                
                # Apply backoff immediately
                self.current_interval = min(
                    self.base_interval * self.backoff_multiplier,
                    self.max_interval
                )
                
                self.is_throttled = True
                self.throttle_events += 1
                
                log_debug(
                    f"API failure #{self.consecutive_failures}, "
                    f"backoff={self.backoff_multiplier}x, "
                    f"new_interval={self.current_interval:.2f}s"
                )
                
        except Exception as e:
            log_error("Error recording request failure", e)
    
    def _adjust_rate_based_on_performance(self):
        """
        Tự động điều chỉnh capture rate dựa trên API performance.
        Gọi bởi record_request_success().
        """
        try:
            if len(self.response_times) < 5:
                # Chưa đủ data để judge
                return
            
            # Tính average response time (last 10 requests)
            recent_times = list(self.response_times)[-10:]
            avg_response_time = sum(recent_times) / len(recent_times)
            
            # Decision logic
            if avg_response_time > self.slow_threshold:
                # API chậm → Throttle (tăng interval)
                if not self.is_throttled:
                    self.current_interval = min(
                        self.current_interval * 1.5,  # Tăng 50%
                        self.max_interval
                    )
                    self.is_throttled = True
                    self.throttle_events += 1
                    log_debug(
                        f"API slow (avg={avg_response_time:.2f}s), "
                        f"throttling to {self.current_interval:.2f}s"
                    )
                    
            elif avg_response_time < self.fast_threshold:
                # API nhanh → Speed up (giảm interval)
                if self.is_throttled or self.current_interval > self.min_interval:
                    self.current_interval = max(
                        self.current_interval * 0.8,  # Giảm 20%
                        self.min_interval
                    )
                    
                    # Unthrottle nếu đã về gần base_interval
                    if self.current_interval <= self.base_interval * 1.1:
                        self.is_throttled = False
                        self.speedup_events += 1
                        log_debug(
                            f"API fast (avg={avg_response_time:.2f}s), "
                            f"speeding up to {self.current_interval:.2f}s"
                        )
                        
        except Exception as e:
            log_error("Error adjusting rate", e)
    
    def get_current_interval(self):
        """
        Get current recommended capture interval.
        
        Returns:
            interval (float) - Seconds between captures
        """
        try:
            with self._lock:
                return self.current_interval
        except Exception as e:
            log_error("Error getting current interval", e)
            return self.base_interval
    
    def should_skip_request(self):
        """
        Kiểm tra có nên skip request này không (khi đang backoff).
        
        Returns:
            True nếu nên skip (đang trong backoff period)
        """
        try:
            with self._lock:
                # Nếu có consecutive failures và chưa đủ thời gian backoff
                if self.consecutive_failures > 0 and self.last_failure_time:
                    time_since_failure = time.time() - self.last_failure_time
                    required_wait = self.current_interval * self.backoff_multiplier
                    
                    if time_since_failure < required_wait:
                        return True
                
                return False
                
        except Exception as e:
            log_error("Error checking should_skip_request", e)
            return False
    
    def reset(self):
        """Reset về base interval."""
        try:
            with self._lock:
                self.current_interval = self.base_interval
                self.is_throttled = False
                self.consecutive_failures = 0
                self.backoff_multiplier = 1.0
                self.response_times.clear()
                log_debug("Rate limiter reset to base interval")
        except Exception as e:
            log_error("Error resetting rate limiter", e)
    
    def get_stats(self):
        """
        Get statistics.
        
        Returns:
            Dictionary với stats
        """
        try:
            with self._lock:
                # Calculate metrics
                avg_response_time = 0.0
                if self.response_times:
                    avg_response_time = sum(self.response_times) / len(self.response_times)
                
                failure_rate = 0.0
                if self.total_requests > 0:
                    failure_rate = self.total_failures / self.total_requests * 100
                
                return {
                    "current_interval": f"{self.current_interval:.3f}s",
                    "base_interval": f"{self.base_interval:.3f}s",
                    "is_throttled": self.is_throttled,
                    "backoff_multiplier": f"{self.backoff_multiplier:.1f}x",
                    "consecutive_failures": self.consecutive_failures,
                    "avg_response_time": f"{avg_response_time:.3f}s",
                    "total_requests": self.total_requests,
                    "total_failures": self.total_failures,
                    "failure_rate": f"{failure_rate:.1f}%",
                    "throttle_events": self.throttle_events,
                    "speedup_events": self.speedup_events,
                    "response_samples": len(self.response_times)
                }
        except Exception as e:
            log_error("Error getting rate limiter stats", e)
            return {
                "current_interval": f"{self.base_interval:.3f}s",
                "base_interval": f"{self.base_interval:.3f}s",
                "is_throttled": False,
                "backoff_multiplier": "1.0x",
                "consecutive_failures": 0,
                "avg_response_time": "0.000s",
                "total_requests": 0,
                "total_failures": 0,
                "failure_rate": "0%",
                "throttle_events": 0,
                "speedup_events": 0,
                "response_samples": 0
            }
    
    def get_average_response_time(self):
        """Get average response time của recent requests."""
        try:
            with self._lock:
                if not self.response_times:
                    return 0.0
                return sum(self.response_times) / len(self.response_times)
        except Exception as e:
            log_error("Error getting average response time", e)
            return 0.0
    
    def is_healthy(self):
        """
        Kiểm tra API có healthy không.
        
        Returns:
            True nếu API đang healthy (không có failures, response time OK)
        """
        try:
            with self._lock:
                # Unhealthy nếu có consecutive failures
                if self.consecutive_failures > 0:
                    return False
                
                # Unhealthy nếu đang throttled
                if self.is_throttled:
                    return False
                
                # Unhealthy nếu avg response time quá cao
                avg_time = self.get_average_response_time()
                if avg_time > self.slow_threshold:
                    return False
                
                return True
                
        except Exception as e:
            log_error("Error checking health", e)
            return True  # Conservative: assume healthy on error


# Singleton instance
_rate_limiter = None

def get_rate_limiter():
    """Get singleton AdaptiveRateLimiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = AdaptiveRateLimiter()
    return _rate_limiter


# Convenience functions
def record_api_start():
    """Convenience function for recording API start."""
    return get_rate_limiter().record_request_start()

def record_api_success(start_time):
    """Convenience function for recording API success."""
    get_rate_limiter().record_request_success(start_time)

def record_api_failure(start_time=None):
    """Convenience function for recording API failure."""
    get_rate_limiter().record_request_failure(start_time)

def get_current_capture_interval():
    """Convenience function for getting current interval."""
    return get_rate_limiter().get_current_interval()

def should_skip_api_request():
    """Convenience function for checking should skip."""
    return get_rate_limiter().should_skip_request()

def reset_rate_limiter():
    """Convenience function for resetting."""
    get_rate_limiter().reset()

def get_rate_limiter_stats():
    """Convenience function for getting stats."""
    return get_rate_limiter().get_stats()

def is_api_healthy():
    """Convenience function for checking health."""
    return get_rate_limiter().is_healthy()
