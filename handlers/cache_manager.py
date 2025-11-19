"""
Cache Manager - quản lý translation cache
"""
import os
import sys
import shutil
import time
from collections import OrderedDict

def get_base_dir():
    """Lấy thư mục gốc để lưu cache file
    Hỗ trợ cả chạy từ Python script và frozen executable (PyInstaller)
    """
    try:
        if getattr(sys, 'frozen', False):
            # Chạy từ executable (PyInstaller)
            # sys.executable trỏ đến file .exe
            base_dir = os.path.dirname(sys.executable)
        else:
            # Chạy từ Python script
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Đảm bảo đường dẫn được chuẩn hóa
        return os.path.normpath(base_dir)
    except Exception:
        # Fallback: sử dụng thư mục hiện tại
        return os.path.normpath(os.getcwd())

def log_error(msg, exception=None):
    """Simple error logging - fallback nếu không có logger"""
    try:
        import traceback
        from datetime import datetime
        
        base_dir = get_base_dir()
        error_log_file = os.path.join(base_dir, "error_log.txt")
        with open(error_log_file, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"\n[{timestamp}] {msg}\n")
            if exception:
                f.write(f"Exception: {str(exception)}\n")
                f.write(f"Traceback:\n{traceback.format_exc()}\n")
    except Exception:
        pass


class TranslationCacheManager:
    """Quản lý translation cache với LRU và file cache"""
    
    def __init__(self, max_size=2000):
        """
        Args:
            max_size: Maximum cache size (LRU eviction)
        """
        self.max_size = max_size
        # LRU cache: OrderedDict để track access order
        self.cache = OrderedDict()
        # File cache paths
        self.cache_file = None
        self._initialize_cache_file()
        # Load preset cache khi khởi động
        self._load_preset_cache()
    
    def _initialize_cache_file(self):
        """Initialize cache file path - hỗ trợ cả exe và script"""
        try:
            base_dir = get_base_dir()
            self.cache_file = os.path.join(base_dir, "translation_cache.txt")
        except Exception as e:
            log_error("Error initializing cache file path", e)
            # Fallback: lưu trong thư mục hiện tại
            self.cache_file = os.path.join(os.getcwd(), "translation_cache.txt")
    
    def _make_cache_key(self, text, source_lang, target_lang, translator_name='google'):
        """
        Tạo cache key - format: translator:source:target:text
        """
        return f"{translator_name}:{source_lang}:{target_lang}:{text}"
    
    def get(self, text, source_lang, target_lang, translator_name='google'):
        """
        Get translation from cache (LRU + file)
        """
        cache_key = self._make_cache_key(text, source_lang, target_lang, translator_name)
        
        # Check LRU cache first
        if cache_key in self.cache:
            # Move to end (most recently used)
            self.cache.move_to_end(cache_key)
            return self.cache[cache_key]
        
        # Check file cache
        if self.cache_file and os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#') or ':==:' not in line:
                            continue
                        
                        parts = line.split(':==:', 1)
                        if len(parts) == 2:
                            key_from_file = parts[0]
                            value_from_file = parts[1]
                            
                            if key_from_file == cache_key:
                                # Found in file cache, add to LRU
                                self._add_to_cache(cache_key, value_from_file)
                                return value_from_file
            except Exception as e:
                log_error("Error reading file cache", e)
        
        return None
    
    def store(self, text, source_lang, target_lang, translated_text, translator_name='google'):
        """
        Store translation in cache (LRU + file)
        """
        cache_key = self._make_cache_key(text, source_lang, target_lang, translator_name)
        
        # Add to LRU cache
        self._add_to_cache(cache_key, translated_text)
        
        # Save to file cache
        self._save_to_file_cache(cache_key, translated_text)
    
    def _add_to_cache(self, key, value):
        """Add to LRU cache with size limit"""
        if key in self.cache:
            # Update existing
            self.cache.move_to_end(key)
            self.cache[key] = value
        else:
            # Add new
            self.cache[key] = value
            
            # Evict oldest if over limit
            if len(self.cache) > self.max_size:
                # Remove oldest (first item)
                self.cache.popitem(last=False)
    
    def _save_to_file_cache(self, cache_key, translated_text):
        """Save to file cache"""
        if not self.cache_file:
            return
        
        try:
            # Check if entry already exists
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith(cache_key + ':==:'):
                            return  # Already exists, skip
            else:
                # Create file with header
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    f.write("# Translation Cache File\n")
                    f.write("# Format: translator:source:target:text:==:translation\n\n")
            
            # Append new entry
            with open(self.cache_file, 'a', encoding='utf-8') as f:
                f.write(f"{cache_key}:==:{translated_text}\n")
                
        except Exception as e:
            log_error("Error saving to file cache", e)
    
    def clear(self):
        """Clear all caches"""
        self.cache.clear()
        if self.cache_file and os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    f.write("# Translation Cache File\n")
                    f.write("# Format: translator:source:target:text:==:translation\n\n")
            except Exception as e:
                log_error("Error clearing file cache", e)
    
    def get_size(self):
        """Get current cache size"""
        return len(self.cache)
    
    def _load_preset_cache(self):
        """Load preset cache từ file preset_cache.txt khi khởi động"""
        try:
            base_dir = get_base_dir()
            preset_cache_file = os.path.join(base_dir, "preset_cache.txt")
            
            # Nếu file không tồn tại, thử extract từ bundled data (nếu chạy từ exe)
            if not os.path.exists(preset_cache_file):
                try:
                    # Kiểm tra nếu chạy từ PyInstaller bundle
                    if getattr(sys, 'frozen', False):
                        # PyInstaller tạo thư mục _MEIPASS chứa bundled files
                        bundle_dir = sys._MEIPASS
                        bundled_preset = os.path.join(bundle_dir, "preset_cache.txt")
                        
                        if os.path.exists(bundled_preset):
                            # Copy từ bundle ra thư mục exe
                            shutil.copy2(bundled_preset, preset_cache_file)
                except Exception as e:
                    log_error("Error extracting preset_cache.txt from bundle", e)
                    # Nếu không extract được, không load preset cache
                    return
            
            if not os.path.exists(preset_cache_file):
                # File preset cache không tồn tại, không cần load
                return
            
            loaded_count = 0
            with open(preset_cache_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Bỏ qua comment và dòng trống
                    if not line or line.startswith('#'):
                        continue
                    
                    # Parse format: translator:source:target:text:==:translation
                    if ':==:' not in line:
                        continue
                    
                    parts = line.split(':==:', 1)
                    if len(parts) != 2:
                        continue
                    
                    cache_key = parts[0].strip()
                    translation = parts[1].strip()
                    
                    if not cache_key or not translation:
                        continue
                    
                    # Parse cache key để lấy translator, source, target, text
                    # Format: translator:source:target:text
                    key_parts = cache_key.split(':', 3)
                    if len(key_parts) < 4:
                        continue
                    
                    translator_name = key_parts[0]
                    source_lang = key_parts[1]
                    target_lang = key_parts[2]
                    text = key_parts[3] if len(key_parts) > 3 else ''
                    
                    if not text:
                        continue
                    
                    # Thêm vào LRU cache (không ghi vào file cache để tránh duplicate)
                    # Chỉ thêm nếu chưa có trong cache
                    if cache_key not in self.cache:
                        self._add_to_cache(cache_key, translation)
                        loaded_count += 1
            
            # Log thông tin load preset cache (chỉ khi có entries)
            if loaded_count > 0:
                try:
                    # Ghi vào error_log.txt nhưng với prefix INFO
                    base_dir = get_base_dir()
                    error_log_file = os.path.join(base_dir, "error_log.txt")
                    from datetime import datetime
                    with open(error_log_file, 'a', encoding='utf-8') as f:
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        f.write(f"\n[{timestamp}] [INFO] Loaded {loaded_count} preset cache entries from preset_cache.txt\n")
                except Exception:
                    pass  # Không cần log nếu không ghi được
        except Exception as e:
            log_error("Error loading preset cache", e)

