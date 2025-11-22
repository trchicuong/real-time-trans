"""
Unified Translation Cache - Thread-safe unified cache for all translation providers
"""
import threading
import time
import hashlib
from .logger import log_debug, log_error

class UnifiedTranslationCache:
    """
    Unified translation cache for all translation providers.
    Thread-safe, configurable, and integrates with existing file caches.
    """
    
    def __init__(self, max_size=2000):
        """
        Initialize the unified translation cache.
        
        Args:
            max_size: Maximum number of entries in the LRU cache
        """
        self.max_size = max_size
        self.lock = threading.RLock()
        
        # Unified cache storage
        # Key format: (text_hash, source_lang, target_lang, provider, params_hash)
        self._cache = {}
        self._access_times = {}  # For LRU eviction
        
        # Statistics tracking
        self._hits = 0
        self._misses = 0
        self._stores = 0
        
        log_debug(f"Initialized unified translation cache with max_size={max_size}")
    
    def _generate_cache_key(self, text, source_lang, target_lang, provider, **kwargs):
        """
        Generate a unique cache key for the translation request.
        
        Args:
            text: Source text to translate
            source_lang: Source language code
            target_lang: Target language code
            provider: Translation provider ('google', 'deepl', 'marianmt')
            **kwargs: Provider-specific parameters
        
        Returns:
            Tuple cache key: (text_hash, source_lang, target_lang, provider, params_hash)
        """
        try:
            # Create deterministic hash of text to handle large inputs efficiently
            text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
            
            # Include provider-specific parameters in the key
            params_str = ""
            if provider.lower() == "marianmt" and "beam_size" in kwargs:
                params_str = f"_beam{kwargs['beam_size']}"
            elif provider.lower() == "deepl" and "model_type" in kwargs:
                params_str = f"_model{kwargs['model_type']}"
            elif provider.lower() == "google" and "format" in kwargs:
                params_str = f"_fmt{kwargs['format']}"
            # Add more provider-specific parameters as needed
            
            params_hash = hashlib.md5(params_str.encode('utf-8')).hexdigest()[:8] if params_str else ""
            
            return (text_hash, source_lang.lower(), target_lang.lower(), provider.lower(), params_hash)
        except Exception as e:
            log_error("Error generating cache key", e)
            # Fallback: use simple hash without params
            try:
                text_hash = hashlib.md5(str(text).encode('utf-8', errors='replace')).hexdigest()
                return (text_hash, str(source_lang).lower(), str(target_lang).lower(), str(provider).lower(), "")
            except Exception as fallback_err:
                log_error("Error in cache key fallback", fallback_err)
                # Ultimate fallback: use text length and provider
                return (str(len(str(text))), str(source_lang), str(target_lang), str(provider), "")
    
    def get(self, text, source_lang, target_lang, provider, **kwargs):
        """
        Get translation from cache. Returns None if not found.
        
        Args:
            text: Source text to translate
            source_lang: Source language code
            target_lang: Target language code  
            provider: Translation provider ('google', 'deepl', 'marianmt')
            **kwargs: Provider-specific parameters (e.g., beam_size for MarianMT, model_type for DeepL)
            
        Returns:
            Cached translation if found, None otherwise
        """
        try:
            cache_key = self._generate_cache_key(text, source_lang, target_lang, provider, **kwargs)
            
            with self.lock:
                if cache_key in self._cache:
                    # Update access time for LRU
                    self._access_times[cache_key] = time.time()
                    translation = self._cache[cache_key]
                    self._hits += 1
                    
                    log_debug(f"Unified cache HIT: {provider} {source_lang}->{target_lang}")
                    return translation
                
                self._misses += 1
                log_debug(f"Unified cache MISS: {provider} {source_lang}->{target_lang}")
                return None
        except Exception as e:
            log_error("Error getting translation from unified cache", e)
            return None
    
    def store(self, text, source_lang, target_lang, provider, translation, **kwargs):
        """
        Store translation in cache.
        
        Args:
            text: Source text that was translated
            source_lang: Source language code
            target_lang: Target language code
            provider: Translation provider ('google', 'deepl', 'marianmt')
            translation: The translated text
            **kwargs: Provider-specific parameters (e.g., beam_size for MarianMT, model_type for DeepL)
        """
        try:
            cache_key = self._generate_cache_key(text, source_lang, target_lang, provider, **kwargs)
            
            with self.lock:
                # Evict old entries if cache is full
                if len(self._cache) >= self.max_size:
                    try:
                        self._evict_lru_entries()
                    except Exception as evict_err:
                        log_error("Error evicting LRU entries from unified cache", evict_err)
                
                # Store the translation
                self._cache[cache_key] = translation
                self._access_times[cache_key] = time.time()
                self._stores += 1
                
                log_debug(f"Unified cache STORE: {provider} {source_lang}->{target_lang}")
        except Exception as e:
            log_error("Error storing translation in unified cache", e)
    
    def _evict_lru_entries(self):
        """Evict least recently used entries (10% of cache size)."""
        try:
            evict_count = max(1, self.max_size // 10)
            
            # Sort by access time and remove oldest
            sorted_items = sorted(self._access_times.items(), key=lambda x: x[1])
            for cache_key, _ in sorted_items[:evict_count]:
                self._cache.pop(cache_key, None)
                self._access_times.pop(cache_key, None)
            
            log_debug(f"Evicted {evict_count} LRU cache entries")
        except Exception as e:
            log_error("Error evicting LRU entries from unified cache", e)
    
    def clear_all(self):
        """Clear all cached translations."""
        try:
            with self.lock:
                entries_cleared = len(self._cache)
                self._cache.clear()
                self._access_times.clear()
                self._hits = 0
                self._misses = 0
                self._stores = 0
                log_debug(f"Cleared unified translation cache ({entries_cleared} entries)")
        except Exception as e:
            log_error("Error clearing unified translation cache", e)
    
    def clear_provider(self, provider):
        """Clear cache entries for a specific provider."""
        try:
            with self.lock:
                provider_lower = provider.lower()
                keys_to_remove = [k for k in self._cache.keys() if k[3] == provider_lower]
                
                for key in keys_to_remove:
                    self._cache.pop(key, None)
                    self._access_times.pop(key, None)
                
                log_debug(f"Cleared {len(keys_to_remove)} cache entries for provider: {provider}")
        except Exception as e:
            log_error(f"Error clearing cache entries for provider: {provider}", e)
    
    def get_stats(self):
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics:
            - total_entries: Current number of entries
            - max_size: Maximum cache size
            - utilization: Percentage of cache used
            - hits: Number of cache hits
            - misses: Number of cache misses
            - hit_rate: Cache hit rate percentage
            - provider_breakdown: Dictionary of entries per provider
        """
        try:
            with self.lock:
                provider_counts = {}
                for key in self._cache.keys():
                    provider = key[3]  # provider is at index 3
                    provider_counts[provider] = provider_counts.get(provider, 0) + 1
                
                total_requests = self._hits + self._misses
                hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0
                
                return {
                    "total_entries": len(self._cache),
                    "max_size": self.max_size,
                    "utilization": f"{len(self._cache) / self.max_size * 100:.1f}%" if self.max_size > 0 else "0%",
                    "hits": self._hits,
                    "misses": self._misses,
                    "hit_rate": f"{hit_rate:.1f}%",
                    "stores": self._stores,
                    "provider_breakdown": provider_counts
                }
        except Exception as e:
            log_error("Error getting unified cache statistics", e)
            # Return empty stats on error
            return {
                "total_entries": 0,
                "max_size": self.max_size,
                "utilization": "0%",
                "hits": 0,
                "misses": 0,
                "hit_rate": "0%",
                "stores": 0,
                "provider_breakdown": {}
            }
    
    def get_size(self):
        """Get current cache size."""
        try:
            with self.lock:
                return len(self._cache)
        except Exception as e:
            log_error("Error getting unified cache size", e)
            return 0

