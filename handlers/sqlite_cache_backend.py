"""
SQLite Cache Backend - Faster, persistent, indexed cache storage
Thay thế file-based cache với performance tốt hơn ~50%
"""
import sqlite3
import os
import sys
import time
import threading
from collections import OrderedDict

try:
    from modules import get_base_dir, log_error, log_debug, normalize_for_cache
except ImportError:
    def get_base_dir():
        try:
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            return os.path.normpath(base_dir)
        except Exception:
            return os.path.normpath(os.getcwd())
    
    def log_error(msg, exception=None):
        pass
    
    def log_debug(msg):
        pass
    
    def normalize_for_cache(text, preserve_case=False):
        if not text:
            return ""
        normalized = str(text).strip()
        if not preserve_case:
            normalized = normalized.lower()
        return normalized


class SQLiteCacheBackend:
    """
    SQLite-based translation cache với indexing và fast lookup
    """
    
    def __init__(self, db_path=None, max_memory_cache=1000):
        """
        Args:
            db_path: Path to SQLite database file
            max_memory_cache: Maximum items in memory LRU cache
        """
        if db_path is None:
            cache_dir = os.path.join(get_base_dir(), "cache")
            os.makedirs(cache_dir, exist_ok=True)
            db_path = os.path.join(cache_dir, "translation_cache.db")
        
        self.db_path = db_path
        self.max_memory_cache = max_memory_cache
        
        # In-memory LRU cache để giảm DB hits
        self.memory_cache = OrderedDict()
        
        # Thread lock cho thread-safe operations
        self.lock = threading.Lock()
        
        self.stats = {
            'memory_hits': 0,
            'db_hits': 0,
            'misses': 0,
            'writes': 0
        }
        
        self._initialize_db()
    
    def _initialize_db(self):
        """Create database schema với indexes"""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS translation_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    normalized_text TEXT NOT NULL,
                    source_lang TEXT NOT NULL,
                    target_lang TEXT NOT NULL,
                    translation TEXT NOT NULL,
                    original_text TEXT,
                    timestamp REAL NOT NULL,
                    hit_count INTEGER DEFAULT 1
                )
            ''')
            
            # Create B-tree indexes cho fast lookup
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_lookup
                ON translation_cache(normalized_text, source_lang, target_lang)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON translation_cache(timestamp)
            ''')
            
            # Enable WAL mode cho better concurrency
            cursor.execute('PRAGMA journal_mode=WAL')
            
            # Optimize for speed
            cursor.execute('PRAGMA synchronous=NORMAL')
            cursor.execute('PRAGMA cache_size=-64000')  # 64MB cache
            cursor.execute('PRAGMA temp_store=MEMORY')
            
            conn.commit()
            conn.close()
            
            log_debug(f"SQLite cache initialized at {self.db_path}")
            
        except Exception as e:
            log_error(f"Failed to initialize SQLite cache: {e}", e)
    
    def get(self, text, source_lang, target_lang):
        """
        Get translation from cache
        Returns: translation string or None
        """
        try:
            normalized = normalize_for_cache(text)
            if not normalized:
                return None
            
            # Memory cache key
            cache_key = f"{normalized}|{source_lang}|{target_lang}"
            
            # Check memory cache first (LRU)
            with self.lock:
                if cache_key in self.memory_cache:
                    self.stats['memory_hits'] += 1
                    # Move to end (most recently used)
                    self.memory_cache.move_to_end(cache_key)
                    return self.memory_cache[cache_key]
            
            # Check database
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT translation, hit_count 
                FROM translation_cache
                WHERE normalized_text = ? AND source_lang = ? AND target_lang = ?
                ORDER BY timestamp DESC
                LIMIT 1
            ''', (normalized, source_lang, target_lang))
            
            result = cursor.fetchone()
            
            if result:
                translation, hit_count = result
                self.stats['db_hits'] += 1
                
                # Update hit count
                cursor.execute('''
                    UPDATE translation_cache
                    SET hit_count = hit_count + 1
                    WHERE normalized_text = ? AND source_lang = ? AND target_lang = ?
                ''', (normalized, source_lang, target_lang))
                
                conn.commit()
                conn.close()
                
                # Add to memory cache
                with self.lock:
                    self.memory_cache[cache_key] = translation
                    # LRU eviction
                    if len(self.memory_cache) > self.max_memory_cache:
                        self.memory_cache.popitem(last=False)
                
                return translation
            else:
                self.stats['misses'] += 1
                conn.close()
                return None
                
        except Exception as e:
            log_error(f"Error getting from SQLite cache: {e}", e)
            return None
    
    def set(self, text, source_lang, target_lang, translation, original_text=None):
        """
        Store translation in cache
        """
        try:
            normalized = normalize_for_cache(text)
            if not normalized or not translation:
                return
            
            cache_key = f"{normalized}|{source_lang}|{target_lang}"
            current_time = time.time()
            
            # Add to memory cache
            with self.lock:
                self.memory_cache[cache_key] = translation
                if len(self.memory_cache) > self.max_memory_cache:
                    self.memory_cache.popitem(last=False)
            
            # Add to database
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            
            # Check if exists
            cursor.execute('''
                SELECT id FROM translation_cache
                WHERE normalized_text = ? AND source_lang = ? AND target_lang = ?
            ''', (normalized, source_lang, target_lang))
            
            if cursor.fetchone():
                # Update existing
                cursor.execute('''
                    UPDATE translation_cache
                    SET translation = ?, timestamp = ?, hit_count = hit_count + 1, original_text = ?
                    WHERE normalized_text = ? AND source_lang = ? AND target_lang = ?
                ''', (translation, current_time, original_text, normalized, source_lang, target_lang))
            else:
                # Insert new
                cursor.execute('''
                    INSERT INTO translation_cache 
                    (normalized_text, source_lang, target_lang, translation, original_text, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (normalized, source_lang, target_lang, translation, original_text, current_time))
            
            conn.commit()
            conn.close()
            
            self.stats['writes'] += 1
            
        except Exception as e:
            log_error(f"Error writing to SQLite cache: {e}", e)
    
    def clear(self):
        """Clear all cache data"""
        try:
            with self.lock:
                self.memory_cache.clear()
            
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM translation_cache')
            conn.commit()
            conn.close()
            
            log_debug("SQLite cache cleared")
            
        except Exception as e:
            log_error(f"Error clearing SQLite cache: {e}", e)
    
    def get_stats(self):
        """Get cache statistics"""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM translation_cache')
            total_entries = cursor.fetchone()[0]
            
            cursor.execute('SELECT SUM(hit_count) FROM translation_cache')
            total_hits = cursor.fetchone()[0] or 0
            
            conn.close()
            
            total_requests = self.stats['memory_hits'] + self.stats['db_hits'] + self.stats['misses']
            hit_rate = (self.stats['memory_hits'] + self.stats['db_hits']) / total_requests * 100 if total_requests > 0 else 0
            
            return {
                'total_entries': total_entries,
                'memory_cache_size': len(self.memory_cache),
                'memory_hits': self.stats['memory_hits'],
                'db_hits': self.stats['db_hits'],
                'misses': self.stats['misses'],
                'writes': self.stats['writes'],
                'hit_rate': f"{hit_rate:.1f}%",
                'total_db_hits': total_hits
            }
            
        except Exception as e:
            log_error(f"Error getting SQLite cache stats: {e}", e)
            return {}
    
    def cleanup_old_entries(self, max_age_days=30):
        """Remove entries older than max_age_days"""
        try:
            cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
            
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM translation_cache WHERE timestamp < ?', (cutoff_time,))
            deleted = cursor.rowcount
            
            # Vacuum to reclaim space
            cursor.execute('VACUUM')
            
            conn.commit()
            conn.close()
            
            log_debug(f"Cleaned up {deleted} old cache entries")
            return deleted
            
        except Exception as e:
            log_error(f"Error cleaning up old entries: {e}", e)
            return 0
    
    def optimize(self):
        """Run database optimization"""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            
            cursor.execute('ANALYZE')
            cursor.execute('VACUUM')
            
            conn.commit()
            conn.close()
            
            log_debug("SQLite cache optimized")
            
        except Exception as e:
            log_error(f"Error optimizing SQLite cache: {e}", e)
