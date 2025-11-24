"""
Translation Continuity Tracker - Track và merge translation results cho dialogue dài
"""
import time
from .logger import log_debug, log_error
from .text_normalizer import normalize_for_comparison

class TranslationContinuityTracker:
    """
    Track translation continuity để merge results thay vì replace.
    Giữ nguyên dialogue dài trên màn hình khi có continuation.
    """
    
    def __init__(self, 
                 similarity_threshold=0.70,
                 max_context_lines=5,
                 context_timeout=15.0):
        """
        Args:
            similarity_threshold: Threshold để coi là continuation (0.70 = 70%)
            max_context_lines: Maximum số lines giữ trong context
            context_timeout: Timeout để clear context (seconds)
        """
        self.similarity_threshold = similarity_threshold
        self.max_context_lines = max_context_lines
        self.context_timeout = context_timeout
        
        # Current context
        self.current_context = []  # List of (timestamp, source_text, translated_text)
        self.last_update_time = None
        
        # Statistics
        self.total_translations = 0
        self.continuations_detected = 0
        self.merges_performed = 0
        self.context_clears = 0
    
    def should_merge(self, new_source_text):
        """
        Kiểm tra new translation có phải continuation của context hiện tại không.
        
        Args:
            new_source_text: Source text của translation mới
        
        Returns:
            (should_merge: bool, merge_type: str)
            - should_merge: True nếu nên merge
            - merge_type: "append", "replace", hoặc "none"
        """
        try:
            current_time = time.time()
            
            # Clear expired context
            self._cleanup_expired_context(current_time)
            
            # Nếu context rỗng → không merge
            if not self.current_context:
                return False, "none"
            
            # Normalize new text
            new_normalized = normalize_for_comparison(new_source_text)
            
            if not new_normalized:
                return False, "none"
            
            # Check similarity với từng line trong context
            for timestamp, source_text, _ in self.current_context:
                normalized_context = normalize_for_comparison(source_text)
                
                if not normalized_context:
                    continue
                
                similarity = self._calculate_similarity(new_normalized, normalized_context)
                
                # Exact match hoặc high similarity → replace (text giống nhau)
                if similarity >= 0.95:
                    return False, "replace"
                
                # Partial overlap → potential continuation
                if similarity >= self.similarity_threshold:
                    # Check nếu new text là extension của context text
                    if self._is_extension(new_normalized, normalized_context):
                        self.continuations_detected += 1
                        log_debug(
                            f"Continuation detected: "
                            f"'{source_text[:20]}...' → '{new_source_text[:20]}...' "
                            f"(similarity={similarity:.2f})"
                        )
                        return True, "append"
            
            # Không có continuation → separate dialogue
            return False, "none"
            
        except Exception as e:
            log_error("Error checking should_merge", e)
            return False, "none"
    
    def add_translation(self, source_text, translated_text):
        """
        Add translation vào context.
        
        Args:
            source_text: Source text
            translated_text: Translated text
        """
        try:
            current_time = time.time()
            
            self.total_translations += 1
            self.last_update_time = current_time
            
            # Add to context
            self.current_context.append((current_time, source_text, translated_text))
            
            # Limit context size
            if len(self.current_context) > self.max_context_lines:
                self.current_context.pop(0)  # Remove oldest
            
        except Exception as e:
            log_error("Error adding translation to context", e)
    
    def merge_translations(self, existing_translations, new_translation, merge_type="append"):
        """
        Merge new translation với existing translations.
        
        Args:
            existing_translations: List of existing translated lines
            new_translation: New translated text
            merge_type: "append" hoặc "replace"
        
        Returns:
            Merged translations (list of strings)
        """
        try:
            if merge_type == "replace":
                # Replace last line với new translation
                if existing_translations:
                    existing_translations[-1] = new_translation
                else:
                    existing_translations = [new_translation]
                    
            elif merge_type == "append":
                # Append new translation
                existing_translations.append(new_translation)
                self.merges_performed += 1
                
                # Limit total lines
                if len(existing_translations) > self.max_context_lines:
                    existing_translations = existing_translations[-self.max_context_lines:]
            
            else:  # "none"
                # Clear và start fresh
                existing_translations = [new_translation]
            
            return existing_translations
            
        except Exception as e:
            log_error("Error merging translations", e)
            return [new_translation]
    
    def _calculate_similarity(self, text1, text2):
        """
        Tính similarity giữa 2 texts.
        
        Returns:
            Similarity score (0.0 - 1.0)
        """
        try:
            if not text1 or not text2:
                return 0.0
            
            # Exact match
            if text1 == text2:
                return 1.0
            
            # Check if one is substring of another
            if text1 in text2 or text2 in text1:
                shorter = min(len(text1), len(text2))
                longer = max(len(text1), len(text2))
                return shorter / longer
            
            # Character-based similarity
            max_len = max(len(text1), len(text2))
            if max_len == 0:
                return 0.0
            
            # Count matching characters at same positions
            matches = sum(1 for a, b in zip(text1, text2) if a == b)
            
            # Count common characters (order-independent)
            set1 = set(text1)
            set2 = set(text2)
            common_chars = len(set1 & set2)
            total_chars = len(set1 | set2)
            
            # Combined similarity
            position_similarity = matches / max_len
            char_similarity = common_chars / total_chars if total_chars > 0 else 0
            
            return (position_similarity * 0.6 + char_similarity * 0.4)
            
        except Exception as e:
            log_error("Error calculating similarity", e)
            return 0.0
    
    def _is_extension(self, new_text, context_text):
        """
        Kiểm tra new_text có phải extension của context_text không.
        
        Extension = new text chứa context text + thêm phần mới
        
        Returns:
            True nếu new_text extends context_text
        """
        try:
            # Remove common words để focus vào content
            words_context = set(context_text.split())
            words_new = set(new_text.split())
            
            # Nếu context words là subset của new words → extension
            if words_context.issubset(words_new) and len(words_new) > len(words_context):
                return True
            
            # Check prefix/suffix
            # Nếu context text là prefix của new text
            if new_text.startswith(context_text[:min(20, len(context_text))]):
                return True
            
            return False
            
        except Exception as e:
            log_error("Error checking extension", e)
            return False
    
    def _cleanup_expired_context(self, current_time):
        """Xóa expired context entries."""
        try:
            # Remove entries older than timeout
            self.current_context = [
                (ts, src, trans) 
                for ts, src, trans in self.current_context
                if current_time - ts <= self.context_timeout
            ]
            
            # Track clears
            if self.last_update_time and current_time - self.last_update_time > self.context_timeout:
                if self.current_context:
                    self.context_clears += 1
                    log_debug("Context cleared due to timeout")
                    
        except Exception as e:
            log_error("Error cleaning up context", e)
    
    def clear_context(self):
        """Manually clear context."""
        try:
            if self.current_context:
                self.context_clears += 1
                log_debug("Context manually cleared")
            self.current_context.clear()
            self.last_update_time = None
        except Exception as e:
            log_error("Error clearing context", e)
    
    def get_context_summary(self):
        """
        Get summary of current context.
        
        Returns:
            List of translated texts trong context
        """
        try:
            return [trans for _, _, trans in self.current_context]
        except Exception as e:
            log_error("Error getting context summary", e)
            return []
    
    def get_stats(self):
        """
        Get statistics.
        
        Returns:
            Dictionary với stats
        """
        try:
            continuation_rate = 0.0
            if self.total_translations > 0:
                continuation_rate = self.continuations_detected / self.total_translations * 100
            
            merge_rate = 0.0
            if self.continuations_detected > 0:
                merge_rate = self.merges_performed / self.continuations_detected * 100
            
            return {
                "total_translations": self.total_translations,
                "continuations_detected": self.continuations_detected,
                "continuation_rate": f"{continuation_rate:.1f}%",
                "merges_performed": self.merges_performed,
                "merge_rate": f"{merge_rate:.1f}%",
                "context_clears": self.context_clears,
                "current_context_size": len(self.current_context),
                "max_context_lines": self.max_context_lines,
                "context_timeout": f"{self.context_timeout:.1f}s"
            }
        except Exception as e:
            log_error("Error getting continuity stats", e)
            return {
                "total_translations": 0,
                "continuations_detected": 0,
                "continuation_rate": "0%",
                "merges_performed": 0,
                "merge_rate": "0%",
                "context_clears": 0,
                "current_context_size": 0,
                "max_context_lines": self.max_context_lines,
                "context_timeout": f"{self.context_timeout:.1f}s"
            }
    
    def set_similarity_threshold(self, threshold):
        """Update similarity threshold."""
        if 0.0 <= threshold <= 1.0:
            self.similarity_threshold = threshold
            log_debug(f"Updated continuity similarity threshold to {threshold}")
    
    def set_context_timeout(self, timeout):
        """Update context timeout."""
        if timeout > 0:
            self.context_timeout = timeout
            log_debug(f"Updated context timeout to {timeout}s")


# Singleton instance
_continuity_tracker = None

def get_continuity_tracker():
    """Get singleton TranslationContinuityTracker instance."""
    global _continuity_tracker
    if _continuity_tracker is None:
        _continuity_tracker = TranslationContinuityTracker()
    return _continuity_tracker


# Convenience functions
def should_merge_translation(source_text):
    """Convenience function for checking should merge."""
    return get_continuity_tracker().should_merge(source_text)

def add_translation_to_context(source_text, translated_text):
    """Convenience function for adding translation."""
    get_continuity_tracker().add_translation(source_text, translated_text)

def merge_translation_results(existing, new, merge_type="append"):
    """Convenience function for merging."""
    return get_continuity_tracker().merge_translations(existing, new, merge_type)

def clear_translation_context():
    """Convenience function for clearing context."""
    get_continuity_tracker().clear_context()

def get_translation_context_summary():
    """Convenience function for getting summary."""
    return get_continuity_tracker().get_context_summary()

def get_continuity_stats():
    """Convenience function for getting stats."""
    return get_continuity_tracker().get_stats()
