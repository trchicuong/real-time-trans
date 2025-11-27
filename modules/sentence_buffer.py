"""
Sentence Buffer Module - Buffer text cho đến khi phát hiện câu hoàn chỉnh
"""
import time
import re
from .logger import log_debug, log_error

class SentenceBuffer:
    """
    Buffer text segments và chỉ release khi detect được sentence boundary.
    Tránh dịch nửa chừng khi câu dài xuất hiện từ từ.
    """
    
    def __init__(self, timeout=1.5, min_sentence_length=5):
        """
        Args:
            timeout: Thời gian tối đa chờ sentence (seconds)
            min_sentence_length: Độ dài tối thiểu để coi là sentence
        """
        self.timeout = timeout
        self.min_sentence_length = min_sentence_length
        
        # Buffer state
        self.buffer = ""
        self.buffer_start_time = None
        
        # Sentence boundary patterns
        # Dấu kết thúc câu: . ! ? … (ellipsis) + optional quotes/brackets
        self.sentence_end_pattern = re.compile(r'[.!?…]+[\"\'\)\]]*\s*$')
        
        self.sentences_released = 0
        self.timeout_releases = 0
        self.immediate_releases = 0
    
    def add_text(self, text, current_time=None):
        """
        Thêm text vào buffer.
        
        Args:
            text: New text segment
            current_time: Current timestamp (nếu None, dùng time.time())
        
        Returns:
            (should_release: bool, complete_text: str or None)
            - should_release: True nếu nên release text để dịch
            - complete_text: Text hoàn chỉnh để dịch (hoặc None nếu chưa release)
        """
        try:
            if not text or not isinstance(text, str):
                return False, None
            
            if current_time is None:
                current_time = time.time()
            
            # Nếu buffer rỗng, khởi tạo
            if not self.buffer:
                self.buffer = text
                self.buffer_start_time = current_time
                
                # Check immediate release (nếu text đã là câu hoàn chỉnh)
                if self._is_complete_sentence(text):
                    result = self.buffer
                    self.buffer = ""
                    self.buffer_start_time = None
                    self.sentences_released += 1
                    self.immediate_releases += 1
                    log_debug(f"Immediate release: '{result[:30]}...'")
                    return True, result
                
                # Chưa hoàn chỉnh, chờ thêm text
                return False, None
            
            # Buffer có text → append new text
            # Thêm space nếu cần (tránh dính chữ)
            if self.buffer and not self.buffer.endswith(' '):
                self.buffer += ' '
            self.buffer += text
            
            # Check sentence completion
            if self._is_complete_sentence(self.buffer):
                result = self.buffer
                self.buffer = ""
                self.buffer_start_time = None
                self.sentences_released += 1
                log_debug(f"Sentence complete: '{result[:30]}...'")
                return True, result
            
            # Check timeout
            if current_time - self.buffer_start_time >= self.timeout:
                result = self.buffer
                self.buffer = ""
                self.buffer_start_time = None
                self.timeout_releases += 1
                log_debug(f"Timeout release: '{result[:30]}...'")
                return True, result
            
            # Chưa hoàn chỉnh và chưa timeout → tiếp tục buffer
            return False, None
            
        except Exception as e:
            log_error(f"Error in sentence buffer: {text[:50]}...", e)
            # Nếu có lỗi, release buffer hiện tại (conservative)
            if self.buffer:
                result = self.buffer
                self.buffer = ""
                self.buffer_start_time = None
                return True, result
            return False, None
    
    def _is_complete_sentence(self, text):
        """
        Kiểm tra text có phải câu hoàn chỉnh không.
        
        Criteria:
        - Length >= min_sentence_length
        - Kết thúc bằng dấu câu (. ! ? …)
        """
        try:
            if not text or len(text.strip()) < self.min_sentence_length:
                return False
            
            # Check sentence ending pattern
            if self.sentence_end_pattern.search(text.strip()):
                return True
            
            return False
            
        except Exception as e:
            log_error("Error checking sentence completion", e)
            return False
    
    def force_release(self):
        """
        Force release buffer ngay lập tức (dùng khi dừng capture hoặc clear).
        
        Returns:
            Buffered text (or None if empty)
        """
        try:
            if self.buffer:
                result = self.buffer
                self.buffer = ""
                self.buffer_start_time = None
                log_debug(f"Force release: '{result[:30]}...'")
                return result
            return None
        except Exception as e:
            log_error("Error force releasing buffer", e)
            return None
    
    def clear(self):
        """Clear buffer."""
        try:
            self.buffer = ""
            self.buffer_start_time = None
            log_debug("Cleared sentence buffer")
        except Exception as e:
            log_error("Error clearing buffer", e)
    
    def get_stats(self):
        """
        Get statistics.
        
        Returns:
            Dictionary với stats
        """
        try:
            total = self.sentences_released + self.timeout_releases + self.immediate_releases
            return {
                "sentences_released": self.sentences_released,
                "timeout_releases": self.timeout_releases,
                "immediate_releases": self.immediate_releases,
                "total_releases": total,
                "timeout_rate": f"{(self.timeout_releases / total * 100) if total > 0 else 0:.1f}%",
                "current_buffer_size": len(self.buffer),
                "is_buffering": bool(self.buffer)
            }
        except Exception as e:
            log_error("Error getting buffer stats", e)
            return {
                "sentences_released": 0,
                "timeout_releases": 0,
                "immediate_releases": 0,
                "total_releases": 0,
                "timeout_rate": "0%",
                "current_buffer_size": 0,
                "is_buffering": False
            }
    
    def set_timeout(self, timeout):
        """Update buffer timeout."""
        if timeout > 0:
            self.timeout = timeout
            log_debug(f"Updated buffer timeout to {timeout}s")
    
    def set_min_sentence_length(self, length):
        """Update min sentence length."""
        if length > 0:
            self.min_sentence_length = length
            log_debug(f"Updated min sentence length to {length}")
    
    def is_empty(self):
        """Check if buffer is empty."""
        return not bool(self.buffer)
    
    def get_buffer_content(self):
        """Get current buffer content (for debugging)."""
        return self.buffer
    
    def get_buffer_age(self, current_time=None):
        """
        Get buffer age in seconds.
        
        Returns:
            Age in seconds (or 0 if buffer empty)
        """
        try:
            if not self.buffer or not self.buffer_start_time:
                return 0.0
            
            if current_time is None:
                current_time = time.time()
            
            return current_time - self.buffer_start_time
            
        except Exception as e:
            log_error("Error getting buffer age", e)
            return 0.0


# Singleton instance
_sentence_buffer = None

def get_sentence_buffer():
    """Get singleton SentenceBuffer instance."""
    global _sentence_buffer
    if _sentence_buffer is None:
        _sentence_buffer = SentenceBuffer()
    return _sentence_buffer


# Convenience functions
def add_text_to_buffer(text, current_time=None):
    """Convenience function for adding text to buffer."""
    return get_sentence_buffer().add_text(text, current_time)

def force_release_buffer():
    """Convenience function for force releasing buffer."""
    return get_sentence_buffer().force_release()

def clear_sentence_buffer():
    """Convenience function for clearing buffer."""
    get_sentence_buffer().clear()

def get_sentence_buffer_stats():
    """Convenience function for getting stats."""
    return get_sentence_buffer().get_stats()
