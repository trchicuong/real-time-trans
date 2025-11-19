"""
EasyOCR Handler - tối ưu CPU cho free engine
"""
import time
import numpy as np
from PIL import Image

def get_base_dir():
    """Lấy thư mục gốc - hỗ trợ cả script và exe"""
    try:
        import sys
        import os
        if getattr(sys, 'frozen', False):
            # Chạy từ executable (PyInstaller)
            base_dir = os.path.dirname(sys.executable)
        else:
            # Chạy từ Python script
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.normpath(base_dir)
    except Exception:
        import os
        return os.path.normpath(os.getcwd())

def log_error(msg, exception=None):
    """Simple error logging - fallback nếu không có logger"""
    try:
        import traceback
        from datetime import datetime
        import os
        
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

EASYOCR_AVAILABLE = False
try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    pass


class EasyOCRHandler:
    """Handler cho EasyOCR với tối ưu CPU"""
    
    def __init__(self, source_language='eng'):
        self.source_language = source_language
        self.reader = None
        self.last_call_time = 0.0
        self.min_call_interval = 0.8  # Minimum 0.8s giữa các calls (giảm CPU)
        self.EASYOCR_AVAILABLE = EASYOCR_AVAILABLE
        
    def set_source_language(self, lang):
        """Cập nhật source language và reset reader"""
        if lang != self.source_language:
            self.source_language = lang
            self.reader = None  # Reset để khởi tạo lại với ngôn ngữ mới
    
    def _initialize_reader(self):
        """Khởi tạo EasyOCR reader (lazy initialization)"""
        if not self.EASYOCR_AVAILABLE:
            return None
        
        if self.reader is None:
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
                
                import warnings
                import os
                import sys
                from io import StringIO
                
                old_stderr = sys.stderr
                try:
                    sys.stderr = StringIO()
                    
                    with warnings.catch_warnings():
                        warnings.filterwarnings('ignore', category=UserWarning)
                        warnings.filterwarnings('ignore', message='.*Using CPU.*')
                        warnings.filterwarnings('ignore', message='.*pin_memory.*')
                        warnings.filterwarnings('ignore', module='torch')
                        warnings.filterwarnings('ignore')
                        
                        os.environ['PYTHONWARNINGS'] = 'ignore'
                        
                        # Tối ưu cho long sessions: reuse reader, không reload model
                        self.reader = easyocr.Reader(
                            [easyocr_lang], 
                            gpu=False, 
                            verbose=False,
                            download_enabled=False  # Không download lại nếu đã có
                        )
                finally:
                    sys.stderr = old_stderr
                    
            except Exception as e:
                log_error("Lỗi khởi tạo EasyOCR reader", e)
                return None
        
        return self.reader
    
    def recognize(self, img, confidence_threshold=0.3):
        """
        Main OCR method với throttling và resize để giảm CPU
        """
        # Throttle: EasyOCR rất nặng CPU, chỉ gọi mỗi 0.8s
        now = time.monotonic()
        time_since_last_call = now - self.last_call_time
        if time_since_last_call < self.min_call_interval:
            return ""  # Skip call này để giảm CPU
        
        # Khởi tạo reader nếu chưa có
        reader = self._initialize_reader()
        if reader is None:
            return ""
        
        # Resize ảnh nhỏ hơn để giảm CPU (EasyOCR vẫn chính xác với ảnh nhỏ)
        # Giữ max dimension <= 800px để giảm ~50% CPU
        if isinstance(img, np.ndarray):
            # Convert numpy array to PIL để resize dễ hơn
            img = Image.fromarray(img)
        
        # PIL Image - resize nếu cần
        w, h = img.size
        max_dim = max(w, h)
        if max_dim > 800:
            scale = 800 / max_dim
            new_w, new_h = int(w * scale), int(h * scale)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # Convert PIL Image to numpy array cho EasyOCR
        img_array = np.array(img)
        
        # Thực hiện OCR
        self.last_call_time = time.monotonic()
        try:
            results = reader.readtext(img_array)
            
            # Trích xuất text từ kết quả
            texts = []
            for (bbox, text, confidence) in results:
                if text and confidence > confidence_threshold:
                    texts.append(text)
            
            if texts:
                return ' '.join(texts).strip()
            return ""
        except Exception as e:
            log_error("Lỗi EasyOCR", e)
            return ""
    
    def is_available(self):
        """Check if EasyOCR is available"""
        return self.EASYOCR_AVAILABLE
    
    def cleanup(self):
        """Cleanup reader khi không dùng nữa"""
        if self.reader is not None:
            self.reader = None

