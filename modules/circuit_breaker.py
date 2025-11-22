"""
Circuit breaker for network API calls
Detects network degradation and handles failures gracefully
"""
import time
from .logger import log_debug, log_error

class NetworkCircuitBreaker:
    """Circuit breaker to detect and handle network degradation."""
    
    def __init__(self):
        self.failure_count = 0
        self.slow_call_count = 0
        self.last_reset = time.time()
        self.is_open = False
        self.total_calls = 0
    
    def record_call(self, duration, success):
        """Record API call result and determine if circuit should open."""
        try:
            self.total_calls += 1
            
            # Reset counters every 5 minutes
            current_time = time.time()
            if current_time - self.last_reset > 300:  # 5 minutes
                log_debug(f"Circuit breaker stats reset. Previous period: {self.failure_count} failures, {self.slow_call_count} slow calls, {self.total_calls} total")
                self.failure_count = 0
                self.slow_call_count = 0
                self.total_calls = 0
                self.is_open = False
                self.last_reset = current_time
            
            if not success:
                self.failure_count += 1
                log_debug(f"Circuit breaker: API failure recorded ({self.failure_count}/5)")
            elif duration > 3.0:  # Slow call threshold
                self.slow_call_count += 1
                log_debug(f"Circuit breaker: Slow call recorded ({duration:.2f}s, {self.slow_call_count}/10)")
            
            # Open circuit if too many failures or slow calls
            if self.failure_count >= 5:
                self.is_open = True
                log_debug("Circuit breaker OPEN due to failure threshold - forcing client refresh")
                return True
            elif self.slow_call_count >= 10:
                self.is_open = True
                log_debug("Circuit breaker OPEN due to slow call threshold - forcing client refresh")
                return True
            
            return False
        except Exception as e:
            log_error("Error in circuit breaker record_call", e)
            return False
    
    def should_force_refresh(self):
        """Check if circuit is open and client should be refreshed."""
        return self.is_open
    
    def reset(self):
        """Manually reset the circuit breaker."""
        try:
            self.failure_count = 0
            self.slow_call_count = 0
            self.is_open = False
            self.last_reset = time.time()
            log_debug("Circuit breaker manually reset")
        except Exception as e:
            log_error("Error resetting circuit breaker", e)

