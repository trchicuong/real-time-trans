"""
Modules package for real-time-trans
Contains utility modules for logging, caching, translation, and OCR processing
"""

# Import commonly used functions for convenience
from .logger import log_error, log_debug, get_base_dir
from .circuit_breaker import NetworkCircuitBreaker
from .ocr_postprocessing import (
    post_process_ocr_text_general,
    remove_text_after_last_punctuation_mark,
    post_process_ocr_for_game_subtitle
)
from .unified_translation_cache import UnifiedTranslationCache
from .batch_translation import (
    split_into_sentences,
    translate_batch_google,
    translate_batch_deepl,
    should_use_batch_translation
)
from .deepl_context import DeepLContextManager

__all__ = [
    'log_error',
    'log_debug',
    'get_base_dir',
    'NetworkCircuitBreaker',
    'post_process_ocr_text_general',
    'remove_text_after_last_punctuation_mark',
    'post_process_ocr_for_game_subtitle',
    'UnifiedTranslationCache',
    'split_into_sentences',
    'translate_batch_google',
    'translate_batch_deepl',
    'should_use_batch_translation',
    'DeepLContextManager',
]

