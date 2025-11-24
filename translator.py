"""
Công cụ dịch màn hình thời gian thực
Tác giả: trchicuong
"""

import os
import sys

# Fix scaling issues on Windows with high DPI displays
if os.name == 'nt':  # Windows only
    try:
        import ctypes
        # Set process DPI awareness (Windows 8.1+)
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            # Fallback for Windows 8 and older
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception as e:
            # log_error chưa được định nghĩa ở đây, sẽ log sau khi import
            try:
                import traceback
                from datetime import datetime
                error_log_file = os.path.join(os.getcwd(), "error_log.txt")
                with open(error_log_file, 'a', encoding='utf-8', errors='replace') as f:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"\n[{timestamp}] Failed to set DPI awareness (fallback also failed)\n")
                    f.write(f"Exception: {str(e)}\n")
                    f.write(f"Traceback:\n{traceback.format_exc()}\n")
                    f.write("-" * 80 + "\n")
            except Exception:
                pass  # If all fails, continue without DPI awareness

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import json
import shutil
import re
import traceback
from datetime import datetime
from PIL import Image, ImageTk
import mss
import numpy as np
import pytesseract
from deep_translator import GoogleTranslator
import cv2
import hashlib
import random
import queue
from concurrent.futures import ThreadPoolExecutor
import warnings

# Suppress PyTorch/EasyOCR warnings
warnings.filterwarnings('ignore', category=UserWarning, module='torch')
warnings.filterwarnings('ignore', message='.*Using CPU.*')
warnings.filterwarnings('ignore', message='.*pin_memory.*')

# DeepL API availability check
DEEPL_API_AVAILABLE = False
try:
    import deepl
    DEEPL_API_AVAILABLE = True
except ImportError:
    pass

# EasyOCR availability check
EASYOCR_AVAILABLE = False
try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    pass

# Import modules from modules package
from modules import (
    log_error,
    log_debug,
    get_base_dir,
    NetworkCircuitBreaker,
    post_process_ocr_text_general,
    remove_text_after_last_punctuation_mark,
    post_process_ocr_for_game_subtitle,
    UnifiedTranslationCache,
    split_into_sentences,
    translate_batch_google,
    translate_batch_deepl,
    should_use_batch_translation,
    DeepLContextManager,
    should_translate_text,
    is_valid_dialogue_text
)

# Handlers cho free OCR engines
try:
    from handlers import TesseractOCRHandler, EasyOCRHandler, TranslationCacheManager
    HANDLERS_AVAILABLE = True
except ImportError:
    HANDLERS_AVAILABLE = False
    TesseractOCRHandler = None
    EasyOCRHandler = None
    TranslationCacheManager = None

def get_actual_screen_size():
    """
    Lấy kích thước màn hình thực tế, xử lý DPI scaling đúng cách.
    
    Returns:
        tuple: (width, height) của màn hình chính
    """
    if os.name == 'nt':  # Windows
        try:
            import ctypes
            # Get actual screen dimensions considering DPI
            user32 = ctypes.windll.user32
            # SM_CXSCREEN = 0, SM_CYSCREEN = 1 (primary monitor)
            width = user32.GetSystemMetrics(0)
            height = user32.GetSystemMetrics(1)
            return (width, height)
        except Exception as e:
            log_error("Error getting screen size from GetSystemMetrics", e)
    
    # Fallback: dùng mss (cross-platform và reliable)
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Primary monitor
            return (monitor['width'], monitor['height'])
    except Exception as e:
        log_error("Error getting screen size from mss", e)
    
    # Last resort: tkinter (có thể không chính xác với DPI)
    try:
        root = tk.Tk()
        root.withdraw()
        width = root.winfo_screenwidth()
        height = root.winfo_screenheight()
        root.destroy()
        return (width, height)
    except Exception as e:
        log_error("Error getting screen size from tkinter", e)
        # Default fallback
        return (1920, 1080)

def get_all_monitors_bounds():
    """
    Lấy bounds của tất cả monitors (hỗ trợ multi-monitor setup)
    
    Returns:
        dict: Monitor bounds từ mss
    """
    try:
        with mss.mss() as sct:
            return sct.monitors
    except Exception as e:
        log_error("Error getting monitor bounds from mss", e)
        return None

def find_tesseract(custom_path=None):
    """Tự động tìm đường dẫn Tesseract OCR - hỗ trợ Windows, Linux, macOS"""
    if custom_path:
        # Chuẩn hóa đường dẫn
        custom_path = os.path.normpath(custom_path)
        if os.path.isfile(custom_path):
            return os.path.normpath(custom_path)
        elif os.path.isdir(custom_path):
            # Windows: tesseract.exe, Linux/Mac: tesseract
            if os.name == 'nt':
                tesseract_exe = os.path.join(custom_path, 'tesseract.exe')
            else:
                tesseract_exe = os.path.join(custom_path, 'tesseract')
            if os.path.exists(tesseract_exe):
                return os.path.normpath(tesseract_exe)
    
    # Thử tìm trong PATH trước (hoạt động trên mọi OS)
    # shutil.which() tự động tìm trong PATH environment variable
    tesseract_cmd = shutil.which('tesseract')
    if tesseract_cmd:
        return os.path.normpath(tesseract_cmd)
    
    # Tìm trong các đường dẫn mặc định theo OS
    if os.name == 'nt':  # Windows
        windows_paths = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
            r'C:\Tesseract-OCR\tesseract.exe',
        ]
        for path in windows_paths:
            if os.path.exists(path):
                return os.path.normpath(path)
    elif sys.platform == 'darwin':  # macOS
        mac_paths = [
            '/usr/local/bin/tesseract',
            '/opt/homebrew/bin/tesseract',
            '/usr/bin/tesseract',
        ]
        for path in mac_paths:
            if os.path.exists(path):
                return os.path.normpath(path)
    else:  # Linux và các OS khác
        linux_paths = [
            '/usr/bin/tesseract',
            '/usr/local/bin/tesseract',
            '/opt/tesseract/bin/tesseract',
        ]
        for path in linux_paths:
            if os.path.exists(path):
                return os.path.normpath(path)
    
    return None

custom_tesseract_path = None


class ScreenTranslator:
    """Class chính quản lý UI, OCR, dịch và overlay window"""
    
    def __init__(self, root):
        """Khởi tạo công cụ"""
        self.root = root
        self.root.title("Công Cụ Dịch Màn Hình Thời Gian Thực")
        
        # Responsive window size based on screen dimensions
        screen_width, screen_height = get_actual_screen_size()
        
        # Calculate appropriate window size (max 600x800, but scale down for small screens)
        window_width = min(600, int(screen_width * 0.4))  # Max 40% of screen width
        window_height = min(800, int(screen_height * 0.7))  # Max 70% of screen height
        
        # Minimum size to ensure UI is usable
        window_width = max(500, window_width)
        window_height = max(600, window_height)
        
        self.root.geometry(f"{window_width}x{window_height}")
        self.root.minsize(500, 600)  # Set minimum size
        self.root.resizable(True, True)
        
        self.author = "trchicuong"
        self.config_file = os.path.join(get_base_dir(), "config.json")
        self.capture_region = None
        self.is_capturing = False
        self.capture_thread = None
        self.overlay_window = None
        self.shadow_label = None
        self.translator = GoogleTranslator(source='auto', target='vi')
        self.custom_tesseract_path = None
        
        # Khởi tạo source_language TRƯỚC khi tạo handlers
        self.source_language = "eng"
        self.target_language = "vi"
        
        # OCR Engine selection
        self.ocr_engine = "tesseract"  # Default: tesseract hoặc easyocr
        self.EASYOCR_AVAILABLE = EASYOCR_AVAILABLE
        self.HANDLERS_AVAILABLE = HANDLERS_AVAILABLE
        
        # EasyOCR GPU option (None = auto-detect, True = force GPU, False = force CPU)
        self.easyocr_use_gpu = None  # Default: auto-detect
        
        # EasyOCR Multi-scale option (True = enable, False = disable)
        self.easyocr_multi_scale = False  # Default: disabled (tối ưu tốc độ)
        
        # Tesseract options
        self.tesseract_multi_scale = False  # Default: disabled (tối ưu tốc độ)
        self.tesseract_text_region_detection = False  # Default: disabled (tốn thời gian)
        
        # OCR Handlers (nếu có) - cần source_language đã được khởi tạo
        # Note: easyocr_handler sẽ được khởi tạo lại khi cần với GPU option
        if HANDLERS_AVAILABLE:
            self.tesseract_handler = TesseractOCRHandler(
                source_language=self.source_language,
                enable_multi_scale=self.tesseract_multi_scale,
                enable_text_region_detection=self.tesseract_text_region_detection
            )
            self.easyocr_handler = None  # Sẽ khởi tạo khi cần với GPU option
        else:
            self.tesseract_handler = None
            self.easyocr_handler = None
            # Fallback: giữ code cũ
            self.easyocr_reader = None
            self.last_easyocr_call_time = 0.0
            self.easyocr_min_interval = 0.6  # Balance cho cấu hình tầm trung
        
        # DeepL API support
        self.DEEPL_API_AVAILABLE = DEEPL_API_AVAILABLE
        self.deepl_api_client = None
        self.use_deepl = False  # Flag to use DeepL instead of Google
        self.deepl_api_key = ""  # DeepL API key
        self.deepl_context_window_size = 2  # Default: 2 previous subtitles (0-3)
        
        # DeepL Context Manager (will be updated after load_config if config exists)
        self.deepl_context_manager = DeepLContextManager(max_context_size=self.deepl_context_window_size)
        
        # Circuit breaker for API calls (network degradation detection)
        self.google_translation_circuit_breaker = NetworkCircuitBreaker()
        self.deepl_translation_circuit_breaker = NetworkCircuitBreaker()
        
        self.overlay_drag_start_x = 0
        self.overlay_drag_start_y = 0
        self.update_interval = 0.18  # Balance: 0.18s cho cấu hình tầm trung
        
        self.overlay_font_size = 15
        self.overlay_font_family = "Arial"
        self.overlay_font_weight = "normal"
        self.overlay_bg_color = "#1a1a1a"
        self.overlay_text_color = "#ffffff"
        self.overlay_original_color = "#cccccc"
        self.overlay_transparency = 0.88
        self.overlay_width = 500
        self.overlay_height = 280
        self.overlay_show_original = True
        self.overlay_keep_history = False  # Ghi lại lịch sử dịch (append thay vì replace)
        self.overlay_text_align = "left"
        self.overlay_line_spacing = 1.3
        self.overlay_padding_x = 18
        self.overlay_padding_y = 18
        self.overlay_border_width = 0
        self.overlay_border_color = "#ffffff"
        self.overlay_text_shadow = False
        self.overlay_word_wrap = True
        
        self.text_history = []
        self.history_size = 5  # Tăng để track context tốt hơn
        self.performance_mode = "balanced"
        
        # Unified Translation Cache (primary cache)
        self.unified_cache = UnifiedTranslationCache(max_size=2000)
        
        # Translation Cache Manager (nếu có handlers) - giữ để backward compatibility
        if HANDLERS_AVAILABLE and TranslationCacheManager:
            self.cache_manager = TranslationCacheManager(max_size=2000)
            self.translation_cache = {}  # Giữ để backward compatibility
        else:
            self.cache_manager = None
            self.translation_cache = {}
        self.max_cache_size = 2000  # Tăng cache cho long sessions
        self.pending_translation = None
        self.translation_lock = threading.Lock()
        
        # Text stability và similarity tracking
        self.text_stability_counter = 0
        self.previous_text = ""
        self.similar_texts_count = 0
        self.prev_ocr_text = ""
        self.last_processed_subtitle = None
        self.last_successful_translation_time = 0.0
        self.stable_threshold = 2  # Số lần text phải giống nhau để coi là stable (2 = cần ít nhất 2 lần đọc giống nhau để giảm dịch trùng)
        self.min_translation_interval = 0.08  # Balance: không quá nhanh gây lag máy yếu
        
        # Threading infrastructure
        self.is_running = False  # Flag để control threads
        self.ocr_queue = queue.Queue(maxsize=5)  # Queue để truyền ảnh từ capture sang OCR thread
        self.translation_queue = queue.Queue(maxsize=10)  # Queue để truyền text (legacy, ít dùng)
        
        # Thread pools cho async processing
        # EasyOCR: giảm workers để giảm CPU (rất nặng)
        # Tesseract: có thể nhiều workers hơn (nhẹ hơn)
        # Sẽ được điều chỉnh trong start_translation() dựa trên OCR engine
        self.ocr_thread_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="OCR")
        self.translation_thread_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="Translation")
        
        # Sequence tracking cho chronological ordering
        self.batch_sequence_counter = 0
        self.translation_sequence_counter = 0
        self.last_displayed_batch_sequence = 0
        self.last_displayed_translation_sequence = 0
        self.active_ocr_calls = set()
        self.active_translation_calls = set()
        # Tăng concurrent calls để xử lý nhanh hơn
        self.max_concurrent_ocr_calls = 8
        # Giảm concurrent translation calls để tránh quá tải với text dài
        self.max_concurrent_translation_calls = 3
        
        # Giới hạn độ dài text để tránh xử lý quá tải (tăng để giữ độ chính xác)
        self.max_text_length_for_translation = 400  # Ký tự (tăng từ 300)
        self.max_text_length_hard_limit = 800  # Hard limit - skip nếu vượt quá (tăng từ 500)
        
        # Long session optimization: periodic cleanup
        self.last_cleanup_time = time.time()
        self.cleanup_interval = 300  # Cleanup mỗi 5 phút
        
        # Cache preprocessing mode và tesseract params
        self.cached_prep_mode = None
        self.cached_tess_params = None
        
        # Adaptive scan interval - balance cho cấu hình tầm trung
        # 250ms = 4 FPS, phù hợp với đa số máy (i5 gen10+, GTX 1650+)
        self.base_scan_interval = 250  # Balance giữa 200ms (nhanh) và 300ms (chậm)
        self.current_scan_interval = self.base_scan_interval
        self.overload_detected = False  # Track OCR overload state
        
        # Threads
        self.capture_thread = None
        self.ocr_thread = None
        self.translation_thread = None
        
        self.overlay_position_x = None
        self.overlay_position_y = None
        self.overlay_locked = False
        
        self.load_config()
        self.create_ui()
        
        # Sync UI với giá trị đã load từ config
        if hasattr(self, 'ocr_engine_var'):
            self.ocr_engine_var.set(self.ocr_engine)
            self.update_ocr_engine_ui()
        
        if hasattr(self, 'translation_service_var'):
            # Sync translation service với giá trị đã load
            if self.use_deepl:
                self.translation_service_var.set("deepl")
            else:
                self.translation_service_var.set("google")
        
        # Sync DeepL context window size với giá trị đã load
        if hasattr(self, 'deepl_context_window_var'):
            self.deepl_context_window_var.set(self.deepl_context_window_size)
        
        # Khởi tạo OCR engine nếu cần
        if self.ocr_engine == "easyocr" and self.EASYOCR_AVAILABLE:
            # Khởi tạo handler với GPU option nếu dùng handlers
            if HANDLERS_AVAILABLE and not self.easyocr_handler:
                try:
                    self.easyocr_handler = EasyOCRHandler(
                        source_language=self.source_language,
                        use_gpu=self.easyocr_use_gpu,
                        enable_multi_scale=self.easyocr_multi_scale
                    )
                except Exception as e:
                    log_error("Lỗi khởi tạo EasyOCR handler từ config", e)
                    self.log(f"Lỗi khởi tạo EasyOCR handler: {e}. Sẽ dùng fallback reader.")
                    # Nếu handler khởi tạo thất bại, fallback về reader cũ
                    self.easyocr_handler = None
                    self.initialize_easyocr_reader()
            # Hoặc khởi tạo reader trực tiếp nếu không dùng handlers
            elif not HANDLERS_AVAILABLE:
                self.initialize_easyocr_reader()
        
        # Khởi tạo DeepL client nếu đang dùng DeepL
        if self.use_deepl and self.DEEPL_API_AVAILABLE and self.deepl_api_key:
            try:
                import deepl
                self.deepl_api_client = deepl.Translator(self.deepl_api_key)
                self.log("Đã khởi tạo DeepL client từ config")
            except Exception as e:
                log_error("Lỗi khởi tạo DeepL từ config", e)
                self.use_deepl = False
                if hasattr(self, 'translation_service_var'):
                    self.translation_service_var.set("google")
        
        # Try to find Tesseract automatically (don't verify yet to avoid startup errors)
        tesseract_path = find_tesseract(self.custom_tesseract_path)
        if tesseract_path:
            # Chuẩn hóa đường dẫn
            tesseract_path = os.path.normpath(tesseract_path)
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
            self.custom_tesseract_path = tesseract_path
            self.log(f"Tìm thấy Tesseract tại: {tesseract_path}")
            if hasattr(self, 'tesseract_path_label'):
                self.tesseract_path_label.config(
                    text=f"Đường dẫn: {tesseract_path}",
                    fg="green"
                )
        else:
            self.log("Cảnh báo: Chưa tìm thấy Tesseract OCR. Nếu sử dụng Tesseract, vui lòng dùng nút 'Duyệt' để chọn đường dẫn.")
            if hasattr(self, 'tesseract_path_label'):
                self.tesseract_path_label.config(
                    text="Chưa cấu hình",
                    fg="orange"
                )
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def update_adaptive_scan_interval(self):
        """
        Điều chỉnh scan interval dựa trên OCR load để tránh bottleneck
        Tăng scan interval khi có quá nhiều active OCR calls
        """
        try:
            # Count active OCR calls
            active_ocr_count = len(self.active_ocr_calls)
            
            # Base interval từ user setting (ms)
            base_interval = int(self.update_interval * 1000)
            
            # Update base_scan_interval nếu user thay đổi setting
            if base_interval != self.base_scan_interval:
                self.base_scan_interval = base_interval
            
            # Adaptive logic: nếu active OCR calls > 5, tăng scan interval lên 150%
            if active_ocr_count > 5:
                if not self.overload_detected:
                    # First detection of overload
                    self.current_scan_interval = int(base_interval * 1.5)  # 150%
                    self.overload_detected = True
                    log_error(f"ADAPTIVE: OCR overload detected ({active_ocr_count} active calls), increasing scan interval to {self.current_scan_interval}ms")
                else:
                    # Already in overload state, maintain increased interval
                    pass  # Keep current_scan_interval unchanged
            elif active_ocr_count < 5:
                if self.overload_detected:
                    # Load has decreased, return to normal
                    self.current_scan_interval = base_interval
                    self.overload_detected = False
                    log_error(f"ADAPTIVE: OCR load normalized ({active_ocr_count} active calls), returning scan interval to {self.current_scan_interval}ms")
                else:
                    # Normal state, no change needed
                    self.current_scan_interval = base_interval
        except Exception as e:
            # Fallback to base interval on error
            self.current_scan_interval = self.base_scan_interval
            log_error("Error in update_adaptive_scan_interval", e)
    
    def verify_tesseract(self, silent=False):
        """Kiểm tra Tesseract OCR đã được cài đặt và có thể truy cập
        
        Args:
            silent: Nếu True, không log error (dùng cho background checks)
        
        Returns:
            bool: True nếu Tesseract available, False otherwise
        """
        try:
            version = pytesseract.get_tesseract_version()
            return True
        except pytesseract.TesseractNotFoundError:
            if not silent:
                self.log("Lỗi: Tesseract OCR chưa được cài đặt hoặc chưa cấu hình đường dẫn.")
            return False
        except Exception as e:
            if not silent:
                log_error("Lỗi kiểm tra Tesseract", e)
            return False
    
    def ensure_tesseract_ready(self):
        """Đảm bảo Tesseract sẵn sàng cho OCR. Return True nếu OK, False nếu fail
        
        Chỉ check khi đang dùng Tesseract engine
        """
        if self.ocr_engine != "tesseract":
            return True  # Không cần Tesseract nếu dùng EasyOCR
        
        if self.verify_tesseract(silent=True):
            return True
        
        # Tesseract not ready - show clear error message
        error_msg = (
            "Tesseract OCR chưa được cài đặt hoặc chưa cấu hình!\n\n"
            "Hướng dẫn:\n"
            "1. Tải Tesseract từ: https://github.com/UB-Mannheim/tesseract/wiki\n"
            "2. Cài đặt Tesseract vào máy\n"
            "3. Sử dụng nút 'Duyệt' trong tab 'Cài Đặt' để chọn đường dẫn tesseract.exe\n\n"
            "Hoặc:\n"
            "- Chuyển sang Engine OCR khác (EasyOCR) nếu đã cài đặt"
        )
        
        try:
            messagebox.showerror("Lỗi Tesseract OCR", error_msg)
        except Exception as e:
            log_error("Error showing messagebox", e)
        
        self.log("Lỗi: Tesseract OCR chưa sẵn sàng. Vui lòng cấu hình theo hướng dẫn.")
        return False
    
    def browse_tesseract_path(self):
        """Duyệt thư mục cài đặt Tesseract - hỗ trợ Windows, Linux, macOS"""
        initial_dir = None
        if self.custom_tesseract_path:
            if os.path.isdir(self.custom_tesseract_path):
                initial_dir = self.custom_tesseract_path
            elif os.path.isfile(self.custom_tesseract_path):
                initial_dir = os.path.dirname(self.custom_tesseract_path)
        
        file_path = None
        # Windows: chọn file .exe hoặc thư mục
        # Linux/Mac: chọn file thực thi hoặc thư mục
        if os.name == 'nt':
            # Windows: ưu tiên chọn file .exe
            file_path = filedialog.askopenfilename(
                title="Chọn Tệp Thực Thi Tesseract (tesseract.exe)",
                initialdir=initial_dir,
                filetypes=[("Tệp thực thi", "*.exe"), ("Tất cả tệp", "*.*")]
            )
            
            if file_path:
                file_path = os.path.normpath(file_path)
                # Kiểm tra tên file
                if os.path.basename(file_path).lower() == 'tesseract.exe' or os.path.basename(file_path).lower() == 'tesseract':
                    self.custom_tesseract_path = file_path
                    pytesseract.pytesseract.tesseract_cmd = file_path
                    self.tesseract_path_label.config(
                        text=f"Đường dẫn: {file_path}",
                        fg="green"
                    )
                    self.save_config()
                    
                    if self.verify_tesseract():
                        self.log(f"Đã đặt đường dẫn Tesseract thành công: {file_path}")
                        messagebox.showinfo("Thành công", "Đã cấu hình đường dẫn Tesseract OCR thành công!")
                        return
                    else:
                        messagebox.showerror("Lỗi", "Tìm thấy tesseract nhưng không hoạt động. Vui lòng kiểm tra lại cài đặt.")
                        return
                else:
                    messagebox.showerror("Lỗi", "Vui lòng chọn file tesseract.exe")
        else:
            # Linux/Mac: chọn file thực thi
            file_path = filedialog.askopenfilename(
                title="Chọn Tệp Thực Thi Tesseract",
                initialdir=initial_dir,
                filetypes=[("Tất cả tệp", "*.*")]
            )
            
            if file_path:
                file_path = os.path.normpath(file_path)
                # Kiểm tra tên file hoặc quyền thực thi
                if os.path.basename(file_path).lower() == 'tesseract' or os.access(file_path, os.X_OK):
                    self.custom_tesseract_path = file_path
                    pytesseract.pytesseract.tesseract_cmd = file_path
                    self.tesseract_path_label.config(
                        text=f"Đường dẫn: {file_path}",
                        fg="green"
                    )
                    self.save_config()
                    
                    if self.verify_tesseract():
                        self.log(f"Đã đặt đường dẫn Tesseract thành công: {file_path}")
                        messagebox.showinfo("Thành công", "Đã cấu hình đường dẫn Tesseract OCR thành công!")
                        return
                    else:
                        messagebox.showerror("Lỗi", "Tìm thấy tesseract nhưng không hoạt động. Vui lòng kiểm tra lại cài đặt.")
                        return
                else:
                    messagebox.showerror("Lỗi", "Vui lòng chọn file tesseract thực thi")
        
        # Nếu không chọn file, thử chọn thư mục và tìm trong đó
        if not file_path:
            folder_path = filedialog.askdirectory(
                title="Chọn Thư Mục Cài Đặt Tesseract OCR",
                initialdir=initial_dir
            )
            
            if folder_path:
                folder_path = os.path.normpath(folder_path)
                # Tìm tesseract trong thư mục
                tesseract_name = 'tesseract.exe' if os.name == 'nt' else 'tesseract'
                tesseract_path = os.path.join(folder_path, tesseract_name)
                
                if os.path.exists(tesseract_path):
                    self.custom_tesseract_path = tesseract_path
                    pytesseract.pytesseract.tesseract_cmd = tesseract_path
                    self.tesseract_path_label.config(
                        text=f"Đường dẫn: {tesseract_path}",
                        fg="green"
                    )
                    self.save_config()
                    
                    if self.verify_tesseract():
                        self.log(f"Đã đặt đường dẫn Tesseract thành công: {tesseract_path}")
                        messagebox.showinfo("Thành công", "Đã cấu hình đường dẫn Tesseract OCR thành công!")
                        return
                    else:
                        messagebox.showerror("Lỗi", f"Tìm thấy {tesseract_name} nhưng không hoạt động. Vui lòng kiểm tra lại cài đặt.")
                        return
                else:
                    # Tìm đệ quy trong thư mục
                    found = False
                    for root, dirs, files in os.walk(folder_path):
                        if tesseract_name in files:
                            tesseract_path = os.path.join(root, tesseract_name)
                            tesseract_path = os.path.normpath(tesseract_path)
                            self.custom_tesseract_path = tesseract_path
                            pytesseract.pytesseract.tesseract_cmd = tesseract_path
                            self.tesseract_path_label.config(
                                text=f"Đường dẫn: {tesseract_path}",
                                fg="green"
                            )
                            self.save_config()
                            
                            if self.verify_tesseract():
                                self.log(f"Đã đặt đường dẫn Tesseract thành công: {tesseract_path}")
                                messagebox.showinfo("Thành công", f"Đã tìm thấy và cấu hình Tesseract OCR:\n{tesseract_path}")
                                found = True
                                return
                    
                    if not found:
                        messagebox.showerror(
                            "Không Tìm Thấy Tesseract",
                            f"Không tìm thấy {tesseract_name} trong thư mục đã chọn:\n{folder_path}\n\n"
                            f"Vui lòng chọn thư mục chứa {tesseract_name}"
                        )
    
    def create_ui(self):
        """Tạo giao diện người dùng chính với các tab"""
        header_frame = tk.Frame(self.root, bg="#f0f0f0", height=60)
        header_frame.pack(fill=tk.X, padx=0, pady=0)
        header_frame.pack_propagate(False)
        
        title_label = tk.Label(
            header_frame,
            text="Công Cụ Dịch Màn Hình Thời Gian Thực",
            font=("Arial", 14, "bold"),
            bg="#f0f0f0",
            pady=5
        )
        title_label.pack()
        
        author_label = tk.Label(
            header_frame,
            text=f"Tác giả: {self.author}",
            font=("Arial", 9),
            bg="#f0f0f0",
            fg="#666666"
        )
        author_label.pack()
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Tab 1: Cài Đặt (Settings)
        settings_tab = ttk.Frame(self.notebook)
        self.notebook.add(settings_tab, text="Cài Đặt")
        self.create_settings_tab(settings_tab)
        
        # Tab 2: Giao Diện Dịch (Overlay)
        overlay_tab = ttk.Frame(self.notebook)
        self.notebook.add(overlay_tab, text="Giao Diện Dịch")
        self.create_overlay_tab(overlay_tab)
        
        # Tab 3: Điều Khiển (Controls)
        controls_tab = ttk.Frame(self.notebook)
        self.notebook.add(controls_tab, text="Điều Khiển")
        self.create_controls_tab(controls_tab)
        
        # Tab 4: Trạng Thái (Status)
        status_tab = ttk.Frame(self.notebook)
        self.notebook.add(status_tab, text="Trạng Thái")
        self.create_status_tab(status_tab)
        
        # Tab 5: Hướng Dẫn (Notes/Help)
        notes_tab = ttk.Frame(self.notebook)
        self.notebook.add(notes_tab, text="Hướng Dẫn")
        self.create_notes_tab(notes_tab)
    
    def create_settings_tab(self, parent):
        """Create settings tab"""
        # Region Selection Frame
        region_frame = ttk.LabelFrame(parent, text="Vùng Chụp Màn Hình", padding=10)
        region_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.region_label = tk.Label(
            region_frame,
            text="Chưa chọn vùng",
            font=("Arial", 10),
            fg="gray"
        )
        self.region_label.pack(pady=5)
        
        if self.capture_region:
            self.region_label.config(
                text=f"Vùng: {self.capture_region}",
                fg="green"
            )
        
        ttk.Button(
            region_frame,
            text="Chọn Vùng",
            command=self.select_region
        ).pack(pady=5)
        
        # Settings Frame
        settings_frame = ttk.LabelFrame(parent, text="Cài Đặt OCR & Dịch", padding=10)
        settings_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Source Language
        ttk.Label(settings_frame, text="Ngôn Ngữ Nguồn:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.source_lang_var = tk.StringVar(value=self.source_language)
        source_lang_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.source_lang_var,
            values=["eng", "jpn", "kor", "chi_sim", "chi_tra", "fra", "deu", "spa"],
            state="readonly",
            width=15
        )
        source_lang_combo.grid(row=0, column=1, pady=5)
        source_lang_combo.bind("<<ComboboxSelected>>", self.on_source_lang_change)
        
        # Update Interval
        ttk.Label(settings_frame, text="Khoảng Thời Gian Cập Nhật (ms):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.interval_var = tk.StringVar(value=str(int(self.update_interval * 1000)))
        interval_spin = ttk.Spinbox(
            settings_frame,
            from_=50,  # Allow faster updates (50ms minimum)
            to=5000,
            increment=50,
            textvariable=self.interval_var,
            width=15
        )
        interval_spin.grid(row=1, column=1, pady=5)
        interval_spin.bind("<FocusOut>", self.on_interval_change)
        
        # OCR Engine Selection - chỉ free engines
        ttk.Label(settings_frame, text="Engine OCR:").grid(row=2, column=0, sticky=tk.W, pady=5)
        ocr_engine_values = ["tesseract"]
        if self.EASYOCR_AVAILABLE:
            ocr_engine_values.append("easyocr")
        # Đảm bảo giá trị hiện tại có trong danh sách
        if self.ocr_engine not in ocr_engine_values:
            self.ocr_engine = "tesseract"
        self.ocr_engine_var = tk.StringVar(value=self.ocr_engine)
        ocr_engine_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.ocr_engine_var,
            values=ocr_engine_values,
            state="readonly",
            width=15
        )
        ocr_engine_combo.grid(row=2, column=1, pady=5)
        ocr_engine_combo.bind("<<ComboboxSelected>>", self.on_ocr_engine_change)
        
        # Tesseract Path (only show when Tesseract is selected)
        self.tesseract_path_row = 3
        self.tesseract_path_label_widget = ttk.Label(settings_frame, text="Đường Dẫn Tesseract:")
        self.tesseract_path_label_widget.grid(row=self.tesseract_path_row, column=0, sticky=tk.W, pady=5)
        tesseract_path_frame = ttk.Frame(settings_frame)
        tesseract_path_frame.grid(row=self.tesseract_path_row, column=1, sticky=tk.W+tk.E, pady=5)
        self.tesseract_path_label_frame = tesseract_path_frame  # Lưu reference để ẩn/hiện
        
        # Display current path
        current_path = "Đang kiểm tra..."
        path_color = "gray"
        
        # Kiểm tra xem Tesseract đã được cấu hình chưa
        if self.custom_tesseract_path and os.path.exists(self.custom_tesseract_path):
            # Chuẩn hóa đường dẫn khi hiển thị
            current_path = os.path.normpath(self.custom_tesseract_path)
            path_color = "green"
        else:
            # Thử xác minh xem Tesseract có hoạt động không
            try:
                if pytesseract.pytesseract.tesseract_cmd:
                    # Chuẩn hóa đường dẫn khi hiển thị
                    current_path = os.path.normpath(pytesseract.pytesseract.tesseract_cmd)
                    path_color = "green"
                else:
                    # Kiểm tra xem có trong PATH không
                    if self.verify_tesseract():
                        current_path = "Tự động phát hiện (PATH)"
                        path_color = "green"
                    else:
                        current_path = "Không tìm thấy - Nhấn Duyệt"
                        path_color = "red"
            except Exception as e:
                log_error("Lỗi kiểm tra đường dẫn Tesseract", e)
                if self.verify_tesseract():
                    current_path = "Tự động phát hiện (PATH)"
                    path_color = "green"
                else:
                    current_path = "Không tìm thấy - Nhấn Duyệt"
                    path_color = "red"
        
        self.tesseract_path_label = tk.Label(
            tesseract_path_frame,
            text=f"Đường dẫn: {current_path}",
            font=("Arial", 8),
            fg=path_color,
            wraplength=200,
            justify=tk.LEFT
        )
        self.tesseract_path_label.pack(side=tk.LEFT, padx=(0, 5))
        
        self.tesseract_browse_button = ttk.Button(
            tesseract_path_frame,
            text="Duyệt",
            command=self.browse_tesseract_path,
            width=10
        )
        self.tesseract_browse_button.pack(side=tk.LEFT)
        
        # Tesseract Options (only show when Tesseract is selected)
        self.tesseract_options_row = 4
        self.tesseract_options_frame = ttk.Frame(settings_frame)
        self.tesseract_options_frame.grid(row=self.tesseract_options_row, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        self.tesseract_multi_scale_var = tk.BooleanVar(value=self.tesseract_multi_scale)
        tesseract_multi_scale_check = ttk.Checkbutton(
            self.tesseract_options_frame,
            text="Bật Multi-scale (Tăng độ chính xác nhưng chậm hơn ~1.5-2x)",
            variable=self.tesseract_multi_scale_var,
            command=self.on_tesseract_multi_scale_change
        )
        tesseract_multi_scale_check.pack(side=tk.TOP, anchor=tk.W, padx=5, pady=2)
        
        self.tesseract_text_region_var = tk.BooleanVar(value=self.tesseract_text_region_detection)
        tesseract_text_region_check = ttk.Checkbutton(
            self.tesseract_options_frame,
            text="Bật Text Region Detection (Phát hiện vùng text trước, chậm hơn)",
            variable=self.tesseract_text_region_var,
            command=self.on_tesseract_text_region_change
        )
        tesseract_text_region_check.pack(side=tk.TOP, anchor=tk.W, padx=5, pady=2)
        
        # Info label
        tesseract_info = tk.Label(
            self.tesseract_options_frame,
            text="(Chỉ nên bật khi cần độ chính xác cao)",
            font=("Arial", 8),
            fg="gray"
        )
        tesseract_info.pack(side=tk.TOP, anchor=tk.W, padx=5, pady=2)
        
        # EasyOCR GPU Option (only show when EasyOCR is selected)
        self.easyocr_gpu_row = 3
        self.easyocr_gpu_frame = ttk.Frame(settings_frame)
        self.easyocr_gpu_frame.grid(row=self.easyocr_gpu_row, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # Detect GPU availability for info display
        gpu_available = False
        gpu_name = None
        try:
            import torch
            if torch.cuda.is_available():
                gpu_available = True
                gpu_name = torch.cuda.get_device_name(0)
        except Exception as e:
            log_error("Error checking GPU availability in UI", e)
        
        # GPU option: Auto/CPU/GPU
        self.easyocr_gpu_var = tk.StringVar(value="auto")  # auto, cpu, gpu
        if self.easyocr_use_gpu is True:
            self.easyocr_gpu_var.set("gpu")
        elif self.easyocr_use_gpu is False:
            self.easyocr_gpu_var.set("cpu")
        else:
            self.easyocr_gpu_var.set("auto")
        
        ttk.Label(self.easyocr_gpu_frame, text="EasyOCR Mode:").pack(side=tk.LEFT, padx=(0, 5))
        
        gpu_radio_frame = ttk.Frame(self.easyocr_gpu_frame)
        gpu_radio_frame.pack(side=tk.LEFT)
        
        ttk.Radiobutton(
            gpu_radio_frame,
            text="Tự động",
            variable=self.easyocr_gpu_var,
            value="auto",
            command=self.on_easyocr_gpu_change
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Radiobutton(
            gpu_radio_frame,
            text="CPU",
            variable=self.easyocr_gpu_var,
            value="cpu",
            command=self.on_easyocr_gpu_change
        ).pack(side=tk.LEFT, padx=5)
        
        gpu_radio = ttk.Radiobutton(
            gpu_radio_frame,
            text="GPU",
            variable=self.easyocr_gpu_var,
            value="gpu",
            command=self.on_easyocr_gpu_change
        )
        gpu_radio.pack(side=tk.LEFT, padx=5)
        
        # Disable GPU option if GPU not available
        if not gpu_available:
            gpu_radio.config(state=tk.DISABLED)
            gpu_info_text = " (GPU không khả dụng)"
        else:
            gpu_info_text = f" ({gpu_name})" if gpu_name else ""
        
        self.gpu_info_label = tk.Label(
            self.easyocr_gpu_frame,
            text=gpu_info_text,
            font=("Arial", 8),
            fg="gray" if not gpu_available else "green"
        )
        self.gpu_info_label.pack(side=tk.LEFT, padx=5)
        
        # EasyOCR Multi-scale Option (only show when EasyOCR is selected)
        self.easyocr_multi_scale_row = 4
        self.easyocr_multi_scale_frame = ttk.Frame(settings_frame)
        self.easyocr_multi_scale_frame.grid(row=self.easyocr_multi_scale_row, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        self.easyocr_multi_scale_var = tk.BooleanVar(value=self.easyocr_multi_scale)
        multi_scale_check = ttk.Checkbutton(
            self.easyocr_multi_scale_frame,
            text="Bật Multi-scale (Tăng độ chính xác nhưng chậm hơn ~2-3x)",
            variable=self.easyocr_multi_scale_var,
            command=self.on_easyocr_multi_scale_change
        )
        multi_scale_check.pack(side=tk.TOP, anchor=tk.W, padx=5, pady=2)
        
        # Info label
        multi_scale_info = tk.Label(
            self.easyocr_multi_scale_frame,
            text="(Chỉ nên bật khi cần độ chính xác cao với text khó đọc)",
            font=("Arial", 8),
            fg="gray"
        )
        multi_scale_info.pack(side=tk.TOP, anchor=tk.W, padx=5, pady=2)
        
        # Translation Service Selection
        translation_frame = ttk.LabelFrame(parent, text="Dịch Thuật", padding=10)
        translation_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Target Language
        ttk.Label(translation_frame, text="Ngôn Ngữ Đích:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.target_lang_var = tk.StringVar(value=self.target_language)
        target_lang_combo = ttk.Combobox(
            translation_frame,
            textvariable=self.target_lang_var,
            values=["vi", "en", "ja", "ko", "zh", "fr", "de", "es"],
            state="readonly",
            width=15
        )
        target_lang_combo.grid(row=0, column=1, pady=5)
        target_lang_combo.bind("<<ComboboxSelected>>", self.on_target_lang_change)
        
        # Translation Service
        ttk.Label(translation_frame, text="Dịch Vụ:").grid(row=1, column=0, sticky=tk.W, pady=5)
        # Sync với giá trị đã load từ config
        initial_service = "deepl" if self.use_deepl else "google"
        self.translation_service_var = tk.StringVar(value=initial_service)
        service_combo = ttk.Combobox(
            translation_frame,
            textvariable=self.translation_service_var,
            values=["google", "deepl"] if self.DEEPL_API_AVAILABLE else ["google"],
            state="readonly",
            width=15
        )
        service_combo.grid(row=1, column=1, pady=5)
        service_combo.bind("<<ComboboxSelected>>", self.on_translation_service_change)
        
        # DeepL API Key (ẩn/hiện dựa vào translation service)
        next_row = 2
        self.deepl_widgets = []  # Lưu tất cả widgets liên quan đến DeepL
        
        if self.DEEPL_API_AVAILABLE:
            # Label cho API Key
            deepl_key_label = ttk.Label(translation_frame, text="DeepL API Key:")
            deepl_key_label.grid(row=next_row, column=0, sticky=tk.W, pady=5)
            self.deepl_widgets.append(deepl_key_label)
            
            # Entry cho API Key
            self.deepl_api_key_var = tk.StringVar(value=self.deepl_api_key)
            deepl_key_entry = ttk.Entry(
                translation_frame,
                textvariable=self.deepl_api_key_var,
                width=40,
                show="*"
            )
            deepl_key_entry.grid(row=next_row, column=1, pady=5, sticky=tk.W+tk.E)
            deepl_key_entry.bind("<FocusOut>", self.on_deepl_key_change)
            self.deepl_widgets.append(deepl_key_entry)
            next_row += 1
            
            # Label cho Context Window
            context_label = ttk.Label(translation_frame, text="Context Window:")
            context_label.grid(row=next_row, column=0, sticky=tk.W, pady=5)
            self.deepl_widgets.append(context_label)
            
            # Combobox cho Context Window
            self.deepl_context_window_var = tk.IntVar(value=self.deepl_context_window_size)
            context_window_combo = ttk.Combobox(
                translation_frame,
                textvariable=self.deepl_context_window_var,
                values=[0, 1, 2, 3],
                state="readonly",
                width=15
            )
            context_window_combo.grid(row=next_row, column=1, pady=5, sticky=tk.W)
            context_window_combo.bind("<<ComboboxSelected>>", self.on_deepl_context_window_change)
            self.deepl_widgets.append(context_window_combo)
            
            # Label mô tả cho Context Window
            context_desc_label = ttk.Label(
                translation_frame, 
                text="(Số subtitle trước đó dùng làm context, 0 = tắt)",
                font=("Arial", 8),
                foreground="gray"
            )
            context_desc_label.grid(row=next_row, column=1, sticky=tk.E, padx=(5, 0))
            self.deepl_widgets.append(context_desc_label)
            next_row += 1
            
            # Ẩn/hiện widgets dựa vào service hiện tại
            self.toggle_deepl_widgets()
        
        translation_frame.columnconfigure(1, weight=1)
    
    def create_overlay_tab(self, parent):
        """Tạo tab tùy chỉnh overlay"""
        # Frame tùy chỉnh overlay
        overlay_frame = ttk.LabelFrame(parent, text="Tùy Chỉnh Giao Diện Dịch", padding=10)
        overlay_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Tạo frame có thể cuộn cho cài đặt overlay
        canvas = tk.Canvas(overlay_frame)
        scrollbar = ttk.Scrollbar(overlay_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        settings_container = scrollable_frame
        
        # Font Size
        ttk.Label(settings_container, text="Cỡ Chữ:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.font_size_var = tk.StringVar(value=str(self.overlay_font_size))
        font_size_spin = ttk.Spinbox(
            settings_container,
            from_=8,
            to=32,
            increment=1,
            textvariable=self.font_size_var,
            width=10
        )
        font_size_spin.grid(row=0, column=1, pady=3, padx=5)
        
        # Transparency
        ttk.Label(settings_container, text="Độ Trong Suốt:").grid(row=0, column=2, sticky=tk.W, pady=3, padx=(20, 0))
        self.transparency_var = tk.StringVar(value=str(int(self.overlay_transparency * 100)))
        transparency_spin = ttk.Spinbox(
            settings_container,
            from_=50,
            to=100,
            increment=5,
            textvariable=self.transparency_var,
            width=10
        )
        transparency_spin.grid(row=0, column=3, pady=3, padx=5)
        
        # Width
        ttk.Label(settings_container, text="Chiều Rộng:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.width_var = tk.StringVar(value=str(self.overlay_width))
        width_spin = ttk.Spinbox(
            settings_container,
            from_=200,
            to=1000,
            increment=50,
            textvariable=self.width_var,
            width=10
        )
        width_spin.grid(row=1, column=1, pady=3, padx=5)
        
        # Height
        ttk.Label(settings_container, text="Chiều Cao:").grid(row=1, column=2, sticky=tk.W, pady=3, padx=(20, 0))
        self.height_var = tk.StringVar(value=str(self.overlay_height))
        height_spin = ttk.Spinbox(
            settings_container,
            from_=100,
            to=800,
            increment=50,
            textvariable=self.height_var,
            width=10
        )
        height_spin.grid(row=1, column=3, pady=3, padx=5)
        
        # Text Color
        ttk.Label(settings_container, text="Màu Chữ:").grid(row=2, column=0, sticky=tk.W, pady=3)
        self.text_color_var = tk.StringVar(value=self.overlay_text_color)
        text_color_entry = ttk.Entry(settings_container, textvariable=self.text_color_var, width=12)
        text_color_entry.grid(row=2, column=1, pady=3, padx=5)
        
        # Background Color
        ttk.Label(settings_container, text="Màu Nền:").grid(row=2, column=2, sticky=tk.W, pady=3, padx=(20, 0))
        self.bg_color_var = tk.StringVar(value=self.overlay_bg_color)
        bg_color_entry = ttk.Entry(settings_container, textvariable=self.bg_color_var, width=12)
        bg_color_entry.grid(row=2, column=3, pady=3, padx=5)
        
        # Show Original Text
        self.show_original_var = tk.BooleanVar(value=self.overlay_show_original)
        show_original_check = ttk.Checkbutton(
            settings_container,
            text="Hiển Thị Văn Bản Gốc",
            variable=self.show_original_var
        )
        show_original_check.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # Text Alignment
        ttk.Label(settings_container, text="Căn Lề:").grid(row=3, column=2, sticky=tk.W, pady=3, padx=(20, 0))
        self.text_align_var = tk.StringVar(value=self.overlay_text_align)
        align_combo = ttk.Combobox(
            settings_container,
            textvariable=self.text_align_var,
            values=["left", "center", "justify"],
            state="readonly",
            width=10
        )
        align_combo.grid(row=3, column=3, pady=3, padx=5)
        
        # Font Family
        ttk.Label(settings_container, text="Phông Chữ:").grid(row=4, column=0, sticky=tk.W, pady=3)
        self.font_family_var = tk.StringVar(value=self.overlay_font_family)
        font_family_combo = ttk.Combobox(
            settings_container,
            textvariable=self.font_family_var,
            values=["Arial", "Helvetica", "Times New Roman", "Courier New", "Verdana", 
                   "Georgia", "Comic Sans MS", "Impact", "Trebuchet MS", "Tahoma", 
                   "Calibri", "Segoe UI", "Consolas", "Lucida Console"],
            state="readonly",
            width=12
        )
        font_family_combo.grid(row=4, column=1, pady=3, padx=5)
        
        # Font Weight
        ttk.Label(settings_container, text="Độ Đậm:").grid(row=4, column=2, sticky=tk.W, pady=3, padx=(20, 0))
        self.font_weight_var = tk.StringVar(value=self.overlay_font_weight)
        font_weight_combo = ttk.Combobox(
            settings_container,
            textvariable=self.font_weight_var,
            values=["normal", "bold"],
            state="readonly",
            width=12
        )
        font_weight_combo.grid(row=4, column=3, pady=3, padx=5)
        
        # Line Spacing
        ttk.Label(settings_container, text="Khoảng Cách Dòng:").grid(row=5, column=0, sticky=tk.W, pady=3)
        self.line_spacing_var = tk.StringVar(value=str(self.overlay_line_spacing))
        line_spacing_spin = ttk.Spinbox(
            settings_container,
            from_=0.8,
            to=3.0,
            increment=0.1,
            textvariable=self.line_spacing_var,
            width=10,
            format="%.1f"
        )
        line_spacing_spin.grid(row=5, column=1, pady=3, padx=5)
        
        # Original Text Color
        ttk.Label(settings_container, text="Màu Văn Bản Gốc:").grid(row=5, column=2, sticky=tk.W, pady=3, padx=(20, 0))
        self.original_color_var = tk.StringVar(value=self.overlay_original_color)
        original_color_entry = ttk.Entry(settings_container, textvariable=self.original_color_var, width=12)
        original_color_entry.grid(row=5, column=3, pady=3, padx=5)
        
        # Padding X
        ttk.Label(settings_container, text="Khoảng Cách Ngang:").grid(row=6, column=0, sticky=tk.W, pady=3)
        self.padding_x_var = tk.StringVar(value=str(self.overlay_padding_x))
        padding_x_spin = ttk.Spinbox(
            settings_container,
            from_=0,
            to=50,
            increment=5,
            textvariable=self.padding_x_var,
            width=10
        )
        padding_x_spin.grid(row=6, column=1, pady=3, padx=5)
        
        # Padding Y
        ttk.Label(settings_container, text="Khoảng Cách Dọc:").grid(row=6, column=2, sticky=tk.W, pady=3, padx=(20, 0))
        self.padding_y_var = tk.StringVar(value=str(self.overlay_padding_y))
        padding_y_spin = ttk.Spinbox(
            settings_container,
            from_=0,
            to=50,
            increment=5,
            textvariable=self.padding_y_var,
            width=10
        )
        padding_y_spin.grid(row=6, column=3, pady=3, padx=5)
        
        # Border Width
        ttk.Label(settings_container, text="Độ Dày Viền:").grid(row=7, column=0, sticky=tk.W, pady=3)
        self.border_width_var = tk.StringVar(value=str(self.overlay_border_width))
        border_width_spin = ttk.Spinbox(
            settings_container,
            from_=0,
            to=10,
            increment=1,
            textvariable=self.border_width_var,
            width=10
        )
        border_width_spin.grid(row=7, column=1, pady=3, padx=5)
        
        # Border Color
        ttk.Label(settings_container, text="Màu Viền:").grid(row=7, column=2, sticky=tk.W, pady=3, padx=(20, 0))
        self.border_color_var = tk.StringVar(value=self.overlay_border_color)
        border_color_entry = ttk.Entry(settings_container, textvariable=self.border_color_var, width=12)
        border_color_entry.grid(row=7, column=3, pady=3, padx=5)
        
        # Word Wrap
        self.word_wrap_var = tk.BooleanVar(value=self.overlay_word_wrap)
        word_wrap_check = ttk.Checkbutton(
            settings_container,
            text="Xuống Dòng Tự Động",
            variable=self.word_wrap_var
        )
        word_wrap_check.grid(row=8, column=0, columnspan=4, sticky=tk.W, pady=5)
        
        # Keep Translation History
        self.keep_history_var = tk.BooleanVar(value=self.overlay_keep_history)
        keep_history_check = ttk.Checkbutton(
            settings_container,
            text="Ghi Lại Lịch Sử Dịch (Không Ghi Đè)",
            variable=self.keep_history_var
            # Không có command - chỉ apply khi nhấn nút Áp dụng
        )
        keep_history_check.grid(row=9, column=0, columnspan=4, sticky=tk.W, pady=5)
        
        # Preset configurations frame
        preset_frame = ttk.LabelFrame(settings_container, text="Cấu Hình Nhanh (Preset)", padding=10)
        preset_frame.grid(row=10, column=0, columnspan=4, pady=10, sticky=tk.EW)
        
        preset_buttons_frame = ttk.Frame(preset_frame)
        preset_buttons_frame.pack(fill=tk.X)
        
        ttk.Button(
            preset_buttons_frame,
            text="Tối Ưu Tốc Độ",
            command=lambda: self.apply_preset('speed'),
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            preset_buttons_frame,
            text="Cân Bằng",
            command=lambda: self.apply_preset('balanced'),
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            preset_buttons_frame,
            text="Tối Ưu Chất Lượng",
            command=lambda: self.apply_preset('quality'),
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            preset_buttons_frame,
            text="Mặc Định",
            command=lambda: self.apply_preset('default'),
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        # Apply and Reset buttons frame
        apply_button_frame = ttk.Frame(settings_container)
        apply_button_frame.grid(row=11, column=0, columnspan=4, pady=15, sticky=tk.EW)
        
        ttk.Button(
            apply_button_frame,
            text="Đặt Lại Tất Cả",
            command=self.reset_all_settings,
            width=18
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            apply_button_frame,
            text="Áp Dụng",
            command=self.apply_overlay_settings,
            width=20
        ).pack(side=tk.RIGHT, padx=5)
    
    def create_controls_tab(self, parent):
        """Create controls tab"""
        # Control Frame
        control_frame = ttk.LabelFrame(parent, text="Điều Khiển Dịch", padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.start_button = ttk.Button(
            control_frame,
            text="Bắt Đầu Dịch",
            command=self.start_translation,
            state=tk.NORMAL if self.capture_region else tk.DISABLED
        )
        self.start_button.pack(pady=5, fill=tk.X)
        
        self.stop_button = ttk.Button(
            control_frame,
            text="Dừng Dịch",
            command=self.stop_translation,
            state=tk.DISABLED
        )
        self.stop_button.pack(pady=5, fill=tk.X)
        
        # Lock overlay frame
        lock_frame = ttk.LabelFrame(parent, text="Khóa Màn Hình Dịch", padding=10)
        lock_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.overlay_lock_var = tk.BooleanVar(value=self.overlay_locked)
        lock_check = ttk.Checkbutton(
            lock_frame,
            text="Khóa màn hình dịch (ngăn di chuyển khi chơi game)",
            variable=self.overlay_lock_var,
            command=self.on_lock_overlay_change
        )
        lock_check.pack(pady=5, anchor=tk.W)
        
        lock_info = tk.Label(
            lock_frame,
            text="Khi khóa, màn hình dịch sẽ không thể di chuyển hoặc thay đổi kích thước.",
            font=("Arial", 8),
            fg="gray",
            wraplength=500,
            justify=tk.LEFT
        )
        lock_info.pack(pady=5, anchor=tk.W)
    
    def create_status_tab(self, parent):
        """Create status tab"""
        # Status Frame
        status_frame = ttk.LabelFrame(parent, text="Trạng Thái & Nhật Ký", padding=10)
        status_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.status_text = tk.Text(
            status_frame,
            height=20,
            wrap=tk.WORD,
            font=("Consolas", 9)
        )
        self.status_text.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(status_frame, command=self.status_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.status_text.config(yscrollcommand=scrollbar.set)
        
        self.log("Công cụ sẵn sàng. Chọn vùng chụp màn hình để bắt đầu.")
    
    def create_notes_tab(self, parent):
        """Create notes/help tab for user instructions"""
        # Instructions frame
        instructions_frame = ttk.LabelFrame(parent, text="Hướng Dẫn Sử Dụng", padding=10)
        instructions_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Tạo vùng văn bản có thể cuộn
        notes_canvas = tk.Canvas(instructions_frame, bg="white")
        notes_scrollbar = ttk.Scrollbar(instructions_frame, orient="vertical", command=notes_canvas.yview)
        notes_scrollable_frame = ttk.Frame(notes_canvas)
        
        notes_scrollable_frame.bind(
            "<Configure>",
            lambda e: notes_canvas.configure(scrollregion=notes_canvas.bbox("all"))
        )
        
        notes_canvas.create_window((0, 0), window=notes_scrollable_frame, anchor="nw")
        notes_canvas.configure(yscrollcommand=notes_scrollbar.set)
        
        # Instructions content - Hướng dẫn cho người dùng phổ thông (EXE)
        # Lưu ý: Nội dung này dành cho người dùng cuối, không chứa thông tin kỹ thuật/dev
        instructions_text = """
HƯỚNG DẪN SỬ DỤNG CÔNG CỤ DỊCH MÀN HÌNH THỜI GIAN THỰC

1. CÀI ĐẶT

BƯỚC 1: Cài đặt Tesseract OCR (BẮT BUỘC)
   • Windows: Tải từ https://github.com/UB-Mannheim/tesseract/wiki
   • macOS: brew install tesseract
   • Linux: sudo apt-get install tesseract-ocr (Ubuntu/Debian) hoặc sudo dnf install tesseract (Fedora)
   • Nếu không tự tìm thấy → Dùng nút "Duyệt" trong tab "Cài Đặt" để chọn đường dẫn

BƯỚC 2: Dữ liệu ngôn ngữ (Nếu cần)
   • Với ngôn ngữ không phải tiếng Anh (Nhật, Hàn, Trung...):
   • Windows: Tải từ https://github.com/tesseract-ocr/tessdata, đặt vào C:\\Program Files\\Tesseract-OCR\\tessdata\\
   • macOS/Linux: sudo apt-get install tesseract-ocr-jpn (ví dụ tiếng Nhật) hoặc brew install tesseract-lang

BƯỚC 3: Chạy công cụ
   • Chạy file RealTimeScreenTranslator.exe
   • Nếu có cảnh báo Windows → "Run anyway"
   • Đợi 5-10s để công cụ khởi động

2. BẮT ĐẦU SỬ DỤNG

BƯỚC 1: Chọn vùng chụp màn hình
   1. Mở ứng dụng/game cần dịch
   2. Tab "Cài Đặt" → Nhấn "Chọn Vùng"
   3. Kéo chuột chọn vùng hộp thoại → Thả chuột để xác nhận
   
   ⚠️ LƯU Ý: Chọn chính xác vùng hộp thoại, vùng nhỏ hơn = dịch nhanh hơn

BƯỚC 2: Cấu hình cài đặt (Tab "Cài Đặt")
   1. NGÔN NGỮ NGUỒN: Chọn ngôn ngữ của văn bản trong ứng dụng
   
   2. KHOẢNG THỜI GIAN CẬP NHẬT:
      - 100-200ms: Game (nhanh, tốn CPU)
      - 200-300ms: Ứng dụng thường (cân bằng)
      - Preset sẽ tự động cập nhật giá trị này
   
   3. ENGINE OCR:
      - Tesseract: Mặc định, CPU thấp (dùng cho nhu cầu phổ thông)
      - EasyOCR: Chính xác hơn, tốn CPU/GPU hơn (khuyến nghị cho game)
      - Nếu Tesseract không tự tìm thấy → Dùng nút "Duyệt" để chọn
   
   4. EASYOCR MODE (chỉ khi chọn EasyOCR):
      - Tự động: Tự chọn CPU/GPU (khuyến nghị)
      - CPU: Tiết kiệm GPU
      - GPU: Nhanh hơn, giảm tải CPU (cần NVIDIA GPU)
   
   4a. EASYOCR MULTI-SCALE (chỉ khi chọn EasyOCR):
      - Tăng độ chính xác nhưng chậm hơn 2-3 lần
   
   4b. TESSERACT OPTIONS (chỉ khi chọn Tesseract):
      - Multi-scale: Tăng độ chính xác, chậm hơn 1.5-2 lần
      - Text Region Detection: Phát hiện vùng text trước, hữu ích với ảnh phức tạp
   
   5. NGÔN NGỮ ĐÍCH: Chọn ngôn ngữ muốn dịch sang
   
   6. DỊCH VỤ DỊCH THUẬT:
      - Google Translate: Miễn phí
      - DeepL: Chất lượng tốt hơn, cần API key (https://www.deepl.com/pro-api)
   
   7. DEEPL CONTEXT WINDOW (chỉ khi chọn DeepL):
      - Số subtitle trước đó dùng làm ngữ cảnh (0-3, mặc định: 2)
      - Giúp dịch hội thoại chính xác hơn

BƯỚC 3: Tùy chỉnh giao diện (Tab "Giao Diện Dịch")
   1. CẤU HÌNH NHANH (PRESET):
      - "Tối Ưu Tốc Độ": Game có hội thoại nhanh
      - "Cân Bằng": Hầu hết game/ứng dụng (khuyến nghị)
      - "Tối Ưu Chất Lượng": Cần đọc kỹ
      - "Mặc Định": Cài đặt mặc định
      - ⚠️ Nhấn "Áp Dụng" sau khi chọn preset
   
   2. TÙY CHỈNH THỦ CÔNG: Font, màu sắc, kích thước, độ trong suốt, căn lề, v.v.
   
   3. NÚT ĐIỀU KHIỂN:
      - "Áp Dụng": Áp dụng cài đặt
      - "Đặt Lại Tất Cả": Reset về mặc định (KHÔNG reset vùng chụp, engine OCR, dịch vụ, DeepL key)

BƯỚC 4: Bắt đầu dịch (Tab "Điều Khiển")
   1. Nhấn "Bắt Đầu Dịch"
   2. Màn hình dịch xuất hiện, văn bản được dịch tự động
   3. Công cụ tự động xử lý nhiều hộp thoại liên tiếp

BƯỚC 5: Sử dụng màn hình dịch
   • DI CHUYỂN: Kéo thả màn hình dịch
   • THAY ĐỔI KÍCH THƯỚC: Kéo cạnh/góc
   • CUỘN: Cuộn lên/xuống nếu văn bản dài
   • KHÓA: Tích "Khóa màn hình dịch" trong tab "Điều Khiển" để tránh di chuyển nhầm
   • TỰ ĐỘNG LƯU: Vị trí và kích thước được lưu tự động

3. MẸO SỬ DỤNG

   • PRESET: "Tối Ưu Tốc Độ" cho game nhanh, "Cân Bằng" cho hầu hết trường hợp, "Tối Ưu Chất Lượng" khi cần đọc kỹ
   
   • CHỌN VÙNG: Chọn chính xác vùng hộp thoại, vùng nhỏ hơn = dịch nhanh hơn
   
   • ENGINE OCR: Thử cả Tesseract và EasyOCR. EasyOCR chính xác hơn cho Nhật/Hàn/Trung. Nếu có NVIDIA GPU → chọn "GPU" mode
   
   • DỊCH VỤ: Google Translate (miễn phí) hoặc DeepL (chất lượng tốt hơn, có phí). DeepL: Context Window = 2 (khuyến nghị)
   
   • TỐI ƯU: Tắt hiển thị văn bản gốc, dùng font đơn giản (Arial, Helvetica), giảm độ trong suốt nếu cần
   
   • KHI CHƠI GAME: Khóa màn hình dịch, dùng preset "Tối Ưu Tốc Độ", đặt màn hình dịch không che gameplay

4. XỬ LÝ SỰ CỐ

   • OCR KHÔNG HOẠT ĐỘNG:
     - Kiểm tra Tesseract đã cài đúng → Dùng nút "Duyệt" để chọn đường dẫn
     - Thử chuyển sang EasyOCR
     - Kiểm tra ngôn ngữ nguồn đã chọn đúng
   
   • DỊCH KHÔNG HOẠT ĐỘNG:
     - Kiểm tra kết nối internet
     - Nếu dùng DeepL: Kiểm tra API key
     - Thử chuyển sang Google Translate
   
   • DỊCH SAI:
     - Thử thay đổi ngôn ngữ nguồn
     - Thử chuyển engine OCR (Tesseract ↔ EasyOCR)
     - Đảm bảo văn bản rõ ràng, không mờ
   
   • CHẬM HOẶC LAG:
     - EasyOCR: Chọn "GPU" mode nếu có NVIDIA GPU
     - Tăng khoảng thời gian cập nhật (200-300ms)
     - Dùng preset "Cân Bằng" hoặc "Tối Ưu Tốc Độ"
     - Chọn vùng chụp nhỏ hơn, tắt hiển thị văn bản gốc
     - Thử chuyển sang Tesseract
   
   • MÀN HÌNH DỊCH KHÔNG HIỂN THỊ:
     - Kiểm tra không bị di chuyển ra ngoài màn hình
     - Dừng và khởi động lại dịch
     - Nhấn "Đặt Lại Tất Cả" để reset vị trí
     - Đảm bảo tỷ lệ hiển thị Windows là 100%
   
   • XEM CHI TIẾT: Tab "Trạng Thái" hoặc file error_log.txt

5. LƯU Ý QUAN TRỌNG

   • Cần kết nối internet để dịch
   • Chất lượng dịch phụ thuộc: Độ rõ văn bản, tương phản nền, font, độ chính xác OCR
   • Tất cả cài đặt được tự động lưu
   • Nút "Đặt Lại Tất Cả" KHÔNG reset: Vùng chụp, Engine OCR, Dịch vụ, DeepL key

6. NGÔN NGỮ ĐƯỢC HỖ TRỢ

   NGÔN NGỮ NGUỒN (OCR): Anh, Nhật, Hàn, Trung (Giản thể/Phồn thể), Pháp, Đức, Tây Ban Nha
   
   NGÔN NGỮ ĐÍCH: Việt, Anh, Nhật, Hàn, Trung, Pháp, Đức, Tây Ban Nha

7. CÁC TAB TRONG CÔNG CỤ

   TAB 1: CÀI ĐẶT - Chọn vùng, ngôn ngữ, engine OCR, dịch vụ, cấu hình OCR
   
   TAB 2: GIAO DIỆN DỊCH - Preset nhanh, tùy chỉnh font/màu/kích thước
   
   TAB 3: ĐIỀU KHIỂN - Bắt đầu/Dừng dịch, khóa màn hình dịch
   
   TAB 4: TRẠNG THÁI - Nhật ký hoạt động, lỗi, cảnh báo
   
   TAB 5: HƯỚNG DẪN - Hướng dẫn sử dụng đầy đủ (tab này)

Chúc bạn sử dụng công cụ hiệu quả!
        """
        
        notes_label = tk.Label(
            notes_scrollable_frame,
            text=instructions_text.strip(),
            font=("Arial", 10),
            bg="white",
            fg="black",
            justify=tk.LEFT,
            wraplength=550,
            anchor="nw"
        )
        notes_label.pack(fill=tk.BOTH, expand=True, padx=10, pady=10, anchor="nw")
        
        notes_canvas.pack(side="left", fill="both", expand=True)
        notes_scrollbar.pack(side="right", fill="y")
    
    def on_lock_overlay_change(self):
        """Handle overlay lock state change"""
        self.overlay_locked = self.overlay_lock_var.get()
        self.save_config()
        
        if self.overlay_locked:
            self.log("Đã khóa màn hình dịch - không thể di chuyển hoặc thay đổi kích thước")
        else:
            self.log("Đã mở khóa màn hình dịch - có thể di chuyển và thay đổi kích thước")
    
    def load_config(self):
        """Load configuration from file - với error handling đầy đủ"""
        if not os.path.exists(self.config_file):
            # File không tồn tại là bình thường lần đầu chạy
            return
        
        try:
            with open(self.config_file, 'r', encoding='utf-8', errors='replace') as f:
                config = json.load(f)
            
            self.capture_region = config.get('capture_region')
            self.source_language = config.get('source_language', 'eng')
            self.ocr_engine = config.get('ocr_engine', 'tesseract')
            self.update_interval = config.get('update_interval', 0.5)
            
            # Load EasyOCR GPU option
            easyocr_gpu_config = config.get('easyocr_use_gpu', None)
            if easyocr_gpu_config is None:
                self.easyocr_use_gpu = None  # Auto-detect
            elif easyocr_gpu_config is True:
                self.easyocr_use_gpu = True  # Force GPU
            else:
                self.easyocr_use_gpu = False  # Force CPU
            
            # Load EasyOCR Multi-scale option
            self.easyocr_multi_scale = config.get('easyocr_multi_scale', False)
            
            # Load Tesseract options
            self.tesseract_multi_scale = config.get('tesseract_multi_scale', False)
            self.tesseract_text_region_detection = config.get('tesseract_text_region_detection', False)
            self.base_scan_interval = int(self.update_interval * 1000)
            if not self.overload_detected:
                self.current_scan_interval = self.base_scan_interval
            self.custom_tesseract_path = config.get('custom_tesseract_path')
            
            # Load overlay customization settings (with optimized defaults)
            overlay_config = config.get('overlay_settings', {})
            self.overlay_font_size = overlay_config.get('font_size', 15)
            self.overlay_font_family = overlay_config.get('font_family', 'Arial')
            self.overlay_font_weight = overlay_config.get('font_weight', 'normal')
            self.overlay_bg_color = overlay_config.get('bg_color', '#1a1a1a')
            self.overlay_text_color = overlay_config.get('text_color', '#ffffff')  # White text default
            self.overlay_original_color = overlay_config.get('original_color', '#cccccc')
            self.overlay_transparency = overlay_config.get('transparency', 0.88)
            self.overlay_width = overlay_config.get('width', 500)
            self.overlay_height = overlay_config.get('height', 280)
            self.overlay_show_original = overlay_config.get('show_original', True)
            self.overlay_keep_history = overlay_config.get('keep_history', False)
            self.overlay_text_align = overlay_config.get('text_align', 'left')
            self.overlay_line_spacing = overlay_config.get('line_spacing', 1.3)
            self.overlay_padding_x = overlay_config.get('padding_x', 18)
            self.overlay_padding_y = overlay_config.get('padding_y', 18)
            self.overlay_border_width = overlay_config.get('border_width', 0)
            self.overlay_border_color = overlay_config.get('border_color', '#ffffff')
            self.overlay_text_shadow = overlay_config.get('text_shadow', False)
            self.overlay_word_wrap = overlay_config.get('word_wrap', True)
            
            # Load overlay position
            overlay_position = config.get('overlay_position', {})
            self.overlay_position_x = overlay_position.get('x')
            self.overlay_position_y = overlay_position.get('y')
            
            # Load overlay lock state
            self.overlay_locked = config.get('overlay_locked', False)
            
            # Set Tesseract path if custom path is configured
            if self.custom_tesseract_path:
                # Chuẩn hóa đường dẫn khi load từ config
                self.custom_tesseract_path = os.path.normpath(self.custom_tesseract_path)
                tesseract_path = find_tesseract(self.custom_tesseract_path)
                if tesseract_path:
                    # Đảm bảo đường dẫn được chuẩn hóa
                    tesseract_path = os.path.normpath(tesseract_path)
                    pytesseract.pytesseract.tesseract_cmd = tesseract_path
            
            # Load DeepL settings
            self.deepl_api_key = config.get('deepl_api_key', '')
            self.use_deepl = config.get('use_deepl', False)
            self.target_language = config.get('target_language', 'vi')
            self.deepl_context_window_size = config.get('deepl_context_window_size', 2)
            # Validate deepl_context_window_size
            if not isinstance(self.deepl_context_window_size, int) or self.deepl_context_window_size < 0 or self.deepl_context_window_size > 3:
                self.deepl_context_window_size = 2
            # Update context manager if it exists
            if hasattr(self, 'deepl_context_manager'):
                self.deepl_context_manager.set_context_size(self.deepl_context_window_size)
            
        except (FileNotFoundError, IOError, PermissionError) as e:
            log_error("Lỗi đọc file cấu hình", e)
            self.log(f"Lỗi đọc file cấu hình: {e}")
        except (json.JSONDecodeError, ValueError) as e:
            log_error("Lỗi parse JSON cấu hình", e)
            self.log(f"Lỗi parse cấu hình (file có thể bị hỏng): {e}")
        except Exception as e:
            log_error("Lỗi tải cấu hình", e)
            self.log(f"Lỗi tải cấu hình: {e}")
    
    def save_config(self):
        """Lưu cấu hình vào file - với error handling đầy đủ"""
        try:
            # Chuẩn hóa đường dẫn Tesseract trước khi lưu
            tesseract_path_to_save = None
            if self.custom_tesseract_path:
                tesseract_path_to_save = os.path.normpath(self.custom_tesseract_path)
            
            config = {
                'capture_region': self.capture_region,
                'source_language': self.source_language,
                'target_language': self.target_language,
                'update_interval': self.update_interval,
                'ocr_engine': self.ocr_engine,
                'easyocr_use_gpu': self.easyocr_use_gpu,
                'easyocr_multi_scale': self.easyocr_multi_scale,
                'tesseract_multi_scale': self.tesseract_multi_scale,
                'tesseract_text_region_detection': self.tesseract_text_region_detection,
                'custom_tesseract_path': tesseract_path_to_save,
                'deepl_api_key': self.deepl_api_key,
                'use_deepl': self.use_deepl,
                'deepl_context_window_size': self.deepl_context_window_size,
                'overlay_settings': {
                    'font_size': self.overlay_font_size,
                    'font_family': self.overlay_font_family,
                    'font_weight': self.overlay_font_weight,
                    'bg_color': self.overlay_bg_color,
                    'text_color': self.overlay_text_color,
                    'original_color': self.overlay_original_color,
                    'transparency': self.overlay_transparency,
                    'width': self.overlay_width,
                    'height': self.overlay_height,
                    'show_original': self.overlay_show_original,
                    'keep_history': self.overlay_keep_history,
                    'text_align': self.overlay_text_align,
                    'line_spacing': self.overlay_line_spacing,
                    'padding_x': self.overlay_padding_x,
                    'padding_y': self.overlay_padding_y,
                    'border_width': self.overlay_border_width,
                    'border_color': self.overlay_border_color,
                    'text_shadow': self.overlay_text_shadow,
                    'word_wrap': self.overlay_word_wrap
                },
                'overlay_position': {
                    'x': self.overlay_position_x,
                    'y': self.overlay_position_y
                },
                'overlay_locked': self.overlay_locked
            }
            # Đảm bảo thư mục tồn tại trước khi ghi
            config_dir = os.path.dirname(self.config_file)
            if config_dir and not os.path.exists(config_dir):
                try:
                    os.makedirs(config_dir, exist_ok=True)
                except Exception as e:
                    log_error(f"Error creating config directory: {config_dir}", e)
                    # Nếu không tạo được thư mục, thử ghi trực tiếp
            
            # Ghi file với error handling
            try:
                with open(self.config_file, 'w', encoding='utf-8', errors='replace') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                    f.flush()  # Force write to disk
            except (IOError, PermissionError, OSError) as file_err:
                log_error("Lỗi ghi file cấu hình (quyền truy cập hoặc I/O)", file_err)
                try:
                    self.log(f"Lỗi lưu cấu hình (quyền truy cập): {file_err}")
                except Exception:
                    pass  # UI log failed, ignore
                return  # Don't continue if file write failed
        except (json.JSONEncodeError, ValueError) as json_err:
            log_error("Lỗi encode JSON cấu hình", json_err)
            try:
                self.log(f"Lỗi lưu cấu hình (JSON error): {json_err}")
            except Exception:
                pass
        except Exception as e:
            log_error("Lỗi lưu cấu hình (unexpected error)", e)
            try:
                self.log(f"Lỗi lưu cấu hình: {e}")
            except Exception:
                pass
    
    def select_region(self):
        """Open region selection window"""
        if self.is_capturing:
            messagebox.showwarning("Cảnh báo", "Vui lòng dừng dịch trước khi chọn vùng mới.")
            return
        
        self.log("Đang chọn vùng... Thu nhỏ cửa sổ này và chọn vùng trên màn hình.")
        self.root.withdraw()  # Hide main window
        
        # Create region selector
        selector = RegionSelector(self.root, self.on_region_selected)
    
    def on_region_selected(self, region):
        """Callback when region is selected"""
        self.capture_region = region
        if region:
            self.region_label.config(
                text=f"Vùng: {region}",
                fg="green"
            )
            self.start_button.config(state=tk.NORMAL)
            self.save_config()
            self.log(f"Đã chọn vùng: {region}")
        else:
            self.region_label.config(
                text="Chưa chọn vùng",
                fg="gray"
            )
            self.start_button.config(state=tk.DISABLED)
        
        self.root.deiconify()  # Show main window again
    
    def on_target_lang_change(self, event=None):
        """Handle target language change"""
        self.target_language = self.target_lang_var.get()
        self.translator = GoogleTranslator(source='auto', target=self.target_language)
        # Clear DeepL context when target language changes
        if hasattr(self, 'deepl_context_manager'):
            self.deepl_context_manager.clear_context()
        self.save_config()
        self.log(f"Đã đổi ngôn ngữ đích: {self.target_language}")
    
    def on_translation_service_change(self, event=None):
        """Handle translation service change"""
        if not hasattr(self, 'translation_service_var'):
            return
        
        service = self.translation_service_var.get()
        old_use_deepl = self.use_deepl
        self.use_deepl = (service == "deepl")
        self.save_config()
        
        # Toggle DeepL widgets visibility
        self.toggle_deepl_widgets()
        
        if self.use_deepl:
            if not self.DEEPL_API_AVAILABLE:
                messagebox.showerror("Lỗi", "DeepL API không khả dụng. Vui lòng cài đặt: pip install deepl")
                self.translation_service_var.set("google")
                self.use_deepl = False
                self.save_config()
                self.toggle_deepl_widgets()
                return
            
            # Lấy API key từ UI nếu có
            if hasattr(self, 'deepl_api_key_var'):
                self.deepl_api_key = self.deepl_api_key_var.get().strip()
            
            if not self.deepl_api_key:
                messagebox.showwarning("Cảnh báo", "Vui lòng nhập DeepL API Key")
                # Không revert về google, để user có thể nhập key
                return
            
            # Initialize DeepL client
            try:
                import deepl
                self.deepl_api_client = deepl.Translator(self.deepl_api_key)
                self.log("Đã chuyển sang DeepL API")
            except Exception as e:
                log_error("Lỗi khởi tạo DeepL khi chuyển dịch vụ", e)
                messagebox.showerror("Lỗi", f"Không thể khởi tạo DeepL: {e}")
                self.translation_service_var.set("google")
                self.use_deepl = False
                self.save_config()
                self.toggle_deepl_widgets()
        else:
            # Chuyển về Google Translate
            if old_use_deepl:
                # Clear DeepL context when switching to Google
                if hasattr(self, 'deepl_context_manager'):
                    self.deepl_context_manager.clear_context()
                self.log("Đã chuyển sang Google Translate")
    
    def toggle_deepl_widgets(self):
        """Ẩn/hiện DeepL widgets dựa vào translation service"""
        if not hasattr(self, 'deepl_widgets'):
            return
        
        # Show widgets nếu chọn DeepL, hide nếu chọn Google
        if self.use_deepl:
            for widget in self.deepl_widgets:
                widget.grid()  # Show widget
        else:
            for widget in self.deepl_widgets:
                widget.grid_remove()  # Hide widget (nhưng giữ nguyên grid config)
    
    def on_deepl_key_change(self, event=None):
        """Handle DeepL API key change"""
        if hasattr(self, 'deepl_api_key_var'):
            self.deepl_api_key = self.deepl_api_key_var.get().strip()
            self.save_config()
            
            # Reinitialize client if using DeepL
            if self.use_deepl and self.deepl_api_key:
                try:
                    self.deepl_api_client = deepl.Translator(self.deepl_api_key)
                    self.log("Đã cập nhật DeepL API Key")
                except Exception as e:
                    log_error("Lỗi khởi tạo DeepL khi cập nhật API key", e)
                    self.log(f"Lỗi khởi tạo DeepL: {e}")
    
    def on_deepl_context_window_change(self, event=None):
        """Handle DeepL context window size change"""
        if hasattr(self, 'deepl_context_window_var'):
            new_size = self.deepl_context_window_var.get()
            if new_size != self.deepl_context_window_size:
                self.deepl_context_window_size = new_size
                self.deepl_context_manager.set_context_size(new_size)
                self.save_config()
                self.log(f"Đã thay đổi DeepL context window size: {new_size}")
    
    def on_source_lang_change(self, event=None):
        """Handle source language change"""
        self.source_language = self.source_lang_var.get()
        # Clear DeepL context when source language changes
        if hasattr(self, 'deepl_context_manager'):
            self.deepl_context_manager.clear_context()
        self.save_config()
        self.log(f"Đã thay đổi ngôn ngữ nguồn thành: {self.source_language}")
        
        # Cập nhật handlers với ngôn ngữ mới
        if self.tesseract_handler:
            self.tesseract_handler.set_source_language(self.source_language)
        # Khởi tạo lại Tesseract handler với options mới nếu cần
        if self.ocr_engine == "tesseract" and HANDLERS_AVAILABLE:
            try:
                self.tesseract_handler = TesseractOCRHandler(
                    source_language=self.source_language,
                    enable_multi_scale=self.tesseract_multi_scale,
                    enable_text_region_detection=self.tesseract_text_region_detection
                )
            except Exception as e:
                log_error("Lỗi khởi tạo Tesseract handler khi đổi ngôn ngữ", e)
        if self.easyocr_handler:
            self.easyocr_handler.set_source_language(self.source_language)
        
        # Fallback: khởi tạo lại EasyOCR reader nếu đang dùng EasyOCR và không có handler
        if self.ocr_engine == "easyocr" and self.EASYOCR_AVAILABLE:
            if HANDLERS_AVAILABLE and not self.easyocr_handler:
                try:
                    self.easyocr_handler = EasyOCRHandler(
                        source_language=self.source_language,
                        use_gpu=self.easyocr_use_gpu,
                        enable_multi_scale=self.easyocr_multi_scale
                    )
                except Exception as e:
                    log_error("Lỗi khởi tạo EasyOCR handler khi đổi ngôn ngữ", e)
                    # Nếu handler khởi tạo thất bại, fallback về reader cũ
                    self.easyocr_handler = None
                    self.easyocr_reader = None  # Reset để khởi tạo lại với ngôn ngữ mới
                    self.initialize_easyocr_reader()
            elif not HANDLERS_AVAILABLE:
                self.easyocr_reader = None  # Reset để khởi tạo lại với ngôn ngữ mới
                self.initialize_easyocr_reader()
    
    def clear_translation_history(self):
        """Xóa toàn bộ lịch sử dịch trong overlay"""
        try:
            if hasattr(self, 'translation_text') and self.translation_text:
                self.translation_text.config(state=tk.NORMAL)
                self.translation_text.delete('1.0', tk.END)
                self.translation_text.insert('1.0', "Đã xóa lịch sử. Đang chờ văn bản mới...")
                self.translation_text.config(state=tk.DISABLED)
                self.translation_text.see('1.0')
            elif hasattr(self, 'translation_label') and self.translation_label:
                self.translation_label.config(text="Đã xóa lịch sử. Đang chờ văn bản mới...")
            
        except Exception as e:
            log_error("Error clearing translation history", e)
    
    def on_ocr_engine_change(self, event=None):
        """Callback khi người dùng thay đổi OCR engine"""
        if not hasattr(self, 'ocr_engine_var'):
            return
        
        new_engine = self.ocr_engine_var.get()
        if new_engine != self.ocr_engine:
            old_engine = self.ocr_engine
            self.ocr_engine = new_engine
            self.save_config()
            self.log(f"Đã thay đổi OCR engine từ {old_engine} sang {self.ocr_engine}")
            
            # Hiển thị/ẩn Tesseract path dựa trên engine được chọn
            self.update_ocr_engine_ui()
            
            # Khởi tạo lại OCR engine nếu cần
            if self.ocr_engine == "tesseract" and HANDLERS_AVAILABLE:
                # Khởi tạo lại Tesseract handler với options
                try:
                    self.tesseract_handler = TesseractOCRHandler(
                        source_language=self.source_language,
                        enable_multi_scale=self.tesseract_multi_scale,
                        enable_text_region_detection=self.tesseract_text_region_detection
                    )
                    self.log("Đã khởi tạo lại Tesseract handler")
                except Exception as e:
                    log_error("Lỗi khởi tạo Tesseract handler khi chuyển engine", e)
            elif self.ocr_engine == "easyocr" and self.EASYOCR_AVAILABLE:
                # Khởi tạo handler với GPU option nếu dùng handlers
                if HANDLERS_AVAILABLE:
                    try:
                        if self.easyocr_handler:
                            self.easyocr_handler = None  # Reset để khởi tạo lại với GPU option mới
                        self.easyocr_handler = EasyOCRHandler(
                            source_language=self.source_language,
                            use_gpu=self.easyocr_use_gpu
                        )
                    except Exception as e:
                        log_error(f"Lỗi khởi tạo EasyOCR handler khi chuyển engine", e)
                        self.log(f"Lỗi khởi tạo EasyOCR handler: {e}. Sẽ dùng fallback reader.")
                        # Nếu handler khởi tạo thất bại, fallback về reader cũ
                        self.easyocr_handler = None
                        # Reset reader cũ nếu có
                        if hasattr(self, 'easyocr_reader'):
                            self.easyocr_reader = None
                        self.initialize_easyocr_reader()
                # Hoặc khởi tạo reader trực tiếp nếu không dùng handlers
                else:
                    # Reset reader cũ nếu có
                    if hasattr(self, 'easyocr_reader') and old_engine == "easyocr":
                        self.easyocr_reader = None
                    self.initialize_easyocr_reader()
            elif self.ocr_engine == "tesseract" and old_engine == "easyocr":
                # Giải phóng EasyOCR reader khi chuyển về Tesseract (chỉ nếu không dùng handlers)
                if not self.easyocr_handler and hasattr(self, 'easyocr_reader'):
                    self.easyocr_reader = None
                    self.log("Đã giải phóng EasyOCR reader")
    
    def update_ocr_engine_ui(self):
        """Cập nhật UI dựa trên OCR engine được chọn"""
        if hasattr(self, 'tesseract_path_label_frame') and hasattr(self, 'tesseract_path_label_widget'):
            if self.ocr_engine == "tesseract":
                # Hiển thị Tesseract path và options
                self.tesseract_path_label_widget.grid()
                self.tesseract_path_label_frame.grid()
                if hasattr(self, 'tesseract_options_frame'):
                    self.tesseract_options_frame.grid()
                # Ẩn EasyOCR GPU option và Multi-scale option
                if hasattr(self, 'easyocr_gpu_frame'):
                    self.easyocr_gpu_frame.grid_remove()
                if hasattr(self, 'easyocr_multi_scale_frame'):
                    self.easyocr_multi_scale_frame.grid_remove()
            else:
                # Ẩn Tesseract path và options khi dùng EasyOCR
                self.tesseract_path_label_widget.grid_remove()
                self.tesseract_path_label_frame.grid_remove()
                if hasattr(self, 'tesseract_options_frame'):
                    self.tesseract_options_frame.grid_remove()
                # Hiển thị EasyOCR GPU option và Multi-scale option
                if hasattr(self, 'easyocr_gpu_frame'):
                    self.easyocr_gpu_frame.grid()
                if hasattr(self, 'easyocr_multi_scale_frame'):
                    self.easyocr_multi_scale_frame.grid()
    
    def on_easyocr_gpu_change(self):
        """Callback khi người dùng thay đổi GPU option"""
        if not hasattr(self, 'easyocr_gpu_var'):
            return
        
        gpu_option = self.easyocr_gpu_var.get()
        if gpu_option == "auto":
            self.easyocr_use_gpu = None
        elif gpu_option == "cpu":
            self.easyocr_use_gpu = False
        elif gpu_option == "gpu":
            self.easyocr_use_gpu = True
        
        self.save_config()
        
        # Nếu đang dùng EasyOCR và reader đã được khởi tạo, cần khởi tạo lại
        if self.ocr_engine == "easyocr" and self.EASYOCR_AVAILABLE:
            # Reset handler và reader để khởi tạo lại với GPU option mới
            if HANDLERS_AVAILABLE:
                try:
                    if self.easyocr_handler:
                        self.easyocr_handler = None
                    # Khởi tạo lại handler với GPU option mới
                    self.easyocr_handler = EasyOCRHandler(
                        source_language=self.source_language,
                        use_gpu=self.easyocr_use_gpu,
                        enable_multi_scale=self.easyocr_multi_scale
                    )
                    self.log(f"Đã thay đổi EasyOCR mode: {gpu_option}. Handler đã được khởi tạo lại.")
                except Exception as e:
                    log_error(f"Lỗi khởi tạo EasyOCR handler với GPU option {gpu_option}", e)
                    self.log(f"Lỗi khởi tạo EasyOCR handler: {e}. Sẽ dùng fallback reader.")
                    # Nếu handler khởi tạo thất bại, fallback về reader cũ
                    self.easyocr_handler = None
                    if hasattr(self, 'easyocr_reader'):
                        self.easyocr_reader = None
                    self.initialize_easyocr_reader()
                    self.log(f"Đã thay đổi EasyOCR mode: {gpu_option}. Fallback reader sẽ được khởi tạo lại.")
            else:
                # Không dùng handlers, reset reader cũ
                if hasattr(self, 'easyocr_reader'):
                    self.easyocr_reader = None
                self.initialize_easyocr_reader()
                self.log(f"Đã thay đổi EasyOCR mode: {gpu_option}. Reader sẽ được khởi tạo lại.")
    
    def on_easyocr_multi_scale_change(self):
        """Callback khi người dùng thay đổi Multi-scale option"""
        if not hasattr(self, 'easyocr_multi_scale_var'):
            return
        
        self.easyocr_multi_scale = self.easyocr_multi_scale_var.get()
        self.save_config()
        
        # Nếu đang dùng EasyOCR và handler đã được khởi tạo, cần khởi tạo lại
        if self.ocr_engine == "easyocr" and self.EASYOCR_AVAILABLE:
            if HANDLERS_AVAILABLE:
                try:
                    if self.easyocr_handler:
                        # Cập nhật multi-scale setting trong handler hiện tại
                        self.easyocr_handler.enable_multi_scale = self.easyocr_multi_scale
                        self.log(f"Đã {'bật' if self.easyocr_multi_scale else 'tắt'} Multi-scale cho EasyOCR.")
                    else:
                        # Nếu chưa có handler, khởi tạo mới
                        self.easyocr_handler = EasyOCRHandler(
                            source_language=self.source_language,
                            use_gpu=self.easyocr_use_gpu,
                            enable_multi_scale=self.easyocr_multi_scale
                        )
                        self.log(f"Đã khởi tạo EasyOCR handler với Multi-scale: {self.easyocr_multi_scale}.")
                except Exception as e:
                    log_error(f"Lỗi cập nhật EasyOCR Multi-scale setting", e)
                    self.log(f"Lỗi cập nhật Multi-scale: {e}.")
    
    def on_tesseract_multi_scale_change(self):
        """Callback khi người dùng thay đổi Tesseract Multi-scale option"""
        if not hasattr(self, 'tesseract_multi_scale_var'):
            return
        
        self.tesseract_multi_scale = self.tesseract_multi_scale_var.get()
        self.save_config()
        
        # Nếu đang dùng Tesseract và handler đã được khởi tạo, cập nhật setting
        if self.ocr_engine == "tesseract" and HANDLERS_AVAILABLE:
            try:
                if self.tesseract_handler:
                    # Cập nhật multi-scale setting trong handler hiện tại
                    self.tesseract_handler.enable_multi_scale = self.tesseract_multi_scale
                    self.log(f"Đã {'bật' if self.tesseract_multi_scale else 'tắt'} Multi-scale cho Tesseract.")
                else:
                    # Nếu chưa có handler, khởi tạo mới
                    self.tesseract_handler = TesseractOCRHandler(
                        source_language=self.source_language,
                        enable_multi_scale=self.tesseract_multi_scale,
                        enable_text_region_detection=self.tesseract_text_region_detection
                    )
                    self.log(f"Đã khởi tạo Tesseract handler với Multi-scale: {self.tesseract_multi_scale}.")
            except Exception as e:
                log_error(f"Lỗi cập nhật Tesseract Multi-scale setting", e)
                self.log(f"Lỗi cập nhật Multi-scale: {e}.")
    
    def on_tesseract_text_region_change(self):
        """Callback khi người dùng thay đổi Tesseract Text Region Detection option"""
        if not hasattr(self, 'tesseract_text_region_var'):
            return
        
        self.tesseract_text_region_detection = self.tesseract_text_region_var.get()
        self.save_config()
        
        # Nếu đang dùng Tesseract và handler đã được khởi tạo, cập nhật setting
        if self.ocr_engine == "tesseract" and HANDLERS_AVAILABLE:
            try:
                if self.tesseract_handler:
                    # Cập nhật text region detection setting trong handler hiện tại
                    self.tesseract_handler.enable_text_region_detection = self.tesseract_text_region_detection
                    self.log(f"Đã {'bật' if self.tesseract_text_region_detection else 'tắt'} Text Region Detection cho Tesseract.")
                else:
                    # Nếu chưa có handler, khởi tạo mới
                    self.tesseract_handler = TesseractOCRHandler(
                        source_language=self.source_language,
                        enable_multi_scale=self.tesseract_multi_scale,
                        enable_text_region_detection=self.tesseract_text_region_detection
                    )
                    self.log(f"Đã khởi tạo Tesseract handler với Text Region Detection: {self.tesseract_text_region_detection}.")
            except Exception as e:
                log_error(f"Lỗi cập nhật Tesseract Text Region Detection setting", e)
                self.log(f"Lỗi cập nhật Text Region Detection: {e}.")
    
    def initialize_easyocr_reader(self):
        """Khởi tạo EasyOCR reader (lazy initialization) - chỉ dùng khi không có handlers"""
        if not self.EASYOCR_AVAILABLE:
            return None
        
        # Chỉ khởi tạo nếu không dùng handlers
        if self.easyocr_handler:
            return None
        
        # Đảm bảo easyocr_reader attribute tồn tại
        if not hasattr(self, 'easyocr_reader'):
            self.easyocr_reader = None
        
        if self.easyocr_reader is None:
            try:
                # Map source language to EasyOCR language codes
                lang_map = {
                    "eng": "en",
                    "jpn": "ja",
                    "kor": "ko",
                    "chi_sim": "ch_sim",
                    "chi_tra": "ch_tra",
                    "fra": "fr",
                    "deu": "de",
                    "spa": "es"
                }
                easyocr_lang = lang_map.get(self.source_language, "en")
                
                self.log(f"Đang khởi tạo EasyOCR reader với ngôn ngữ: {easyocr_lang}...")
                
                # Suppress warnings khi khởi tạo EasyOCR
                import os
                import sys
                from io import StringIO
                
                # Lưu stderr hiện tại
                old_stderr = sys.stderr
                
                try:
                    # Redirect stderr tạm thời để suppress warnings
                    sys.stderr = StringIO()
                    
                    with warnings.catch_warnings():
                        warnings.filterwarnings('ignore', category=UserWarning)
                        warnings.filterwarnings('ignore', message='.*Using CPU.*')
                        warnings.filterwarnings('ignore', message='.*pin_memory.*')
                        warnings.filterwarnings('ignore', module='torch')
                        warnings.filterwarnings('ignore')
                        
                        # Set environment variable để suppress PyTorch warnings
                        os.environ['PYTHONWARNINGS'] = 'ignore'
                        
                        import easyocr
                        
                        # Determine GPU usage based on user preference
                        use_gpu = False
                        gpu_name = None
                        gpu_debug = ""
                        
                        if self.easyocr_use_gpu is True:
                            # Force GPU mode
                            try:
                                import torch
                                if torch.cuda.is_available():
                                    use_gpu = True
                                    gpu_name = torch.cuda.get_device_name(0)
                                    gpu_debug = f"GPU mode forced by user: {gpu_name}"
                                    log_error(f"[INFO] {gpu_debug}")
                                    self.log(f"GPU mode forced: {gpu_name}")
                                else:
                                    gpu_debug = "GPU mode requested but GPU not available. Falling back to CPU."
                                    log_error(f"[WARNING] {gpu_debug}")
                                    self.log("GPU requested but not available. Using CPU mode.")
                            except Exception as e:
                                gpu_debug = f"Error checking GPU: {str(e)}"
                                log_error(f"[WARNING] {gpu_debug}")
                        elif self.easyocr_use_gpu is False:
                            # Force CPU mode
                            use_gpu = False
                            gpu_debug = "CPU mode forced by user"
                            log_error(f"[INFO] {gpu_debug}")
                            self.log("CPU mode forced by user")
                        else:
                            # Auto-detect (default)
                            try:
                                import torch
                                gpu_debug = f"PyTorch version: {torch.__version__}"
                                
                                if torch.cuda.is_available():
                                    use_gpu = True
                                    gpu_name = torch.cuda.get_device_name(0)
                                    cuda_version = getattr(torch.version, 'cuda', 'Unknown')
                                    device_count = torch.cuda.device_count()
                                    gpu_debug += f", CUDA: {cuda_version}, Devices: {device_count}, GPU: {gpu_name}"
                                    log_error(f"[INFO] GPU auto-detected: {gpu_name}. EasyOCR will use GPU mode.")
                                    self.log(f"GPU auto-detected: {gpu_name}. EasyOCR will use GPU mode.")
                                else:
                                    cuda_version = getattr(torch.version, 'cuda', None)
                                    if cuda_version:
                                        gpu_debug += f", CUDA version: {cuda_version}, but torch.cuda.is_available() = False"
                                    else:
                                        gpu_debug += ", PyTorch installed without CUDA support"
                                    log_error(f"[INFO] No GPU detected. {gpu_debug}")
                                    self.log("No GPU detected. EasyOCR will use CPU mode.")
                            except ImportError:
                                gpu_debug = "PyTorch not installed"
                                log_error(f"[INFO] {gpu_debug}. EasyOCR will use CPU mode.")
                                self.log("PyTorch not available for GPU detection. EasyOCR will use CPU mode.")
                            except Exception as e:
                                gpu_debug = f"Error: {str(e)}"
                                log_error(f"[INFO] GPU detection error: {gpu_debug}. EasyOCR will use CPU mode.")
                                self.log("GPU detection error. EasyOCR will use CPU mode.")
                        
                        # Tối ưu cho long sessions: reuse reader, không reload model
                        self.easyocr_reader = easyocr.Reader(
                            [easyocr_lang], 
                            gpu=use_gpu, 
                            verbose=False,
                            download_enabled=False  # Không download lại nếu đã có
                        )
                        
                        if use_gpu:
                            log_error(f"[INFO] EasyOCR initialized with GPU acceleration ({gpu_name})")
                            self.log(f"EasyOCR initialized with GPU acceleration ({gpu_name})")
                        else:
                            log_error("[INFO] EasyOCR initialized with CPU mode")
                            self.log("EasyOCR initialized with CPU mode")
                finally:
                    # Khôi phục stderr
                    sys.stderr = old_stderr
                
                self.log("EasyOCR reader đã được khởi tạo thành công!")
            except Exception as e:
                log_error("Lỗi khởi tạo EasyOCR reader", e)
                self.log(f"Lỗi khởi tạo EasyOCR: {e}")
                return None
        
        return self.easyocr_reader
    
    def on_interval_change(self, event=None):
        """Handle update interval change"""
        try:
            interval_ms = int(self.interval_var.get())
            self.update_interval = interval_ms / 1000.0
            # Update adaptive scan interval base
            self.base_scan_interval = int(self.update_interval * 1000)
            if not self.overload_detected:
                self.current_scan_interval = self.base_scan_interval
            self.save_config()
            self.log(f"Đã thay đổi khoảng thời gian cập nhật thành: {interval_ms}ms")
        except ValueError as e:
            log_error("Invalid update interval value", e)
            self.log("Giá trị khoảng thời gian không hợp lệ")
    
    def apply_preset(self, preset_type):
        """Apply preset configuration based on performance level - deeply tuned for translation speed"""
        if preset_type == 'speed':
            # Speed optimized: minimal UI processing, fastest updates, minimal visual effects
            # Also update interval for maximum speed
            self.update_interval = 0.1  # 100ms for fastest updates
            self.base_scan_interval = int(self.update_interval * 1000)
            if not self.overload_detected:
                self.current_scan_interval = self.base_scan_interval
            # Sync với Tab Cài Đặt - cập nhật interval_var nếu đã được tạo
            if hasattr(self, 'interval_var'):
                self.interval_var.set("100")
            
            self.font_size_var.set("13")
            self.transparency_var.set("92")
            self.width_var.set("420")
            self.height_var.set("220")
            self.text_color_var.set("#ffffff")  # White for fast reading
            self.bg_color_var.set("#000000")
            self.original_color_var.set("#888888")
            self.show_original_var.set(False)  # Hide original to reduce rendering
            self.text_align_var.set("left")
            self.font_family_var.set("Arial")  # Fast rendering font
            self.font_weight_var.set("normal")  # Normal weight is faster
            self.line_spacing_var.set("1.1")  # Tighter spacing
            self.padding_x_var.set("12")
            self.padding_y_var.set("12")
            self.border_width_var.set("0")  # No border for speed
            self.border_color_var.set("#ffffff")
            self.word_wrap_var.set(True)
            self.keep_history_var.set(False)  # No history for speed
            # Không save config và không apply ngay - chỉ set giá trị vào UI vars
            self.log("Đã chọn cấu hình: Tối Ưu Tốc Độ. Nhấn 'Áp Dụng' để áp dụng.")
        elif preset_type == 'balanced':
            # Balanced: good quality and speed - optimized for most games
            self.update_interval = 0.15  # 150ms for balanced speed
            self.base_scan_interval = int(self.update_interval * 1000)
            if not self.overload_detected:
                self.current_scan_interval = self.base_scan_interval
            # Sync với Tab Cài Đặt - cập nhật interval_var nếu đã được tạo
            if hasattr(self, 'interval_var'):
                self.interval_var.set("150")
            
            self.font_size_var.set("15")
            self.transparency_var.set("88")
            self.width_var.set("500")
            self.height_var.set("280")
            self.text_color_var.set("#ffffff")  # White for readability
            self.bg_color_var.set("#1a1a1a")
            self.original_color_var.set("#cccccc")
            self.show_original_var.set(True)
            self.text_align_var.set("left")
            self.font_family_var.set("Arial")
            self.font_weight_var.set("normal")
            self.line_spacing_var.set("1.3")
            self.padding_x_var.set("18")
            self.padding_y_var.set("18")
            self.border_width_var.set("0")
            self.border_color_var.set("#ffffff")
            self.word_wrap_var.set(True)
            self.keep_history_var.set(False)  # No history for balanced
            # Không save config và không apply ngay - chỉ set giá trị vào UI vars
            self.log("Đã chọn cấu hình: Cân Bằng. Nhấn 'Áp Dụng' để áp dụng.")
        elif preset_type == 'quality':
            # Quality optimized: best readability, slightly slower for accuracy
            self.update_interval = 0.2  # 200ms for quality (default)
            self.base_scan_interval = int(self.update_interval * 1000)
            if not self.overload_detected:
                self.current_scan_interval = self.base_scan_interval
            # Sync với Tab Cài Đặt - cập nhật interval_var nếu đã được tạo
            if hasattr(self, 'interval_var'):
                self.interval_var.set("200")
            
            self.font_size_var.set("16")
            self.transparency_var.set("85")
            self.width_var.set("550")
            self.height_var.set("320")
            self.text_color_var.set("#ffffff")
            self.bg_color_var.set("#1a1a1a")
            self.original_color_var.set("#dddddd")
            self.show_original_var.set(True)
            self.text_align_var.set("left")
            self.font_family_var.set("Segoe UI")
            self.font_weight_var.set("bold")
            self.line_spacing_var.set("1.4")
            self.padding_x_var.set("20")
            self.padding_y_var.set("20")
            self.border_width_var.set("1")
            self.border_color_var.set("#ffffff")
            self.word_wrap_var.set(True)
            self.keep_history_var.set(False)  # No history for quality
            # Không save config và không apply ngay - chỉ set giá trị vào UI vars
            self.log("Đã chọn cấu hình: Tối Ưu Chất Lượng. Nhấn 'Áp Dụng' để áp dụng.")
        elif preset_type == 'default':
            # Default settings (optimized defaults)
            self.update_interval = 0.2  # 200ms default
            self.base_scan_interval = int(self.update_interval * 1000)
            if not self.overload_detected:
                self.current_scan_interval = self.base_scan_interval
            # Sync với Tab Cài Đặt - cập nhật interval_var nếu đã được tạo
            if hasattr(self, 'interval_var'):
                self.interval_var.set("200")
            
            self.font_size_var.set("15")
            self.transparency_var.set("88")
            self.width_var.set("500")
            self.height_var.set("280")
            self.text_color_var.set("#ffffff")  # White text
            self.bg_color_var.set("#1a1a1a")  # Dark background
            self.original_color_var.set("#cccccc")
            self.show_original_var.set(True)
            self.text_align_var.set("left")
            self.font_family_var.set("Arial")
            self.font_weight_var.set("normal")
            self.line_spacing_var.set("1.3")
            self.padding_x_var.set("18")
            self.padding_y_var.set("18")
            self.border_width_var.set("0")
            self.border_color_var.set("#ffffff")
            self.word_wrap_var.set(True)
            self.keep_history_var.set(False)  # No history for default
            # Không save config và không apply ngay - chỉ set giá trị vào UI vars
            self.log("Đã chọn cấu hình: Mặc Định. Nhấn 'Áp Dụng' để áp dụng.")
    
    def reset_all_settings(self):
        """Reset all settings to defaults except OCR engine, translation service, and DeepL key"""
        try:
            # Reset update interval to default (200ms)
            self.update_interval = 0.2
            self.base_scan_interval = int(self.update_interval * 1000)  # 200ms
            if not self.overload_detected:
                self.current_scan_interval = self.base_scan_interval
            
            # Reset source and target languages to defaults
            self.source_language = "eng"
            self.target_language = "vi"
            
            # KHÔNG reset capture region - giữ nguyên vùng đã chọn
            
            # Reset Tesseract path (người dùng cần chọn lại nếu cần)
            self.custom_tesseract_path = None
            # Reset pytesseract path về auto-detect
            try:
                pytesseract.pytesseract.tesseract_cmd = None
            except Exception as e:
                log_error("Error resetting Tesseract path", e)
            
            # Reset to default values (optimized defaults)
            self.overlay_font_size = 15
            self.overlay_font_family = "Arial"
            self.overlay_font_weight = "normal"
            self.overlay_bg_color = "#1a1a1a"
            self.overlay_text_color = "#ffffff"  # White text
            self.overlay_original_color = "#cccccc"
            self.overlay_transparency = 0.88
            self.overlay_width = 500
            self.overlay_height = 280
            self.overlay_show_original = True
            self.overlay_text_align = "left"
            self.overlay_line_spacing = 1.3
            self.overlay_padding_x = 18
            self.overlay_padding_y = 18
            self.overlay_border_width = 0
            self.overlay_border_color = "#ffffff"
            self.overlay_word_wrap = True
            self.overlay_keep_history = False
            
            # Reset overlay position to None (will use original position calculation)
            self.overlay_position_x = None
            self.overlay_position_y = None
            
            # Update UI variables
            if hasattr(self, 'interval_var'):
                self.interval_var.set("200")  # Reset update interval to 200ms
            if hasattr(self, 'source_lang_var'):
                self.source_lang_var.set(self.source_language)
            if hasattr(self, 'target_lang_var'):
                self.target_lang_var.set(self.target_language)
            # Cập nhật translator với target language mới
            try:
                self.translator = GoogleTranslator(source='auto', target=self.target_language)
            except Exception as e:
                log_error("Error updating translator after reset", e)
            # Cập nhật handlers với source language mới
            if self.tesseract_handler:
                try:
                    self.tesseract_handler.set_source_language(self.source_language)
                except Exception as e:
                    log_error("Error updating Tesseract handler after reset", e)
            # Khởi tạo lại Tesseract handler với options mới
            if self.ocr_engine == "tesseract" and HANDLERS_AVAILABLE:
                try:
                    self.tesseract_handler = TesseractOCRHandler(
                        source_language=self.source_language,
                        enable_multi_scale=self.tesseract_multi_scale,
                        enable_text_region_detection=self.tesseract_text_region_detection
                    )
                except Exception as e:
                    log_error("Error reinitializing Tesseract handler after reset", e)
            if self.easyocr_handler:
                try:
                    self.easyocr_handler.set_source_language(self.source_language)
                except Exception as e:
                    log_error("Error updating EasyOCR handler after reset", e)
            # Cập nhật Tesseract path display
            if hasattr(self, 'tesseract_path_label'):
                try:
                    self.tesseract_path_label.config(
                        text="Đường dẫn: Tự động phát hiện (PATH)",
                        fg="green"
                    )
                except Exception as e:
                    log_error("Error updating Tesseract path label after reset", e)
            if hasattr(self, 'font_size_var'):
                self.font_size_var.set(str(self.overlay_font_size))
            if hasattr(self, 'font_family_var'):
                self.font_family_var.set(self.overlay_font_family)
            if hasattr(self, 'font_weight_var'):
                self.font_weight_var.set(self.overlay_font_weight)
            if hasattr(self, 'bg_color_var'):
                self.bg_color_var.set(self.overlay_bg_color)
            if hasattr(self, 'text_color_var'):
                self.text_color_var.set(self.overlay_text_color)
            if hasattr(self, 'original_color_var'):
                self.original_color_var.set(self.overlay_original_color)
            if hasattr(self, 'transparency_var'):
                self.transparency_var.set(str(int(self.overlay_transparency * 100)))
            if hasattr(self, 'width_var'):
                self.width_var.set(str(self.overlay_width))
            if hasattr(self, 'height_var'):
                self.height_var.set(str(self.overlay_height))
            if hasattr(self, 'show_original_var'):
                self.show_original_var.set(self.overlay_show_original)
            if hasattr(self, 'text_align_var'):
                self.text_align_var.set(self.overlay_text_align)
            if hasattr(self, 'line_spacing_var'):
                self.line_spacing_var.set(str(self.overlay_line_spacing))
            if hasattr(self, 'padding_x_var'):
                self.padding_x_var.set(str(self.overlay_padding_x))
            if hasattr(self, 'padding_y_var'):
                self.padding_y_var.set(str(self.overlay_padding_y))
            if hasattr(self, 'border_width_var'):
                self.border_width_var.set(str(self.overlay_border_width))
            if hasattr(self, 'border_color_var'):
                self.border_color_var.set(self.overlay_border_color)
            if hasattr(self, 'word_wrap_var'):
                self.word_wrap_var.set(self.overlay_word_wrap)
            if hasattr(self, 'keep_history_var'):
                self.keep_history_var.set(self.overlay_keep_history)
            
            # Tạo lại overlay nếu có để áp dụng reset vị trí
            if self.overlay_window:
                try:
                    self.create_overlay()
                except Exception as e:
                    log_error("Error recreating overlay after reset", e)
            
            self.log("Đã đặt lại tất cả cài đặt về mặc định (trừ Engine OCR, Dịch vụ dịch, DeepL key và vùng capture)")
            messagebox.showinfo(
                "Thành công", 
                "Đã đặt lại tất cả cài đặt về mặc định.\n\n"
                "Không reset:\n"
                "- Engine OCR (giữ nguyên)\n"
                "- Dịch vụ dịch (giữ nguyên)\n"
                "- DeepL API Key (giữ nguyên)\n"
                "- Vùng chụp màn hình (giữ nguyên)\n\n"
                "Nhấn 'Áp Dụng' để áp dụng thay đổi."
            )
        except Exception as e:
            log_error("Error resetting settings", e)
            self.log(f"Lỗi khi đặt lại cài đặt: {e}")
    
    def apply_overlay_settings(self):
        """Apply overlay settings when Apply button is clicked"""
        try:
            # Lưu text hiện tại nếu overlay đang hiển thị
            current_translation = ""
            current_original = ""
            if self.overlay_window:
                try:
                    # Lưu vị trí hiện tại trước khi tạo lại
                    self.overlay_position_x = self.overlay_window.winfo_x()
                    self.overlay_position_y = self.overlay_window.winfo_y()
                    
                    # Lưu text hiện tại nếu có
                    if hasattr(self, 'translation_text') and self.translation_text:
                        try:
                            current_translation = self.translation_text.get('1.0', tk.END).strip()
                        except Exception as e:
                            log_error("Error reading translation text from overlay", e)
                    if hasattr(self, 'original_label') and self.original_label:
                        try:
                            original_text = self.original_label.cget('text')
                            if original_text.startswith("Nguyên bản: "):
                                current_original = original_text[12:]  # Remove "Nguyên bản: " prefix
                        except Exception as e:
                            log_error("Error reading original text from overlay", e)
                except Exception as e:
                    log_error("Error reading overlay content", e)
            
            # Update font settings
            self.overlay_font_size = int(self.font_size_var.get())
            self.overlay_font_family = self.font_family_var.get()
            self.overlay_font_weight = self.font_weight_var.get()
            
            # Update transparency
            transparency_percent = int(self.transparency_var.get())
            self.overlay_transparency = transparency_percent / 100.0
            
            # Update dimensions
            self.overlay_width = int(self.width_var.get())
            self.overlay_height = int(self.height_var.get())
            
            # Update colors
            self.overlay_text_color = self.text_color_var.get()
            self.overlay_bg_color = self.bg_color_var.get()
            self.overlay_original_color = self.original_color_var.get()
            self.overlay_border_color = self.border_color_var.get()
            
            # Update spacing and padding
            self.overlay_line_spacing = float(self.line_spacing_var.get())
            self.overlay_padding_x = int(self.padding_x_var.get())
            self.overlay_padding_y = int(self.padding_y_var.get())
            
            # Update border
            self.overlay_border_width = int(self.border_width_var.get())
            
            # Update checkboxes
            self.overlay_show_original = self.show_original_var.get()
            self.overlay_text_shadow = False  # Đã xóa option, luôn False
            self.overlay_word_wrap = self.word_wrap_var.get()
            self.overlay_keep_history = self.keep_history_var.get()
            
            # Update text alignment
            self.overlay_text_align = self.text_align_var.get()
            
            # Lưu config
            self.save_config()
            
            # Tạo lại overlay nếu có (vị trí sẽ được giữ)
            if self.overlay_window:
                self.create_overlay()
                # Khôi phục text nếu có
                if current_translation and current_translation != "Đang chờ văn bản...":
                    self.update_overlay(current_original, current_translation)
            
            self.log("Đã áp dụng cài đặt giao diện")
        except ValueError as e:
            log_error("Invalid overlay setting value", e)
            self.log(f"Giá trị cài đặt giao diện không hợp lệ: {e}")
    
    def start_translation(self):
        """Start the translation process với 3 threads riêng biệt"""
        if not self.capture_region:
            try:
                messagebox.showerror("Lỗi", "Vui lòng chọn vùng chụp màn hình trước.")
            except Exception as e:
                log_error("Error showing messagebox", e)
            return
        
        # Check if Tesseract is ready (if using Tesseract engine)
        if not self.ensure_tesseract_ready():
            return
        
        self.is_capturing = True
        self.is_running = True  # Flag cho threads
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        
        # Reset counters
        self.batch_sequence_counter = 0
        self.translation_sequence_counter = 0
        self.last_displayed_batch_sequence = 0
        self.last_displayed_translation_sequence = 0
        self.active_ocr_calls.clear()
        self.active_translation_calls.clear()
        self.last_easyocr_call_time = 0.0  # Reset EasyOCR throttle
        
        # Clear queues
        while not self.ocr_queue.empty():
            try:
                self.ocr_queue.get_nowait()
            except queue.Empty:
                break
        while not self.translation_queue.empty():
            try:
                self.translation_queue.get_nowait()
            except queue.Empty:
                break
        
        # Create overlay window
        self.create_overlay()
        
        # Điều chỉnh thread pool dựa trên OCR engine (EasyOCR cần ít workers hơn)
        if self.ocr_engine == "easyocr":
            # EasyOCR: giảm workers để giảm CPU (rất nặng)
            ocr_workers = 2
            if hasattr(self.ocr_thread_pool, '_max_workers') and self.ocr_thread_pool._max_workers != ocr_workers:
                self.ocr_thread_pool.shutdown(wait=False)
                self.ocr_thread_pool = ThreadPoolExecutor(max_workers=ocr_workers, thread_name_prefix="OCR")
        else:
            # Tesseract: có thể nhiều workers hơn (nhẹ hơn)
            ocr_workers = 8
            if hasattr(self.ocr_thread_pool, '_max_workers') and self.ocr_thread_pool._max_workers != ocr_workers:
                self.ocr_thread_pool.shutdown(wait=False)
                self.ocr_thread_pool = ThreadPoolExecutor(max_workers=ocr_workers, thread_name_prefix="OCR")
        
        # Start 3 threads riêng biệt
        self.capture_thread = threading.Thread(target=self.run_capture_thread, daemon=True)
        self.ocr_thread = threading.Thread(target=self.run_ocr_thread, daemon=True)
        self.translation_thread = threading.Thread(target=self.run_translation_thread, daemon=True)
        
        self.capture_thread.start()
        self.ocr_thread.start()
        self.translation_thread.start()
        
        self.log("Đã bắt đầu dịch với kiến trúc đa luồng!")
    
    def stop_translation(self):
        """Stop the translation process - dừng tất cả 3 threads"""
        self.is_capturing = False
        self.is_running = False  # Signal tất cả threads dừng
        
        # Wait for threads to finish
        threads_to_join = [self.capture_thread, self.ocr_thread, self.translation_thread]
        for thread in threads_to_join:
            if thread and thread.is_alive():
                try:
                    thread.join(timeout=1.0)
                except Exception as e:
                    log_error("Error joining thread", e)
        
        # Shutdown thread pools
        try:
            self.ocr_thread_pool.shutdown(wait=False)
            self.translation_thread_pool.shutdown(wait=False)
        except Exception as e:
            log_error("Error shutting down thread pools", e)
        
        # Giải phóng OCR engines với suppress warnings
        # Cleanup handlers nếu có
        if self.easyocr_handler:
            try:
                self.easyocr_handler.cleanup()
            except Exception as e:
                log_error("Error cleaning up EasyOCR handler", e)
        
        # Cleanup easyocr_reader nếu có (fallback khi không dùng handlers)
        if hasattr(self, 'easyocr_reader') and self.easyocr_reader is not None:
            try:
                import sys
                from io import StringIO
                
                # Redirect stderr tạm thời để suppress warnings
                old_stderr = sys.stderr
                try:
                    sys.stderr = StringIO()
                    with warnings.catch_warnings():
                        warnings.filterwarnings('ignore')
                        # EasyOCR reader sẽ tự động cleanup khi không còn reference
                        self.easyocr_reader = None
                finally:
                    sys.stderr = old_stderr
            except Exception as e:
                log_error("Error cleaning up EasyOCR reader (fallback)", e)
        
        # Recreate thread pools for next run
        # EasyOCR: giảm workers để giảm CPU (rất nặng)
        # Tesseract: có thể nhiều workers hơn (nhẹ hơn)
        ocr_workers = 2 if self.ocr_engine == "easyocr" else 8
        self.ocr_thread_pool = ThreadPoolExecutor(max_workers=ocr_workers, thread_name_prefix="OCR")
        self.translation_thread_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="Translation")
        
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        
        # Reset text history and cache
        self.text_history = []
        self.translation_cache.clear()
        # Clear unified cache
        try:
            self.unified_cache.clear_all()
        except Exception as e:
            log_error("Error clearing unified cache", e)
        self.pending_translation = None
        self.text_stability_counter = 0
        self.previous_text = ""
        self.similar_texts_count = 0
        self.prev_ocr_text = ""
        self.last_processed_subtitle = None
        
        # Clear DeepL context when stopping translation
        if hasattr(self, 'deepl_context_manager'):
            self.deepl_context_manager.clear_context()
        
        # Clear queues
        while not self.ocr_queue.empty():
            try:
                self.ocr_queue.get_nowait()
            except queue.Empty:
                break
        while not self.translation_queue.empty():
            try:
                self.translation_queue.get_nowait()
            except queue.Empty:
                break
        
        # Clear translation history in overlay nếu keep_history được bật (trước khi đóng window)
        if self.overlay_keep_history and self.overlay_window:
            try:
                self.clear_translation_history()
            except Exception as e:
                log_error("Error clearing translation history on stop", e)
        
        # Close overlay window
        if self.overlay_window:
            try:
                self.overlay_window.destroy()
            except Exception as e:
                log_error("Error destroying overlay window", e)
            self.overlay_window = None
        
        self.log("Đã dừng dịch.")
    
    def _periodic_cleanup(self):
        """Periodic cleanup cho long sessions - giảm memory leak"""
        try:
            # Cleanup translation cache nếu quá lớn
            if self.cache_manager:
                # Cache manager tự quản lý LRU, không cần cleanup thủ công
                pass
            else:
                # Fallback: cleanup translation_cache cũ
                if len(self.translation_cache) > self.max_cache_size:
                    keys_to_remove = list(self.translation_cache.keys())[:int(self.max_cache_size * 0.2)]
                    for key in keys_to_remove:
                        del self.translation_cache[key]
            
            # Trim text history
            if len(self.text_history) > self.history_size:
                self.text_history = self.text_history[-self.history_size:]
            
            # Force garbage collection nếu cần
            import gc
            cache_size = self.cache_manager.get_size() if self.cache_manager else len(self.translation_cache)
            if cache_size > self.max_cache_size * 0.8:
                gc.collect()
        except Exception as e:
            log_error("Lỗi periodic cleanup", e)
    
    def create_overlay(self):
        """Tạo cửa sổ overlay trong suốt để hiển thị bản dịch"""
        if self.overlay_window:
            self.overlay_window.destroy()
        
        self.overlay_window = tk.Toplevel(self.root)
        # Xóa thanh tiêu đề và trang trí cửa sổ
        self.overlay_window.overrideredirect(True)
        self.overlay_window.attributes('-topmost', True)
        self.overlay_window.attributes('-alpha', self.overlay_transparency)
        
        # Đặt vị trí overlay - giữ vị trí đã lưu nếu có, không thì căn giữa màn hình
        if self.overlay_position_x is not None and self.overlay_position_y is not None:
            # Dùng vị trí đã lưu
            overlay_x = self.overlay_position_x
            overlay_y = self.overlay_position_y
        elif self.capture_region:
            x, y, w, h = self.capture_region
            overlay_x = x + w + 20
            overlay_y = y
        else:
            # Căn giữa màn hình mặc định - sử dụng actual screen size
            screen_width, screen_height = get_actual_screen_size()
            overlay_x = (screen_width - self.overlay_width) // 2
            overlay_y = (screen_height - self.overlay_height) // 2
        
        self.overlay_window.geometry(f"{self.overlay_width}x{self.overlay_height}+{overlay_x}+{overlay_y}")
        
        # Cập nhật vị trí đã lưu
        self.overlay_position_x = overlay_x
        self.overlay_position_y = overlay_y
        self.overlay_window.configure(bg=self.overlay_bg_color)
        
        # Add drag functionality - bind to window (but not on resize handles)
        self.overlay_window.bind('<Button-1>', self.on_overlay_click)
        self.overlay_window.bind('<B1-Motion>', self.on_overlay_motion)
        
        # Add resize handles (8px border for resizing)
        self.resize_handle_size = 8
        self.setup_resize_handles()
        
        # Add border if specified
        if self.overlay_border_width > 0:
            border_frame = tk.Frame(
                self.overlay_window,
                bg=self.overlay_border_color,
                padx=self.overlay_border_width,
                pady=self.overlay_border_width
            )
            border_frame.pack(fill=tk.BOTH, expand=True)
            container_parent = border_frame
        else:
            container_parent = self.overlay_window
        
        # Main container with customizable padding
        main_container = tk.Frame(
            container_parent,
            bg=self.overlay_bg_color,
            padx=self.overlay_padding_x,
            pady=self.overlay_padding_y
        )
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Make container draggable too
        main_container.bind('<Button-1>', self.on_overlay_click)
        main_container.bind('<B1-Motion>', self.on_overlay_motion)
        
        # Make border frame draggable if it exists
        if self.overlay_border_width > 0:
            border_frame.bind('<Button-1>', self.on_overlay_click)
            border_frame.bind('<B1-Motion>', self.on_overlay_motion)
        
        # Translation display - main text area with better formatting
        translation_frame = tk.Frame(main_container, bg=self.overlay_bg_color)
        translation_frame.pack(fill=tk.BOTH, expand=True)
        
        # Determine justify option
        justify_option = {
            'left': tk.LEFT,
            'center': tk.CENTER,
            'justify': tk.LEFT  # Tkinter doesn't support justify directly, use left
        }.get(self.overlay_text_align, tk.LEFT)
        
        # Build font string with weight
        font_weight_str = "bold" if self.overlay_font_weight == "bold" else "normal"
        font_tuple = (self.overlay_font_family, self.overlay_font_size, font_weight_str)
        
        # Calculate wraplength (account for padding and border)
        padding_total = (self.overlay_padding_x * 2) + (self.overlay_border_width * 2) + 20
        wraplength = self.overlay_width - padding_total if self.overlay_word_wrap else 0
        
        # Use Text widget with scrollbar for scrollable translation
        text_frame = tk.Frame(translation_frame, bg=self.overlay_bg_color)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbar for text
        text_scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL)
        text_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Text widget for translation (scrollable)
        self.translation_text = tk.Text(
            text_frame,
            font=font_tuple,
            bg=self.overlay_bg_color,
            fg=self.overlay_text_color,
            wrap=tk.WORD if self.overlay_word_wrap else tk.NONE,
            yscrollcommand=text_scrollbar.set,
            padx=5,
            pady=8,
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            insertwidth=0  # Hide cursor
        )
        self.translation_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text_scrollbar.config(command=self.translation_text.yview)
        
        # Insert initial text
        self.translation_text.insert('1.0', "Đang chờ văn bản...")
        self.translation_text.config(state=tk.DISABLED)  # Make read-only
        
        # Make text widget draggable (but allow text selection)
        self.translation_text.bind('<Button-1>', self.on_text_click)
        self.translation_text.bind('<B1-Motion>', self.on_text_motion)
        
        # Keep translation_label for backward compatibility (fallback)
        self.translation_label = None
        
        # Original text display (optional, smaller, with separator)
        if self.overlay_show_original:
            # Separator line
            separator = tk.Frame(
                main_container,
                bg=self.overlay_original_color,
                height=1
            )
            separator.pack(fill=tk.X, pady=(8, 5))
            
            # Make separator draggable
            separator.bind('<Button-1>', self.on_overlay_click)
            separator.bind('<B1-Motion>', self.on_overlay_motion)
            
            # Original text font
            original_font_size = max(8, self.overlay_font_size - 4)
            original_font_tuple = (self.overlay_font_family, original_font_size, font_weight_str)
            original_wraplength = self.overlay_width - padding_total if self.overlay_word_wrap else 0
            
            self.original_label = tk.Label(
                main_container,
                text="",
                font=original_font_tuple,
                bg=self.overlay_bg_color,
                fg=self.overlay_original_color,
                wraplength=original_wraplength,
                justify=tk.LEFT,
                anchor='nw',
                padx=5,
                pady=5,
                relief=tk.FLAT
            )
            self.original_label.pack(fill=tk.X, anchor='nw')
            
            # Make original label draggable
            self.original_label.bind('<Button-1>', self.on_overlay_click)
            self.original_label.bind('<B1-Motion>', self.on_overlay_motion)
        else:
            self.original_label = None
        
        # Make translation frame draggable
        translation_frame.bind('<Button-1>', self.on_overlay_click)
        translation_frame.bind('<B1-Motion>', self.on_overlay_motion)
    
    def get_resize_edge(self, x, y):
        """Determine which edge/corner the mouse is on for resizing"""
        if not self.overlay_window:
            return None
        
        width = self.overlay_window.winfo_width()
        height = self.overlay_window.winfo_height()
        handle_size = self.resize_handle_size
        
        # Check corners first (higher priority)
        if x <= handle_size and y <= handle_size:
            return 'nw'  # Top-left
        elif x >= width - handle_size and y <= handle_size:
            return 'ne'  # Top-right
        elif x <= handle_size and y >= height - handle_size:
            return 'sw'  # Bottom-left
        elif x >= width - handle_size and y >= height - handle_size:
            return 'se'  # Bottom-right
        # Check edges
        elif x <= handle_size:
            return 'w'  # Left
        elif x >= width - handle_size:
            return 'e'  # Right
        elif y <= handle_size:
            return 'n'  # Top
        elif y >= height - handle_size:
            return 's'  # Bottom
        
        return None
    
    def setup_resize_handles(self):
        """Setup resize handles on overlay window"""
        if not self.overlay_window:
            return
        
        # Bind mouse enter/leave để thay đổi con trỏ
        def on_mouse_move(event):
            # Nếu khóa, không hiển thị con trỏ resize
            if self.overlay_locked:
                self.overlay_window.config(cursor='')
                return
            
            edge = self.get_resize_edge(event.x, event.y)
            if edge:
                # Set appropriate cursor
                cursors = {
                    'n': 'sb_v_double_arrow',
                    's': 'sb_v_double_arrow',
                    'e': 'sb_h_double_arrow',
                    'w': 'sb_h_double_arrow',
                    'ne': 'top_right_corner',
                    'nw': 'top_left_corner',
                    'se': 'bottom_right_corner',
                    'sw': 'bottom_left_corner'
                }
                self.overlay_window.config(cursor=cursors.get(edge, ''))
            else:
                self.overlay_window.config(cursor='')
        
        self.overlay_window.bind('<Motion>', on_mouse_move)
    
    def on_overlay_click(self, event):
        """Handle click on overlay window"""
        if not self.overlay_window:
            return
        
        # Nếu khóa, không cho phép kéo hoặc resize
        if self.overlay_locked:
            return
        
        # Kiểm tra xem có click vào handle resize không
        edge = self.get_resize_edge(event.x, event.y)
        if edge:
            # Bắt đầu resize - lưu giá trị ban đầu
            self.overlay_resize_edge = edge
            self.overlay_resize_start_x = event.x_root
            self.overlay_resize_start_y = event.y_root
            self.overlay_resize_start_width = self.overlay_window.winfo_width()
            self.overlay_resize_start_height = self.overlay_window.winfo_height()
            # Store initial window position
            self._resize_start_win_x = self.overlay_window.winfo_x()
            self._resize_start_win_y = self.overlay_window.winfo_y()
            self.overlay_window.bind('<B1-Motion>', self.on_overlay_resize)
            self.overlay_window.bind('<ButtonRelease-1>', self.on_overlay_resize_end)
        else:
            # Start dragging
            self.overlay_drag_start_x = event.x_root - self.overlay_window.winfo_x()
            self.overlay_drag_start_y = event.y_root - self.overlay_window.winfo_y()
            self.overlay_resize_edge = None
    
    def on_overlay_motion(self, event):
        """Handle mouse motion on overlay window"""
        if not self.overlay_window:
            return
        
        # Nếu khóa, không cho phép kéo hoặc resize
        if self.overlay_locked:
            return
        
        if self.overlay_resize_edge:
            # Resizing is handled by on_overlay_resize
            return
        
        # Dragging
        x = event.x_root - self.overlay_drag_start_x
        y = event.y_root - self.overlay_drag_start_y
        self.overlay_window.geometry(f"+{x}+{y}")
        # Cập nhật vị trí đã lưu
        self.overlay_position_x = x
        self.overlay_position_y = y
    
    def on_overlay_resize(self, event):
        """Handle window resizing - fixed to prevent unwanted movement"""
        if not self.overlay_window or not self.overlay_resize_edge:
            return
        
        # Nếu khóa, không cho phép resize
        if self.overlay_locked:
            return
        
        # Tính toán thay đổi kích thước từ vị trí ban đầu
        dx = event.x_root - self.overlay_resize_start_x
        dy = event.y_root - self.overlay_resize_start_y
        
        # Use initial window position (stored at start of resize)
        if not hasattr(self, '_resize_start_win_x'):
            self._resize_start_win_x = self.overlay_window.winfo_x()
            self._resize_start_win_y = self.overlay_window.winfo_y()
        
        # Calculate new dimensions based on initial values
        new_width = self.overlay_resize_start_width
        new_height = self.overlay_resize_start_height
        new_x = self._resize_start_win_x  # Always start from initial X
        new_y = self._resize_start_win_y  # Always start from initial Y
        
        # Apply resize based on edge
        # Right edge: only change width, keep position
        if 'e' in self.overlay_resize_edge:
            new_width = max(200, self.overlay_resize_start_width + dx)
        
        # Left edge: change width and move X position
        if 'w' in self.overlay_resize_edge:
            new_width = max(200, self.overlay_resize_start_width - dx)
            new_x = self._resize_start_win_x + dx
        
        # Bottom edge: only change height, keep Y position (top stays fixed)
        if 's' in self.overlay_resize_edge:
            new_height = max(100, self.overlay_resize_start_height + dy)
            # Y position stays the same (top-left corner fixed)
        
        # Top edge: change height and move Y position
        if 'n' in self.overlay_resize_edge:
            new_height = max(100, self.overlay_resize_start_height - dy)
            new_y = self._resize_start_win_y + dy
        
        # Lấy kích thước màn hình - sử dụng actual screen size
        screen_width, screen_height = get_actual_screen_size()
        
        # Giới hạn vị trí để giữ cửa sổ trên màn hình
        # Đảm bảo cửa sổ không ra ngoài cạnh phải
        if new_x + new_width > screen_width:
            if 'e' in self.overlay_resize_edge:
                # Nếu resize từ phải, giới hạn chiều rộng
                new_width = screen_width - new_x
            elif 'w' in self.overlay_resize_edge:
                # Nếu resize từ trái, điều chỉnh vị trí
                new_x = screen_width - new_width
            else:
                # Nếu không, chỉ điều chỉnh vị trí
                new_x = max(0, screen_width - new_width)
        
        # Đảm bảo cửa sổ không ra ngoài cạnh dưới
        if new_y + new_height > screen_height:
            if 's' in self.overlay_resize_edge:
                # Nếu resize từ dưới, giới hạn chiều cao
                new_height = screen_height - new_y
            elif 'n' in self.overlay_resize_edge:
                # Nếu resize từ trên, điều chỉnh vị trí
                new_y = screen_height - new_height
            else:
                # Nếu không, chỉ điều chỉnh vị trí
                new_y = max(0, screen_height - new_height)
        
        # Đảm bảo cửa sổ không ra ngoài cạnh trái
        new_x = max(0, new_x)
        
        # Đảm bảo cửa sổ không ra ngoài cạnh trên
        new_y = max(0, new_y)
        
        # Đảm bảo kích thước tối thiểu
        new_width = max(200, new_width)
        new_height = max(100, new_height)
        
        # Cập nhật vị trí cửa sổ
        self.overlay_window.geometry(f"{int(new_width)}x{int(new_height)}+{int(new_x)}+{int(new_y)}")
        # Cập nhật vị trí đã lưu
        self.overlay_position_x = int(new_x)
        self.overlay_position_y = int(new_y)
    
    def on_overlay_resize_end(self, event):
        """Handle end of resize operation"""
        if self.overlay_window and self.overlay_resize_edge:
            # Cập nhật kích thước đã lưu
            self.overlay_width = self.overlay_window.winfo_width()
            self.overlay_height = self.overlay_window.winfo_height()
            
            # Lấy vị trí hiện tại (đã cập nhật trong quá trình resize)
            current_x = self.overlay_position_x
            current_y = self.overlay_position_y
            
            # Đảm bảo vị trí hợp lệ
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            current_x = max(0, min(current_x, screen_width - self.overlay_width))
            current_y = max(0, min(current_y, screen_height - self.overlay_height))
            
            # Cập nhật vị trí đã lưu
            self.overlay_position_x = current_x
            self.overlay_position_y = current_y
            
            # Update UI variables if they exist
            if hasattr(self, 'width_var'):
                self.width_var.set(str(self.overlay_width))
            if hasattr(self, 'height_var'):
                self.height_var.set(str(self.overlay_height))
            
            # Lưu config
            self.save_config()
            
            # Tạo lại overlay để áp dụng kích thước mới đúng cách (vị trí sẽ được giữ)
            self.create_overlay()
        
        # Dọn dẹp trạng thái resize
        self.overlay_resize_edge = None
        if hasattr(self, '_resize_start_win_x'):
            delattr(self, '_resize_start_win_x')
            delattr(self, '_resize_start_win_y')
        if self.overlay_window:
            self.overlay_window.unbind('<B1-Motion>')
            self.overlay_window.unbind('<ButtonRelease-1>')
    
    def on_text_click(self, event):
        """Handle click on text widget - allow text selection or start drag"""
        # If locked, don't allow drag
        if self.overlay_locked:
            return
        
        # Kiểm tra xem có đang ở chế độ chọn văn bản không (click vào văn bản, không phải vùng trống)
        if self.translation_text.index(f"@{event.x},{event.y}") != "1.0":
            # Cho phép chọn văn bản bình thường
            return
        
        # Nếu không, bắt đầu kéo
        self.overlay_drag_start_x = event.x_root - self.overlay_window.winfo_x()
        self.overlay_drag_start_y = event.y_root - self.overlay_window.winfo_y()
    
    def on_text_motion(self, event):
        """Handle mouse motion on text widget"""
        # If locked, don't allow drag
        if self.overlay_locked:
            return
        
        # If text is selected, don't drag
        try:
            if self.translation_text.tag_ranges(tk.SEL):
                return
        except Exception as e:
            # Tkinter có thể raise exception nếu widget không còn tồn tại
            log_error("Error checking text selection in overlay drag", e)
        
        # Otherwise, drag the window
        if self.overlay_window:
            x = event.x_root - self.overlay_drag_start_x
            y = event.y_root - self.overlay_drag_start_y
            self.overlay_window.geometry(f"+{x}+{y}")
            # Cập nhật vị trí đã lưu
            self.overlay_position_x = x
            self.overlay_position_y = y
    
    def scale_for_ocr(self, img):
        """
        Scale ảnh nhỏ lên nếu < 300px để Tesseract đọc tốt hơn
        Chỉ nhận numpy array (được gọi trong ocr_region_with_confidence)
        """
        if img is None or img.size == 0:
            return img
        h, w = img.shape[:2]
        min_dim = 300
        if h < min_dim or w < min_dim:
            scale_factor = max(min_dim / h, min_dim / w)
            scaled = cv2.resize(img, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)
            return scaled
        return img
    
    def preprocess_image(self, img, mode='adaptive', block_size=41, c_value=-60):
        """
        Tiền xử lý ảnh để tối ưu độ chính xác và tốc độ OCR
        
        Args:
            img: PIL Image hoặc numpy array
            mode: 'adaptive', 'binary', 'binary_inv', 'none'
            block_size: Kích thước block cho adaptive thresholding (phải là số lẻ)
            c_value: Hằng số trừ từ mean cho adaptive thresholding
        """
        img_array = np.array(img)
        
        # Chuyển sang BGR nếu cần (PIL là RGB, OpenCV cần BGR)
        if len(img_array.shape) == 3:
            if img_array.shape[2] == 3:
                # PIL RGB -> OpenCV BGR
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            elif img_array.shape[2] == 4:
                # RGBA -> BGR -> GRAY
                bgr = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)
                gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            else:
                gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
        else:
            gray = img_array.copy()
        
        # Scale thông minh: chỉ scale khi cần
        height, width = gray.shape
        scale_factor = 1.0
        min_dim = 300
        if height < min_dim or width < min_dim:
            scale_factor = max(min_dim / width, min_dim / height)
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            gray = cv2.resize(gray, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
        
        # Xử lý theo mode
        try:
            if mode == 'adaptive':
                # Adaptive thresholding - tốt nhất cho nền thay đổi
                # Đảm bảo block_size là số lẻ
                if block_size % 2 == 0:
                    block_size += 1
                processed = cv2.adaptiveThreshold(
                    gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY_INV, block_size, c_value
                )
                return [processed], scale_factor
                
            elif mode == 'binary':
                # Fixed binary thresholding (inverted)
                _, processed = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
                return [processed], scale_factor
                
            elif mode == 'binary_inv':
                # Fixed binary thresholding (standard)
                _, processed = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
                return [processed], scale_factor
                
            elif mode == 'none':
                # Không thresholding, chỉ grayscale
                return [gray], scale_factor
                
            else:
                # Fallback: adaptive
                if block_size % 2 == 0:
                    block_size += 1
                processed = cv2.adaptiveThreshold(
                    gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY_INV, block_size, c_value
                )
                return [processed], scale_factor
                
        except Exception as e:
            log_error(f"Preprocessing error (mode: {mode}): {e}", e)
            # Fallback về grayscale
            return [gray], scale_factor
    
    def get_tesseract_config(self, mode='gaming'):
        """
        Lấy Tesseract config dựa trên mode
        """
        if mode == 'subtitle':
            return '--psm 7 --oem 3 -c preserve_interword_spaces=1'
        elif mode == 'gaming':
            return '--psm 6 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,!?:;()[]-_\'"/\\$%&@ '
        elif mode == 'document':
            return '--psm 3 --oem 3'
        else:
            return '--psm 6 --oem 3'
    
    def perform_ocr(self, processed_images, scale_factor, confidence_threshold=50):
        """
        Thực hiện OCR trên ảnh đã xử lý - chỉ free engines
        Hỗ trợ Tesseract và EasyOCR (không rate limit)
        """
        # Chọn engine OCR - chỉ free engines
        if self.ocr_engine == "easyocr" and self.EASYOCR_AVAILABLE:
            return self.perform_easyocr(processed_images)
        else:
            # Default: Tesseract
            return self.perform_tesseract_ocr(processed_images, confidence_threshold)
    
    def perform_easyocr(self, processed_images):
        """Thực hiện OCR bằng EasyOCR - tối ưu CPU"""
        try:
            if not processed_images or len(processed_images) == 0:
                log_debug("Empty processed_images for EasyOCR")
                return ""
            
            # Throttle: EasyOCR rất nặng CPU, chỉ gọi mỗi 0.8s
            now = time.monotonic()
            time_since_last_call = now - self.last_easyocr_call_time
            if time_since_last_call < self.easyocr_min_interval:
                # Skip call này để giảm CPU
                return ""
            
            # Khởi tạo reader nếu chưa có
            reader = self.initialize_easyocr_reader()
            if reader is None:
                log_error("EasyOCR reader không khả dụng", None)
                return ""
            
            # Sử dụng ảnh đầu tiên (đã được xử lý tốt nhất)
            img = processed_images[0]
            
            if img is None or img.size == 0:
                log_debug("Empty image for EasyOCR")
                return ""
            
            # Resize ảnh nhỏ hơn để giảm CPU (EasyOCR vẫn chính xác với ảnh nhỏ)
            # Giữ max dimension <= 800px để giảm ~50% CPU
            if isinstance(img, np.ndarray):
                # Convert numpy array to PIL để resize dễ hơn
                try:
                    img = Image.fromarray(img)
                except Exception as img_conv_err:
                    log_error("Error converting numpy array to PIL Image for EasyOCR", img_conv_err)
                    return ""
            
            # PIL Image - resize nếu cần
            try:
                w, h = img.size
                max_dim = max(w, h)
                if max_dim > 800:
                    scale = 800 / max_dim
                    new_w, new_h = int(w * scale), int(h * scale)
                    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            except Exception as resize_err:
                log_error("Error resizing image for EasyOCR", resize_err)
                return ""
            
            # Convert PIL Image to numpy array cho EasyOCR
            try:
                img_array = np.array(img)
            except Exception as array_err:
                log_error("Error converting PIL Image to numpy array for EasyOCR", array_err)
                return ""
            
            # Thực hiện OCR
            try:
                self.last_easyocr_call_time = time.monotonic()
                results = reader.readtext(img_array)
            except Exception as ocr_err:
                log_error("EasyOCR readtext error", ocr_err)
                return ""
            
            # Trích xuất text từ kết quả
            texts = []
            try:
                for (bbox, text, confidence) in results:
                    if text and confidence > 0.3:  # Confidence threshold cho EasyOCR
                        texts.append(text)
            except Exception as extract_err:
                log_error("Error extracting text from EasyOCR results", extract_err)
                return ""
            
            if texts:
                combined_text = ' '.join(texts).strip()
                if combined_text:
                    cleaned = self.clean_ocr_text(combined_text)
                    # Dùng dialogue-aware validator thay vì simple length check
                    if should_translate_text(cleaned):
                        return cleaned
            
            return ""
        except Exception as e:
            log_error("Lỗi EasyOCR", e)
            return ""
    
    def preprocess_for_ocr_cv(self, img, mode='adaptive', block_size=41, c_value=-60):
        """
        Preprocess image cho OCR
        Chỉ trả về 1 ảnh đã processed, không phải list
        """
        if img is None or img.size == 0:
            return np.zeros((10, 10), dtype=np.uint8)
        
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()
        
        try:
            if mode == 'adaptive':
                # Đảm bảo block_size là số lẻ
                if block_size % 2 == 0:
                    block_size += 1
                processed = cv2.adaptiveThreshold(
                    gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY_INV, block_size, c_value
                )
            elif mode == 'binary':
                _, processed = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
            elif mode == 'binary_inv':
                _, processed = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
            elif mode == 'none':
                processed = gray
            else:
                processed = gray
            
            return processed
        except Exception as e:
            log_error(f"Preprocessing error (mode: {mode}): {e}", e)
            return gray
    
    def ocr_region_with_confidence(self, img, region, confidence_threshold=50):
        """
        OCR region với confidence filtering
        Scale được gọi TRONG function này, không phải trước
        """
        try:
            x, y, w, h = region
            if len(img.shape) == 3:
                roi = img[y:y+h, x:x+w]
            else:
                roi = img[y:y+h, x:x+w]
            
            # Validate ROI
            if roi.size == 0 or roi.shape[0] == 0 or roi.shape[1] == 0:
                log_debug(f"Empty ROI for region {region}")
                return ""
            
            # Scale for OCR
            scaled_roi = self.scale_for_ocr(roi)
            
            # Dùng cached config
            config = self.cached_tess_params if self.cached_tess_params else self.get_tesseract_config('gaming')
            
            data = pytesseract.image_to_data(
                scaled_roi,
                lang=self.source_language,
                config=config,
                output_type=pytesseract.Output.DICT
            )
            
            filtered_text = []
            for i in range(len(data['text'])):
                if not data['text'][i].strip():
                    continue
                try:
                    conf = float(data['conf'][i])
                    if conf >= confidence_threshold:
                        filtered_text.append(data['text'][i])
                except (ValueError, TypeError, IndexError) as conf_err:
                    log_debug(f"Error parsing confidence value: {conf_err}")
                    continue
            
            return ' '.join(filtered_text)
        except Exception as e:
            log_error(f"OCR error in region {region}: {e}", e)
            return ""
    
    def clean_ocr_text(self, text):
        """
        Làm sạch và sửa lỗi nhận dạng OCR thường gặp
        Sử dụng modules từ modules package
        """
        if not text:
            return ""
        
        # Sử dụng post_process_ocr_text_general với source_language
        cleaned = post_process_ocr_text_general(text, lang=self.source_language)
        
        # Áp dụng game subtitle specific processing
        cleaned = post_process_ocr_for_game_subtitle(cleaned)
        
        return cleaned.strip()
    
    def remove_text_after_last_punctuation_mark(self, text):
        """
        Xóa garbage sau dấu câu cuối
        Sử dụng hàm từ modules package
        """
        return remove_text_after_last_punctuation_mark(text)
    
    def post_process_translation_text(self, text):
        """Post-process translation text"""
        """
        Xử lý text sau khi dịch
        """
        if not text:
            return text
        
        # Fix spacing trước dấu câu
        text = re.sub(r'\s+\?', '?', text)
        text = re.sub(r'([.!?])([A-Z])', r'\1 \2', text)
        
        # PRESERVE dialog line breaks while cleaning up excessive spaces
        # Split by newlines, clean spaces within each line, then rejoin
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            # Clean up multiple spaces within each line, but preserve the line structure
            cleaned_line = re.sub(r'[ \t]{2,}', ' ', line)  # Only target spaces and tabs, not newlines
            cleaned_lines.append(cleaned_line)
        
        # Rejoin with preserved newlines
        text = '\n'.join(cleaned_lines)
        
        return text
    
    def chunk_text_for_translation(self, text, max_chunk_length=300):
        """
        Chia text dài thành các đoạn nhỏ hơn để dịch nhanh hơn
        Tách theo câu (sentence boundaries) để giữ ngữ nghĩa
        """
        if not text or len(text) <= max_chunk_length:
            return [text] if text else []
        
        chunks = []
        # Tách theo sentence boundaries (., !, ?, ...)
        sentence_endings = re.compile(r'([.!?…]+[\s\n]*)')
        sentences = sentence_endings.split(text)
        
        current_chunk = ""
        for i, part in enumerate(sentences):
            # Nếu part là sentence ending, thêm vào chunk hiện tại
            if sentence_endings.match(part):
                current_chunk += part
                if len(current_chunk.strip()) > 0:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
            else:
                # Nếu thêm part này vượt quá max_chunk_length, tách chunk
                if len(current_chunk) + len(part) > max_chunk_length and current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = part
                else:
                    current_chunk += part
        
        # Thêm chunk cuối cùng
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        # Nếu vẫn có chunk quá dài, cắt cứng
        final_chunks = []
        for chunk in chunks:
            if len(chunk) <= max_chunk_length:
                final_chunks.append(chunk)
            else:
                # Cắt cứng theo từ
                words = chunk.split()
                current = ""
                for word in words:
                    if len(current) + len(word) + 1 > max_chunk_length and current:
                        final_chunks.append(current.strip())
                        current = word
                    else:
                        current += (" " + word if current else word)
                if current:
                    final_chunks.append(current.strip())
        
        return final_chunks if final_chunks else [text[:max_chunk_length]]
    
    def format_dialog_text(self, text):
        """
        Format dialog text bằng cách thêm line breaks trước dashes sau sentence-ending punctuation
        
        Ví dụ: "- How are you? - Fine. - Great." 
        -> "- How are you?\n- Fine.\n- Great."
        """
        if not text or not isinstance(text, str):
            return text
        
        # Chỉ format nếu text bắt đầu bằng dash
        dash_check = (text.startswith("-") or text.startswith("–") or text.startswith("—"))
        if not dash_check:
            return text
        
        formatted_text = text
        
        # Xử lý quoted dialogue format
        dialogue_patterns = ['"-', '" "', '- "', '" - "']
        has_dialogue_quotes = formatted_text.count('"') >= 4
        has_dialogue_pattern = any(pattern in formatted_text for pattern in dialogue_patterns)
        
        if has_dialogue_quotes and has_dialogue_pattern:
            # Check if there are occurrences of '"-'
            if '"-' in formatted_text:
                formatted_text = formatted_text.replace('"-', '-')
            # Check if there are occurrences of '- "' (dash + space + quote)
            elif '- "' in formatted_text:
                formatted_text = formatted_text.replace('- "', '-')
            else:
                # Replace odd occurrences of '"' with '-'
                result = []
                quote_count = 0
                for char in formatted_text:
                    if char == '"':
                        quote_count += 1
                        if quote_count % 2 == 1:  # Odd occurrence
                            result.append('-')
                        else:  # Even occurrence
                            result.append('"')
                    else:
                        result.append(char)
                formatted_text = ''.join(result)
            
            # Remove all remaining quotes
            formatted_text = formatted_text.replace('"', '')
        
        # Replace ". -" with ".\n-" (period + space + hyphen)
        formatted_text = formatted_text.replace(". -", ".\n-")
        formatted_text = formatted_text.replace(". –", ".\n–")
        formatted_text = formatted_text.replace(". —", ".\n—")
        
        # Replace "? -" with "?\n-" (question mark + space + hyphen)
        formatted_text = formatted_text.replace("? -", "?\n-")
        formatted_text = formatted_text.replace("? –", "?\n–")
        formatted_text = formatted_text.replace("? —", "?\n—")
        
        # Replace "! -" with "!\n-" (exclamation mark + space + hyphen)
        formatted_text = formatted_text.replace("! -", "!\n-")
        formatted_text = formatted_text.replace("! –", "!\n–")
        formatted_text = formatted_text.replace("! —", "!\n—")
        
        return formatted_text
    
    def is_error_message(self, text):
        """
        Kiểm tra xem text có phải là error message không
        """
        if not isinstance(text, str):
            return True
        error_indicators = [
            "error:", "api error", "not initialized", "missing", 
            "failed", "not available", "not supported", 
            "invalid result", "empty result", "lỗi"
        ]
        return any(indicator in text.lower() for indicator in error_indicators)
    
    def is_placeholder_text(self, text):
        """
        Kiểm tra xem text có phải là placeholder không
        """
        if not text:
            return True
        text_lower = text.lower().strip()
        placeholders = [
            "source text will appear here", "translation will appear here", 
            "translation...", "ocr source", "source text", 
            "loading...", "translating...", "", "translation", 
            "...", "translation error:", "đang chờ văn bản..."
        ]
        return text_lower in placeholders or text_lower.startswith("translation error:")
    
    def is_text_stable(self, text):
        """
        Kiểm tra độ ổn định văn bản
        Sử dụng text_history để track và so sánh với các lần đọc trước
        Yêu cầu ít nhất stable_threshold lần đọc giống nhau để giảm dịch trùng
        """
        try:
            # Dùng dialogue validator thay vì simple length check
            if not text or not is_valid_dialogue_text(text):
                return False
            
            # Tính similarity với text gần nhất trong history
            if len(self.text_history) > 0:
                last_text = self.text_history[-1]
                
                # Nếu text giống hệt với lần đọc trước, kiểm tra số lần liên tiếp
                if text == last_text:
                    # Đếm số lần text này xuất hiện liên tiếp trong history
                    consecutive_count = 1
                    for i in range(len(self.text_history) - 2, -1, -1):
                        if self.text_history[i] == text:
                            consecutive_count += 1
                        else:
                            break
                    
                    # Cần ít nhất stable_threshold lần đọc giống nhau
                    if consecutive_count >= self.stable_threshold:
                        return True
                
                # Tính similarity dựa trên word overlap (tốt hơn character matching)
                words1 = set(text.lower().split())
                words2 = set(last_text.lower().split())
                
                if words1 and words2:
                    intersection = words1.intersection(words2)
                    union = words1.union(words2)
                    similarity = len(intersection) / len(union) if union else 0
                    
                    # Nếu similarity > 0.9, kiểm tra số lần đọc tương tự
                    if similarity > 0.9:
                        # Đếm số lần đọc tương tự liên tiếp
                        similar_count = 1
                        for i in range(len(self.text_history) - 2, -1, -1):
                            prev_text = self.text_history[i]
                            prev_words = set(prev_text.lower().split())
                            prev_intersection = words1.intersection(prev_words)
                            prev_union = words1.union(prev_words)
                            prev_similarity = len(prev_intersection) / len(prev_union) if prev_union else 0
                            if prev_similarity > 0.9:
                                similar_count += 1
                            else:
                                break
                        
                        # Cần ít nhất stable_threshold lần đọc tương tự
                        if similar_count >= self.stable_threshold:
                            return True
                    
                    # Nếu độ dài tương tự và similarity > 0.6, cũng kiểm tra
                    if abs(len(text) - len(last_text)) <= 3 and similarity > 0.6:
                        # Đếm số lần đọc tương tự liên tiếp
                        similar_count = 1
                        for i in range(len(self.text_history) - 2, -1, -1):
                            prev_text = self.text_history[i]
                            if abs(len(text) - len(prev_text)) <= 3:
                                prev_words = set(prev_text.lower().split())
                                prev_intersection = words1.intersection(prev_words)
                                prev_union = words1.union(prev_words)
                                prev_similarity = len(prev_intersection) / len(prev_union) if prev_union else 0
                                if prev_similarity > 0.6:
                                    similar_count += 1
                                else:
                                    break
                            else:
                                break
                        
                        # Cần ít nhất stable_threshold lần đọc tương tự
                        if similar_count >= self.stable_threshold:
                            return True
            
            # Add to history (chỉ thêm nếu chưa có trong history hoặc khác với lần cuối)
            if len(self.text_history) == 0 or text != self.text_history[-1]:
                self.text_history.append(text)
                if len(self.text_history) > self.history_size:
                    self.text_history.pop(0)
            
            # For very short text, cần ít nhất stable_threshold lần đọc giống nhau
            if len(text) < 10:
                if len(self.text_history) >= self.stable_threshold:
                    # Kiểm tra xem có đủ số lần đọc giống nhau liên tiếp không
                    all_same = True
                    start_idx = len(self.text_history) - self.stable_threshold
                    for i in range(start_idx, len(self.text_history)):
                        if self.text_history[i] != text:
                            all_same = False
                            break
                    if all_same:
                        return True
                return False
            
            # Với text dài hơn, cần ít nhất stable_threshold lần đọc trong history
            if len(self.text_history) >= self.stable_threshold:
                # Kiểm tra xem có đủ số lần đọc tương tự không
                return True
            
            return False
        except Exception as e:
            log_error("Error in is_text_stable()", e)
            # Trả về False để an toàn (không dịch nếu có lỗi)
            return False
    
    def translate_with_deepl(self, text, source_text_for_context=None):
        """
        Dịch văn bản sử dụng DeepL API với context window support
        """
        if not self.deepl_api_client:
            # Thử khởi tạo lại nếu chưa có
            if self.deepl_api_key:
                try:
                    self.deepl_api_client = deepl.Translator(self.deepl_api_key)
                except Exception as e:
                    log_error("DeepL initialization error", e)
                    return None
            else:
                return None
        
        # Check circuit breaker
        if self.deepl_translation_circuit_breaker.should_force_refresh():
            log_debug("DeepL circuit breaker is open, forcing client refresh")
            try:
                self.deepl_api_client = deepl.Translator(self.deepl_api_key)
                self.deepl_translation_circuit_breaker.reset()
            except Exception as e:
                log_error("Error refreshing DeepL client", e)
                return None
        
        start_time = time.time()
        try:
            # Map target language to DeepL format
            deepl_target_map = {
                'vi': 'VI',
                'en': 'EN-US',
                'ja': 'JA',
                'ko': 'KO',
                'zh': 'ZH',
                'fr': 'FR',
                'de': 'DE',
                'es': 'ES'
            }
            target_lang = deepl_target_map.get(self.target_language, 'EN-US')
            
            # Map source language to DeepL format
            deepl_source_map = {
                'vi': 'VI',
                'en': 'EN',
                'ja': 'JA',
                'ko': 'KO',
                'zh': 'ZH',
                'fr': 'FR',
                'de': 'DE',
                'es': 'ES'
            }
            source_lang = deepl_source_map.get(self.source_language, None)
            
            # Build context string if context window is enabled
            context_string = None
            if self.deepl_context_window_size > 0:
                context_string = self.deepl_context_manager.build_context_string()
                if context_string:
                    log_debug(f"DeepL context ({len(context_string)} chars, {self.deepl_context_window_size} subtitles): {context_string[:100]}...")
            
            # Prepare translation parameters
            translate_params = {
                'text': text,
                'target_lang': target_lang
            }
            
            # Add source language if available (required for context)
            if source_lang:
                translate_params['source_lang'] = source_lang
            
            # Add context if available (IMPORTANT: context not counted for billing!)
            # Context only works with explicit source_lang
            if context_string and source_lang:
                translate_params['context'] = context_string
                log_debug(f"Using DeepL context window: {self.deepl_context_window_size} previous subtitles")
            
            # Translate with DeepL
            result = self.deepl_api_client.translate_text(**translate_params)
            
            duration = time.time() - start_time
            
            if result and hasattr(result, 'text'):
                translated_text = result.text
                
                # Update context window with source text after successful translation
                # Only update if source_text_for_context is provided (single translation case)
                if source_text_for_context:
                    try:
                        self.deepl_context_manager.update_context(
                            source_text_for_context,
                            self.source_language,
                            self.target_language
                        )
                    except Exception as e:
                        log_error("Error updating DeepL context", e)
                
                # Record successful call in circuit breaker
                self.deepl_translation_circuit_breaker.record_call(duration, success=True)
                
                return translated_text
            
            # Record failed call
            self.deepl_translation_circuit_breaker.record_call(duration, success=False)
            return None
        except Exception as e:
            duration = time.time() - start_time
            self.deepl_translation_circuit_breaker.record_call(duration, success=False)
            log_error("DeepL translation error", e)
            return None
    
    def calculate_text_similarity(self, text1, text2):
        """
        Tính độ tương đồng giữa 2 text sử dụng Jaccard similarity
        Dựa trên word overlap
        """
        if not text1 or not text2:
            return 0.0
        if len(text1) < 10 or len(text2) < 10:
            return 1.0 if text1 == text2 else 0.0
        
        words1_set = set(text1.lower().split())
        words2_set = set(text2.lower().split())
        intersection_len = len(words1_set.intersection(words2_set))
        union_len = len(words1_set.union(words2_set))
        return intersection_len / union_len if union_len > 0 else 0.0
    
    # ==================== THREADING FUNCTIONS ====================
    
    def run_capture_thread(self):
        """Capture thread - chỉ chụp màn hình và đưa vào queue"""
        log_error("WT: Capture thread started.", None)
        sct = None
        try:
            sct = mss.mss()
        except Exception as e:
            log_error("Failed to initialize screen capture", e)
            self.log(f"Không thể khởi tạo chụp màn hình: {e}")
            return
        
        last_cap_time = 0.0
        last_cap_hash = None
        # EasyOCR: tăng min_interval để giảm CPU (chậm hơn nhưng ổn định)
        min_interval = 0.1 if self.ocr_engine == "easyocr" else 0.03
        similar_frames = 0
        current_scan_interval_sec = min_interval
        
        while self.is_running:
            now = time.monotonic()
            try:
                # Update adaptive scan interval based on OCR load
                self.update_adaptive_scan_interval()
                
                # Use adaptive scan interval (convert from ms to seconds)
                adaptive_scan_interval_ms = self.current_scan_interval
                base_interval_sec = adaptive_scan_interval_ms / 1000.0
                
                # Additional queue-based adjustment
                q_fullness = self.ocr_queue.qsize() / (self.ocr_queue.maxsize or 1)
                if q_fullness > 0.7:
                    current_scan_interval_sec = base_interval_sec * (1 + q_fullness)
                elif q_fullness > 0.4:
                    current_scan_interval_sec = base_interval_sec * 1.25
                else:
                    current_scan_interval_sec = max(min_interval, base_interval_sec)
                
                if now - last_cap_time < current_scan_interval_sec:
                    sleep_duration = current_scan_interval_sec - (now - last_cap_time)
                    slept_time = 0
                    while slept_time < sleep_duration and self.is_running:
                        chunk = min(0.03, sleep_duration - slept_time)  # 0.03s balance responsive/CPU
                        time.sleep(chunk)
                        slept_time += chunk
                    if not self.is_running:
                        break
                    continue
                
                # Chụp vùng màn hình
                monitor = {
                    "top": self.capture_region[1],
                    "left": self.capture_region[0],
                    "width": self.capture_region[2],
                    "height": self.capture_region[3]
                }
                
                capture_moment = time.monotonic()
                screenshot = sct.grab(monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                last_cap_time = capture_moment
                
                # Hash deduplication với resize 1/4
                width, height = img.size
                img_small = img.resize(
                    (max(1, width//4), max(1, height//4)),
                    Image.Resampling.NEAREST if hasattr(Image, "Resampling") else Image.NEAREST
                )
                img_hash = hashlib.md5(img_small.tobytes()).hexdigest()
                
                # Deduplication: EasyOCR cần skip aggressive hơn (rất nặng CPU)
                if img_hash == last_cap_hash:
                    similar_frames += 1
                    if self.ocr_engine == "easyocr":
                        # EasyOCR: skip 100% duplicate frames để giảm CPU
                        time.sleep(min(0.2, current_scan_interval_sec))
                        continue
                    else:
                        # Tesseract: probability skip
                        skip_probability = min(0.95, 0.5 + (similar_frames * 0.05))
                        if random.random() < skip_probability:
                            time.sleep(min(0.1, current_scan_interval_sec * 0.5))
                            continue
                else:
                    similar_frames = 0
                last_cap_hash = img_hash
                
                # Đưa vào queue
                try:
                    if not self.ocr_queue.full():
                        self.ocr_queue.put_nowait(img)
                except queue.Full:
                    pass  # Skip frame if queue is full
                except Exception as q_err:
                    log_error(f"Error putting to OCR queue", q_err)
            
            except Exception as loop_err:
                log_error("Capture thread error", loop_err)
                sleep_after_error = current_scan_interval_sec if 'current_scan_interval_sec' in locals() else 0.5
                time.sleep(max(sleep_after_error, 0.5))
        
        try:
            log_error("WT: Capture thread finished.", None)
        except Exception as e:
            # Fallback: print to stderr if log_error fails
            try:
                import sys
                sys.stderr.write(f"Error logging capture thread finish: {e}\n")
            except Exception:
                pass  # Ultimate fallback - cannot log
    
    def run_ocr_thread(self):
        """OCR thread - lấy từ queue, xử lý OCR, gọi async translation"""
        try:
            log_error("WT: OCR thread started.", None)
        except Exception as e:
            # Fallback: print to stderr if log_error fails
            try:
                import sys
                sys.stderr.write(f"Error logging OCR thread start: {e}\n")
            except Exception:
                pass  # Ultimate fallback - cannot log
        last_ocr_proc_time = 0
        min_ocr_interval = 0.03  # Giảm từ 0.05 cho máy mạnh - xử lý nhanh hơn
        similar_texts_count = 0
        prev_ocr_text = ""
        
        while self.is_running:
            now = time.monotonic()
            
            # Periodic cleanup cho long sessions (mỗi 5 phút)
            current_time = time.time()
            if current_time - self.last_cleanup_time > self.cleanup_interval:
                self._periodic_cleanup()
                self.last_cleanup_time = current_time
            
            try:
                # Adaptive OCR interval based on queue size
                q_sz = self.ocr_queue.qsize()
                ocr_q_max = self.ocr_queue.maxsize or 1
                adaptive_ocr_interval = min_ocr_interval * (0.8 if q_sz <= 1 else (1.0 + (q_sz / ocr_q_max)))
                
                if now - last_ocr_proc_time < adaptive_ocr_interval:
                    sleep_duration = adaptive_ocr_interval - (now - last_ocr_proc_time)
                    slept_time = 0
                    while slept_time < sleep_duration and self.is_running:
                        chunk = min(0.03, sleep_duration - slept_time)  # Balance cho tầm trung
                        time.sleep(chunk)
                        slept_time += chunk
                    if not self.is_running:
                        break
                    continue
                
                # Lấy ảnh từ queue
                try:
                    img = self.ocr_queue.get(timeout=0.5)
                except queue.Empty:
                    time.sleep(0.03)  # Balance: không quá nhanh gây CPU spike
                    continue
                
                ocr_proc_start_time = time.monotonic()
                last_ocr_proc_time = ocr_proc_start_time
                
                # OCR - sử dụng handlers nếu có, fallback về code cũ
                text = ""
                try:
                    if self.ocr_engine == "tesseract" and self.tesseract_handler:
                        # Sử dụng Tesseract Handler
                        img_np = np.array(img)
                        img_shape = img_np.shape
                        
                        # Convert to BGR
                        if len(img_shape) == 3:
                            if img_shape[2] == 3:
                                img_cv_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                            elif img_shape[2] == 4:
                                img_cv_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGBA2BGR)
                            else:
                                img_cv_bgr = cv2.cvtColor(img_np, cv2.COLOR_BGR2BGR)
                        elif len(img_shape) == 2:
                            img_cv_bgr = cv2.cvtColor(img_np, cv2.COLOR_GRAY2BGR)
                        else:
                            img_cv_bgr = img_np
                        
                        # OCR với handler (adaptive mode, gaming config)
                        ocr_raw_text = self.tesseract_handler.recognize(
                            img_cv_bgr, 
                            prep_mode='adaptive', 
                            block_size=41, 
                            c_value=-60,
                            confidence_threshold=50
                        )
                        
                        # Post-process text
                        text = self.clean_ocr_text(ocr_raw_text)
                        
                        # Apply linebreak conversion
                        text = text.replace('\n', ' ')
                        
                        # Remove trailing garbage nếu có punctuation
                        if text:
                            pattern = r'[.!?]|\.{3}|…'
                            if not list(re.finditer(pattern, text)):
                                text = ""
                            else:
                                text = self.remove_text_after_last_punctuation_mark(text)
                                
                    elif self.ocr_engine == "easyocr":
                        # Sử dụng EasyOCR - ưu tiên handler nếu có, fallback về reader cũ
                        if self.easyocr_handler:
                            # Sử dụng EasyOCR Handler (tối ưu hơn)
                            img_np = np.array(img)
                            text = self.easyocr_handler.recognize(img_np, confidence_threshold=0.3)
                            if text:
                                text = self.clean_ocr_text(text)
                        else:
                            # Fallback: sử dụng EasyOCR reader cũ (nếu handler không available)
                            processed_images, scale_factor = self.preprocess_image(img, mode='adaptive', block_size=41, c_value=-60)
                            text = self.perform_easyocr(processed_images)
                    else:
                        # Tesseract mode
                        if self.ocr_engine == "tesseract":
                            # Convert PIL to numpy array
                            img_np = np.array(img)
                            img_shape = img_np.shape
                            
                            if len(img_shape) == 3:
                                if img_shape[2] == 3:
                                    img_cv_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                                elif img_shape[2] == 4:
                                    img_cv_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGBA2BGR)
                                else:
                                    img_cv_bgr = cv2.cvtColor(img_np, cv2.COLOR_BGR2BGR)
                            elif len(img_shape) == 2:
                                img_cv_bgr = cv2.cvtColor(img_np, cv2.COLOR_GRAY2BGR)
                            else:
                                img_cv_bgr = img_np
                            
                            processed_cv_img = self.preprocess_for_ocr_cv(img_cv_bgr, mode='adaptive', block_size=41, c_value=-60)
                            
                            if self.cached_prep_mode != 'adaptive':
                                self.cached_prep_mode = 'adaptive'
                                self.cached_tess_params = self.get_tesseract_config('gaming')
                            
                            full_img_region = (0, 0, processed_cv_img.shape[1], processed_cv_img.shape[0])
                            ocr_raw_text = self.ocr_region_with_confidence(processed_cv_img, full_img_region, confidence_threshold=50)
                            text = self.clean_ocr_text(ocr_raw_text)
                            text = text.replace('\n', ' ')
                            
                            if text:
                                pattern = r'[.!?]|\.{3}|…'
                                if not list(re.finditer(pattern, text)):
                                    text = ""
                                else:
                                    text = self.remove_text_after_last_punctuation_mark(text)
                except Exception as ocr_err:
                    log_error(f"OCR processing error (engine: {self.ocr_engine})", ocr_err)
                    text = ""  # Set empty text on error
                
                if not text or self.is_placeholder_text(text):
                    self.text_stability_counter = 0
                    self.previous_text = ""
                    continue
                
                # Tính similarity (0.9 threshold) để tracking
                similarity = self.calculate_text_similarity(text, prev_ocr_text)
                if similarity > 0.9:
                    similar_texts_count += 1
                else:
                    similar_texts_count = 0
                    prev_ocr_text = text
                
                # Skip nếu có quá nhiều text tương tự (> 2 và < 1.0s)
                if similar_texts_count > 2 and (now - self.last_successful_translation_time) < 1.0:
                    continue
                
                # Sử dụng is_text_stable() để kiểm tra độ ổn định text
                # Hàm này sử dụng text_history và similarity để đánh giá
                if self.is_text_stable(text):
                    stable_text = text
                    
                    # Kiểm tra duplicate subtitle
                    if stable_text == self.last_processed_subtitle:
                        self.last_successful_translation_time = now
                        continue
                    
                    # Kiểm tra độ dài text - skip nếu quá dài (tránh quá tải)
                    if len(stable_text) > self.max_text_length_hard_limit:
                        log_error(f"Text quá dài ({len(stable_text)} chars), bỏ qua để tránh quá tải")
                        continue
                    
                    # Tính adaptive translation interval (tối ưu để nhanh hơn)
                    s_count = len(re.findall(r'[.!?]+', stable_text)) + 1
                    txt_len = len(stable_text)
                    # Adaptive interval: text dài hơn cần thời gian lâu hơn
                    # Tăng interval cho text dài để tránh quá tải
                    length_factor = 1.0 + (txt_len / 500)  # Mỗi 500 chars tăng 1x interval
                    adaptive_trans_interval = max(
                        0.05,  # Giảm từ 0.2 xuống 0.05 để nhanh hơn
                        min(
                            self.min_translation_interval * 2,  # Max 2x base interval
                            self.min_translation_interval * (0.3 + (0.05 * s_count) + (txt_len / 1000)) * length_factor
                        )
                    )
                    
                    # Chỉ translate nếu đã đủ thời gian
                    if (now - self.last_successful_translation_time) >= adaptive_trans_interval:
                        try:
                            # Start async translation
                            self.start_async_translation(stable_text, 0)
                            # QUAN TRỌNG: Update ngay lập tức để cho phép dialog tiếp theo được xử lý
                            # (không chờ translation hoàn thành)
                            self.last_successful_translation_time = now
                            self.text_stability_counter = 0
                            self.last_processed_subtitle = stable_text
                            similar_texts_count = 0
                            # Clear text history sau khi đã dịch để tránh ảnh hưởng đến text mới
                            self.text_history = []
                        except Exception as start_trans_err:
                            log_error("Error starting async translation", start_trans_err)
            
            except Exception as e_ocr_loop:
                log_error("OCR thread error", e_ocr_loop)
                self.text_stability_counter = 0
                self.previous_text = ""
                time.sleep(0.2)
        
        try:
            log_error("WT: OCR thread finished.", None)
        except Exception as e:
            # Fallback: print to stderr if log_error fails
            try:
                import sys
                sys.stderr.write(f"Error logging OCR thread finish: {e}\n")
            except Exception:
                pass  # Ultimate fallback - cannot log
    
    def run_translation_thread(self):
        """Translation thread - xử lý translation từ queue (legacy, ít dùng)"""
        try:
            log_error("WT: Translation thread started.", None)
        except Exception as e:
            # Fallback: print to stderr if log_error fails
            try:
                import sys
                sys.stderr.write(f"Error logging translation thread start: {e}\n")
            except Exception:
                pass  # Ultimate fallback - cannot log
        
        while self.is_running:
            try:
                # Xử lý translation từ queue nếu có (legacy)
                try:
                    text_to_translate = self.translation_queue.get(timeout=0.1)
                    if text_to_translate and not self.is_placeholder_text(text_to_translate):
                        try:
                            self.start_async_translation(text_to_translate, 0)
                        except Exception as start_err:
                            log_error("Error starting translation from queue", start_err)
                except queue.Empty:
                    pass  # Normal - queue is empty
                except Exception as queue_err:
                    log_error("Error getting from translation queue", queue_err)
                
                time.sleep(0.1)
            
            except Exception as e:
                log_error("Translation thread error", e)
                time.sleep(0.2)
        
        try:
            log_error("WT: Translation thread finished.", None)
        except Exception as e:
            # Fallback: print to stderr if log_error fails
            try:
                import sys
                sys.stderr.write(f"Error logging translation thread finish: {e}\n")
            except Exception:
                pass  # Ultimate fallback - cannot log
    
    def start_async_translation(self, text_to_translate, ocr_sequence_number):
        """Start async translation processing"""
        try:
            # Dùng dialogue validator thay vì simple length check
            if not text_to_translate or not should_translate_text(text_to_translate):
                log_debug("Skipping translation - invalid dialogue text")
                return  # Skip empty or invalid text
            
            self.translation_sequence_counter += 1
            translation_sequence = self.translation_sequence_counter
            
            if len(self.active_translation_calls) >= self.max_concurrent_translation_calls:
                log_debug(f"Skipping translation - too many concurrent calls ({len(self.active_translation_calls)})")
                return  # Skip if too many concurrent calls
            
            self.active_translation_calls.add(translation_sequence)
            
            self.translation_thread_pool.submit(
                self.process_translation_async,
                text_to_translate, translation_sequence, ocr_sequence_number
            )
        
        except Exception as e:
            log_error("Error starting async translation", e)
    
    def process_translation_async(self, text_to_translate, translation_sequence, ocr_sequence_number):
        """Process translation asynchronously với text chunking cho text dài"""
        try:
            clean_text = self.clean_ocr_text(text_to_translate)
            
            if self.is_placeholder_text(clean_text):
                return
            
            # Skip nếu text quá dài (hard limit)
            if len(clean_text) > self.max_text_length_hard_limit:
                log_error(f"Text quá dài ({len(clean_text)} chars) trong process_translation_async, bỏ qua")
                return
            
            if clean_text and len(clean_text) > 2:
                # Check unified cache first (primary cache)
                translated_text = None
                translator_name = 'deepl' if self.use_deepl else 'google'
                
                try:
                    translated_text = self.unified_cache.get(
                        clean_text, 
                        self.source_language, 
                        self.target_language, 
                        translator_name
                    )
                except Exception as cache_err:
                    log_error("Error getting translation from unified cache", cache_err)
                    translated_text = None
                
                # Fallback to cache_manager if unified cache misses
                if not translated_text and self.cache_manager:
                    try:
                        translated_text = self.cache_manager.get(clean_text, self.source_language, self.target_language, translator_name)
                    except Exception as cache_err:
                        log_error("Error getting translation from cache_manager", cache_err)
                        translated_text = None
                
                # Fallback to old translation_cache
                if not translated_text:
                    cache_key = clean_text.lower().strip()
                    if cache_key in self.translation_cache:
                        translated_text = self.translation_cache[cache_key]
                
                if not translated_text:
                    # Check if batch translation should be used
                    use_batch = should_use_batch_translation(clean_text)
                    
                    if use_batch:
                        # Use batch translation
                        try:
                            # split_into_sentences returns batches (list of lists)
                            batches = split_into_sentences(clean_text)
                            
                            if not batches:
                                # No batches, fallback to single translation
                                use_batch = False
                            else:
                                # Flatten batches into sentences for batch translation
                                sentences = []
                                for batch in batches:
                                    if isinstance(batch, list):
                                        sentences.extend(batch)
                                    elif isinstance(batch, str):
                                        sentences.append(batch)
                                
                                if not sentences:
                                    use_batch = False
                                elif self.use_deepl and self.DEEPL_API_AVAILABLE and self.deepl_api_client:
                                    # Map target language to DeepL format
                                    deepl_target_map = {
                                        'vi': 'VI',
                                        'en': 'EN-US',
                                        'ja': 'JA',
                                        'ko': 'KO',
                                        'zh': 'ZH',
                                        'fr': 'FR',
                                        'de': 'DE',
                                        'es': 'ES'
                                    }
                                    deepl_target_lang = deepl_target_map.get(self.target_language, 'EN-US')
                                    translated_sentences = translate_batch_deepl(
                                        self.deepl_api_client, 
                                        sentences, 
                                        deepl_target_lang
                                    )
                                    # Convert list to string
                                    if translated_sentences:
                                        translated_text = " ".join(translated_sentences)
                                    else:
                                        translated_text = None
                                    # Update context after batch translation
                                    if translated_text:
                                        try:
                                            self.deepl_context_manager.update_context(
                                                clean_text,
                                                self.source_language,
                                                self.target_language
                                            )
                                        except Exception as e:
                                            log_error("Error updating DeepL context after batch", e)
                                else:
                                    translated_sentences = translate_batch_google(
                                        self.translator,
                                        sentences
                                    )
                                    # Convert list to string
                                    if translated_sentences:
                                        translated_text = " ".join(translated_sentences)
                                    else:
                                        translated_text = None
                        except Exception as batch_err:
                            log_error("Batch translation failed, falling back to single translation", batch_err)
                            use_batch = False
                    
                    if not use_batch or not translated_text:
                        # Single translation (original logic)
                        # Chunk text nếu quá dài để dịch nhanh hơn
                        if len(clean_text) > self.max_text_length_for_translation:
                            # Chia text thành chunks và dịch từng chunk
                            chunks = self.chunk_text_for_translation(clean_text, self.max_text_length_for_translation)
                            translated_chunks = []
                            
                            for chunk in chunks:
                                if not chunk or len(chunk.strip()) < 2:
                                    continue
                                
                                max_retries = 2
                                chunk_translated = None
                                for attempt in range(max_retries):
                                    try:
                                        # Check circuit breaker for Google
                                        if not self.use_deepl:
                                            if self.google_translation_circuit_breaker.should_force_refresh():
                                                log_debug("Google Translate circuit breaker is open, skipping")
                                                break
                                        
                                        # Ưu tiên: DeepL > Google
                                        if self.use_deepl and self.DEEPL_API_AVAILABLE and self.deepl_api_client:
                                            chunk_translated = self.translate_with_deepl(chunk, source_text_for_context=chunk)
                                        else:
                                            start_time = time.time()
                                            chunk_translated = self.translator.translate(chunk)
                                            duration = time.time() - start_time
                                            self.google_translation_circuit_breaker.record_call(duration, success=chunk_translated is not None)
                                        
                                        if self.is_error_message(chunk_translated) or self.is_placeholder_text(chunk_translated):
                                            chunk_translated = None
                                            break
                                        
                                        break
                                    except Exception as trans_error:
                                        if not self.use_deepl:
                                            duration = time.time() - start_time if 'start_time' in locals() else 0.1
                                            self.google_translation_circuit_breaker.record_call(duration, success=False)
                                        if attempt < max_retries - 1:
                                            time.sleep(0.1 * (attempt + 1))
                                            continue
                                        else:
                                            log_error(f"Translation failed for chunk ({len(chunk)} chars)", trans_error)
                                            chunk_translated = None
                                
                                if chunk_translated:
                                    translated_chunks.append(chunk_translated)
                                # Thêm delay nhỏ giữa các chunks để tránh quá tải API
                                if len(chunks) > 1:
                                    time.sleep(0.1)
                            
                            # Ghép các chunks lại
                            translated_text = " ".join(translated_chunks) if translated_chunks else None
                        else:
                            # Text ngắn, dịch bình thường
                            max_retries = 2
                            for attempt in range(max_retries):
                                try:
                                    # Check circuit breaker for Google
                                    if not self.use_deepl:
                                        if self.google_translation_circuit_breaker.should_force_refresh():
                                            log_debug("Google Translate circuit breaker is open, skipping")
                                            break
                                    
                                    # Ưu tiên: DeepL > Google
                                    if self.use_deepl and self.DEEPL_API_AVAILABLE and self.deepl_api_client:
                                        translated_text = self.translate_with_deepl(clean_text, source_text_for_context=clean_text)
                                    else:
                                        start_time = time.time()
                                        translated_text = self.translator.translate(clean_text)
                                        duration = time.time() - start_time
                                        self.google_translation_circuit_breaker.record_call(duration, success=translated_text is not None)
                                    
                                    if self.is_error_message(translated_text) or self.is_placeholder_text(translated_text):
                                        translated_text = None
                                        break
                                    
                                    break
                                except Exception as trans_error:
                                    if not self.use_deepl:
                                        duration = time.time() - start_time if 'start_time' in locals() else 0.1
                                        self.google_translation_circuit_breaker.record_call(duration, success=False)
                                    if attempt < max_retries - 1:
                                        time.sleep(0.1 * (attempt + 1))
                                        continue
                                    else:
                                        log_error("Translation failed after retries", trans_error)
                                        translated_text = None
                    
                    # Cache result
                    if translated_text and not self.is_error_message(translated_text):
                        translated_text = self.post_process_translation_text(translated_text)
                        translated_text = self.format_dialog_text(translated_text)
                        
                        # Store in unified cache (primary)
                        try:
                            self.unified_cache.store(
                                clean_text, 
                                self.source_language, 
                                self.target_language, 
                                translator_name,
                                translated_text
                            )
                        except Exception as cache_err:
                            log_error("Error storing translation to unified cache", cache_err)
                        
                        # Also store in cache_manager for backward compatibility
                        if self.cache_manager:
                            try:
                                self.cache_manager.store(clean_text, self.source_language, self.target_language, translated_text, translator_name)
                            except Exception as cache_err:
                                log_error("Error storing translation to cache_manager", cache_err)
                        
                        # Also store in old translation_cache for backward compatibility
                        cache_key = clean_text.lower().strip()
                        self.translation_cache[cache_key] = translated_text
                        
                        # Limit cache size - tối ưu cho long sessions
                        if len(self.translation_cache) > self.max_cache_size:
                            # Xóa 20% cache cũ nhất (LRU-like)
                            keys_to_remove = list(self.translation_cache.keys())[:int(self.max_cache_size * 0.2)]
                            for key in keys_to_remove:
                                del self.translation_cache[key]
                
                # Process translation response với chronological ordering
                # QUAN TRỌNG: Luôn gọi process_translation_response để đảm bảo chronological ordering
                # Ngay cả khi translated_text là None hoặc empty, vẫn cần check sequence
                if self.overlay_window and self.is_running:
                    try:
                        # Thread-safe: check if window still exists before scheduling
                        if hasattr(self.overlay_window, 'winfo_exists') and self.overlay_window.winfo_exists():
                            self.overlay_window.after(
                                0, self.process_translation_response,
                                translated_text, translation_sequence, clean_text, ocr_sequence_number
                            )
                    except (RuntimeError, tk.TclError) as e:
                        # Window destroyed or main loop not running, ignore
                        pass
                    except Exception as e:
                        log_error("Error scheduling translation response", e)
                else:
                    # Nếu không có overlay window, vẫn cần update sequence để không block dialog tiếp theo
                    if translation_sequence > self.last_displayed_translation_sequence:
                        self.last_displayed_translation_sequence = translation_sequence
        
        except Exception as e:
            log_error("Error in async translation", e)
        finally:
            self.active_translation_calls.discard(translation_sequence)
    
    def process_translation_response(self, translation_result, translation_sequence, original_text, ocr_sequence_number):
        """Process translation response với chronological order enforcement - thread-safe"""
        try:
            # QUAN TRỌNG: Kiểm tra chronological order TRƯỚC, không phụ thuộc vào translation_result
            if not hasattr(self, 'last_displayed_translation_sequence'):
                self.last_displayed_translation_sequence = 0
            
            if translation_sequence <= self.last_displayed_translation_sequence:
                # Sequence quá cũ, bỏ qua (nhưng vẫn giữ trong cache)
                return
            
            # Nếu translation_result là None, vẫn update sequence để không block dialog tiếp theo
            if translation_result is None:
                self.last_displayed_translation_sequence = translation_sequence
                return
            
            # Kiểm tra error message
            error_prefixes = (
                "Err:", "error:", "api error", "not initialized", "missing",
                "failed", "not available", "not supported",
                "invalid result", "empty result", "lỗi"
            )
            
            if isinstance(translation_result, str) and any(translation_result.startswith(p) for p in error_prefixes):
                # Hiển thị error nhưng vẫn update sequence
                if self.overlay_window:
                    try:
                        # Thread-safe: check if window still exists
                        if hasattr(self.overlay_window, 'winfo_exists') and self.overlay_window.winfo_exists():
                            self.overlay_window.after(
                                0, self.update_overlay, original_text, f"Lỗi Dịch Thuật:\n{translation_result}"
                            )
                    except (RuntimeError, tk.TclError) as e:
                        # Window destroyed, ignore
                        pass
                    except Exception as e:
                        log_error("Error displaying error message in overlay", e)
                self.last_displayed_translation_sequence = translation_sequence
                return
            
            # Hiển thị translation hợp lệ
            if isinstance(translation_result, str) and translation_result.strip():
                if self.overlay_window:
                    try:
                        # Thread-safe: check if window still exists
                        if hasattr(self.overlay_window, 'winfo_exists') and self.overlay_window.winfo_exists():
                            self.overlay_window.after(
                                0, self.update_overlay, original_text, translation_result
                            )
                    except (RuntimeError, tk.TclError) as e:
                        # Window destroyed, ignore
                        pass
                    except Exception as e:
                        log_error("Error scheduling overlay update", e)
                self.last_displayed_translation_sequence = translation_sequence
                self.last_successful_translation_time = time.monotonic()
            else:
                # Empty hoặc invalid result, vẫn update sequence để không block dialog tiếp theo
                self.last_displayed_translation_sequence = translation_sequence
        
        except (RuntimeError, tk.TclError) as e:
            # Tkinter error - window destroyed or main loop not running
            # Ignore silently to avoid spam
            pass
        except Exception as e:
            log_error("Error processing translation response", e)
    
    def capture_loop(self):
        """DEPRECATED: Vòng lặp chụp và dịch chạy trong thread nền - Đã thay bằng 3 threads riêng"""
        # Code cũ đã được thay thế bằng kiến trúc đa luồng:
        # - run_capture_thread(): Chụp màn hình và đưa vào queue
        # - run_ocr_thread(): Xử lý OCR từ queue
        # - run_translation_thread(): Xử lý translation
        # Giữ lại hàm này để tương thích, nhưng không dùng nữa
        pass
    
    def update_overlay(self, original, translated):
        """Cập nhật cửa sổ overlay với bản dịch mới - thread-safe (chỉ gọi từ main thread)"""
        if not self.overlay_window:
            return
        
        try:
            # Thread-safe check: verify window still exists
            if hasattr(self.overlay_window, 'winfo_exists') and not self.overlay_window.winfo_exists():
                return
            
            # Cập nhật text widget bản dịch (có thể cuộn)
            if hasattr(self, 'translation_text') and self.translation_text:
                try:
                    # Verify widget still exists (winfo_exists() returns True if exists)
                    widget_exists = True
                    if hasattr(self.translation_text, 'winfo_exists'):
                        try:
                            widget_exists = self.translation_text.winfo_exists()
                        except (RuntimeError, tk.TclError):
                            widget_exists = False
                    
                    if widget_exists:
                        self.translation_text.config(state=tk.NORMAL)
                    
                    if self.overlay_keep_history:
                        # Append mode: thêm bản dịch mới vào cuối với spacing (không dùng ký tự)
                        current_text = self.translation_text.get('1.0', tk.END).strip()
                        if current_text and current_text != "Đang chờ văn bản...":
                            # Thêm spacing (2 dòng trống) và text mới
                            spacing = "\n\n"
                            self.translation_text.insert(tk.END, spacing + translated)
                        else:
                            # Lần đầu tiên, chỉ insert text
                            self.translation_text.delete('1.0', tk.END)
                            self.translation_text.insert('1.0', translated)
                        # Auto-scroll to bottom để xem text mới nhất
                        self.translation_text.see(tk.END)
                    else:
                        # Replace mode: thay thế toàn bộ text
                        self.translation_text.delete('1.0', tk.END)
                        self.translation_text.insert('1.0', translated)
                        # Auto-scroll to top
                        self.translation_text.see('1.0')
                    
                    self.translation_text.config(state=tk.DISABLED)
                except (RuntimeError, tk.TclError) as e:
                    # Widget destroyed or main loop not running, ignore
                    pass
                except Exception as e:
                    log_error("Error updating translation text widget", e)
            elif hasattr(self, 'translation_label') and self.translation_label:
                # Fallback về label nếu text widget không tồn tại
                try:
                    # Verify label still exists
                    label_exists = True
                    if hasattr(self.translation_label, 'winfo_exists'):
                        try:
                            label_exists = self.translation_label.winfo_exists()
                        except (RuntimeError, tk.TclError):
                            label_exists = False
                    
                    if not label_exists:
                        return
                    if self.overlay_keep_history:
                        # Append cho label (giới hạn độ dài)
                        current_text = self.translation_label.cget('text')
                        if current_text and current_text != "Đang chờ văn bản...":
                            # Dùng spacing (2 dòng trống) thay vì ký tự
                            new_text = current_text + "\n\n" + translated
                            # Giới hạn độ dài để tránh quá dài
                            if len(new_text) > 2000:
                                new_text = new_text[-1500:]  # Giữ 1500 ký tự cuối
                            self.translation_label.config(text=new_text)
                        else:
                            self.translation_label.config(text=translated)
                    else:
                        self.translation_label.config(text=translated)
                except (RuntimeError, tk.TclError) as e:
                    # Widget destroyed or main loop not running, ignore
                    pass
                except Exception as e:
                    log_error("Error updating translation label", e)
            
            # Update original text if enabled (chỉ hiển thị text gốc mới nhất)
            if self.overlay_show_original and hasattr(self, 'original_label') and self.original_label:
                try:
                    # Verify label still exists
                    label_exists = True
                    if hasattr(self.original_label, 'winfo_exists'):
                        try:
                            label_exists = self.original_label.winfo_exists()
                        except (RuntimeError, tk.TclError):
                            label_exists = False
                    
                    if label_exists:
                        # Truncate if too long, but show more characters
                        max_length = self.overlay_width // 8  # Rough character estimate
                        display_original = original[:max_length] + "..." if len(original) > max_length else original
                        self.original_label.config(text=f"Nguyên bản: {display_original}")
                except (RuntimeError, tk.TclError) as e:
                    # Widget destroyed or main loop not running, ignore
                    pass
                except Exception as e:
                    log_error("Error updating original label in overlay", e)
        except (RuntimeError, tk.TclError) as e:
            # Tkinter error - window destroyed or main loop not running
            # Ignore silently to avoid spam
            pass
        except Exception as e:
            # Log error but don't block if window was closed or widget doesn't exist
            log_error("Error updating overlay", e)
    
    def log(self, message):
        """Thêm message vào status log - thread-safe"""
        # Kiểm tra xem status_text đã được tạo chưa
        if not hasattr(self, 'status_text') or self.status_text is None:
            return
        
        # Thread-safe: schedule call vào main thread
        def _log_in_main_thread():
            try:
                if hasattr(self, 'status_text') and self.status_text is not None:
                    timestamp = time.strftime("%H:%M:%S")
                    self.status_text.insert(tk.END, f"[{timestamp}] {message}\n")
                    self.status_text.see(tk.END)
            except (RuntimeError, tk.TclError):
                # Widget đã bị destroy, ignore
                pass
        
        try:
            # Schedule vào main thread
            self.root.after(0, _log_in_main_thread)
        except (RuntimeError, tk.TclError):
            # Root window đã bị destroy, fallback to file log
            log_error(f"[LOG] {message}")
    
    def on_closing(self):
        """Handle window close event"""
        try:
            # Stop capture loop first
            if self.is_capturing:
                self.stop_translation()
            
            # Stop all worker threads
            if hasattr(self, 'translation_worker') and self.translation_worker:
                try:
                    self.translation_worker.stop()
                    self.translation_worker = None
                except Exception as e:
                    log_error("Error stopping translation worker", e)
            
            # Clear tkinter variables to prevent threading issues
            try:
                # Delete all StringVar, BooleanVar, IntVar to prevent __del__ errors
                for attr_name in dir(self):
                    if attr_name.endswith('_var'):
                        try:
                            attr = getattr(self, attr_name)
                            if hasattr(attr, '_name'):
                                delattr(self, attr_name)
                        except:
                            pass
            except Exception as e:
                log_error("Error cleaning up tkinter variables", e)
            
            # Giải phóng OCR engines khi đóng ứng dụng
            if self.easyocr_handler:
                try:
                    self.easyocr_handler.cleanup()
                except Exception as e:
                    log_error("Error cleaning up EasyOCR handler in on_closing", e)
            
            # Cleanup easyocr_reader nếu có (fallback khi không dùng handlers)
            if hasattr(self, 'easyocr_reader') and self.easyocr_reader is not None:
                try:
                    import sys
                    from io import StringIO
                    
                    # Redirect stderr tạm thời để suppress warnings
                    old_stderr = sys.stderr
                    try:
                        sys.stderr = StringIO()
                        with warnings.catch_warnings():
                            warnings.filterwarnings('ignore')
                            self.easyocr_reader = None
                    finally:
                        sys.stderr = old_stderr
                except Exception as e:
                    log_error("Error cleaning up EasyOCR reader", e)
            
            self.save_config()
        except Exception as e:
            # Log but don't block closing
            try:
                log_error("Error during cleanup", e)
                self.log(f"Lỗi khi dọn dẹp: {e}")
            except:
                pass
        finally:
            # Properly destroy window
            try:
                self.root.quit()  # Stop mainloop
                self.root.destroy()  # Destroy window
            except Exception:
                pass


class RegionSelector:
    """Công cụ tương tác để chọn vùng chụp màn hình - hỗ trợ DPI scaling"""
    
    def __init__(self, parent, callback):
        self.parent = parent
        self.callback = callback
        self.start_x = None
        self.start_y = None
        self.end_x = None
        self.end_y = None
        self.rect = None
        
        # Get actual screen dimensions (handles DPI scaling correctly)
        self.screen_width, self.screen_height = get_actual_screen_size()
        
        # Create fullscreen transparent window
        self.selector = tk.Toplevel()
        self.selector.overrideredirect(True)  # Remove window decorations
        self.selector.attributes('-topmost', True)
        self.selector.attributes('-alpha', 0.3)
        self.selector.configure(bg='black')
        
        # Set geometry explicitly to cover entire screen (fixes DPI scaling issue)
        # Use negative offset to ensure coverage on all DPI settings
        self.selector.geometry(f"{self.screen_width}x{self.screen_height}+0+0")
        self.selector.state('normal')  # Don't use fullscreen, use explicit geometry
        
        # Ensure window is raised and focused
        self.selector.lift()
        self.selector.focus_force()
        
        # Create canvas for drawing selection
        self.canvas = tk.Canvas(
            self.selector,
            width=self.screen_width,
            height=self.screen_height,
            highlightthickness=0,
            bg='black',
            cursor="crosshair"
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Instructions - use actual screen width
        self.canvas.create_text(
            self.screen_width // 2,
            50,
            text="Click and drag to select the dialogue box region. Press ESC to cancel.",
            fill='white',
            font=("Arial", 14),
            anchor=tk.CENTER
        )
        
        # Bind events
        self.canvas.bind("<Button-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.selector.bind("<Escape>", self.cancel)
        
        # Update to ensure geometry is applied
        self.selector.update_idletasks()
        self.selector.focus_set()
    
    def on_button_press(self, event):
        """Handle mouse button press"""
        self.start_x = event.x
        self.start_y = event.y
        
        # Delete previous rectangle if exists
        if self.rect:
            self.canvas.delete(self.rect)
    
    def on_move_press(self, event):
        """Handle mouse drag"""
        if self.start_x and self.start_y:
            # Delete previous rectangle
            if self.rect:
                self.canvas.delete(self.rect)
            
            # Draw new rectangle
            self.rect = self.canvas.create_rectangle(
                self.start_x,
                self.start_y,
                event.x,
                event.y,
                outline='yellow',
                width=2
            )
    
    def on_button_release(self, event):
        """Handle mouse button release"""
        if self.start_x and self.start_y:
            self.end_x = event.x
            self.end_y = event.y
            
            # Calculate region
            x1 = min(self.start_x, self.end_x)
            y1 = min(self.start_y, self.end_y)
            x2 = max(self.start_x, self.end_x)
            y2 = max(self.start_y, self.end_y)
            
            width = x2 - x1
            height = y2 - y1
            
            if width > 50 and height > 20:  # Minimum size check
                region = (x1, y1, width, height)
                self.selector.destroy()
                self.callback(region)
            else:
                messagebox.showwarning(
                    "Vùng Không Hợp Lệ",
                    "Vùng đã chọn quá nhỏ. Vui lòng chọn vùng lớn hơn."
                )
                self.cancel()
    
    def cancel(self, event=None):
        """Cancel region selection"""
        self.selector.destroy()
        self.callback(None)


def main():
    """Điểm vào chính của công cụ"""
    root = None
    app = None
    try:
        root = tk.Tk()
        app = ScreenTranslator(root)
        root.mainloop()
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        if app:
            try:
                app.stop_translation()
                app.save_config()
            except Exception:
                pass
        if root:
            try:
                root.destroy()
            except Exception:
                pass
    except Exception as e:
        # Log error to file (important for exe that has no console)
        error_msg = f"Application startup error: {e}"
        log_error(error_msg, e)
        
        # Try to show error in messagebox if possible
        try:
            import tkinter.messagebox as mb
            mb.showerror("Lỗi Khởi Động", 
                        f"Công cụ gặp lỗi khi khởi động:\n\n{str(e)}\n\n"
                        f"Chi tiết đã được ghi vào file: {os.path.join(get_base_dir(), 'error_log.txt')}")
        except Exception:
            # If messagebox fails, at least we logged it
            pass
        
        # Try to print to console if available (for debugging)
        try:
            print(f"Application error: {e}")
            traceback.print_exc()
        except Exception:
            pass
        
        if root:
            try:
                root.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    main()