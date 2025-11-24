"""
Text Validator Module - Validate text với dialogue-aware logic
Xử lý câu thoại game có special chars như: oh-oh, i'm-i'm, so... sorry
"""
import re
import unicodedata
from .logger import log_debug, log_error

class TextValidator:
    """
    Validate text trước khi dịch với dialogue-aware rules.
    Không skip các câu thoại có pattern hợp lệ dù có nhiều special chars.
    """
    
    def __init__(self):
        # Pattern cho dialogue hợp lệ (stuttering, ellipsis, hyphens)
        # oh-oh, i'm-i'm, so... sorry, what--what
        self.dialogue_stutter_pattern = re.compile(
            r'\b(\w+)[-\s]+\1\b',  # word-word hoặc word word (stuttering)
            re.IGNORECASE
        )
        
        # Pattern cho contractions (I'm, you're, don't, can't, etc.)
        self.contraction_pattern = re.compile(
            r"\b\w+['']\w+\b",  # I'm, you're, don't
            re.IGNORECASE
        )
        
        # Pattern cho ellipsis trong dialogue (..., .., ……)
        self.ellipsis_pattern = re.compile(r'\.{2,}|…+')
        
        # Pattern cho exclamations (!!!, ???, !?, ...)
        self.exclamation_pattern = re.compile(r'[!?]{1,}')
        
        # Pattern cho dialogue với dấu gạch (oh-oh, well-well, uh-huh)
        self.hyphenated_dialogue_pattern = re.compile(
            r'\b\w{2,}[-]\w{2,}\b',  # oh-oh, uh-huh
            re.IGNORECASE
        )
        
        # Common game dialogue interjections
        self.dialogue_interjections = {
            'oh', 'ah', 'uh', 'um', 'hmm', 'huh', 'hey', 'well',
            'so', 'but', 'and', 'or', 'no', 'yes', 'yeah', 'nah',
            'wow', 'whoa', 'oops', 'ouch', 'yikes', 'damn', 'shit'
        }
        
        # Minimum word count cho valid dialogue (1 word OK nếu là dialogue)
        self.min_word_count = 1
        
        # Minimum letter count (phải có ít nhất 2 chữ cái thực)
        self.min_letter_count = 2
    
    def is_valid_dialogue_text(self, text):
        """
        Kiểm tra text có phải dialogue hợp lệ không.
        Return True nếu nên dịch, False nếu nên skip.
        
        Args:
            text: Text cần validate
        
        Returns:
            bool: True = dịch, False = skip
        """
        try:
            if not text or not isinstance(text, str):
                return False
            
            text = text.strip()
            if not text:
                return False
            
            # 1. Đếm số chữ cái thực (loại bỏ punctuation, numbers, spaces)
            letter_count = sum(1 for c in text if c.isalpha())
            
            if letter_count < self.min_letter_count:
                # Quá ít chữ cái -> không phải text thực
                return False
            
            # 2. Check dialogue patterns đặc biệt (stuttering, contractions, ellipsis)
            has_stutter = self.dialogue_stutter_pattern.search(text) is not None
            has_contraction = self.contraction_pattern.search(text) is not None
            has_ellipsis = self.ellipsis_pattern.search(text) is not None
            has_hyphenated = self.hyphenated_dialogue_pattern.search(text) is not None
            
            # Nếu có dialogue patterns, chắc chắn là dialogue hợp lệ
            if has_stutter or has_contraction or has_hyphenated:
                log_debug(f"Valid dialogue pattern detected: '{text[:50]}...'")
                return True
            
            # 3. Check interjections (oh, ah, uh, etc.)
            words = re.findall(r'\b\w+\b', text.lower())
            if any(word in self.dialogue_interjections for word in words):
                # Có interjection -> likely dialogue
                return True
            
            # 4. Check word count với special handling
            word_count = len(words)
            
            if word_count == 0:
                return False
            
            # Với 1-2 words, cần có ít nhất 3 letters
            if word_count <= 2:
                if letter_count >= 3:
                    return True
                else:
                    # Too short, nhưng nếu có exclamation/ellipsis thì OK
                    if has_ellipsis or self.exclamation_pattern.search(text):
                        return True
                    return False
            
            # 5. Với text dài hơn (3+ words), check letter ratio
            text_length = len(text)
            letter_ratio = letter_count / text_length if text_length > 0 else 0
            
            # Nếu > 30% là chữ cái -> valid text
            if letter_ratio >= 0.3:
                return True
            
            # 6. Special case: text có nhiều punctuation nhưng vẫn có words
            # Example: "What... what?!", "No--no, wait!"
            if word_count >= 2 and letter_count >= 5:
                # Có ít nhất 2 words và 5 letters -> valid dialogue
                return True
            
            # 7. Check xem có phải pure noise không (chỉ toàn special chars)
            # Loại bỏ tất cả non-alphanumeric
            cleaned = re.sub(r'[^a-zA-Z0-9]', '', text)
            if len(cleaned) == 0:
                # Pure noise
                return False
            
            # Default: nếu có ít nhất 2 letters và 1 word -> OK
            if letter_count >= 2 and word_count >= 1:
                return True
            
            return False
            
        except Exception as e:
            log_error(f"Error validating dialogue text: {text[:50]}...", e)
            # Khi có lỗi, default = True (dịch) để không bỏ sót
            return True
    
    def extract_actual_words(self, text):
        """
        Trích xuất words thực từ text (loại bỏ pure punctuation).
        
        Args:
            text: Text cần extract
        
        Returns:
            list: Danh sách words hợp lệ
        """
        try:
            if not text or not isinstance(text, str):
                return []
            
            # Tìm tất cả word patterns (including hyphenated và apostrophes)
            words = re.findall(r"\b[\w''-]+\b", text.lower())
            
            # Filter: chỉ giữ words có ít nhất 1 letter
            actual_words = [w for w in words if any(c.isalpha() for c in w)]
            
            return actual_words
            
        except Exception as e:
            log_error(f"Error extracting words: {text[:50]}...", e)
            return []
    
    def is_too_noisy_for_translation(self, text, noise_threshold=0.7):
        """
        Kiểm tra text có quá nhiều noise không (special chars > threshold).
        
        Args:
            text: Text cần check
            noise_threshold: Tỷ lệ noise tối đa (0.0-1.0)
        
        Returns:
            bool: True nếu quá noisy (nên skip), False nếu OK (dịch được)
        """
        try:
            if not text or not isinstance(text, str):
                return True  # Empty/invalid = noisy
            
            text = text.strip()
            if not text:
                return True
            
            # Đếm alphanumeric vs special chars
            alphanumeric_count = sum(1 for c in text if c.isalnum() or c.isspace())
            special_count = len(text) - alphanumeric_count
            
            if len(text) == 0:
                return True
            
            noise_ratio = special_count / len(text)
            
            # Nếu noise > threshold -> too noisy
            if noise_ratio > noise_threshold:
                # Exception: nếu có dialogue patterns, vẫn OK
                if self.is_valid_dialogue_text(text):
                    return False  # Not noisy despite special chars
                return True
            
            return False
            
        except Exception as e:
            log_error(f"Error checking noise level: {text[:50]}...", e)
            return False  # Default = not noisy khi có lỗi
    
    def should_translate_text(self, text):
        """
        Main validation function: kiểm tra text có nên dịch không.
        Combine tất cả checks: dialogue patterns, noise level, validity.
        
        Args:
            text: Text cần validate
        
        Returns:
            bool: True = nên dịch, False = skip
        """
        try:
            # Quick checks
            if not text or not isinstance(text, str):
                return False
            
            text = text.strip()
            if not text:
                return False
            
            # 1. Check noise level
            if self.is_too_noisy_for_translation(text):
                log_debug(f"Skipping noisy text: '{text[:50]}...'")
                return False
            
            # 2. Check dialogue validity
            if not self.is_valid_dialogue_text(text):
                log_debug(f"Skipping invalid dialogue: '{text[:50]}...'")
                return False
            
            # Passed all checks
            return True
            
        except Exception as e:
            log_error(f"Error in should_translate_text: {text[:50]}...", e)
            # Default = True để không bỏ sót text
            return True


# Singleton instance
_text_validator = None

def get_text_validator():
    """Get singleton TextValidator instance."""
    global _text_validator
    if _text_validator is None:
        _text_validator = TextValidator()
    return _text_validator


# Convenience functions
def is_valid_dialogue_text(text):
    """Check if text is valid dialogue."""
    return get_text_validator().is_valid_dialogue_text(text)

def should_translate_text(text):
    """Check if text should be translated."""
    return get_text_validator().should_translate_text(text)

def extract_actual_words(text):
    """Extract actual words from text."""
    return get_text_validator().extract_actual_words(text)

def is_too_noisy_for_translation(text, noise_threshold=0.7):
    """Check if text is too noisy."""
    return get_text_validator().is_too_noisy_for_translation(text, noise_threshold)
