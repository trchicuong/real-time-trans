"""
Công cụ dịch màn hình thời gian thực
Tác giả: trchicuong
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import json
import os
import sys
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

def get_base_dir():
    """Lấy thư mục gốc để lưu config.json và error_log.txt
    Hỗ trợ cả chạy từ Python script và frozen executable (PyInstaller)
    """
    try:
        if getattr(sys, 'frozen', False):
            # Chạy từ executable (PyInstaller)
            # sys.executable trỏ đến file .exe
            base_dir = os.path.dirname(sys.executable)
        else:
            # Chạy từ Python script
            base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Đảm bảo đường dẫn được chuẩn hóa
        return os.path.normpath(base_dir)
    except Exception:
        # Fallback: sử dụng thư mục hiện tại
        return os.path.normpath(os.getcwd())

def log_error(error_msg, exception=None):
    """Ghi lỗi ra file error_log.txt để debug"""
    try:
        base_dir = get_base_dir()
        error_log_file = os.path.join(base_dir, "error_log.txt")
        with open(error_log_file, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"\n[{timestamp}] {error_msg}\n")
            if exception:
                f.write(f"Exception: {str(exception)}\n")
                f.write(f"Traceback:\n{traceback.format_exc()}\n")
            f.write("-" * 80 + "\n")
    except Exception:
        pass

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
    tesseract_cmd = shutil.which('tesseract')
    if tesseract_cmd:
        return os.path.normpath(tesseract_cmd)
    
    # Chỉ tìm trong các đường dẫn Windows mặc định nếu là Windows
    if os.name == 'nt':
        windows_paths = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        ]
        for path in windows_paths:
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
        self.root.geometry("600x800")
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
        
        # OCR Engine selection
        self.ocr_engine = "tesseract"  # Default: tesseract hoặc easyocr
        self.EASYOCR_AVAILABLE = EASYOCR_AVAILABLE
        self.easyocr_reader = None  # Lazy initialization
        
        # DeepL API support
        self.DEEPL_API_AVAILABLE = DEEPL_API_AVAILABLE
        self.deepl_api_client = None
        self.use_deepl = False  # Flag to use DeepL instead of Google
        self.deepl_api_key = ""  # DeepL API key
        
        self.overlay_drag_start_x = 0
        self.overlay_drag_start_y = 0
        
        self.source_language = "eng"
        self.target_language = "vi"
        self.update_interval = 0.2
        
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
        self.overlay_text_align = "left"
        self.overlay_line_spacing = 1.3
        self.overlay_padding_x = 18
        self.overlay_padding_y = 18
        self.overlay_border_width = 0
        self.overlay_border_color = "#ffffff"
        self.overlay_text_shadow = False
        self.overlay_word_wrap = True
        
        self.text_history = []
        self.history_size = 1
        self.performance_mode = "balanced"
        self.translation_cache = {}
        self.pending_translation = None
        self.translation_lock = threading.Lock()
        
        # Text stability và similarity tracking
        self.text_stability_counter = 0
        self.previous_text = ""
        self.similar_texts_count = 0
        self.prev_ocr_text = ""
        self.last_processed_subtitle = None
        self.last_successful_translation_time = 0.0
        self.stable_threshold = 0  # Số lần text phải giống nhau để coi là stable (0 = instant)
        self.min_translation_interval = 0.1  # Khoảng thời gian tối thiểu giữa các lần dịch (giảm từ 0.2 để nhanh hơn)
        
        # Threading infrastructure
        self.is_running = False  # Flag để control threads
        self.ocr_queue = queue.Queue(maxsize=5)  # Queue để truyền ảnh từ capture sang OCR thread
        self.translation_queue = queue.Queue(maxsize=10)  # Queue để truyền text (legacy, ít dùng)
        
        # Thread pools cho async processing
        # Tăng thread pool size để xử lý nhanh hơn
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
        self.max_concurrent_translation_calls = 6
        
        # Adaptive scan interval
        self.base_scan_interval = int(self.update_interval * 1000)  # ms
        self.current_scan_interval = self.base_scan_interval
        
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
        
        # Khởi tạo OCR engine nếu cần
        if self.ocr_engine == "easyocr" and self.EASYOCR_AVAILABLE:
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
        
        if not self.verify_tesseract():
            self.log("Cảnh báo: Không tìm thấy Tesseract OCR. Vui lòng sử dụng nút 'Duyệt' để đặt đường dẫn.")
            tesseract_path = find_tesseract(self.custom_tesseract_path)
            if tesseract_path:
                # Chuẩn hóa đường dẫn
                tesseract_path = os.path.normpath(tesseract_path)
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
                if self.verify_tesseract():
                    self.log(f"Tự động tìm thấy Tesseract: {tesseract_path}")
                    if hasattr(self, 'tesseract_path_label'):
                        self.tesseract_path_label.config(
                            text=f"Đường dẫn: {tesseract_path}",
                            fg="green"
                        )
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def verify_tesseract(self):
        """Kiểm tra Tesseract OCR đã được cài đặt và có thể truy cập"""
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception as e:
            log_error("Lỗi kiểm tra Tesseract version", e)
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
        
        # OCR Engine Selection
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
        
        # DeepL API Key (only show if DeepL is available)
        if self.DEEPL_API_AVAILABLE:
            ttk.Label(translation_frame, text="DeepL API Key:").grid(row=2, column=0, sticky=tk.W, pady=5)
            self.deepl_api_key_var = tk.StringVar(value=self.deepl_api_key)
            deepl_key_entry = ttk.Entry(
                translation_frame,
                textvariable=self.deepl_api_key_var,
                width=40,
                show="*"
            )
            deepl_key_entry.grid(row=2, column=1, pady=5, sticky=tk.W+tk.E)
            deepl_key_entry.bind("<FocusOut>", self.on_deepl_key_change)
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
        
        # Text Shadow
        self.text_shadow_var = tk.BooleanVar(value=self.overlay_text_shadow)
        text_shadow_check = ttk.Checkbutton(
            settings_container,
            text="Bóng Chữ",
            variable=self.text_shadow_var
        )
        text_shadow_check.grid(row=8, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # Word Wrap
        self.word_wrap_var = tk.BooleanVar(value=self.overlay_word_wrap)
        word_wrap_check = ttk.Checkbutton(
            settings_container,
            text="Xuống Dòng Tự Động",
            variable=self.word_wrap_var
        )
        word_wrap_check.grid(row=8, column=2, columnspan=2, sticky=tk.W, pady=5)
        
        # Preset configurations frame
        preset_frame = ttk.LabelFrame(settings_container, text="Cấu Hình Nhanh (Preset)", padding=10)
        preset_frame.grid(row=9, column=0, columnspan=4, pady=10, sticky=tk.EW)
        
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
        apply_button_frame.grid(row=10, column=0, columnspan=4, pady=15, sticky=tk.EW)
        
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
        instructions_text = """
HƯỚNG DẪN SỬ DỤNG CÔNG CỤ DỊCH MÀN HÌNH THỜI GIAN THỰC

1. CÀI ĐẶT:
   • Cài đặt Tesseract OCR (BẮT BUỘC):
     - Tải từ: https://github.com/UB-Mannheim/tesseract/wiki
     - Chạy file cài đặt và làm theo hướng dẫn
     - Ghi nhớ thư mục cài đặt
     - Nếu công cụ không tự động tìm thấy, dùng nút "Duyệt" trong tab "Cài Đặt" để chọn
   
   • Cài đặt dữ liệu ngôn ngữ (Nếu cần):
     - Nếu ứng dụng dùng tiếng Nhật, Hàn, Trung, v.v.
     - Tải từ: https://github.com/tesseract-ocr/tessdata
     - Đặt file .traineddata vào thư mục tessdata của Tesseract
   
   • Chạy công cụ:
     - Chạy trực tiếp file RealTimeScreenTranslator.exe
     - Cửa sổ công cụ sẽ hiện ra

2. BẮT ĐẦU SỬ DỤNG:
   • Chọn vùng chụp màn hình:
     - Mở ứng dụng (game, ứng dụng, v.v.) mà bạn muốn dịch
     - Trong tab "Cài Đặt", nhấn nút "Chọn Vùng"
     - Cửa sổ sẽ thu nhỏ, màn hình sẽ tối đi
     - Dùng chuột kéo để chọn vùng hộp thoại, thả để xác nhận
     - ⚠️ Chọn càng chính xác càng tốt - chỉ vùng hộp thoại!
   
   • Cấu hình cài đặt (Tab "Cài Đặt"):
     - Ngôn ngữ nguồn: Chọn ngôn ngữ của văn bản trong ứng dụng
     - Khoảng thời gian cập nhật: 100-200ms cho game, 200-300ms cho ứng dụng thường
     - Engine OCR: Chọn Tesseract hoặc EasyOCR
     - Ngôn ngữ đích: Chọn ngôn ngữ muốn dịch sang
     - Dịch vụ dịch thuật: Google Translate (miễn phí) hoặc DeepL (cần API key)
   
   • Tùy chỉnh giao diện (Tab "Giao Diện Dịch"):
     - Sử dụng Preset: "Tối Ưu Tốc Độ", "Cân Bằng", "Tối Ưu Chất Lượng", "Mặc Định"
     - Hoặc tùy chỉnh thủ công: cỡ chữ, phông chữ, màu sắc, kích thước, v.v.
     - Nhấn "Áp Dụng" sau khi thay đổi
   
   • Bắt đầu dịch (Tab "Điều Khiển"):
     - Nhấn nút "Bắt Đầu Dịch"
     - Màn hình dịch sẽ xuất hiện và tự động dịch văn bản

3. SỬ DỤNG MÀN HÌNH DỊCH:
   • Di chuyển: Kéo thả màn hình dịch đến vị trí mong muốn
   • Thay đổi kích thước: Kéo các cạnh hoặc góc để resize
   • Cuộn văn bản: Cuộn lên/xuống trong màn hình dịch nếu văn bản quá dài
   • Khóa: Tích vào "Khóa màn hình dịch" trong tab "Điều Khiển" để ngăn di chuyển nhầm
   • Tự động lưu: Vị trí và kích thước được tự động lưu lại

4. MẸO SỬ DỤNG:
   • Sử dụng Preset:
     - Game có hội thoại nhanh: "Tối Ưu Tốc Độ"
     - Game/ứng dụng thường: "Cân Bằng"
     - Cần đọc kỹ: "Tối Ưu Chất Lượng"
   
   • Chọn vùng chụp càng chính xác càng tốt - chỉ vùng hộp thoại
   • Thử cả Tesseract và EasyOCR để xem engine nào chính xác hơn
   • Google Translate: Miễn phí, đủ dùng cho hầu hết trường hợp
   • DeepL: Chất lượng tốt hơn, đặc biệt cho tiếng Nhật, Hàn (cần trả phí)
   • Khi chơi game: Khóa màn hình dịch và sử dụng preset "Tối Ưu Tốc Độ"

5. XỬ LÝ SỰ CỐ:
   • OCR không hoạt động:
     - Kiểm tra Tesseract đã cài đặt đúng chưa
     - Dùng nút "Duyệt" để chọn đường dẫn Tesseract
     - Thử chuyển sang EasyOCR
     - Kiểm tra ngôn ngữ nguồn đã chọn đúng chưa
   
   • Dịch không hoạt động:
     - Kiểm tra kết nối internet
     - Nếu dùng DeepL: Kiểm tra API key đã nhập đúng chưa
     - Thử chuyển sang Google Translate
   
   • Dịch sai:
     - Thử thay đổi ngôn ngữ nguồn
     - Thử chuyển engine OCR (Tesseract ↔ EasyOCR)
     - Đảm bảo văn bản trong vùng chụp rõ ràng, không bị mờ
   
   • Chậm hoặc lag:
     - Tăng khoảng thời gian cập nhật (200-300ms)
     - Sử dụng preset "Cân Bằng" hoặc "Tối Ưu Tốc Độ"
     - Chọn vùng chụp nhỏ hơn
     - Tắt hiển thị văn bản gốc
     - Đóng các ứng dụng khác đang chạy
   
   • Màn hình dịch không hiển thị:
     - Kiểm tra màn hình dịch không bị di chuyển ra ngoài màn hình
     - Thử dừng và khởi động lại dịch
     - Nhấn "Đặt Lại Tất Cả" để reset vị trí
     - Đảm bảo tỷ lệ hiển thị màn hình Windows là 100%
   
   • Xem chi tiết:
     - Xem tab "Trạng Thái" để biết thông tin chi tiết về lỗi
     - Kiểm tra file error_log.txt trong thư mục chương trình (nếu có)

6. LƯU Ý QUAN TRỌNG:
   • Cần kết nối internet để dịch (Google Translate và DeepL)
   • Chất lượng dịch phụ thuộc vào:
     - Độ rõ và kích thước văn bản
     - Độ tương phản nền
     - Kiểu phông chữ
     - Độ chính xác của OCR
   • Tất cả cài đặt được tự động lưu lại
   • Công cụ sẽ tự động điều chỉnh tốc độ để hoạt động mượt mà

7. CÁC TÍNH NĂNG:
   • Hỗ trợ 2 engine OCR: Tesseract và EasyOCR
   • Hỗ trợ 2 dịch vụ dịch thuật: Google Translate và DeepL
   • Tự động phát hiện và xử lý nhiều hộp thoại liên tiếp
   • Tự động lưu và khôi phục cài đặt
   • Giao diện tùy chỉnh hoàn toàn với preset nhanh
   • Hỗ trợ nhiều ngôn ngữ OCR và dịch thuật
   • Khóa màn hình dịch để tránh di chuyển nhầm khi chơi game

8. NGÔN NGỮ ĐƯỢC HỖ TRỢ:
   • Ngôn ngữ nguồn (OCR): Anh, Nhật, Hàn, Trung, Pháp, Đức, Tây Ban Nha
   • Ngôn ngữ đích (Dịch thuật): Việt, Anh, Nhật, Hàn, Trung, Pháp, Đức, Tây Ban Nha

9. CÁC TAB TRONG CÔNG CỤ:
   • Tab "Cài Đặt": Chọn vùng, ngôn ngữ, engine OCR, dịch vụ dịch thuật
   • Tab "Giao Diện Dịch": Tùy chỉnh giao diện với preset hoặc thủ công
   • Tab "Điều Khiển": Bắt đầu/dừng dịch, khóa màn hình dịch
   • Tab "Trạng Thái": Xem nhật ký hoạt động và thông tin lỗi
   • Tab "Hướng Dẫn": Xem hướng dẫn sử dụng đầy đủ
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
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            self.capture_region = config.get('capture_region')
            self.source_language = config.get('source_language', 'eng')
            self.ocr_engine = config.get('ocr_engine', 'tesseract')
            self.update_interval = config.get('update_interval', 0.5)
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
                'custom_tesseract_path': tesseract_path_to_save,
                'deepl_api_key': self.deepl_api_key,
                'use_deepl': self.use_deepl,
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
                except Exception:
                    pass  # Nếu không tạo được thư mục, thử ghi trực tiếp
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except (IOError, PermissionError) as e:
            log_error("Lỗi ghi file cấu hình (quyền truy cập)", e)
            self.log(f"Lỗi lưu cấu hình (quyền truy cập): {e}")
        except Exception as e:
            log_error("Lỗi lưu cấu hình", e)
            self.log(f"Lỗi lưu cấu hình: {e}")
    
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
        
        if self.use_deepl:
            if not self.DEEPL_API_AVAILABLE:
                messagebox.showerror("Lỗi", "DeepL API không khả dụng. Vui lòng cài đặt: pip install deepl")
                self.translation_service_var.set("google")
                self.use_deepl = False
                self.save_config()
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
        else:
            # Chuyển về Google Translate
            if old_use_deepl:
                self.log("Đã chuyển sang Google Translate")
    
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
    
    def on_source_lang_change(self, event=None):
        """Handle source language change"""
        self.source_language = self.source_lang_var.get()
        self.save_config()
        self.log(f"Đã thay đổi ngôn ngữ nguồn thành: {self.source_language}")
        
        # Khởi tạo lại EasyOCR reader nếu đang dùng EasyOCR
        if self.ocr_engine == "easyocr" and self.EASYOCR_AVAILABLE:
            self.easyocr_reader = None  # Reset để khởi tạo lại với ngôn ngữ mới
            self.initialize_easyocr_reader()
    
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
            if self.ocr_engine == "easyocr" and self.EASYOCR_AVAILABLE:
                # Reset reader cũ nếu có
                if old_engine == "easyocr":
                    self.easyocr_reader = None
                self.initialize_easyocr_reader()
            elif self.ocr_engine == "tesseract" and old_engine == "easyocr":
                # Giải phóng EasyOCR reader khi chuyển về Tesseract
                self.easyocr_reader = None
                self.log("Đã giải phóng EasyOCR reader")
    
    def update_ocr_engine_ui(self):
        """Cập nhật UI dựa trên OCR engine được chọn"""
        if hasattr(self, 'tesseract_path_label_frame') and hasattr(self, 'tesseract_path_label_widget'):
            if self.ocr_engine == "tesseract":
                # Hiển thị Tesseract path
                self.tesseract_path_label_widget.grid()
                self.tesseract_path_label_frame.grid()
            else:
                # Ẩn Tesseract path khi dùng EasyOCR
                self.tesseract_path_label_widget.grid_remove()
                self.tesseract_path_label_frame.grid_remove()
    
    def initialize_easyocr_reader(self):
        """Khởi tạo EasyOCR reader (lazy initialization)"""
        if not self.EASYOCR_AVAILABLE:
            return None
        
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
                        self.easyocr_reader = easyocr.Reader([easyocr_lang], gpu=False, verbose=False)
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
            self.save_config()
            self.log(f"Đã thay đổi khoảng thời gian cập nhật thành: {interval_ms}ms")
        except ValueError:
            self.log("Giá trị khoảng thời gian không hợp lệ")
    
    def apply_preset(self, preset_type):
        """Apply preset configuration based on performance level - deeply tuned for translation speed"""
        if preset_type == 'speed':
            # Speed optimized: minimal UI processing, fastest updates, minimal visual effects
            # Also update interval for maximum speed
            self.update_interval = 0.1  # 100ms for fastest updates
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
            self.text_shadow_var.set(False)  # No shadow for speed
            self.word_wrap_var.set(True)
            self.save_config()  # Save interval change
            self.log("Đã áp dụng cấu hình: Tối Ưu Tốc Độ (100ms cập nhật)")
        elif preset_type == 'balanced':
            # Balanced: good quality and speed - optimized for most games
            self.update_interval = 0.15  # 150ms for balanced speed
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
            self.text_shadow_var.set(False)
            self.word_wrap_var.set(True)
            self.save_config()  # Save interval change
            self.log("Đã áp dụng cấu hình: Cân Bằng (150ms cập nhật)")
        elif preset_type == 'quality':
            # Quality optimized: best readability, slightly slower for accuracy
            self.update_interval = 0.2  # 200ms for quality (default)
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
            self.text_shadow_var.set(True)
            self.word_wrap_var.set(True)
            self.save_config()  # Save interval change
            self.log("Đã áp dụng cấu hình: Tối Ưu Chất Lượng (200ms cập nhật)")
        elif preset_type == 'default':
            # Default settings (optimized defaults)
            self.update_interval = 0.2  # 200ms default
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
            self.text_shadow_var.set(False)
            self.word_wrap_var.set(True)
            self.save_config()  # Save interval change
            self.log("Đã áp dụng cấu hình: Mặc Định (200ms cập nhật)")
    
    def reset_all_settings(self):
        """Reset all overlay settings to defaults including position"""
        try:
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
            self.overlay_text_shadow = False
            self.overlay_word_wrap = True
            
            # Reset overlay position to None (will use original position calculation)
            self.overlay_position_x = None
            self.overlay_position_y = None
            
            # Update UI variables
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
            if hasattr(self, 'text_shadow_var'):
                self.text_shadow_var.set(self.overlay_text_shadow)
            if hasattr(self, 'word_wrap_var'):
                self.word_wrap_var.set(self.overlay_word_wrap)
            
            # Tạo lại overlay nếu có để áp dụng reset vị trí
            if self.overlay_window:
                try:
                    self.create_overlay()
                except Exception as e:
                    log_error("Error recreating overlay after reset", e)
            
            self.log("Đã đặt lại tất cả cài đặt về mặc định (bao gồm vị trí màn hình dịch)")
            messagebox.showinfo("Thành công", "Đã đặt lại tất cả cài đặt về mặc định.\nVị trí màn hình dịch đã được đặt lại về vị trí ban đầu.\nNhấn 'Áp Dụng' để áp dụng thay đổi.")
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
            self.overlay_text_shadow = self.text_shadow_var.get()
            self.overlay_word_wrap = self.word_wrap_var.get()
            
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
                except Exception:
                    pass
        
        # Shutdown thread pools
        try:
            self.ocr_thread_pool.shutdown(wait=False)
            self.translation_thread_pool.shutdown(wait=False)
        except Exception:
            pass
        
        # Giải phóng OCR engines với suppress warnings
        if self.easyocr_reader is not None:
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
            except Exception:
                pass
        
        # Recreate thread pools for next run
        # Tăng thread pool size để xử lý nhanh hơn
        self.ocr_thread_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="OCR")
        self.translation_thread_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="Translation")
        
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        
        # Reset text history and cache
        self.text_history = []
        self.translation_cache.clear()
        self.pending_translation = None
        self.text_stability_counter = 0
        self.previous_text = ""
        self.similar_texts_count = 0
        self.prev_ocr_text = ""
        self.last_processed_subtitle = None
        
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
        
        # Close overlay window
        if self.overlay_window:
            try:
                self.overlay_window.destroy()
            except Exception:
                pass
            self.overlay_window = None
            self.shadow_label = None
        
        self.log("Đã dừng dịch.")
    
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
            # Căn giữa màn hình mặc định
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
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
        
        # Text shadow effect (using multiple labels for shadow)
        self.shadow_label = None
        if self.overlay_text_shadow:
            # Shadow label (behind main text)
            self.shadow_label = tk.Label(
                translation_frame,
                text="Đang chờ văn bản...",
                font=font_tuple,
                bg=self.overlay_bg_color,
                fg="#000000",  # Black shadow
                wraplength=wraplength,
                justify=justify_option,
                anchor='nw' if justify_option == tk.LEFT else 'center',
                padx=7,  # Offset for shadow
                pady=10,
                relief=tk.FLAT
            )
            self.shadow_label.place(x=2, y=2)  # Position shadow slightly offset
            # Make shadow draggable too
            self.shadow_label.bind('<Button-1>', self.on_overlay_click)
            self.shadow_label.bind('<B1-Motion>', self.on_overlay_motion)
        
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
        
        # Lấy kích thước màn hình
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
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
        except:
            pass
        
        # Otherwise, drag the window
        if self.overlay_window:
            x = event.x_root - self.overlay_drag_start_x
            y = event.y_root - self.overlay_drag_start_y
            self.overlay_window.geometry(f"+{x}+{y}")
            # Cập nhật vị trí đã lưu
            self.overlay_position_x = x
            self.overlay_position_y = y
    
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
        Thực hiện OCR trên ảnh đã xử lý, chọn kết quả tốt nhất dựa trên độ tin cậy
        Hỗ trợ Tesseract và EasyOCR
        """
        # Chọn engine OCR
        if self.ocr_engine == "easyocr" and self.EASYOCR_AVAILABLE:
            return self.perform_easyocr(processed_images)
        else:
            # Default: Tesseract
            return self.perform_tesseract_ocr(processed_images, confidence_threshold)
    
    def perform_easyocr(self, processed_images):
        """Thực hiện OCR bằng EasyOCR"""
        try:
            # Khởi tạo reader nếu chưa có
            reader = self.initialize_easyocr_reader()
            if reader is None:
                log_error("EasyOCR reader không khả dụng", None)
                return ""
            
            # Sử dụng ảnh đầu tiên (đã được xử lý tốt nhất)
            img = processed_images[0]
            
            # EasyOCR yêu cầu numpy array
            if isinstance(img, np.ndarray):
                img_array = img
            else:
                # Convert PIL Image to numpy array
                img_array = np.array(img)
            
            # Thực hiện OCR
            results = reader.readtext(img_array)
            
            # Trích xuất text từ kết quả
            texts = []
            for (bbox, text, confidence) in results:
                if text and confidence > 0.3:  # Confidence threshold cho EasyOCR
                    texts.append(text)
            
            if texts:
                combined_text = ' '.join(texts).strip()
                if combined_text:
                    cleaned = self.clean_ocr_text(combined_text)
                    if len(cleaned) > 2 and any(c.isalpha() for c in cleaned):
                        return cleaned
            
            return ""
        except Exception as e:
            log_error("Lỗi EasyOCR", e)
            return ""
    
    def perform_tesseract_ocr(self, processed_images, confidence_threshold=50):
        """
        Thực hiện OCR bằng Tesseract
        """
        best_text = ""
        best_confidence = 0
        
        # PSM modes tối ưu: ưu tiên hiệu quả nhất cho hội thoại
        # PSM 6 tốt nhất cho khối đồng nhất (hầu hết hội thoại game)
        psm_modes = [6, 7]  # 6=khối đồng nhất, 7=dòng đơn
        
        # Lấy config cho gaming mode (phù hợp với hội thoại game)
        gaming_config = self.get_tesseract_config('gaming')
        subtitle_config = self.get_tesseract_config('subtitle')
        
        # Thử với confidence scoring - thứ tự tối ưu cho tốc độ
        for img_idx, img in enumerate(processed_images):
            # Thử gaming config trước (tốt nhất cho hội thoại)
            configs_to_try = [
                (gaming_config, 'gaming'),
                (subtitle_config, 'subtitle'),
                ('--psm 6 --oem 3', 'general')
            ]
            
            for config, config_name in configs_to_try:
                try:
                    # Lấy văn bản với dữ liệu confidence
                    data = pytesseract.image_to_data(
                        img,
                        lang=self.source_language,
                        config=config,
                        output_type=pytesseract.Output.DICT
                    )
                    
                    # Trích xuất văn bản và tính confidence trung bình
                    words = []
                    confidences = []
                    for i in range(len(data['text'])):
                        text = data['text'][i].strip()
                        conf = float(data['conf'][i])
                        # Chỉ lấy text có confidence >= threshold
                        if text and conf >= confidence_threshold:
                            words.append(text)
                            confidences.append(conf)
                    
                    if words:
                        text = ' '.join(words).strip()
                        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
                        
                        if text and len(text) > 2:
                            cleaned = self.clean_ocr_text(text)
                            if len(cleaned) > 2 and any(c.isalpha() for c in cleaned):
                                # Dùng kết quả nếu confidence đủ cao hoặc tốt hơn kết quả trước
                                if avg_confidence > 60 or (avg_confidence > best_confidence and avg_confidence > 30):
                                    best_text = cleaned
                                    best_confidence = avg_confidence
                                    # Thoát sớm nếu confidence cao (>75)
                                    if avg_confidence > 75:
                                        return best_text
                except Exception as e:
                    log_error(f"OCR error with config {config_name}: {e}", e)
                    continue
        
        # Fallback: dùng image_to_string đơn giản nếu phương pháp confidence thất bại
        if not best_text:
            # Chỉ thử ảnh đầu tiên với PSM 6 (fallback nhanh nhất)
            try:
                text = pytesseract.image_to_string(
                    processed_images[0],
                    lang=self.source_language,
                    config='--psm 6 --oem 3'
                ).strip()
                
                if text and len(text) > 2:
                    cleaned = self.clean_ocr_text(text)
                    if len(cleaned) > 2 and any(c.isalpha() for c in cleaned):
                        best_text = cleaned
            except Exception as e:
                log_error("OCR fallback error", e)
        
        return best_text.strip()
    
    def clean_ocr_text(self, text):
        """
        Làm sạch và sửa lỗi nhận dạng OCR thường gặp
        """
        if not text:
            return ""
        
        cleaned = text.strip()
        
        # Sửa lỗi Unicode thường gặp
        ocr_errors = {
            '\u201E': '"',  # Double low-9 quotation mark
            '\u2019': "'",  # Right single quotation mark
            '\u2014': '-',  # Em dash
            '\u2013': '-',  # En dash
        }
        
        # Sửa lỗi theo ngôn ngữ
        if self.source_language.startswith('fra') or self.source_language.startswith('fr'):
            cleaned = cleaned.replace('||', 'Il')
        
        # English-specific OCR fixes
        if self.source_language.startswith('eng') or self.source_language.startswith('en'):
            # Special case for | character (commonly at start of sentences)
            cleaned = re.sub(r'^\|\s', 'I ', cleaned)  # | at start followed by space
            cleaned = re.sub(r'\s\|\s', ' I ', cleaned)  # | surrounded by spaces
            
            # Other fixes using word boundaries
            english_ocr_fixes = {
                '{': '(', '}': ')', '\\/': 'V',
            }
            for error, correction in english_ocr_fixes.items():
                cleaned = re.sub(r'\b' + re.escape(error) + r'\b', correction, cleaned)
        
        # Áp dụng các fix Unicode
        for error, correction in ocr_errors.items():
            cleaned = cleaned.replace(error, correction)
        
        # Xóa khoảng trắng thừa (nhưng giữ newlines nếu có)
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)
        
        # Xóa ký tự nhiễu ở đầu/cuối
        cleaned = re.sub(r'^[\|\[\]\{\}<>\s\.,;:_\-=+\'\"]{1,5}', '', cleaned)
        cleaned = re.sub(r'[\|\[\]\{\}<>\s\.,;:_\-=+\'\"]{1,5}$', '', cleaned)
        
        # Chuẩn hóa dấu ngoặc kép và nháy đơn
        cleaned = cleaned.replace('"', '"').replace('"', '"')
        cleaned = cleaned.replace(''', "'").replace(''', "'")
        
        return cleaned.strip()
    
    def remove_text_after_last_punctuation_mark(self, text):
        """
        Xóa văn bản sau dấu câu cuối cùng
        Giúp loại bỏ text nhiễu sau câu kết thúc
        """
        if not text:
            return text
        pattern = r'[.!?]|\.{3}|…'
        matches = list(re.finditer(pattern, text))
        if not matches:
            return text
        last_match = matches[-1]
        end_pos = last_match.end()
        if last_match.group() == ".":
            if end_pos + 2 <= len(text) and text[end_pos:end_pos+2] == "..":
                end_pos += 2
        return text[:end_pos]
    
    def post_process_translation_text(self, text):
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
        """
        if not text or len(text) < 2:
            return False
        
        # Tính similarity với text gần nhất
        if len(self.text_history) > 0:
            last_text = self.text_history[-1]
            
            # Nếu text giống hệt, coi là stable ngay
            if text == last_text:
                return True
            
            # Tính similarity dựa trên word overlap (tốt hơn character matching)
            words1 = set(text.lower().split())
            words2 = set(last_text.lower().split())
            
            if words1 and words2:
                intersection = words1.intersection(words2)
                union = words1.union(words2)
                similarity = len(intersection) / len(union) if union else 0
                
                # Nếu similarity > 0.9, coi là stable
                if similarity > 0.9:
                    return True
                
                # Nếu độ dài tương tự và similarity > 0.6, cũng coi là stable
                if abs(len(text) - len(last_text)) <= 3 and similarity > 0.6:
                    return True
        
        # Add to history
        self.text_history.append(text)
        if len(self.text_history) > self.history_size:
            self.text_history.pop(0)
        
        # For very short text hoặc first reading, cần ít nhất 2 lần đọc giống nhau
        if len(text) < 10:
            # Với text ngắn, cần ít nhất 2 lần đọc giống nhau
            if len(self.text_history) >= 2:
                if self.text_history[-1] == self.text_history[-2]:
                    return True
            return False
        
        # Với text dài hơn, cần ít nhất 1 lần đọc ổn định
        if len(self.text_history) >= 2:
            return True
        
        return False
    
    def translate_with_deepl(self, text):
        """
        Dịch văn bản sử dụng DeepL API
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
            
            # Translate with DeepL
            result = self.deepl_api_client.translate_text(
                text,
                target_lang=target_lang,
                source_lang=None  # Auto-detect
            )
            
            if result and hasattr(result, 'text'):
                return result.text
            return None
        except Exception as e:
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
        min_interval = 0.03  # Giảm từ 0.05 xuống 0.03 (30ms) để capture nhanh hơn
        similar_frames = 0
        current_scan_interval_sec = min_interval
        
        while self.is_running:
            now = time.monotonic()
            try:
                # Adaptive scan interval based on queue load
                q_fullness = self.ocr_queue.qsize() / (self.ocr_queue.maxsize or 1)
                if q_fullness > 0.7:
                    current_scan_interval_sec = self.update_interval * (1 + q_fullness)
                elif q_fullness > 0.4:
                    current_scan_interval_sec = self.update_interval * 1.25
                else:
                    current_scan_interval_sec = max(min_interval, current_scan_interval_sec * 0.95)
                
                if now - last_cap_time < current_scan_interval_sec:
                    sleep_duration = current_scan_interval_sec - (now - last_cap_time)
                    slept_time = 0
                    while slept_time < sleep_duration and self.is_running:
                        chunk = min(0.05, sleep_duration - slept_time)
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
                
                # Tesseract-specific deduplication
                if img_hash == last_cap_hash:
                    similar_frames += 1
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
        except:
            pass
    
    def run_ocr_thread(self):
        """OCR thread - lấy từ queue, xử lý OCR, gọi async translation"""
        try:
            log_error("WT: OCR thread started.", None)
        except:
            pass
        last_ocr_proc_time = 0
        min_ocr_interval = 0.05  # Giảm từ 0.1 xuống 0.05 để xử lý nhanh hơn
        similar_texts_count = 0
        prev_ocr_text = ""
        
        while self.is_running:
            now = time.monotonic()
            try:
                # Adaptive OCR interval based on queue size
                q_sz = self.ocr_queue.qsize()
                ocr_q_max = self.ocr_queue.maxsize or 1
                adaptive_ocr_interval = min_ocr_interval * (0.8 if q_sz <= 1 else (1.0 + (q_sz / ocr_q_max)))
                
                if now - last_ocr_proc_time < adaptive_ocr_interval:
                    sleep_duration = adaptive_ocr_interval - (now - last_ocr_proc_time)
                    slept_time = 0
                    while slept_time < sleep_duration and self.is_running:
                        chunk = min(0.05, sleep_duration - slept_time)
                        time.sleep(chunk)
                        slept_time += chunk
                    if not self.is_running:
                        break
                    continue
                
                # Lấy ảnh từ queue
                try:
                    img = self.ocr_queue.get(timeout=0.5)
                except queue.Empty:
                    time.sleep(0.05)
                    continue
                
                ocr_proc_start_time = time.monotonic()
                last_ocr_proc_time = ocr_proc_start_time
                
                # Tiền xử lý ảnh
                processed_images, scale_factor = self.preprocess_image(img, mode='adaptive', block_size=41, c_value=-60)
                
                # OCR
                text = self.perform_ocr(processed_images, scale_factor, confidence_threshold=50)
                
                # Xử lý text
                if text:
                    # Bỏ check punctuation strict - có thể bỏ qua text hợp lệ
                    # Chỉ remove trailing garbage nếu có punctuation
                    text = self.remove_text_after_last_punctuation_mark(text)
                
                if not text or self.is_placeholder_text(text):
                    self.text_stability_counter = 0
                    self.previous_text = ""
                    continue
                
                # Tính similarity (để tránh spam nhưng không quá strict)
                similarity = self.calculate_text_similarity(text, prev_ocr_text)
                if similarity > 0.95:  # Chỉ skip nếu gần như giống hệt (0.95 thay vì 0.9)
                    similar_texts_count += 1
                else:
                    similar_texts_count = 0
                    prev_ocr_text = text
                
                # Skip nếu có quá nhiều text tương tự (giảm threshold từ 2 xuống 3 và time từ 1.0 xuống 0.5)
                if similar_texts_count > 3 and (now - self.last_successful_translation_time) < 0.5:
                    continue
                
                # Kiểm tra text stability
                if text == self.previous_text:
                    self.text_stability_counter += 1
                else:
                    self.text_stability_counter = 0
                    self.previous_text = text
                
                # Chỉ translate khi text đã stable
                if self.text_stability_counter >= self.stable_threshold:
                    stable_text = text
                    
                    # Kiểm tra duplicate subtitle
                    if stable_text == self.last_processed_subtitle:
                        self.last_successful_translation_time = now
                        continue
                    
                    # Tính adaptive translation interval (tối ưu để nhanh hơn)
                    s_count = len(re.findall(r'[.!?]+', stable_text)) + 1
                    txt_len = len(stable_text)
                    # Giảm base interval và tối ưu công thức
                    adaptive_trans_interval = max(
                        0.05,  # Giảm từ 0.2 xuống 0.05 để nhanh hơn
                        min(
                            self.min_translation_interval,
                            self.min_translation_interval * (0.3 + (0.05 * s_count) + (txt_len / 2000))  # Tối ưu công thức
                        )
                    )
                    
                    # Chỉ translate nếu đã đủ thời gian
                    if (now - self.last_successful_translation_time) >= adaptive_trans_interval:
                        # Start async translation
                        self.start_async_translation(stable_text, 0)
                        # QUAN TRỌNG: Update ngay lập tức để cho phép dialog tiếp theo được xử lý
                        # (không chờ translation hoàn thành)
                        self.last_successful_translation_time = now
                        self.text_stability_counter = 0
                        self.last_processed_subtitle = stable_text
                        similar_texts_count = 0
            
            except Exception as e_ocr_loop:
                log_error("OCR thread error", e_ocr_loop)
                self.text_stability_counter = 0
                self.previous_text = ""
                time.sleep(0.2)
        
        try:
            log_error("WT: OCR thread finished.", None)
        except:
            pass
    
    def run_translation_thread(self):
        """Translation thread - xử lý translation từ queue (legacy, ít dùng)"""
        try:
            log_error("WT: Translation thread started.", None)
        except:
            pass
        
        while self.is_running:
            try:
                # Xử lý translation từ queue nếu có (legacy)
                try:
                    text_to_translate = self.translation_queue.get(timeout=0.1)
                    if text_to_translate and not self.is_placeholder_text(text_to_translate):
                        self.start_async_translation(text_to_translate, 0)
                except queue.Empty:
                    pass
                
                time.sleep(0.1)
            
            except Exception as e:
                log_error("Translation thread error", e)
                time.sleep(0.2)
        
        try:
            log_error("WT: Translation thread finished.", None)
        except:
            pass
    
    def start_async_translation(self, text_to_translate, ocr_sequence_number):
        """Start async translation processing"""
        try:
            self.translation_sequence_counter += 1
            translation_sequence = self.translation_sequence_counter
            
            if len(self.active_translation_calls) >= self.max_concurrent_translation_calls:
                return  # Skip if too many concurrent calls
            
            self.active_translation_calls.add(translation_sequence)
            
            self.translation_thread_pool.submit(
                self.process_translation_async,
                text_to_translate, translation_sequence, ocr_sequence_number
            )
        
        except Exception as e:
            log_error("Error starting async translation", e)
    
    def process_translation_async(self, text_to_translate, translation_sequence, ocr_sequence_number):
        """Process translation asynchronously"""
        try:
            clean_text = self.clean_ocr_text(text_to_translate)
            
            if self.is_placeholder_text(clean_text):
                return
            
            if clean_text and len(clean_text) > 2:
                cache_key = clean_text.lower().strip()
                
                # Check cache
                if cache_key in self.translation_cache:
                    translated_text = self.translation_cache[cache_key]
                else:
                    # Translate
                    max_retries = 2
                    translated_text = None
                    for attempt in range(max_retries):
                        try:
                            if self.use_deepl and self.DEEPL_API_AVAILABLE and self.deepl_api_client:
                                translated_text = self.translate_with_deepl(clean_text)
                            else:
                                translated_text = self.translator.translate(clean_text)
                            
                            if self.is_error_message(translated_text) or self.is_placeholder_text(translated_text):
                                translated_text = None
                                break
                            
                            break
                        except Exception as trans_error:
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
                        self.translation_cache[cache_key] = translated_text
                        
                        # Limit cache size
                        if len(self.translation_cache) > 1000:
                            keys_to_remove = list(self.translation_cache.keys())[:200]
                            for key in keys_to_remove:
                                del self.translation_cache[key]
                
                # Process translation response với chronological ordering
                # QUAN TRỌNG: Luôn gọi process_translation_response để đảm bảo chronological ordering
                # Ngay cả khi translated_text là None hoặc empty, vẫn cần check sequence
                if self.overlay_window and self.is_running:
                    try:
                        self.overlay_window.after(
                            0, self.process_translation_response,
                            translated_text, translation_sequence, clean_text, ocr_sequence_number
                        )
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
        """Process translation response với chronological order enforcement"""
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
                        self.overlay_window.after(
                            0, self.update_overlay, original_text, f"Lỗi Dịch Thuật:\n{translation_result}"
                        )
                    except Exception as e:
                        log_error("Error displaying error message in overlay", e)
                self.last_displayed_translation_sequence = translation_sequence
                return
            
            # Hiển thị translation hợp lệ
            if isinstance(translation_result, str) and translation_result.strip():
                if self.overlay_window:
                    try:
                        self.overlay_window.after(
                            0, self.update_overlay, original_text, translation_result
                        )
                    except Exception as e:
                        log_error("Error scheduling overlay update", e)
                self.last_displayed_translation_sequence = translation_sequence
                self.last_successful_translation_time = time.monotonic()
            else:
                # Empty hoặc invalid result, vẫn update sequence để không block dialog tiếp theo
                self.last_displayed_translation_sequence = translation_sequence
        
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
        """Cập nhật cửa sổ overlay với bản dịch mới"""
        if not self.overlay_window:
            return
        
        try:
            # Cập nhật shadow label nếu có
            if self.shadow_label:
                try:
                    self.shadow_label.config(text=translated)
                except Exception as e:
                    log_error("Error updating shadow label in overlay", e)
            
            # Cập nhật text widget bản dịch (có thể cuộn)
            if hasattr(self, 'translation_text') and self.translation_text:
                try:
                    self.translation_text.config(state=tk.NORMAL)
                    self.translation_text.delete('1.0', tk.END)
                    self.translation_text.insert('1.0', translated)
                    self.translation_text.config(state=tk.DISABLED)
                    # Auto-scroll to top
                    self.translation_text.see('1.0')
                except Exception as e:
                    log_error("Error updating translation text widget", e)
            elif hasattr(self, 'translation_label') and self.translation_label:
                # Fallback về label nếu text widget không tồn tại
                try:
                    self.translation_label.config(text=translated)
                except Exception as e:
                    log_error("Error updating translation label", e)
            
            # Update original text if enabled
            if self.overlay_show_original and hasattr(self, 'original_label') and self.original_label:
                try:
                    # Truncate if too long, but show more characters
                    max_length = self.overlay_width // 8  # Rough character estimate
                    display_original = original[:max_length] + "..." if len(original) > max_length else original
                    self.original_label.config(text=f"Nguyên bản: {display_original}")
                except Exception as e:
                    log_error("Error updating original label in overlay", e)
        except Exception as e:
            # Log error but don't block if window was closed or widget doesn't exist
            log_error("Error updating overlay", e)
    
    def log(self, message):
        """Thêm message vào status log"""
        # Kiểm tra xem status_text đã được tạo chưa
        if not hasattr(self, 'status_text') or self.status_text is None:
            return
        timestamp = time.strftime("%H:%M:%S")
        self.status_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.status_text.see(tk.END)
        self.root.update_idletasks()
    
    def on_closing(self):
        """Handle window close event"""
        try:
            if self.is_capturing:
                self.stop_translation()
            
            # Giải phóng OCR engines khi đóng ứng dụng
            if self.easyocr_reader is not None:
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
                except Exception:
                    pass
            
            self.save_config()
        except Exception as e:
            # Log but don't block closing
            try:
                log_error("Error during cleanup", e)
                self.log(f"Lỗi khi dọn dẹp: {e}")
            except:
                pass
        finally:
            try:
                self.root.destroy()
            except Exception:
                pass


class RegionSelector:
    """Công cụ tương tác để chọn vùng chụp màn hình"""
    
    def __init__(self, parent, callback):
        self.parent = parent
        self.callback = callback
        self.start_x = None
        self.start_y = None
        self.end_x = None
        self.end_y = None
        self.rect = None
        
        # Create fullscreen transparent window
        self.selector = tk.Toplevel()
        self.selector.attributes('-fullscreen', True)
        self.selector.attributes('-alpha', 0.3)
        self.selector.attributes('-topmost', True)
        self.selector.configure(bg='black')
        
        # Create canvas for drawing selection
        self.canvas = tk.Canvas(
            self.selector,
            highlightthickness=0,
            bg='black',
            cursor="crosshair"
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Instructions
        self.canvas.create_text(
            self.selector.winfo_screenwidth() // 2,
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

