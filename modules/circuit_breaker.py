"""
Circuit breaker for network API calls
"""
import time
from .logger import log_debug, log_error

class NetworkCircuitBreaker:
    """Circuit breaker nhẹ - chỉ mở khi network thực sự có vấn đề."""
    
    def __init__(self):
        self.failure_count = 0
        self.slow_call_count = 0
        self.last_reset = time.time()
        self.is_open = False
        self.total_calls = 0
        self.success_count = 0  # Đếm success để auto-close circuit
        
        # RELAXED THRESHOLDS - API rất ổn định
        self.failure_threshold = 15      # 15 failures liên tiếp mới mở (tăng từ 5)
        self.slow_call_threshold = 30    # 30 slow calls mới mở (tăng từ 10)
        self.slow_duration = 8.0         # 8s mới coi là slow (tăng từ 3s)
        self.reset_interval = 120        # Reset mỗi 2 phút (giảm từ 5 phút)
        self.recovery_success_count = 3  # 3 success liên tiếp → auto close circuit
    
    def record_call(self, duration, success):
        """Ghi nhận kết quả API call - relaxed logic."""
        try:
            self.total_calls += 1
            current_time = time.time()
            
            # Reset counters định kỳ
            if current_time - self.last_reset > self.reset_interval:
                self.failure_count = 0
                self.slow_call_count = 0
                self.total_calls = 0
                self.success_count = 0
                self.is_open = False
                self.last_reset = current_time
            
            if success:
                self.success_count += 1
                # Reset failure count khi có success (không tích lũy failures rời rạc)
                self.failure_count = max(0, self.failure_count - 1)
                
                # Auto-close circuit nếu đã recover
                if self.is_open and self.success_count >= self.recovery_success_count:
                    self.is_open = False
                    self.failure_count = 0
                    self.slow_call_count = 0
                    log_debug("Circuit breaker AUTO-CLOSED sau recovery")
            else:
                self.failure_count += 1
                self.success_count = 0  # Reset success streak
            
            # Chỉ đếm slow call khi THỰC SỰ chậm (8s+)
            if success and duration > self.slow_duration:
                self.slow_call_count += 1
            
            # Mở circuit chỉ khi THỰC SỰ có vấn đề nghiêm trọng
            if self.failure_count >= self.failure_threshold:
                if not self.is_open:
                    self.is_open = True
                    log_debug(f"Circuit breaker OPEN: {self.failure_count} failures liên tiếp")
                return True
            elif self.slow_call_count >= self.slow_call_threshold:
                if not self.is_open:
                    self.is_open = True
                    log_debug(f"Circuit breaker OPEN: {self.slow_call_count} slow calls (>{self.slow_duration}s)")
                return True
            
            return False
        except Exception as e:
            log_error("Error in circuit breaker record_call", e)
            return False
    
    def should_force_refresh(self):
        """Kiểm tra có cần refresh client không."""
        return self.is_open
    
    def reset(self):
        """Reset thủ công circuit breaker."""
        try:
            self.failure_count = 0
            self.slow_call_count = 0
            self.success_count = 0
            self.is_open = False
            self.last_reset = time.time()
        except Exception as e:
            log_error("Error resetting circuit breaker", e)

