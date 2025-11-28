"""
DeepL Context Window Manager
Manages context window for DeepL translation to improve dialogue quality
"""
from .logger import log_debug, log_error

class DeepLContextManager:
    """
    Manages DeepL context window for improved translation quality.
    Context window stores previous source texts to provide context for current translation.
    """
    
    def __init__(self, max_context_size=3):
        """
        Initialize DeepL context manager.
        
        Args:
            max_context_size: Maximum number of previous subtitles to keep (0-3)
        """
        self.max_context_size = max(0, min(3, max_context_size))  # Clamp to 0-3
        self.context_window = []  # List of source texts only
        self.current_source_lang = None
        self.current_target_lang = None
        
        log_debug(f"Initialized DeepL context manager with max_context_size={self.max_context_size}")
    
    def _normalize_for_dedup(self, text):
        """Normalize text để check duplicate (loại bỏ emotion markers và excess punctuation)"""
        try:
            normalized = text.lower().strip()
            # Loại bỏ emotion markers: [action], (sound), **emotion**
            normalized = re.sub(r'\[[^\]]+\]|\([^\)]+\)|\*+[^\*]+\*+', '', normalized)
            # Normalize excess punctuation
            normalized = re.sub(r'[!]{2,}', '!', normalized)
            normalized = re.sub(r'[?]{2,}', '?', normalized)
            normalized = re.sub(r'[~]{2,}', '~', normalized)
            normalized = re.sub(r'\.{2,}', '.', normalized)
            normalized = re.sub(r'\s+', ' ', normalized).strip()
            return normalized
        except Exception as e:
            log_error("Error normalizing text for dedup", e)
            return text.lower().strip()
    
    def _clean_text_for_context(self, text):
        """Clean text để dùng làm context (loại bỏ emotion markers nhưng giữ punctuation)"""
        try:
            # Loại bỏ emotion markers: [action], (sound), **emotion**, *emphasis*
            cleaned = re.sub(r'\[[^\]]+\]|\([^\)]+\)|\*+[^\*]+\*+', '', text)
            # Loại bỏ excess whitespace
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            return cleaned if cleaned else text
        except Exception as e:
            log_error("Error cleaning text for context", e)
            return text
    
    def set_context_size(self, size):
        """
        Update context window size.
        
        Args:
            size: New context size (0-3)
        """
        try:
            old_size = self.max_context_size
            self.max_context_size = max(0, min(3, size))
            
            # Trim context window if new size is smaller
            if self.max_context_size < len(self.context_window):
                self.context_window = self.context_window[-self.max_context_size:]
            
            if old_size != self.max_context_size:
                log_debug(f"DeepL context size changed from {old_size} to {self.max_context_size}")
        except Exception as e:
            log_error("Error setting DeepL context size", e)
    
    def clear_context(self):
        """Clear context window (called on language change or session end)."""
        try:
            self.context_window = []
            self.current_source_lang = None
            self.current_target_lang = None
            log_debug("DeepL context cleared")
        except Exception as e:
            log_error("Error clearing DeepL context", e)
    
    def build_context_string(self, context_size=None):
        """
        Build DeepL context string from previous source texts.
        
        Args:
            context_size: Number of previous subtitles to include (0-3). 
                         If None, uses self.max_context_size
        
        Returns:
            Context string or None if no context available
        """
        try:
            if context_size is None:
                context_size = self.max_context_size
            
            # Validate context size
            if not isinstance(context_size, int):
                log_debug(f"Invalid DeepL context size type: {type(context_size)}, using 0")
                return None
            
            if context_size < 0 or context_size > 3:
                log_debug(f"Invalid DeepL context size: {context_size}, clamping to 0-3")
                context_size = max(0, min(3, context_size))
            
            if context_size == 0 or not self.context_window:
                return None
            
            # Get last N source texts và clean chúng (loại bỏ emotion markers)
            context_texts = self.context_window[-context_size:]
            cleaned_texts = [self._clean_text_for_context(t) for t in context_texts]
            # Filter out empty texts sau khi clean
            cleaned_texts = [t for t in cleaned_texts if t and len(t.strip()) > 0]
            
            if not cleaned_texts:
                return None
            
            # Simple concatenation with period separation
            # DeepL expects natural text in source language
            context_string = ". ".join(cleaned_texts)
            
            # Ensure proper ending
            if context_string and not context_string.endswith('.'):
                context_string += '.'
            
            return context_string
        except Exception as e:
            log_error("Error building DeepL context string", e)
            return None
    
    def update_context(self, source_text, source_lang=None, target_lang=None):
        """
        Update context window with new source text.
        
        Args:
            source_text: New source subtitle to add to context
            source_lang: Source language code (optional, for validation)
            target_lang: Target language code (optional, for validation)
        """
        try:
            # Ensure source_text is string
            if not isinstance(source_text, str):
                source_text = str(source_text) if source_text else ""
                if not source_text:
                    return
            
            # Check if language changed (clear context if so)
            if source_lang and target_lang:
                if (self.current_source_lang != source_lang or 
                    self.current_target_lang != target_lang):
                    log_debug(f"Language changed ({self.current_source_lang}->{source_lang}, {self.current_target_lang}->{target_lang}), clearing context")
                    self.clear_context()
                    self.current_source_lang = source_lang
                    self.current_target_lang = target_lang
            
            # Check for duplicate (same as last subtitle) - dùng normalized text
            if self.context_window:
                normalized_new = self._normalize_for_dedup(source_text)
                normalized_last = self._normalize_for_dedup(self.context_window[-1])
                if normalized_new == normalized_last:
                    log_debug("Skipping DeepL context update - duplicate source text (normalized)")
                    return
            
            self.context_window.append(source_text)
            
            # Keep only last 5 texts (more than max context setting for flexibility)
            self.context_window = self.context_window[-5:]
            
            log_debug(f"DeepL context updated. Window size: {len(self.context_window)}")
        except Exception as e:
            log_error("Error updating DeepL context", e)
    
    def get_context_size(self):
        """Get current context window size."""
        return len(self.context_window)
    
    def has_context(self):
        """Check if context window has any entries."""
        return len(self.context_window) > 0

