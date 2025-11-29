"""
Modules package for real-time-trans
Contains utility modules for logging, translation, and OCR processing
Optimized for CPU-only real-time gaming translation
"""

from .logger import log_error, log_debug, get_base_dir
from .circuit_breaker import NetworkCircuitBreaker
from .ocr_postprocessing import (
    post_process_ocr_text_general,
    remove_text_after_last_punctuation_mark,
    post_process_ocr_for_game_subtitle
)
from .batch_translation import (
    split_into_sentences,
    translate_batch_google,
    translate_batch_deepl,
    should_use_batch_translation
)
from .deepl_context import DeepLContextManager
from .text_validator import (
    is_valid_dialogue_text,
    should_translate_text,
    extract_actual_words,
    is_too_noisy_for_translation,
    TextValidator
)
from .advanced_deduplication import AdvancedDeduplicator
from .hotkey_manager import HotkeyManager
from .image_processing import (
    StrokeWidthTransform,
    ColorTextExtractor,
    BackgroundNoiseDetector,
    AdvancedImageProcessor
)

__all__ = [
    'log_error',
    'log_debug',
    'get_base_dir',
    'NetworkCircuitBreaker',
    'post_process_ocr_text_general',
    'remove_text_after_last_punctuation_mark',
    'post_process_ocr_for_game_subtitle',
    'split_into_sentences',
    'translate_batch_google',
    'translate_batch_deepl',
    'should_use_batch_translation',
    'DeepLContextManager',
    'is_valid_dialogue_text',
    'should_translate_text',
    'extract_actual_words',
    'is_too_noisy_for_translation',
    'TextValidator',
    'AdvancedDeduplicator',
    'HotkeyManager',
    'StrokeWidthTransform',
    'ColorTextExtractor',
    'BackgroundNoiseDetector',
    'AdvancedImageProcessor',
]

