"""
Text Normalization Module - Chuẩn hóa text để tăng cache hit rate
"""
import re
import unicodedata
from .logger import log_debug, log_error

class TextNormalizer:
    """
    Chuẩn hóa text trước khi cache/dịch để tăng khả năng tìm thấy trong cache.
    Xử lý các trường hợp: số thứ tự, dấu câu dư thừa, ký tự đặc biệt game, whitespace.
    """
    
    def __init__(self):
        # Pattern cho số thứ tự ở đầu câu (1., 2), [1], (1), etc.)
        self.leading_numbers_pattern = re.compile(r'^[\[\(]?\d+[\]\)\.:]?\s*')
        
        # Pattern cho ký tú đặc biệt game thường gặp
        self.game_special_chars = re.compile(r'[►▼▲◄●○■□※★☆♪♫]')
        
        # Pattern cho whitespace dư thừa
        self.extra_whitespace = re.compile(r'\s+')
        
        # Pattern cho dấu câu lặp lại (!!!, ???, ...)
        self.repeated_punctuation = re.compile(r'([!?.]){2,}')
    
    def normalize_for_cache(self, text, preserve_case=False):
        """
        Chuẩn hóa text để tạo cache key.
        
        Args:
            text: Text cần chuẩn hóa
            preserve_case: Giữ nguyên uppercase/lowercase (mặc định: False)
        
        Returns:
            Text đã chuẩn hóa
        """
        try:
            if not text or not isinstance(text, str):
                return ""
            
            normalized = ''.join(
                char for char in text 
                if unicodedata.category(char)[0] != 'C' or char in '\n\r\t'
            )
            
            normalized = self.leading_numbers_pattern.sub('', normalized)
            
            normalized = self.game_special_chars.sub('', normalized)
            
            normalized = self.repeated_punctuation.sub(r'\1', normalized)
            
            normalized = self.extra_whitespace.sub(' ', normalized)
            
            normalized = normalized.strip()
            
            # 7. Lowercase nếu không preserve_case (giúp "Hello" = "hello")
            if not preserve_case:
                normalized = normalized.lower()
            
            # 8. Loại bỏ dấu câu ở đầu/cuối nếu chỉ là dấu đơn lẻ
            # Giữ lại nếu là dấu quan trọng (?, !)
            normalized = normalized.strip('.,;:\'"')
            
            return normalized
            
        except Exception as e:
            log_error(f"Error normalizing text for cache: {text[:50]}...", e)
            # Fallback: trả về text gốc nếu có lỗi
            return text.strip() if text else ""
    
    def normalize_for_display(self, text):
        """
        Chuẩn hóa text để hiển thị (ít aggressive hơn).
        Chỉ loại bỏ whitespace dư thừa và ký tự đặc biệt game.
        
        Args:
            text: Text cần chuẩn hóa
        
        Returns:
            Text đã chuẩn hóa
        """
        try:
            if not text or not isinstance(text, str):
                return ""
            
            normalized = self.game_special_chars.sub('', text)
            
            normalized = self.extra_whitespace.sub(' ', normalized)
            
            normalized = normalized.strip()
            
            return normalized
            
        except Exception as e:
            log_error(f"Error normalizing text for display: {text[:50]}...", e)
            return text.strip() if text else ""
    
    def normalize_for_comparison(self, text):
        """
        Chuẩn hóa text để so sánh similarity (moderately aggressive).
        Giữ lại hyphens và apostrophes để preserve dialogue structure.
        Example: "oh-oh no, i'm-i'm so... sorry" → "oh-oh no im-im so sorry"
        
        Args:
            text: Text cần chuẩn hóa
        
        Returns:
            Text đã chuẩn hóa (chữ cái, spaces, hyphens, apostrophes)
        """
        try:
            if not text or not isinstance(text, str):
                return ""
            
            normalized = text.lower()
            
            # 2. Normalize ellipsis và multiple punctuation
            normalized = re.sub(r'\.{2,}', ' ', normalized)  # ... → space
            normalized = re.sub(r'[!?]{2,}', ' ', normalized)  # !!!, ??? → space
            
            # 3. Giữ lại hyphens, apostrophes, letters, spaces
            # Remove tất cả punctuation EXCEPT hyphens và apostrophes
            # Loại bỏ: .,;:!?"()[]{}…
            normalized = re.sub(r'[^\w\s\'-]', ' ', normalized)
            
            # 4. Clean up apostrophes (chỉ giữ trong contractions)
            # i ' m → i'm, but ' hello → hello
            normalized = re.sub(r"\s+'", " ", normalized)  # Remove leading apostrophes
            normalized = re.sub(r"'\s+", " ", normalized)  # Remove trailing apostrophes
            
            normalized = self.extra_whitespace.sub(' ', normalized)
            
            normalized = normalized.strip()
            
            return normalized
            
        except Exception as e:
            log_error(f"Error normalizing text for comparison: {text[:50]}...", e)
            return text.strip().lower() if text else ""
    
    def is_similar_enough_for_cache(self, text1, text2, threshold=0.85):
        """
        Kiểm tra 2 text có đủ giống nhau để dùng chung cache không.
        Dựa trên normalized text (loại bỏ punctuation, numbers).
        
        Args:
            text1: Text thứ nhất
            text2: Text thứ hai
            threshold: Ngưỡng similarity (0.0-1.0)
        
        Returns:
            True nếu đủ giống nhau
        """
        try:
            if not text1 or not text2:
                return False
            
            # Chuẩn hóa cả 2 text
            norm1 = self.normalize_for_comparison(text1)
            norm2 = self.normalize_for_comparison(text2)
            
            if not norm1 or not norm2:
                return False
            
            # Nếu giống hệt sau khi normalize → similar
            if norm1 == norm2:
                return True
            
            # Tính simple character-based similarity
            # (Levenshtein distance sẽ được implement trong module riêng)
            max_len = max(len(norm1), len(norm2))
            if max_len == 0:
                return False
            
            # Đếm số ký tự giống nhau ở cùng vị trí
            matches = sum(1 for a, b in zip(norm1, norm2) if a == b)
            similarity = matches / max_len
            
            return similarity >= threshold
            
        except Exception as e:
            log_error("Error comparing text similarity", e)
            return False
    
    def extract_core_text(self, text):
        """
        Trích xuất phần text cốt lõi (loại bỏ decorations, numbers, special chars).
        Dùng để so sánh xem có phải cùng một dialogue không.
        
        Args:
            text: Text gốc
        
        Returns:
            Core text (chỉ còn chữ cái và spaces quan trọng)
        """
        try:
            return self.normalize_for_comparison(text)
        except Exception as e:
            log_error(f"Error extracting core text: {text[:50]}...", e)
            return text.strip() if text else ""


# Singleton instance
_text_normalizer = None

def get_text_normalizer():
    """Get singleton TextNormalizer instance."""
    global _text_normalizer
    if _text_normalizer is None:
        _text_normalizer = TextNormalizer()
    return _text_normalizer


# Convenience functions
def normalize_for_cache(text, preserve_case=False):
    """Convenience function for normalizing text for cache."""
    return get_text_normalizer().normalize_for_cache(text, preserve_case)

def normalize_for_display(text):
    """Convenience function for normalizing text for display."""
    return get_text_normalizer().normalize_for_display(text)

def normalize_for_comparison(text):
    """Convenience function for normalizing text for comparison."""
    return get_text_normalizer().normalize_for_comparison(text)

def is_similar_enough_for_cache(text1, text2, threshold=0.85):
    """Convenience function for checking text similarity."""
    return get_text_normalizer().is_similar_enough_for_cache(text1, text2, threshold)

def extract_core_text(text):
    """Convenience function for extracting core text."""
    return get_text_normalizer().extract_core_text(text)
