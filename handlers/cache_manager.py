"""Translation Cache Manager"""
import os
import sys
import shutil
import time
from collections import OrderedDict

try:
    import chardet
    CHARDET_AVAILABLE = True
except ImportError:
    CHARDET_AVAILABLE = False

try:
    from .sqlite_cache_backend import SQLiteCacheBackend
    SQLITE_AVAILABLE = True
except ImportError:
    SQLITE_AVAILABLE = False

try:
    from modules import get_base_dir, log_error, normalize_for_cache
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
    
    def normalize_for_cache(text, preserve_case=False):
        """Fallback normalization"""
        if not text:
            return ""
        normalized = str(text).strip()
        if not preserve_case:
            normalized = normalized.lower()
        return normalized

def detect_file_encoding(file_path):
    """Phát hiện encoding của file"""
    if CHARDET_AVAILABLE:
        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read(10000)  # Đọc 10KB đầu để detect
                if raw_data:
                    result = chardet.detect(raw_data)
                    detected_encoding = result.get('encoding', 'utf-8')
                    confidence = result.get('confidence', 0)
                    
                    if confidence > 0.7 and detected_encoding:
                        return detected_encoding
        except Exception as e:
            log_error(f"Error detecting encoding: {e}", e)
    
    encodings_to_try = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
    for encoding in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                f.read(1000)
            return encoding
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    # Last resort: UTF-8 với error handling
    return 'utf-8'

def safe_read_file_lines(file_path, encodings=None):
    """
    Đọc file an toàn với nhiều encoding fallback
    Returns: (lines, encoding_used) hoặc (None, None) nếu fail
    """
    if encodings is None:
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
    
    # Thử detect encoding trước
    try:
        detected = detect_file_encoding(file_path)
        if detected and detected not in encodings:
            encodings.insert(0, detected)
    except Exception as e:
        log_error(f"Error detecting encoding for {file_path}", e)
    
    for encoding in encodings:
        try:
            lines = []
            with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        # Validate line có thể decode được
                        line.encode('utf-8')
                        lines.append(line)
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        log_error(f"Skipping invalid line {line_num} in {file_path}")
                        continue
            return lines, encoding
        except (UnicodeDecodeError, UnicodeError) as e:
            log_error(f"Failed to read {file_path} with encoding {encoding}: {e}")
            continue
        except Exception as e:
            log_error(f"Error reading {file_path} with encoding {encoding}: {e}")
            continue
    
    # Nếu tất cả đều fail, thử UTF-8 với errors='replace'
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        log_error(f"Read {file_path} with UTF-8 (errors replaced) - file may be corrupted")
        return lines, 'utf-8'
    except Exception as e:
        log_error(f"Completely failed to read {file_path}: {e}")
        return None, None


class TranslationCacheManager:
    """
    Quản lý translation cache với hybrid backend:
    - SQLite backend (preferred): Fast, indexed, persistent
    - File backend (fallback): Legacy support
    """
    
    def __init__(self, max_size=2000, fuzzy_threshold=0.85, use_sqlite=True):
        """
        Args:
            max_size: Maximum cache size (for file backend LRU)
            fuzzy_threshold: Similarity threshold cho fuzzy matching (0.85 = 85%)
            use_sqlite: True = use SQLite backend (faster), False = use file backend
        """
        self.max_size = max_size
        self.fuzzy_threshold = fuzzy_threshold
        self.fuzzy_enabled = True  # Enable fuzzy matching by default
        
        # Backend selection
        self.use_sqlite = use_sqlite and SQLITE_AVAILABLE
        
        if self.use_sqlite:
            # SQLite backend - faster, indexed
            self.sqlite_backend = SQLiteCacheBackend(max_memory_cache=max_size)
            self.cache = None  # Not used with SQLite
            self.fuzzy_cache = None
        else:
            # File backend - legacy
            self.sqlite_backend = None
            # LRU cache: OrderedDict để track access order
            self.cache = OrderedDict()
            # Fuzzy cache: Track normalized texts cho fuzzy lookup
            self.fuzzy_cache = {}
        
        # File cache paths (for file backend)
        self.cache_file = None
        self._initialize_cache_file()
        
        # Load preset cache
        if not self.use_sqlite:
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
        Tạo cache key với text normalization - format: translator:source:target:normalized_text
        Chuẩn hóa text để tăng cache hit rate (loại bỏ số thứ tự, dấu câu dư thừa, ký tự đặc biệt).
        """
        try:
            # Chuẩn hóa text trước khi tạo key
            normalized_text = normalize_for_cache(text, preserve_case=False)
            
            # Nếu normalize thất bại hoặc text rỗng, dùng text gốc
            if not normalized_text:
                normalized_text = str(text).strip().lower()
            
            return f"{translator_name}:{source_lang}:{target_lang}:{normalized_text}"
        except Exception as e:
            log_error(f"Error making cache key, using fallback", e)
            # Fallback: dùng text gốc
            return f"{translator_name}:{source_lang}:{target_lang}:{str(text).strip().lower()}"
    
    def get(self, text, source_lang, target_lang, translator_name='google'):
        """
        Get translation from cache
        Routes to appropriate backend (SQLite or file-based)
        """
        if self.use_sqlite:
            return self._get_sqlite(text, source_lang, target_lang, translator_name)
        else:
            return self._get_file_based(text, source_lang, target_lang, translator_name)
    
    def _get_sqlite(self, text, source_lang, target_lang, translator_name):
        """Get from SQLite backend"""
        try:
            return self.sqlite_backend.get(text, source_lang, target_lang)
        except Exception as e:
            log_error(f"Error getting from SQLite cache: {e}", e)
            return None
    
    def _get_file_based(self, text, source_lang, target_lang, translator_name='google'):
        """
        Get translation from file-based cache (legacy method)
        """
        cache_key = self._make_cache_key(text, source_lang, target_lang, translator_name)
        
        # Check LRU cache first (exact match)
        if cache_key in self.cache:
            # Move to end (most recently used)
            self.cache.move_to_end(cache_key)
            return self.cache[cache_key]
        
        # Try fuzzy matching nếu enabled
        if self.fuzzy_enabled:
            fuzzy_result = self._fuzzy_lookup(text, source_lang, target_lang, translator_name)
            if fuzzy_result:
                return fuzzy_result
        
        # Check file cache
        if self.cache_file and os.path.exists(self.cache_file):
            try:
                lines, encoding_used = safe_read_file_lines(self.cache_file)
                if lines is None:
                    log_error("Failed to read cache file, skipping file cache lookup")
                    return None
                
                for line in lines:
                    try:
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
                    except Exception as line_error:
                        continue
            except Exception as e:
                log_error("Error reading file cache", e)
        
        return None
    
    def store(self, text, source_lang, target_lang, translated_text, translator_name='google'):
        """
        Store translation in cache
        Routes to appropriate backend (SQLite or file-based)
        """
        if self.use_sqlite:
            return self._store_sqlite(text, source_lang, target_lang, translated_text, translator_name)
        else:
            return self._store_file_based(text, source_lang, target_lang, translated_text, translator_name)
    
    def _store_sqlite(self, text, source_lang, target_lang, translated_text, translator_name):
        """Store in SQLite backend"""
        try:
            self.sqlite_backend.set(text, source_lang, target_lang, translated_text, original_text=text)
        except Exception as e:
            log_error(f"Error storing in SQLite cache: {e}", e)
    
    def _store_file_based(self, text, source_lang, target_lang, translated_text, translator_name='google'):
        """
        Store translation in file-based cache (legacy method)
        """
        cache_key = self._make_cache_key(text, source_lang, target_lang, translator_name)
        
        # Add to LRU cache
        self._add_to_cache(cache_key, translated_text)
        
        # Add to fuzzy cache
        if self.fuzzy_enabled:
            self._add_to_fuzzy_cache(text, cache_key, translated_text)
        
        # Save to file cache
        self._save_to_file_cache(cache_key, translated_text)
    
    def _fuzzy_lookup(self, text, source_lang, target_lang, translator_name='google'):
        """
        Tìm translation với fuzzy matching (Levenshtein-like similarity).
        Return translation nếu tìm thấy text tương tự >= threshold, None otherwise.
        """
        try:
            # Import normalize_for_comparison
            try:
                from modules import normalize_for_comparison
            except ImportError:
                # Fallback: simple normalization
                def normalize_for_comparison(t):
                    return str(t).strip().lower() if t else ""
            
            normalized_text = normalize_for_comparison(text)
            if not normalized_text or len(normalized_text) < 3:
                return None
            
            # Search trong fuzzy_cache
            best_match = None
            best_similarity = 0.0
            
            for cached_normalized, (cached_key, cached_translation) in self.fuzzy_cache.items():
                # Check nếu cùng language pair
                key_parts = cached_key.split(':', 3)
                if len(key_parts) >= 3:
                    if (key_parts[0] == translator_name and 
                        key_parts[1] == source_lang and 
                        key_parts[2] == target_lang):
                        
                        # Calculate similarity
                        similarity = self._calculate_similarity(normalized_text, cached_normalized)
                        
                        if similarity >= self.fuzzy_threshold and similarity > best_similarity:
                            best_similarity = similarity
                            best_match = cached_translation
            
            return best_match
            
        except Exception as e:
            log_error("Error in fuzzy lookup", e)
            return None
    
    def _add_to_fuzzy_cache(self, text, cache_key, translation):
        """Add entry to fuzzy cache."""
        try:
            from modules import normalize_for_comparison
        except ImportError:
            def normalize_for_comparison(t):
                return str(t).strip().lower() if t else ""
        
        try:
            normalized = normalize_for_comparison(text)
            if normalized:
                self.fuzzy_cache[normalized] = (cache_key, translation)
                
                # Limit fuzzy cache size (keep last 500 entries)
                if len(self.fuzzy_cache) > 500:
                    # Remove oldest 100 entries
                    keys_to_remove = list(self.fuzzy_cache.keys())[:100]
                    for k in keys_to_remove:
                        self.fuzzy_cache.pop(k, None)
        except Exception as e:
            log_error("Error adding to fuzzy cache", e)
    
    def _calculate_similarity(self, text1, text2):
        """
        Calculate similarity score giữa 2 texts (Levenshtein-like).
        Returns: float 0.0-1.0
        """
        try:
            if not text1 or not text2:
                return 0.0
            
            # Exact match
            if text1 == text2:
                return 1.0
            
            # Length difference check (quick filter)
            len1, len2 = len(text1), len(text2)
            max_len = max(len1, len2)
            min_len = min(len1, len2)
            
            if max_len == 0:
                return 0.0
            
            # If length difference > 30%, similarity < 70%
            if min_len / max_len < 0.7:
                return min_len / max_len * 0.7
            
            # Simple Levenshtein distance (optimized for short texts)
            # Use Wagner-Fischer algorithm với early termination
            if max_len > 100:
                # For long texts, use character-based matching (faster)
                matches = sum(1 for a, b in zip(text1, text2) if a == b)
                return matches / max_len
            
            # Full Levenshtein for short texts
            d = [[0] * (len2 + 1) for _ in range(len1 + 1)]
            
            for i in range(len1 + 1):
                d[i][0] = i
            for j in range(len2 + 1):
                d[0][j] = j
            
            for i in range(1, len1 + 1):
                for j in range(1, len2 + 1):
                    cost = 0 if text1[i-1] == text2[j-1] else 1
                    d[i][j] = min(
                        d[i-1][j] + 1,      # deletion
                        d[i][j-1] + 1,      # insertion
                        d[i-1][j-1] + cost  # substitution
                    )
            
            # Convert distance to similarity
            distance = d[len1][len2]
            similarity = 1.0 - (distance / max_len)
            
            return max(0.0, similarity)
            
        except Exception as e:
            log_error("Error calculating similarity", e)
            return 0.0
    
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
                lines, encoding_used = safe_read_file_lines(self.cache_file)
                if lines is not None:
                    for line in lines:
                        try:
                            if line.startswith(cache_key + ':==:'):
                                return  # Already exists, skip
                        except Exception:
                            continue
                else:
                    # File bị corrupt, tạo lại file mới
                    log_error(f"Cache file {self.cache_file} is corrupted, will recreate it")
                    try:
                        # Backup file cũ
                        backup_file = self.cache_file + '.backup'
                        if os.path.exists(self.cache_file):
                            shutil.copy2(self.cache_file, backup_file)
                        # Tạo file mới
                        try:
                            # Đảm bảo thư mục tồn tại
                            cache_dir = os.path.dirname(self.cache_file)
                            if cache_dir and not os.path.exists(cache_dir):
                                os.makedirs(cache_dir, exist_ok=True)
                        except (OSError, PermissionError):
                            pass  # Continue anyway
                        
                        with open(self.cache_file, 'w', encoding='utf-8', errors='replace') as f:
                            f.write("# Translation Cache File\n")
                            f.write("# Format: translator:source:target:text:==:translation\n\n")
                            f.flush()
                    except Exception as backup_error:
                        log_error(f"Error backing up corrupted cache file: {backup_error}")
            else:
                # Create file with header
                try:
                    # Đảm bảo thư mục tồn tại
                    cache_dir = os.path.dirname(self.cache_file)
                    if cache_dir and not os.path.exists(cache_dir):
                        os.makedirs(cache_dir, exist_ok=True)
                except (OSError, PermissionError):
                    pass  # Continue anyway
                
                with open(self.cache_file, 'w', encoding='utf-8', errors='replace') as f:
                    f.write("# Translation Cache File\n")
                    f.write("# Format: translator:source:target:text:==:translation\n\n")
                    f.flush()
            
            # Append new entry (luôn dùng UTF-8 khi ghi)
            try:
                with open(self.cache_file, 'a', encoding='utf-8', errors='replace') as f:
                    # Đảm bảo cache_key và translated_text là UTF-8 valid
                    try:
                        safe_key = cache_key.encode('utf-8', errors='replace').decode('utf-8')
                        safe_value = translated_text.encode('utf-8', errors='replace').decode('utf-8')
                        f.write(f"{safe_key}:==:{safe_value}\n")
                        f.flush()  # Force write to disk
                    except Exception as encode_error:
                        log_error(f"Error encoding cache entry: {encode_error}")
                        # Thử ghi với ASCII fallback
                        try:
                            safe_key = cache_key.encode('ascii', errors='replace').decode('ascii')
                            safe_value = translated_text.encode('ascii', errors='replace').decode('ascii')
                            f.write(f"{safe_key}:==:{safe_value}\n")
                            f.flush()
                        except Exception:
                            log_error("Completely failed to save cache entry")
            except (IOError, PermissionError, OSError) as file_err:
                log_error(f"Error writing to cache file: {file_err}")
                
        except Exception as e:
            log_error("Error saving to file cache", e)
    
    def clear(self):
        """Clear all caches"""
        if self.use_sqlite:
            try:
                self.sqlite_backend.clear()
            except Exception as e:
                log_error("Error clearing SQLite cache", e)
        else:
            self.cache.clear()
            if self.cache_file and os.path.exists(self.cache_file):
                try:
                    with open(self.cache_file, 'w', encoding='utf-8', errors='replace') as f:
                        f.write("# Translation Cache File\n")
                        f.write("# Format: translator:source:target:text:==:translation\n\n")
                        f.flush()
                except (IOError, PermissionError, OSError) as e:
                    log_error("Error clearing file cache", e)
    
    def get_size(self):
        """Get current cache size"""
        if self.use_sqlite:
            try:
                stats = self.sqlite_backend.get_stats()
                return stats.get('total_entries', 0)
            except:
                return 0
        else:
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
            lines, encoding_used = safe_read_file_lines(preset_cache_file)
            if lines is None:
                log_error("Failed to read preset cache file, skipping preset cache loading")
                return
            
            for line in lines:
                try:
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
                except Exception as line_error:
                    continue
            
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

