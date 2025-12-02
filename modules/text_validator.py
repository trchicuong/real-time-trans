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
        
        # Pattern cho exclamations (!!!, ???, !?, ...) và emotion tilde (~)
        self.exclamation_pattern = re.compile(r'[!?~]{1,}')
        
        # Pattern cho dialogue với dấu gạch (oh-oh, well-well, uh-huh)
        self.hyphenated_dialogue_pattern = re.compile(
            r'\b\w{2,}[-]\w{2,}\b',  # oh-oh, uh-huh
            re.IGNORECASE
        )
        
        # Pattern cho emotion markers trong game dialogue
        # [action], (sound), **emotion**, *emphasis*
        self.emotion_marker_pattern = re.compile(
            r'\[[^\]]+\]|\([^\)]+\)|\*+[^\*]+\*+',  # [text], (text), **text**, *text*
            re.IGNORECASE
        )
        
        # Common game dialogue interjections
        self.dialogue_interjections = {
            'oh', 'ah', 'uh', 'um', 'hmm', 'huh', 'hey', 'well',
            'so', 'but', 'and', 'or', 'no', 'yes', 'yeah', 'nah',
            'wow', 'whoa', 'oops', 'ouch', 'yikes', 'damn', 'shit',
            'hi', 'go', 'ok', 'me', 'we', 'he', 'it', 'is', 'as',
            'at', 'on', 'in', 'to', 'do', 'be', 'my', 'up', 'an',
        }
        
        # OCR garbage patterns - CHÍNH XÁC CÁC TỪ VÔ NGHĨA
        # Thay vì dùng regex chung (dễ false positive), liệt kê cụ thể
        self.ocr_garbage_words = {
            'ned', 'ined', 'jined', 'ained', 'sist', 'inod',
            'ded', 'aed', 'ued', 'oed', 'ied', 'eed',
            'nod', 'jod', 'lod', 'iod',
            'ned.', 'ined.', 'jined.', 'ained.',
            'ded.', 'nod.', 'sist.',
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
            
            # Lọc UI elements: số, codes, menu items
            # Pattern: "223/1", "*223", "[9]", "3 B]", "Quick bar", etc.
            
            # Skip nếu text chủ yếu là số với ít chữ cái
            digit_count = sum(1 for c in text if c.isdigit())
            letter_count = sum(1 for c in text if c.isalpha())
            
            # Nếu > 50% là số và < 5 chữ cái -> UI element
            if digit_count > len(text) * 0.5 and letter_count < 5:
                return False
            
            # Skip nếu match UI patterns
            ui_patterns = [
                r'^[\d\/\*\[\]\s]+$',  # Chỉ số, slash, asterisk, brackets
                r'^[\*\d\s]+[A-Z]?[\]\)]',  # *223 223 B], *223 223 L9], etc.
                r'^\[\d+\]',  # [9], [10], etc.
                r'^\d+\/\d+',  # 223/1, 5/10, etc.
                r'^[\d\s]+[A-Z]{1,2}\]\s*[A-Z]?$',  # 3 B] R, 223 BB] R, etc.
                r'^\*+[\d\s]+',  # *223, **123, etc.
            ]
            
            for pattern in ui_patterns:
                if re.match(pattern, text.strip()):
                    return False
            
            # 1. Đếm số chữ cái thực (loại bỏ punctuation, numbers, spaces)
            letter_count = sum(1 for c in text if c.isalpha())
            
            if letter_count < self.min_letter_count:
                # Quá ít chữ cái -> không phải text thực
                return False
            
            # 1.5. Filter OCR garbage - text ngắn vô nghĩa
            # Dùng danh sách cụ thể thay vì regex để tránh false positive
            text_stripped = text.strip().lower()
            if text_stripped in self.ocr_garbage_words:
                return False  # OCR garbage, skip
            
            # 2. Check dialogue patterns đặc biệt (stuttering, contractions, ellipsis)
            has_stutter = self.dialogue_stutter_pattern.search(text) is not None
            has_contraction = self.contraction_pattern.search(text) is not None
            has_ellipsis = self.ellipsis_pattern.search(text) is not None
            has_hyphenated = self.hyphenated_dialogue_pattern.search(text) is not None
            has_emotion_markers = self.emotion_marker_pattern.search(text) is not None
            
            # Nếu có dialogue patterns (bao gồm emotion markers), chắc chắn là dialogue hợp lệ
            if has_stutter or has_contraction or has_hyphenated or has_emotion_markers:
                # Không log để tránh spam
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
            # NHƯNG loại trừ emotion markers ([...], (...), **...**) khỏi special chars count
            text_without_markers = self.emotion_marker_pattern.sub('', text)  # Remove emotion markers
            
            alphanumeric_count = sum(1 for c in text_without_markers if c.isalnum() or c.isspace())
            special_count = len(text_without_markers) - alphanumeric_count
            
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
            
            if self.is_too_noisy_for_translation(text):
                return False
            
            if not self.is_valid_dialogue_text(text):
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
