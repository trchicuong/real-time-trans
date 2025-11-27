"""
Modules package for real-time-trans
Contains utility modules for logging, caching, translation, and OCR processing
"""

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
from .text_normalizer import (
    normalize_for_cache,
    normalize_for_display,
    normalize_for_comparison,
    is_similar_enough_for_cache,
    extract_core_text,
    TextNormalizer
)
from .text_deduplication import (
    is_duplicate_text,
    clear_deduplication_cache,
    get_deduplication_stats,
    TextDeduplicator
)
from .sentence_buffer import (
    add_text_to_buffer,
    force_release_buffer,
    clear_sentence_buffer,
    get_sentence_buffer_stats,
    SentenceBuffer
)
from .smart_queue import SmartQueue
from .rate_limiter import (
    record_api_start,
    record_api_success,
    record_api_failure,
    get_current_capture_interval,
    should_skip_api_request,
    reset_rate_limiter,
    get_rate_limiter_stats,
    is_api_healthy,
    AdaptiveRateLimiter
)
from .translation_continuity import (
    should_merge_translation,
    add_translation_to_context,
    merge_translation_results,
    clear_translation_context,
    get_translation_context_summary,
    get_continuity_stats,
    TranslationContinuityTracker
)
from .text_validator import (
    is_valid_dialogue_text,
    should_translate_text,
    extract_actual_words,
    is_too_noisy_for_translation,
    TextValidator
)
from .advanced_deduplication import AdvancedDeduplicator
from .hotkey_manager import HotkeyManager

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
    'normalize_for_cache',
    'normalize_for_display',
    'normalize_for_comparison',
    'is_similar_enough_for_cache',
    'extract_core_text',
    'TextNormalizer',
    'is_duplicate_text',
    'clear_deduplication_cache',
    'get_deduplication_stats',
    'TextDeduplicator',
    'add_text_to_buffer',
    'force_release_buffer',
    'clear_sentence_buffer',
    'get_sentence_buffer_stats',
    'SentenceBuffer',
    'SmartQueue',
    'record_api_start',
    'record_api_success',
    'record_api_failure',
    'get_current_capture_interval',
    'should_skip_api_request',
    'reset_rate_limiter',
    'get_rate_limiter_stats',
    'is_api_healthy',
    'AdaptiveRateLimiter',
    'should_merge_translation',
    'add_translation_to_context',
    'merge_translation_results',
    'clear_translation_context',
    'get_translation_context_summary',
    'get_continuity_stats',
    'TranslationContinuityTracker',
    'is_valid_dialogue_text',
    'should_translate_text',
    'extract_actual_words',
    'is_too_noisy_for_translation',
    'TextValidator',
    'AdvancedDeduplicator',
    'HotkeyManager',
]

