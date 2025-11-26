"""
Advanced Deduplication Module
Giải quyết vấn đề:
1. Same scene, different dialogue → skip (FIXED: hash text region only)
2. Different scene, same dialogue → duplicate (FIXED: text content comparison)
3. Short dialogue bị skip (FIXED: relaxed similarity for short text)
"""
import time
import difflib
import numpy as np
from PIL import Image
import cv2
from collections import deque
from typing import Optional, Tuple

# Import centralized logger
try:
    from .logger import log_error, log_debug
except ImportError:
    def log_error(msg, exception=None):
        pass
    def log_debug(msg):
        pass

# Import imagehash cho perceptual hashing (robust với scene changes)
IMAGEHASH_AVAILABLE = False
try:
    import imagehash
    IMAGEHASH_AVAILABLE = True
except ImportError:
    pass


class AdvancedDeduplicator:
    """
    Advanced deduplication với hybrid approach:
    - Perceptual image hash (robust với camera movement, lighting changes)
    - Text content similarity (detect actual text changes)
    - Time-window based caching
    - Special handling cho short text
    """
    
    def __init__(self, 
                 similarity_threshold=0.85,
                 short_text_threshold=50,
                 time_window=5.0,
                 max_cache_size=20):
        """
        Args:
            similarity_threshold: Ngưỡng similarity để coi là duplicate (0.0-1.0)
            short_text_threshold: Text ngắn hơn X chars được ưu tiên và relaxed similarity
            time_window: Thời gian cache (seconds) - chỉ compare với text trong window này
            max_cache_size: Max số lượng entries trong cache
        """
        self.similarity_threshold = similarity_threshold
        self.short_text_threshold = short_text_threshold
        self.time_window = time_window
        self.max_cache_size = max_cache_size
        
        # Cache: deque of (timestamp, text, text_hash, image_hash)
        self.cache = deque(maxlen=max_cache_size)
        
        # Thống kê
        self.stats = {
            'total_checks': 0,
            'duplicates_found': 0,
            'short_text_processed': 0,
            'cache_hits': 0
        }
        
        self.imagehash_available = IMAGEHASH_AVAILABLE
        if not self.imagehash_available:
            log_error("imagehash library không khả dụng. Sẽ dùng fallback hash method.")
    
    def is_duplicate(self, text: str, image: np.ndarray, current_time: Optional[float] = None) -> Tuple[bool, str]:
        """
        Check xem text+image có phải duplicate không
        
        Returns:
            (is_duplicate: bool, reason: str)
        """
        if current_time is None:
            current_time = time.time()
        
        self.stats['total_checks'] += 1
        
        # Empty text luôn là duplicate
        if not text or not text.strip():
            return True, "empty_text"
        
        text = text.strip()
        text_len = len(text)
        
        # Short text tracking
        is_short_text = text_len < self.short_text_threshold
        if is_short_text:
            self.stats['short_text_processed'] += 1
        
        # Cleanup cache - xóa entries cũ hơn time_window
        self._cleanup_cache(current_time)
        
        # Nếu cache rỗng - không phải duplicate
        if not self.cache:
            self._add_to_cache(text, image, current_time)
            return False, "cache_empty"
        
        # Tính hash của text và image hiện tại
        text_hash = self._compute_text_hash(text)
        image_hash = self._compute_image_hash(image)
        
        # Check với từng entry trong cache (trong time window)
        for cached_time, cached_text, cached_text_hash, cached_image_hash in self.cache:
            # Text exact match
            if text_hash == cached_text_hash:
                self.stats['duplicates_found'] += 1
                self.stats['cache_hits'] += 1
                return True, "exact_text_match"
            
            # Text similarity check (dùng difflib)
            text_similarity = self._compute_text_similarity(text, cached_text)
            
            # Short text: relaxed similarity threshold (0.7 thay vì 0.85)
            # Vì short text dễ false positive với strict threshold
            effective_threshold = 0.7 if is_short_text else self.similarity_threshold
            
            if text_similarity >= effective_threshold:
                # Text rất giống - check image để xác nhận
                # Nếu image cũng giống → duplicate (same scene, same text)
                # Nếu image khác → NOT duplicate (different scene, similar text - có thể là repeated dialogue)
                
                image_similarity = self._compute_image_similarity(image_hash, cached_image_hash)
                
                # Image similarity threshold: 0.8 (cho phép slight camera movement)
                if image_similarity >= 0.8:
                    # Cả text và image giống → chắc chắn duplicate
                    self.stats['duplicates_found'] += 1
                    return True, f"text_image_similar (text={text_similarity:.2f}, img={image_similarity:.2f})"
                else:
                    # Text giống nhưng image khác → KHÔNG duplicate
                    # Đây là repeated dialogue ở scene khác
                    log_debug(f"Same text different scene: '{text[:30]}...' (text_sim={text_similarity:.2f}, img_sim={image_similarity:.2f})")
                    # Vẫn add vào cache để track
                    self._add_to_cache(text, image, current_time)
                    return False, f"repeated_dialogue_different_scene"
        
        # Không match với cache nào - không phải duplicate
        self._add_to_cache(text, image, current_time)
        return False, "new_content"
    
    def _compute_text_hash(self, text: str) -> str:
        """Compute hash của text - dùng lowercase để ignore case"""
        import hashlib
        return hashlib.md5(text.lower().encode('utf-8', errors='ignore')).hexdigest()
    
    def _compute_text_similarity(self, text1: str, text2: str) -> float:
        """
        Compute text similarity dùng difflib SequenceMatcher
        Returns: 0.0-1.0 (1.0 = identical)
        """
        try:
            # Normalize: lowercase, strip whitespace
            t1 = text1.lower().strip()
            t2 = text2.lower().strip()
            
            # Dùng SequenceMatcher
            matcher = difflib.SequenceMatcher(None, t1, t2)
            return matcher.ratio()
        except Exception as e:
            log_error(f"Error computing text similarity", e)
            return 0.0
    
    def _compute_image_hash(self, image: np.ndarray) -> str:
        """
        Compute perceptual hash của image
        Perceptual hash robust với:
        - Slight camera movement
        - Lighting changes
        - Compression artifacts
        """
        if not self.imagehash_available:
            return self._fallback_image_hash(image)
        
        try:
            # Convert numpy array to PIL Image
            if isinstance(image, np.ndarray):
                # OpenCV BGR -> RGB
                if len(image.shape) == 3 and image.shape[2] == 3:
                    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                else:
                    image_rgb = image
                pil_image = Image.fromarray(image_rgb)
            else:
                pil_image = image
            
            # Dùng phash (perceptual hash) - robust nhất cho video frames
            # phash dựa trên DCT, ít sensitive với minor changes
            img_hash = imagehash.phash(pil_image, hash_size=8)
            return str(img_hash)
        except Exception as e:
            log_error(f"Error computing perceptual hash, using fallback", e)
            return self._fallback_image_hash(image)
    
    def _fallback_image_hash(self, image: np.ndarray) -> str:
        """
        Fallback hash method nếu imagehash không khả dụng
        Dùng simple hash trên resized image
        """
        try:
            import hashlib
            # Resize về size nhỏ để hash
            if isinstance(image, np.ndarray):
                h, w = image.shape[:2]
                small_img = cv2.resize(image, (16, 16), interpolation=cv2.INTER_NEAREST)
                img_bytes = small_img.tobytes()
            else:
                # PIL Image
                small_img = image.resize((16, 16), Image.Resampling.NEAREST)
                img_bytes = small_img.tobytes()
            
            return hashlib.md5(img_bytes).hexdigest()
        except Exception as e:
            log_error(f"Error in fallback image hash", e)
            return "error_hash"
    
    def _compute_image_similarity(self, hash1: str, hash2: str) -> float:
        """
        Compute similarity giữa 2 image hashes
        Returns: 0.0-1.0 (1.0 = identical)
        """
        if not self.imagehash_available:
            # Fallback: exact match only
            return 1.0 if hash1 == hash2 else 0.0
        
        try:
            # Parse imagehash strings
            import imagehash
            ihash1 = imagehash.hex_to_hash(hash1)
            ihash2 = imagehash.hex_to_hash(hash2)
            
            # Hamming distance (số bits khác nhau)
            distance = ihash1 - ihash2
            
            # Convert to similarity (0-1)
            # hash_size=8 → 64 bits total
            max_distance = 64
            similarity = 1.0 - (distance / max_distance)
            return max(0.0, min(1.0, similarity))
        except Exception as e:
            log_error(f"Error computing image similarity", e)
            return 1.0 if hash1 == hash2 else 0.0
    
    def _add_to_cache(self, text: str, image: np.ndarray, current_time: float):
        """Add entry vào cache"""
        try:
            text_hash = self._compute_text_hash(text)
            image_hash = self._compute_image_hash(image)
            
            # Add to deque (auto evict oldest nếu full)
            self.cache.append((current_time, text, text_hash, image_hash))
        except Exception as e:
            log_error(f"Error adding to cache", e)
    
    def _cleanup_cache(self, current_time: float):
        """Xóa entries cũ hơn time_window khỏi cache"""
        cutoff_time = current_time - self.time_window
        
        # Remove entries cũ hơn cutoff_time
        while self.cache and self.cache[0][0] < cutoff_time:
            self.cache.popleft()
    
    def clear_cache(self):
        """Clear toàn bộ cache"""
        self.cache.clear()
        log_debug("Advanced deduplicator cache cleared")
    
    def get_stats(self) -> dict:
        """Get statistics"""
        if self.stats['total_checks'] > 0:
            duplicate_rate = (self.stats['duplicates_found'] / self.stats['total_checks']) * 100
        else:
            duplicate_rate = 0.0
        
        return {
            **self.stats,
            'duplicate_rate': duplicate_rate,
            'cache_size': len(self.cache),
            'imagehash_available': self.imagehash_available
        }
    
    def reset_stats(self):
        """Reset statistics"""
        self.stats = {
            'total_checks': 0,
            'duplicates_found': 0,
            'short_text_processed': 0,
            'cache_hits': 0
        }
