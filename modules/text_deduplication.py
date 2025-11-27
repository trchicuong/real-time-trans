"""
Text Deduplication Module - Lọc text trùng lặp để tránh dịch lại
Optimized với SequenceMatcher cho accuracy tốt hơn
"""
import time
from collections import deque
from difflib import SequenceMatcher
from .logger import log_debug, log_error
from .text_normalizer import normalize_for_comparison

class TextDeduplicator:
    """
    Track recent texts và filter duplicates trong time window.
    Giúp tránh dịch lại text giống nhau (dialogue giữ nguyên trên màn hình game).
    """
    
    def __init__(self, window_size=10.0, similarity_threshold=0.90):
        """
        Args:
            window_size: Time window in seconds (mặc định: 10s)
            similarity_threshold: Threshold để coi là duplicate (mặc định: 0.90 = 90%)
        """
        self.window_size = window_size
        self.similarity_threshold = similarity_threshold
        
        # Recent texts: (timestamp, normalized_text, original_text)
        self.recent_texts = deque(maxlen=50)  # Giới hạn 50 entries
        
        self.total_checks = 0
        self.duplicates_filtered = 0
    
    def _get_dynamic_threshold(self, text):
        """
        Dynamic threshold dựa trên text length
        Short text cần strict hơn, long text có thể relaxed
        """
        text_len = len(text)
        if text_len < 10:
            return 0.95  # Very strict cho text ngắn
        elif text_len < 30:
            return 0.90  # Standard
        else:
            return 0.85  # Relaxed cho text dài
    
    def is_duplicate(self, text, current_time=None):
        """
        Kiểm tra text có phải duplicate của text gần đây không.
        
        Args:
            text: Text cần kiểm tra
            current_time: Current timestamp (nếu None, dùng time.time())
        
        Returns:
            (is_duplicate: bool, matched_text: str or None)
        """
        try:
            if not text or len(str(text).strip()) < 2:
                return False, None
            
            if current_time is None:
                current_time = time.time()
            
            self.total_checks += 1
            
            # Chuẩn hóa text để so sánh
            normalized = normalize_for_comparison(text)
            
            if not normalized:
                return False, None
            
            # Xóa expired entries (ngoài time window)
            self._cleanup_expired_entries(current_time)
            
            # Kiểm tra với các texts gần đây
            # Sử dụng dynamic threshold
            dynamic_threshold = self._get_dynamic_threshold(normalized)
            
            for timestamp, recent_normalized, recent_original in self.recent_texts:
                if not recent_normalized:
                    continue
                
                # Tính similarity (optimized với SequenceMatcher)
                similarity = self._calculate_similarity_v2(normalized, recent_normalized)
                
                if similarity >= dynamic_threshold:
                    self.duplicates_filtered += 1
                    return True, recent_original
            
            # Không phải duplicate → add vào recent texts
            self.recent_texts.append((current_time, normalized, text))
            return False, None
            
        except Exception as e:
            log_error(f"Error checking duplicate: {text[:50]}...", e)
            # Nếu có lỗi, cho phép text đi qua (conservative approach)
            return False, None
    
    def _cleanup_expired_entries(self, current_time):
        """Xóa các entries ngoài time window."""
        try:
            # Remove từ đầu deque (oldest entries)
            while self.recent_texts:
                timestamp, _, _ = self.recent_texts[0]
                if current_time - timestamp > self.window_size:
                    self.recent_texts.popleft()
                else:
                    break
        except Exception as e:
            log_error("Error cleaning up expired entries", e)
    
    def _calculate_similarity_v2(self, text1, text2):
        """
        Optimized similarity với SequenceMatcher + word-level matching
        Accuracy cao hơn character matching
        
        Returns:
            Similarity score (0.0 - 1.0)
        """
        try:
            if not text1 or not text2:
                return 0.0
            
            # Exact match - fast path
            if text1 == text2:
                return 1.0
            
            # SequenceMatcher - tốt hơn character matching
            # Xử lý insertions, deletions, substitutions
            char_similarity = SequenceMatcher(None, text1, text2).ratio()
            
            # Word-level similarity (Jaccard index)
            words1 = set(text1.split())
            words2 = set(text2.split())
            
            if len(words1) == 0 and len(words2) == 0:
                word_similarity = 1.0
            elif len(words1) == 0 or len(words2) == 0:
                word_similarity = 0.0
            else:
                intersection = len(words1 & words2)
                union = len(words1 | words2)
                word_similarity = intersection / union if union > 0 else 0.0
            
            # Combined score: 60% char-level + 40% word-level
            # Char-level bắt typos, word-level bắt semantic similarity
            combined = 0.6 * char_similarity + 0.4 * word_similarity
            
            return combined
            
        except Exception as e:
            log_error("Error calculating similarity v2", e)
            return 0.0
    
    def _calculate_similarity(self, text1, text2):
        """
        Legacy similarity method - kept for backward compatibility
        """
        try:
            if not text1 or not text2:
                return 0.0
            
            if text1 == text2:
                return 1.0
            
            max_len = max(len(text1), len(text2))
            min_len = min(len(text1), len(text2))
            
            if max_len == 0:
                return 0.0
            
            matches = sum(1 for a, b in zip(text1, text2) if a == b)
            length_penalty = min_len / max_len
            position_similarity = matches / max_len
            similarity = (position_similarity * 0.7 + length_penalty * 0.3)
            
            return similarity
            
        except Exception as e:
            log_error("Error calculating similarity", e)
            return 0.0
    
    def clear(self):
        """Clear tất cả recent texts."""
        try:
            self.recent_texts.clear()
            log_debug("Cleared text deduplication cache")
        except Exception as e:
            log_error("Error clearing deduplication cache", e)
    
    def get_stats(self):
        """
        Get statistics.
        
        Returns:
            Dictionary với stats
        """
        try:
            return {
                "total_checks": self.total_checks,
                "duplicates_filtered": self.duplicates_filtered,
                "current_cache_size": len(self.recent_texts),
                "filter_rate": f"{(self.duplicates_filtered / self.total_checks * 100) if self.total_checks > 0 else 0:.1f}%"
            }
        except Exception as e:
            log_error("Error getting deduplication stats", e)
            return {
                "total_checks": 0,
                "duplicates_filtered": 0,
                "current_cache_size": 0,
                "filter_rate": "0%"
            }
    
    def set_window_size(self, window_size):
        """Update time window size."""
        if window_size > 0:
            self.window_size = window_size
            log_debug(f"Updated deduplication window size to {window_size}s")
    
    def set_similarity_threshold(self, threshold):
        """Update similarity threshold."""
        if 0.0 <= threshold <= 1.0:
            self.similarity_threshold = threshold
            log_debug(f"Updated similarity threshold to {threshold}")


# Singleton instance
_text_deduplicator = None

def get_text_deduplicator():
    """Get singleton TextDeduplicator instance."""
    global _text_deduplicator
    if _text_deduplicator is None:
        _text_deduplicator = TextDeduplicator()
    return _text_deduplicator


# Convenience functions
def is_duplicate_text(text, current_time=None):
    """Convenience function for checking duplicate."""
    return get_text_deduplicator().is_duplicate(text, current_time)

def clear_deduplication_cache():
    """Convenience function for clearing cache."""
    get_text_deduplicator().clear()

def get_deduplication_stats():
    """Convenience function for getting stats."""
    return get_text_deduplicator().get_stats()
