"""
Smart Queue Module - Priority queue với smart eviction cho OCR/Translation
"""
import queue
import threading
import time
from .logger import log_debug, log_error
from .text_normalizer import normalize_for_comparison

class SmartQueue:
    """
    Queue thông minh với:
    - Priority: new items > old items
    - Smart eviction: drop duplicate items when full
    - Statistics tracking
    """
    
    def __init__(self, maxsize=20, name="SmartQueue"):
        """
        Args:
            maxsize: Maximum queue size
            name: Queue name (for logging)
        """
        self.maxsize = maxsize
        self.name = name
        
        # Internal queue: Priority queue (lower priority number = higher priority)
        # Items: (priority, timestamp, data)
        self._queue = queue.PriorityQueue(maxsize=maxsize)
        self._lock = threading.RLock()
        
        # Counter để tạo unique priority (lower = newer = higher priority)
        self._counter = 0
        
        # Track recent items để detect duplicates
        self._recent_hashes = set()  # Set of recent item hashes
        self._hash_to_data = {}  # Map hash → data (để avoid re-adding same item)
        
        # Statistics
        self.total_puts = 0
        self.total_gets = 0
        self.duplicates_dropped = 0
        self.items_evicted = 0
    
    def put(self, item, block=True, timeout=None, priority=None):
        """
        Put item vào queue với priority.
        
        Args:
            item: Data to put
            block: Block if queue full
            timeout: Timeout for blocking
            priority: Optional priority (lower = higher priority). Nếu None, dùng counter
        
        Returns:
            True nếu đã put thành công, False nếu queue full hoặc duplicate
        """
        try:
            with self._lock:
                self.total_puts += 1
                
                # Calculate hash để detect duplicates
                item_hash = self._calculate_hash(item)
                
                # Check duplicate
                if item_hash in self._recent_hashes:
                    self.duplicates_dropped += 1
                    log_debug(f"{self.name}: Dropped duplicate item")
                    return False
                
                # Generate priority
                if priority is None:
                    # Lower counter = newer = higher priority
                    priority = -self._counter
                    self._counter += 1
                
                timestamp = time.time()
                
                # Try put
                try:
                    self._queue.put((priority, timestamp, item), block=block, timeout=timeout)
                    
                    # Track hash
                    self._recent_hashes.add(item_hash)
                    self._hash_to_data[item_hash] = item
                    
                    # Limit recent_hashes size (keep last 100)
                    if len(self._recent_hashes) > 100:
                        # Remove oldest (simple approach: clear some)
                        hashes_to_remove = list(self._recent_hashes)[:20]
                        for h in hashes_to_remove:
                            self._recent_hashes.discard(h)
                            self._hash_to_data.pop(h, None)
                    
                    return True
                    
                except queue.Full:
                    # Queue full → Smart eviction
                    if self._try_smart_eviction():
                        # After eviction, try again
                        try:
                            self._queue.put((priority, timestamp, item), block=False)
                            self._recent_hashes.add(item_hash)
                            self._hash_to_data[item_hash] = item
                            return True
                        except queue.Full:
                            log_error(f"{self.name}: Queue still full after eviction")
                            return False
                    else:
                        log_error(f"{self.name}: Queue full, eviction failed")
                        return False
                        
        except Exception as e:
            log_error(f"{self.name}: Error putting item", e)
            return False
    
    def get(self, block=True, timeout=None):
        """
        Get item từ queue (highest priority first).
        
        Returns:
            Data (không bao gồm priority/timestamp)
        
        Raises:
            queue.Empty nếu queue empty
        """
        try:
            priority, timestamp, data = self._queue.get(block=block, timeout=timeout)
            
            with self._lock:
                self.total_gets += 1
                
                # Remove hash từ recent
                item_hash = self._calculate_hash(data)
                self._recent_hashes.discard(item_hash)
                self._hash_to_data.pop(item_hash, None)
            
            return data
            
        except queue.Empty:
            raise
        except Exception as e:
            log_error(f"{self.name}: Error getting item", e)
            raise
    
    def get_nowait(self):
        """Get item without blocking."""
        return self.get(block=False)
    
    def put_nowait(self, item, priority=None):
        """Put item without blocking."""
        return self.put(item, block=False, priority=priority)
    
    def empty(self):
        """Check if queue is empty."""
        return self._queue.empty()
    
    def full(self):
        """Check if queue is full."""
        return self._queue.full()
    
    def qsize(self):
        """Get approximate queue size."""
        return self._queue.qsize()
    
    def _calculate_hash(self, item):
        """
        Tính hash cho item để detect duplicates.
        
        Hỗ trợ:
        - String: normalize rồi hash
        - Dict: hash các values quan trọng
        - Tuple/List: hash elements
        - Image (PIL/numpy): hash size + type
        """
        try:
            if isinstance(item, str):
                # String: normalize rồi hash
                normalized = normalize_for_comparison(item)
                return hash(normalized)
            elif isinstance(item, dict):
                # Dict: hash text hoặc các keys quan trọng
                if 'text' in item:
                    normalized = normalize_for_comparison(str(item['text']))
                    return hash(normalized)
                else:
                    # Hash tất cả keys/values
                    return hash(tuple(sorted(item.items())))
            elif isinstance(item, (tuple, list)):
                # Tuple/List: hash elements
                return hash(tuple(item))
            elif hasattr(item, 'tobytes'):
                # Numpy array or PIL Image: hash size + dtype
                if hasattr(item, 'shape') and hasattr(item, 'dtype'):
                    # Numpy array
                    return hash((item.shape, str(item.dtype)))
                elif hasattr(item, 'size') and hasattr(item, 'mode'):
                    # PIL Image
                    return hash((item.size, item.mode))
                else:
                    return hash(id(item))  # Fallback: object id
            else:
                # Fallback: object id
                return hash(id(item))
                
        except Exception as e:
            log_error("Error calculating item hash", e)
            return hash(id(item))  # Ultimate fallback
    
    def _try_smart_eviction(self):
        """
        Thử evict item từ queue để tạo space.
        Strategy: Evict oldest item (lowest priority = oldest).
        
        Returns:
            True nếu eviction thành công
        """
        try:
            # Get oldest item (highest priority number = oldest)
            # PriorityQueue không có peek, phải get rồi put lại
            # → Simple strategy: clear 1/4 của queue
            
            items_to_keep = []
            evicted_count = 0
            target_evict = max(1, self.maxsize // 4)
            
            # Get tất cả items
            while not self._queue.empty():
                try:
                    item = self._queue.get_nowait()
                    items_to_keep.append(item)
                except queue.Empty:
                    break
            
            # Sort by priority (lower = higher priority = keep)
            items_to_keep.sort(key=lambda x: x[0])
            
            # Keep highest priority items, drop oldest
            items_to_evict = items_to_keep[-target_evict:]
            items_to_keep = items_to_keep[:-target_evict]
            
            # Put back kept items
            for item in items_to_keep:
                try:
                    self._queue.put_nowait(item)
                except queue.Full:
                    break
            
            # Track evicted items
            for priority, timestamp, data in items_to_evict:
                evicted_count += 1
                item_hash = self._calculate_hash(data)
                self._recent_hashes.discard(item_hash)
                self._hash_to_data.pop(item_hash, None)
            
            self.items_evicted += evicted_count
            log_debug(f"{self.name}: Evicted {evicted_count} oldest items")
            
            return evicted_count > 0
            
        except Exception as e:
            log_error(f"{self.name}: Error during smart eviction", e)
            return False
    
    def clear(self):
        """Clear all items from queue."""
        try:
            with self._lock:
                while not self._queue.empty():
                    try:
                        self._queue.get_nowait()
                    except queue.Empty:
                        break
                
                self._recent_hashes.clear()
                self._hash_to_data.clear()
                
                log_debug(f"{self.name}: Cleared")
        except Exception as e:
            log_error(f"{self.name}: Error clearing", e)
    
    def get_stats(self):
        """
        Get statistics.
        
        Returns:
            Dictionary với stats
        """
        try:
            with self._lock:
                return {
                    "name": self.name,
                    "maxsize": self.maxsize,
                    "current_size": self.qsize(),
                    "utilization": f"{(self.qsize() / self.maxsize * 100) if self.maxsize > 0 else 0:.1f}%",
                    "total_puts": self.total_puts,
                    "total_gets": self.total_gets,
                    "duplicates_dropped": self.duplicates_dropped,
                    "items_evicted": self.items_evicted,
                    "drop_rate": f"{(self.duplicates_dropped / self.total_puts * 100) if self.total_puts > 0 else 0:.1f}%"
                }
        except Exception as e:
            log_error(f"{self.name}: Error getting stats", e)
            return {
                "name": self.name,
                "maxsize": self.maxsize,
                "current_size": 0,
                "utilization": "0%",
                "total_puts": 0,
                "total_gets": 0,
                "duplicates_dropped": 0,
                "items_evicted": 0,
                "drop_rate": "0%"
            }
