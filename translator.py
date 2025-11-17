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

def get_base_dir():
    """Lấy thư mục gốc để lưu config.json và error_log.txt"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

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
    """Tự động tìm đường dẫn Tesseract OCR"""
    if custom_path:
        if os.path.isfile(custom_path):
            return custom_path
        elif os.path.isdir(custom_path):
            tesseract_exe = os.path.join(custom_path, 'tesseract.exe')
            if os.path.exists(tesseract_exe):
                return tesseract_exe
    
    windows_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    ]
    
    tesseract_cmd = shutil.which('tesseract')
    if tesseract_cmd:
        return tesseract_cmd
    
    if os.name == 'nt':
        for path in windows_paths:
            if os.path.exists(path):
                return path
    
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
        
        self.overlay_position_x = None
        self.overlay_position_y = None
        self.overlay_locked = False
        
        self.load_config()
        self.create_ui()
        
        if not self.verify_tesseract():
            self.log("Cảnh báo: Không tìm thấy Tesseract OCR. Vui lòng sử dụng nút 'Duyệt' để đặt đường dẫn.")
            tesseract_path = find_tesseract(self.custom_tesseract_path)
            if tesseract_path:
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
        except Exception:
            return False
    
    def browse_tesseract_path(self):
        """Duyệt thư mục cài đặt Tesseract"""
        initial_dir = None
        if self.custom_tesseract_path:
            if os.path.isdir(self.custom_tesseract_path):
                initial_dir = self.custom_tesseract_path
            elif os.path.isfile(self.custom_tesseract_path):
                initial_dir = os.path.dirname(self.custom_tesseract_path)
        
        folder_path = filedialog.askdirectory(
                title="Chọn Thư Mục Cài Đặt Tesseract OCR",
            initialdir=initial_dir
        )
        
        if folder_path:
            tesseract_exe = os.path.join(folder_path, 'tesseract.exe')
            if os.path.exists(tesseract_exe):
                self.custom_tesseract_path = tesseract_exe
                pytesseract.pytesseract.tesseract_cmd = tesseract_exe
                self.tesseract_path_label.config(
                    text=f"Path: {tesseract_exe}",
                    fg="green"
                )
                self.save_config()
                
                if self.verify_tesseract():
                    self.log(f"Đã đặt đường dẫn Tesseract thành công: {tesseract_exe}")
                    messagebox.showinfo("Thành công", "Đã cấu hình đường dẫn Tesseract OCR thành công!")
                else:
                    messagebox.showerror("Lỗi", "Tìm thấy tesseract.exe nhưng không hoạt động. Vui lòng kiểm tra lại cài đặt.")
            else:
                for root, dirs, files in os.walk(folder_path):
                    if 'tesseract.exe' in files:
                        tesseract_exe = os.path.join(root, 'tesseract.exe')
                        self.custom_tesseract_path = tesseract_exe
                        pytesseract.pytesseract.tesseract_cmd = tesseract_exe
                        self.tesseract_path_label.config(
                            text=f"Path: {tesseract_exe}",
                            fg="green"
                        )
                        self.save_config()
                        
                        if self.verify_tesseract():
                            self.log(f"Đã đặt đường dẫn Tesseract thành công: {tesseract_exe}")
                            messagebox.showinfo("Thành công", f"Đã tìm thấy và cấu hình Tesseract OCR:\n{tesseract_exe}")
                            return
                
                messagebox.showerror(
                    "Không Tìm Thấy Tesseract",
                    f"Không tìm thấy tesseract.exe trong thư mục đã chọn:\n{folder_path}\n\n"
                    "Vui lòng chọn thư mục chứa tesseract.exe"
                )
        else:
            file_path = filedialog.askopenfilename(
                title="Chọn Tệp Thực Thi Tesseract (tesseract.exe)",
                initialdir=initial_dir,
                filetypes=[("Executable files", "*.exe"), ("All files", "*.*")]
            )
            
            if file_path and os.path.basename(file_path).lower() == 'tesseract.exe':
                self.custom_tesseract_path = file_path
                pytesseract.pytesseract.tesseract_cmd = file_path
                self.tesseract_path_label.config(
                    text=f"Path: {file_path}",
                    fg="green"
                )
                self.save_config()
                
                if self.verify_tesseract():
                    self.log(f"Tesseract path set successfully: {file_path}")
                    messagebox.showinfo("Thành công", "Đã cấu hình đường dẫn Tesseract OCR thành công!")
                else:
                    messagebox.showerror("Lỗi", "Tìm thấy tesseract.exe nhưng không hoạt động. Vui lòng kiểm tra lại cài đặt.")
    
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
        
        # Tesseract Path
        ttk.Label(settings_frame, text="Đường Dẫn Tesseract:").grid(row=2, column=0, sticky=tk.W, pady=5)
        tesseract_path_frame = ttk.Frame(settings_frame)
        tesseract_path_frame.grid(row=2, column=1, sticky=tk.W+tk.E, pady=5)
        
        # Display current path
        current_path = "Đang kiểm tra..."
        path_color = "gray"
        
        # Kiểm tra xem Tesseract đã được cấu hình chưa
        if self.custom_tesseract_path and os.path.exists(self.custom_tesseract_path):
            current_path = self.custom_tesseract_path
            path_color = "green"
        else:
            # Thử xác minh xem Tesseract có hoạt động không
            try:
                if pytesseract.pytesseract.tesseract_cmd:
                    current_path = pytesseract.pytesseract.tesseract_cmd
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
                log_error("Error checking Tesseract path", e)
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
        
        ttk.Button(
            tesseract_path_frame,
            text="Duyệt",
            command=self.browse_tesseract_path,
            width=10
        ).pack(side=tk.LEFT)
    
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
        
        # Instructions content
        instructions_text = """
HƯỚNG DẪN SỬ DỤNG CÔNG CỤ DỊCH MÀN HÌNH THỜI GIAN THỰC

1. CÀI ĐẶT:
   - Cài đặt Tesseract OCR từ: https://github.com/UB-Mannheim/tesseract/wiki
   - Nếu Tesseract không tự động phát hiện, sử dụng nút "Duyệt" để chọn đường dẫn
   - Cài đặt các ngôn ngữ cần thiết cho Tesseract (tiếng Anh, Nhật, Hàn, v.v.)

2. THIẾT LẬP:
   - Chọn tab "Cài Đặt" và nhấn "Chọn Vùng" để chọn vùng hộp thoại trong ứng dụng
   - Chọn ngôn ngữ nguồn phù hợp (tiếng Anh, Nhật, Hàn, v.v.)
   - Điều chỉnh khoảng thời gian cập nhật (ms) - giá trị nhỏ hơn = cập nhật nhanh hơn

3. TÙY CHỈNH GIAO DIỆN DỊCH:
   - Chọn tab "Giao Diện Dịch" để tùy chỉnh
   - SỬ DỤNG CẤU HÌNH NHANH (PRESET):
     * "Tối Ưu Tốc Độ": Tốc độ nhanh nhất (100ms) - phù hợp game có hội thoại nhanh
     * "Cân Bằng": Cân bằng tốc độ và chất lượng (150ms) - phù hợp hầu hết game
     * "Tối Ưu Chất Lượng": Chất lượng tốt nhất (200ms) - phù hợp khi cần đọc kỹ
     * "Mặc Định": Cài đặt mặc định (200ms) - chữ trắng, nền tối trong suốt
   - TÙY CHỈNH THỦ CÔNG:
     * Cỡ chữ, phông chữ, màu sắc (mặc định: chữ trắng, nền tối)
     * Kích thước màn hình dịch (mặc định: 500x280 - hình chữ nhật vừa phải)
     * Độ trong suốt, căn lề, khoảng cách dòng
     * Viền, đệm, bóng chữ
   - Nhấn "Áp Dụng" sau khi thay đổi để áp dụng cài đặt
   - Nhấn "Đặt Lại Tất Cả" để reset về mặc định (bao gồm vị trí màn hình dịch)

4. ĐIỀU KHIỂN:
   - Nhấn "Bắt Đầu Dịch" để bắt đầu dịch
   - Nhấn "Dừng Dịch" để dừng
   - Sử dụng "Khóa màn hình dịch" để ngăn di chuyển khi chơi game

5. SỬ DỤNG MÀN HÌNH DỊCH:
   - Kéo thả để di chuyển màn hình dịch
   - Kéo các cạnh/góc để thay đổi kích thước
   - Cuộn lên/xuống để xem toàn bộ văn bản dịch nếu quá dài
   - Khi khóa, màn hình dịch sẽ không thể di chuyển

6. MẸO TỐI ƯU TỐC ĐỘ:
   - Sử dụng preset "Tối Ưu Tốc Độ" cho game có hội thoại xuất hiện nhanh
   - Chọn vùng chụp càng chính xác càng tốt (chỉ vùng hộp thoại) - giảm thời gian xử lý
   - Giảm khoảng thời gian cập nhật (50-150ms) nếu máy đủ mạnh
   - Tắt hiển thị văn bản gốc để giảm tải rendering
   - Khi chơi game, khóa màn hình dịch để tránh di chuyển nhầm
   - Màn hình dịch mặc định đã được tối ưu: chữ trắng, nền tối trong suốt, kích thước vừa phải

7. XỬ LÝ SỰ CỐ:
   - Nếu không dịch được: Kiểm tra Tesseract đã cài đặt đúng chưa
   - Nếu dịch sai: Thử thay đổi ngôn ngữ nguồn
   - Nếu chậm: Tăng khoảng thời gian cập nhật (ms)
   - Xem tab "Trạng Thái" để biết thông tin chi tiết

8. LƯU Ý:
   - Cần kết nối internet để dịch
   - Chất lượng dịch phụ thuộc vào độ rõ của văn bản
   - Màn hình dịch sẽ tự động lưu vị trí và kích thước
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
        """Load configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.capture_region = config.get('capture_region')
                    self.source_language = config.get('source_language', 'eng')
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
                        tesseract_path = find_tesseract(self.custom_tesseract_path)
                        if tesseract_path:
                            pytesseract.pytesseract.tesseract_cmd = tesseract_path
            except Exception as e:
                log_error("Error loading config", e)
                self.log(f"Lỗi tải cấu hình: {e}")
    
    def save_config(self):
        """Save configuration to file"""
        try:
            config = {
                'capture_region': self.capture_region,
                'source_language': self.source_language,
                'update_interval': self.update_interval,
                'custom_tesseract_path': self.custom_tesseract_path,
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
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            log_error("Error saving config", e)
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
    
    def on_source_lang_change(self, event=None):
        """Handle source language change"""
        self.source_language = self.source_lang_var.get()
        self.save_config()
        self.log(f"Đã thay đổi ngôn ngữ nguồn thành: {self.source_language}")
    
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
            self.interval_var.set("100")  # Update UI
            
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
            self.interval_var.set("150")  # Update UI
            
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
            self.interval_var.set("200")  # Update UI
            
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
            self.interval_var.set("200")  # Update UI
            
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
                # Lưu vị trí hiện tại trước khi tạo lại
                try:
                    self.overlay_position_x = self.overlay_window.winfo_x()
                    self.overlay_position_y = self.overlay_window.winfo_y()
                except:
                    pass
                self.create_overlay()
            
            self.log("Đã áp dụng cài đặt giao diện")
        except ValueError as e:
            log_error("Invalid overlay setting value", e)
            self.log(f"Giá trị cài đặt giao diện không hợp lệ: {e}")
    
    def start_translation(self):
        """Start the translation process"""
        if not self.capture_region:
            try:
                messagebox.showerror("Lỗi", "Vui lòng chọn vùng chụp màn hình trước.")
            except Exception as e:
                log_error("Error showing messagebox", e)
            return
        
        self.is_capturing = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        
        # Create overlay window
        self.create_overlay()
        
        # Start capture thread
        self.capture_thread = threading.Thread(target=self.capture_loop, daemon=True)
        self.capture_thread.start()
        
        self.log("Đã bắt đầu dịch!")
    
    def stop_translation(self):
        """Stop the translation process"""
        self.is_capturing = False
        
        # Wait a moment for the thread to finish current iteration
        if self.capture_thread and self.capture_thread.is_alive():
            try:
                # Give the thread a moment to check is_capturing flag
                self.capture_thread.join(timeout=0.5)
            except Exception:
                pass  # Thread will exit when is_capturing is False
        
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        
        # Reset text history and cache
        self.text_history = []
        self.translation_cache.clear()
        self.pending_translation = None
        
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
    
    def preprocess_image(self, img):
        """Tiền xử lý ảnh để tối ưu độ chính xác và tốc độ OCR"""
        img_array = np.array(img)
        
        # Chuyển sang grayscale
        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array
        
        # Scale thông minh: chỉ scale khi cần, tối đa 3x
        height, width = gray.shape
        scale_factor = 1.0
        if height < 120 or width < 250:
            scale_factor = min(3.0, max(250 / width, 120 / height, 2.5))
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            # Dùng INTER_CUBIC cho chất lượng tốt hơn
            if scale_factor <= 2.5:
                gray = cv2.resize(gray, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
            else:
                gray = cv2.resize(gray, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
        
        # Phân tích độ sáng
        mean_brightness = np.mean(gray)
        is_dark = mean_brightness < 120
        
        # CLAHE tối ưu
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(4, 4))
        
        # Phương pháp 1: Tăng cường chuẩn
        enhanced1 = clahe.apply(gray)
        
        # Phương pháp 2: Đảo ngược cho nền tối (thường gặp trong game)
        if is_dark:
            inverted = cv2.bitwise_not(gray)
            enhanced2 = clahe.apply(inverted)
        else:
            enhanced2 = enhanced1
        
        # OTSU thresholding (chính xác nhất cho văn bản)
        _, thresh1 = cv2.threshold(enhanced1, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, thresh2 = cv2.threshold(enhanced2, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        return [thresh1, thresh2], scale_factor
    
    def perform_ocr(self, processed_images, scale_factor):
        """Thực hiện OCR trên ảnh đã xử lý, chọn kết quả tốt nhất dựa trên độ tin cậy"""
        best_text = ""
        best_confidence = 0
        
        # PSM modes tối ưu: ưu tiên hiệu quả nhất cho hội thoại
        # PSM 6 tốt nhất cho khối đồng nhất (hầu hết hội thoại game)
        psm_modes = [6, 7]  # 6=khối đồng nhất, 7=dòng đơn
        
        # Thử với confidence scoring - thứ tự tối ưu cho tốc độ
        for img_idx, img in enumerate(processed_images[:2]):  # Chỉ thử 2 phương pháp đầu
            for psm in psm_modes:
                try:
                    # Lấy văn bản với dữ liệu confidence
                    data = pytesseract.image_to_data(
                        img,
                        lang=self.source_language,
                        config=f'--psm {psm}',
                        output_type=pytesseract.Output.DICT
                    )
                    
                    # Trích xuất văn bản và tính confidence trung bình
                    words = []
                    confidences = []
                    for i in range(len(data['text'])):
                        text = data['text'][i].strip()
                        conf = int(data['conf'][i])
                        if text and conf > 0:
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
                except Exception:
                    continue
        
        # Fallback: dùng image_to_string đơn giản nếu phương pháp confidence thất bại
        if not best_text:
            # Chỉ thử ảnh đầu tiên với PSM 6 (fallback nhanh nhất)
            try:
                text = pytesseract.image_to_string(
                    processed_images[0],
                    lang=self.source_language,
                    config='--psm 6'
                ).strip()
                
                if text and len(text) > 2:
                    cleaned = self.clean_ocr_text(text)
                    if len(cleaned) > 2 and any(c.isalpha() for c in cleaned):
                        best_text = cleaned
            except Exception:
                pass
        
        return best_text.strip()
    
    def clean_ocr_text(self, text):
        """Làm sạch và sửa lỗi nhận dạng OCR thường gặp"""
        if not text:
            return ""
        
        # Xóa khoảng trắng thừa
        text = re.sub(r'\s+', ' ', text)
        
        # Sửa lỗi OCR thường gặp
        replacements = {
            r'\b0\b': 'O',  # Số 0 thành chữ O trong từ
            r'rn': 'm',     # Lỗi OCR thường gặp
            r'vv': 'w',     # Lỗi OCR thường gặp
            r'ii': 'n',     # Lỗi OCR thường gặp
        }
        
        # Xóa ký tự nhiễu (ký tự đơn lẻ có thể là lỗi)
        words = text.split()
        cleaned_words = []
        
        for word in words:
            # Xóa từ chỉ là dấu câu hoặc ký tự đơn (có thể là nhiễu)
            if len(word) > 1 or word.isalnum():
                # Sửa lỗi nhầm ký tự thường gặp
                word = re.sub(r'^0([a-zA-Z])', r'O\1', word)  # 0 ở đầu từ
                word = re.sub(r'([a-zA-Z])0([a-zA-Z])', r'\1O\2', word)  # 0 ở giữa từ
                cleaned_words.append(word)
        
        text = ' '.join(cleaned_words)
        
        # Xóa dấu câu đầu/cuối không hợp lý
        text = text.strip('.,;:!?')
        
        # Chuẩn hóa dấu ngoặc kép và nháy đơn
        text = text.replace('"', '"').replace('"', '"')
        text = text.replace(''', "'").replace(''', "'")
        
        return text.strip()
    
    def is_text_stable(self, text):
        """Kiểm tra độ ổn định văn bản nhanh cho hội thoại nhanh"""
        if not text or len(text) < 2:
            return False
        
        # Cho hội thoại nhanh, dùng kiểm tra tối thiểu
        # Chỉ kiểm tra xem đã thấy văn bản tương tự gần đây chưa
        if len(self.text_history) > 0:
            last_text = self.text_history[-1]
            # Quick similarity: same length ±2 and >60% match
            if abs(len(text) - len(last_text)) <= 2:
                matches = sum(c1 == c2 for c1, c2 in zip(text, last_text))
                similarity = matches / max(len(text), len(last_text), 1)
                if similarity > 0.6:
                    # Text is stable enough
                    return True
        
        # Add to history
        self.text_history.append(text)
        if len(self.text_history) > 2:  # Keep only last 2
            self.text_history.pop(0)
        
        # For very short text or first reading, accept immediately
        if len(text) < 10 or len(self.text_history) == 1:
            return True
        
        return False
    
    def capture_loop(self):
        """Vòng lặp chụp và dịch chạy trong thread nền"""
        sct = None
        try:
            sct = mss.mss()
        except Exception as e:
            log_error("Failed to initialize screen capture", e)
            self.log(f"Không thể khởi tạo chụp màn hình: {e}")
            return
        
        last_translated_text = ""
        last_stable_text = ""
        last_image_hash = None
        
        while self.is_capturing:
            try:
                # Kiểm tra xem có nên dừng trước mỗi thao tác không
                if not self.is_capturing:
                    break
                
                # Chụp vùng màn hình
                monitor = {
                    "top": self.capture_region[1],
                    "left": self.capture_region[0],
                    "width": self.capture_region[2],
                    "height": self.capture_region[3]
                }
                
                screenshot = sct.grab(monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                
                # Kiểm tra lại sau khi chụp
                if not self.is_capturing:
                    break
                
                # Kiểm tra hash nhanh để bỏ qua xử lý frame giống nhau
                img_hash = hash(img.tobytes())
                if img_hash == last_image_hash:
                    # Dùng sleep ngắn hơn khi bỏ qua frame giống nhau
                    time.sleep(min(self.update_interval, 0.1))
                    continue
                last_image_hash = img_hash
                
                # Tiền xử lý ảnh nhanh (một phương pháp)
                processed_images, scale_factor = self.preprocess_image(img)
                
                # Kiểm tra lại trước OCR (OCR có thể chậm)
                if not self.is_capturing:
                    break
                
                # OCR nhanh (giảm số lần thử)
                text = self.perform_ocr(processed_images, scale_factor)
                
                # Kiểm tra ổn định nhanh hơn (chỉ cần 2 frame)
                if text and self.is_text_stable(text):
                    stable_text = self.text_history[-1]  # Use the most recent stable reading
                    
                    # Only translate if text changed significantly
                    if stable_text != last_stable_text:
                        last_stable_text = stable_text
                        
                        # Check before translation (translation is slow)
                        if not self.is_capturing:
                            break
                        
                        # Dịch văn bản với caching và threading
                        try:
                            # Làm sạch văn bản thêm trước khi dịch
                            clean_text = self.clean_ocr_text(stable_text)
                            
                            if clean_text and len(clean_text) > 2:
                                # Kiểm tra cache trước (tìm kiếm tức thì)
                                cache_key = clean_text.lower().strip()
                                if cache_key in self.translation_cache:
                                    translated_text = self.translation_cache[cache_key]
                                else:
                                    # Kiểm tra xem bản dịch đã đang được xử lý cho văn bản này chưa
                                    with self.translation_lock:
                                        if self.pending_translation == clean_text:
                                            # Bỏ qua - bản dịch đã đang được xử lý
                                            continue
                                        self.pending_translation = clean_text
                                    
                                    try:
                                        # Dịch (đây là phần chậm nhất, nhưng cần thiết)
                                        # Add retry logic for production reliability
                                        max_retries = 2
                                        translated_text = None
                                        for attempt in range(max_retries):
                                            try:
                                                translated_text = self.translator.translate(clean_text)
                                                break  # Thành công, thoát vòng lặp retry
                                            except Exception as trans_error:
                                                if attempt < max_retries - 1:
                                                    # Đợi một chút trước khi thử lại (exponential backoff)
                                                    time.sleep(0.1 * (attempt + 1))
                                                    continue
                                                else:
                                                    # Lần thử cuối thất bại, log và dùng fallback
                                                    log_error("Translation failed after retries", trans_error)
                                                    translated_text = clean_text  # Fallback về bản gốc
                                        
                                        # Chỉ cache bản dịch thành công
                                        if translated_text and translated_text != clean_text:
                                            self.translation_cache[cache_key] = translated_text
                                            # Giới hạn kích thước cache để tránh vấn đề bộ nhớ
                                            if len(self.translation_cache) > 1000:
                                                # Xóa 200 entry cũ nhất
                                                keys_to_remove = list(self.translation_cache.keys())[:200]
                                                for key in keys_to_remove:
                                                    del self.translation_cache[key]
                                    finally:
                                        with self.translation_lock:
                                            if self.pending_translation == clean_text:
                                                self.pending_translation = None
                                
                                # Kiểm tra lại sau khi dịch
                                if not self.is_capturing:
                                    break
                                
                                # Chỉ cập nhật nếu bản dịch khác
                                if translated_text != last_translated_text:
                                    last_translated_text = translated_text
                                    
                                    # Cập nhật cửa sổ overlay
                                    if self.overlay_window and self.is_capturing:
                                        try:
                                            self.overlay_window.after(
                                                0, self.update_overlay, clean_text, translated_text
                                            )
                                        except Exception:
                                            pass  # Cửa sổ có thể đã đóng
                                    
                                    if self.is_capturing:  # Chỉ log nếu vẫn đang chụp
                                        self.log(f"Nguyên bản: {clean_text[:60]}...")
                                        self.log(f"Đã dịch: {translated_text[:60]}...")
                                    
                        except Exception as e:
                            with self.translation_lock:
                                self.pending_translation = None
                            log_error("Translation error", e)
                            if self.is_capturing:
                                self.log(f"Lỗi dịch: {e}")
                
                # Kiểm tra trước khi sleep
                if not self.is_capturing:
                    break
                    
                time.sleep(self.update_interval)
                
            except KeyboardInterrupt:
                # Xử lý keyboard interrupt
                break
            except Exception as e:
                log_error("Capture error", e)
                if self.is_capturing:
                    self.log(f"Lỗi chụp màn hình: {e}")
                # Sleep ngắn hơn khi lỗi để kiểm tra is_capturing thường xuyên hơn
                for _ in range(10):  # Kiểm tra mỗi 0.1s trong 1 giây
                    if not self.is_capturing:
                        break
                    time.sleep(0.1)
    
    def update_overlay(self, original, translated):
        """Cập nhật cửa sổ overlay với bản dịch mới"""
        if self.overlay_window:
            try:
                # Cập nhật shadow label nếu có (chỉ khi dùng label, không phải text widget)
                if self.shadow_label and hasattr(self, 'translation_label') and self.translation_label:
                    self.shadow_label.config(text=translated)
                
                # Cập nhật text widget bản dịch (có thể cuộn)
                if hasattr(self, 'translation_text') and self.translation_text:
                    self.translation_text.config(state=tk.NORMAL)
                    self.translation_text.delete('1.0', tk.END)
                    self.translation_text.insert('1.0', translated)
                    self.translation_text.config(state=tk.DISABLED)
                    # Auto-scroll to top
                    self.translation_text.see('1.0')
                elif hasattr(self, 'translation_label') and self.translation_label:
                    # Fallback về label nếu text widget không tồn tại
                    self.translation_label.config(text=translated)
                
                # Update original text if enabled
                if self.overlay_show_original and self.original_label:
                    # Truncate if too long, but show more characters
                    max_length = self.overlay_width // 8  # Rough character estimate
                    display_original = original[:max_length] + "..." if len(original) > max_length else original
                    self.original_label.config(text=f"Nguyên bản: {display_original}")
            except Exception as e:
                # Silently fail if window was closed
                pass
    
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

