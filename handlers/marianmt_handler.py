# -*- coding: utf-8 -*-
"""
MarianMT Handler - Local Neural Machine Translation
Adapted from OCR-Translator for real-time-trans
GPU-accelerated translation with automatic CPU fallback

Performance:
- CPU mode: 100-300ms per translation
- GPU mode: 50-150ms per translation
vs API: 200-2000ms

Supported pairs: en-pl, pl-en, en-de, de-en, en-fr, fr-en, etc.
"""

import threading
import time
import gc
import re
import os
import traceback
from pathlib import Path
import warnings

# Suppress sacremoses warning (optional dependency)
warnings.filterwarnings('ignore', message='.*sacremoses.*')

# Import log_error from modules package
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from modules import log_error, log_debug, get_base_dir

# Try to import MarianMT dependencies
MARIANMT_AVAILABLE = False
torch = None
GPU_AVAILABLE = False
GPU_DEVICE = None
GPU_NAME = None

try:
    from transformers import MarianMTModel, MarianTokenizer
    import torch
    
    # Check GPU availability
    CUDA_LIBRARIES_AVAILABLE = (hasattr(torch, 'version') and 
                                hasattr(torch.version, 'cuda') and 
                                torch.version.cuda is not None)
    
    if CUDA_LIBRARIES_AVAILABLE:
        GPU_AVAILABLE = torch.cuda.is_available()
        if GPU_AVAILABLE:
            GPU_DEVICE = torch.device("cuda:0")
            try:
                GPU_NAME = torch.cuda.get_device_name(0)
                log_debug(f"[MarianMT] GPU detected: {GPU_NAME}")
            except Exception as e:
                GPU_NAME = "Unknown GPU"
                log_error("[MarianMT] Error getting GPU name", e)
        else:
            GPU_DEVICE = torch.device("cpu")
            log_debug("[MarianMT] CUDA available but no GPU detected, using CPU")
    else:
        GPU_DEVICE = torch.device("cpu")
        log_debug("[MarianMT] CUDA not available, using CPU")
    
    MARIANMT_AVAILABLE = True
    log_debug("[MarianMT] Successfully initialized")
    
except ImportError as e:
    log_error(f"[MarianMT] Import failed: {e}. Install: pip install transformers torch sentencepiece", e)
except Exception as e:
    log_error(f"[MarianMT] Initialization error", e)


class MarianMTHandler:
    """Simplified MarianMT handler for real-time translation"""
    
    def __init__(self, cache_dir=None, num_beams=2, use_gpu=None):
        """
        Initialize MarianMT handler
        
        Args:
            cache_dir: Directory to store models (default: ./marian_models_cache)
            num_beams: Beam search value (1-8, higher = better quality but slower)
            use_gpu: None=auto, True=force GPU, False=force CPU
        """
        if not MARIANMT_AVAILABLE:
            raise ImportError("MarianMT not available. Install: pip install transformers torch sentencepiece")
        
        # Device configuration
        if use_gpu is True:
            if GPU_AVAILABLE:
                self.device = GPU_DEVICE
                self.gpu_enabled = True
                log_debug(f"[MarianMT] GPU mode forced: {GPU_NAME}")
            else:
                self.device = torch.device("cpu")
                self.gpu_enabled = False
                log_debug("[MarianMT] GPU requested but not available, using CPU")
        elif use_gpu is False:
            self.device = torch.device("cpu")
            self.gpu_enabled = False
            log_debug("[MarianMT] CPU mode forced")
        else:
            # Auto-detect
            self.device = GPU_DEVICE if GPU_AVAILABLE else torch.device("cpu")
            self.gpu_enabled = GPU_AVAILABLE
            if self.gpu_enabled:
                log_debug(f"[MarianMT] Auto-detected GPU: {GPU_NAME}")
            else:
                log_debug("[MarianMT] Auto-detected CPU mode")
        
        self.cache_dir = cache_dir if cache_dir else os.path.join(get_base_dir(), "marian_models_cache")
        self.num_beams = num_beams
        self.model_lock = threading.RLock()
        
        # Current loaded model
        self.active_model_key = None
        self.active_tokenizer = None
        self.active_model = None
        
        # Supported language pairs (Helsinki-NLP models)
        self.direct_pairs = {
            ('en', 'vi'): 'Helsinki-NLP/opus-mt-en-vi',  # English to Vietnamese
            ('vi', 'en'): 'Helsinki-NLP/opus-mt-vi-en',  # Vietnamese to English
            ('en', 'ja'): 'Helsinki-NLP/opus-mt-en-jap',  # English to Japanese
            ('ja', 'en'): 'Helsinki-NLP/opus-mt-jap-en',  # Japanese to English
            ('en', 'ko'): 'Helsinki-NLP/opus-mt-en-ko',   # English to Korean
            ('ko', 'en'): 'Helsinki-NLP/opus-mt-ko-en',   # Korean to English
            ('en', 'zh'): 'Helsinki-NLP/opus-mt-en-zh',   # English to Chinese
            ('zh', 'en'): 'Helsinki-NLP/opus-mt-zh-en',   # Chinese to English
            ('en', 'de'): 'Helsinki-NLP/opus-mt-en-de',   # English to German
            ('de', 'en'): 'Helsinki-NLP/opus-mt-de-en',   # German to English
            ('en', 'fr'): 'Helsinki-NLP/opus-mt-en-fr',   # English to French
            ('fr', 'en'): 'Helsinki-NLP/opus-mt-fr-en',   # French to English
            ('en', 'es'): 'Helsinki-NLP/opus-mt-en-es',   # English to Spanish
            ('es', 'en'): 'Helsinki-NLP/opus-mt-es-en',   # Spanish to English
        }
        
        # Stats
        self.stats = {
            'translations': 0,
            'cache_hits': 0,
            'avg_time': 0.0
        }
    
    def is_available(self):
        """Check if MarianMT is available"""
        return MARIANMT_AVAILABLE
    
    def is_language_pair_supported(self, source_lang, target_lang):
        """Check if language pair is supported"""
        return (source_lang, target_lang) in self.direct_pairs
    
    def get_supported_pairs(self):
        """Get list of supported language pairs"""
        return list(self.direct_pairs.keys())
    
    def _load_model(self, source_lang, target_lang):
        """Load translation model for language pair"""
        model_key = (source_lang, target_lang)
        
        with self.model_lock:
            # Check if already loaded
            if self.active_model_key == model_key and self.active_model is not None:
                return True
            
            # Unload previous model
            if self.active_model is not None:
                log_debug(f"[MarianMT] Unloading previous model {self.active_model_key}")
                self.active_model = None
                self.active_tokenizer = None
                self.active_model_key = None
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            
            # Check if pair is supported
            if model_key not in self.direct_pairs:
                error_msg = f"[MarianMT] Language pair {source_lang}->{target_lang} not supported"
                log_error(error_msg, None)
                log_debug(f"[MarianMT] Available pairs: {list(self.direct_pairs.keys())}")
                return None
            
            model_name = self.direct_pairs[model_key]
            log_debug(f"[MarianMT] Loading model: {model_name} on {'GPU' if self.gpu_enabled else 'CPU'}")
            log_debug(f"[MarianMT] Note: First download may take 1-5 minutes (~300MB)")
            
            try:
                start_time = time.time()
                
                # Load tokenizer
                self.active_tokenizer = MarianTokenizer.from_pretrained(
                    model_name, 
                    cache_dir=self.cache_dir
                )
                
                # Load model
                self.active_model = MarianMTModel.from_pretrained(
                    model_name,
                    cache_dir=self.cache_dir,
                    low_cpu_mem_usage=True,
                    dtype=torch.float16 if self.gpu_enabled else torch.float32
                )
                
                # Move to device
                self.active_model = self.active_model.to(self.device)
                
                load_time = time.time() - start_time
                device_name = "GPU" if self.device.type == 'cuda' else "CPU"
                log_debug(f"[MarianMT] Model loaded on {device_name} in {load_time:.2f}s")
                
                self.active_model_key = model_key
                return True
                
            except Exception as e:
                log_error(f"[MarianMT] Failed to load model: {e}", e)
                return False
    
    def translate(self, text, source_lang, target_lang):
        """
        Translate text using MarianMT
        
        Args:
            text: Text to translate
            source_lang: Source language code (e.g., 'en', 'vi')
            target_lang: Target language code
            
        Returns:
            Translated text or error message
        """
        if not text or not isinstance(text, str):
            return ""
        
        # Normalize language codes
        source_lang = source_lang.lower()
        target_lang = target_lang.lower()
        
        # Map common codes
        lang_map = {
            'eng': 'en',
            'vie': 'vi',
            'jpn': 'ja',
            'jap': 'ja',
            'kor': 'ko',
            'chi': 'zh',
            'zho': 'zh',
            'deu': 'de',
            'fra': 'fr',
            'spa': 'es'
        }
        source_lang = lang_map.get(source_lang, source_lang)
        target_lang = lang_map.get(target_lang, target_lang)
        
        if source_lang == target_lang:
            return text
        
        # Check if supported
        if not self.is_language_pair_supported(source_lang, target_lang):
            return f"Error: {source_lang}->{target_lang} not supported by MarianMT"
        
        # Load model if needed
        if not self._load_model(source_lang, target_lang):
            return f"Error: Failed to load MarianMT model for {source_lang}->{target_lang}"
        
        # Translate
        try:
            start_time = time.time()
            
            # Clean text
            text = re.sub(r'\s+', ' ', text).strip()
            if not text:
                return ""
            
            # Tokenize
            inputs = self.active_tokenizer([text], return_tensors="pt", padding=True)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # Generate
            with torch.no_grad():
                if self.device.type == 'cuda':
                    # GPU with mixed precision
                    with torch.amp.autocast('cuda'):
                        outputs = self.active_model.generate(
                            **inputs,
                            max_length=512,
                            num_beams=self.num_beams,
                            length_penalty=1.0,
                            no_repeat_ngram_size=2
                        )
                else:
                    # CPU
                    outputs = self.active_model.generate(
                        **inputs,
                        max_length=512,
                        num_beams=self.num_beams,
                        length_penalty=1.0,
                        no_repeat_ngram_size=2
                    )
            
            # Decode
            result = self.active_tokenizer.batch_decode(outputs, skip_special_tokens=True)[0]
            
            # Update stats
            trans_time = time.time() - start_time
            self.stats['translations'] += 1
            self.stats['avg_time'] = (
                (self.stats['avg_time'] * (self.stats['translations'] - 1) + trans_time) 
                / self.stats['translations']
            )
            
            device_name = "GPU" if self.device.type == 'cuda' else "CPU"
            log_debug(f"[MarianMT] Translated on {device_name} in {trans_time*1000:.0f}ms: {len(text)} -> {len(result)} chars")
            
            return result
            
        except torch.cuda.OutOfMemoryError:
            log_error("[MarianMT] GPU out of memory, try using CPU mode", None)
            log_debug("[MarianMT] Suggestion: Close other GPU apps or set marianmt_use_gpu=False in config")
            return "Error: GPU out of memory"
        except Exception as e:
            log_error(f"[MarianMT] Translation error", e)
            log_debug(f"[MarianMT] Text length: {len(text)}, Lang: {source_lang}->{target_lang}")
            return f"Error: {str(e)}"
    
    def get_stats(self):
        """Get handler statistics"""
        return {
            **self.stats,
            'gpu_enabled': self.gpu_enabled,
            'gpu_name': GPU_NAME if self.gpu_enabled else 'N/A',
            'device': str(self.device),
            'active_model': f"{self.active_model_key[0]}->{self.active_model_key[1]}" if self.active_model_key else None,
            'supported_pairs': len(self.direct_pairs),
            'beam_search': self.num_beams,
            'total_gpu_memory': f"{torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB" if GPU_AVAILABLE else "N/A"
        }
    
    def cleanup(self):
        """Cleanup resources"""
        with self.model_lock:
            if self.active_model is not None:
                log_debug("[MarianMT] Cleaning up model resources")
                model_key = self.active_model_key
                self.active_model = None
                self.active_tokenizer = None
                self.active_model_key = None
                gc.collect()
                if torch and torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    log_debug(f"[MarianMT] Cleaned up model {model_key}, freed GPU memory")
                else:
                    log_debug(f"[MarianMT] Cleaned up model {model_key}")
