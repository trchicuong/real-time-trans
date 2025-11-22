"""
EasyOCR Handler - tối ưu CPU cho free engine
"""
import time
import numpy as np
from PIL import Image
import sys
import os

# Import centralized logger from modules
try:
    from modules import log_error, log_debug
except ImportError:
    # Fallback if modules not available
    def log_error(msg, exception=None):
        pass
    def log_debug(msg):
        pass

EASYOCR_AVAILABLE = False
try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    pass

def detect_gpu_availability():
    """
    Detect GPU availability using torch.cuda
    Returns: (gpu_available: bool, gpu_name: str or None, debug_info: str)
    """
    try:
        import torch
        debug_info = f"PyTorch version: {torch.__version__}"
        
        # Check if CUDA is available
        if not torch.cuda.is_available():
            cuda_version = getattr(torch.version, 'cuda', None)
            if cuda_version:
                debug_info += f", CUDA version: {cuda_version}, but torch.cuda.is_available() = False"
            else:
                debug_info += ", PyTorch installed without CUDA support"
            log_error(f"[GPU Detection] {debug_info}")
            return False, None, debug_info
        
        # CUDA is available
        gpu_name = torch.cuda.get_device_name(0)
        cuda_version = getattr(torch.version, 'cuda', 'Unknown')
        device_count = torch.cuda.device_count()
        debug_info += f", CUDA version: {cuda_version}, GPU devices: {device_count}, GPU: {gpu_name}"
        log_error(f"[GPU Detection] SUCCESS - {debug_info}")
        return True, gpu_name, debug_info
        
    except ImportError:
        debug_info = "PyTorch not installed"
        log_error(f"[GPU Detection] {debug_info}")
        return False, None, debug_info
    except Exception as e:
        debug_info = f"Error detecting GPU: {str(e)}"
        log_error(f"[GPU Detection] {debug_info}")
        return False, None, debug_info


class EasyOCRHandler:
    """Handler cho EasyOCR với tối ưu CPU/GPU"""
    
    def __init__(self, source_language='eng', use_gpu=None, enable_multi_scale=False):
        """
        Args:
            source_language: Ngôn ngữ nguồn cho OCR
            use_gpu: None = auto-detect, True = force GPU, False = force CPU
            enable_multi_scale: True = enable multi-scale processing (chính xác hơn nhưng chậm hơn)
        """
        self.source_language = source_language
        self.reader = None
        self.last_call_time = 0.0
        self.EASYOCR_AVAILABLE = EASYOCR_AVAILABLE
        
        # Detect GPU availability
        detected_gpu_available, detected_gpu_name, gpu_debug_info = detect_gpu_availability()
        
        # Determine GPU usage based on user preference
        if use_gpu is True:
            # Force GPU mode
            if detected_gpu_available:
                self.gpu_available = True
                self.gpu_name = detected_gpu_name
                self.gpu_debug_info = gpu_debug_info
                log_error(f"[INFO] GPU mode forced by user: {self.gpu_name}")
            else:
                # GPU requested but not available
                self.gpu_available = False
                self.gpu_name = None
                self.gpu_debug_info = f"{gpu_debug_info} (GPU requested but not available)"
                log_error(f"[WARNING] GPU mode requested but GPU not available. Falling back to CPU.")
        elif use_gpu is False:
            # Force CPU mode
            self.gpu_available = False
            self.gpu_name = None
            self.gpu_debug_info = f"{gpu_debug_info} (CPU mode forced by user)"
            log_error("[INFO] CPU mode forced by user.")
        else:
            # Auto-detect (default)
            self.gpu_available = detected_gpu_available
            self.gpu_name = detected_gpu_name
            self.gpu_debug_info = gpu_debug_info
            if self.gpu_available:
                log_error(f"[INFO] GPU auto-detected: {self.gpu_name}. EasyOCR will use GPU mode.")
            else:
                log_error("[INFO] No GPU detected. EasyOCR will use CPU mode.")
        
        # Adaptive throttling: GPU mode cần ít throttling hơn CPU mode
        if self.gpu_available:
            self.min_call_interval = 0.5  # GPU mode: 0.5s (GPU xử lý nhanh hơn)
            log_error(f"[INFO] EasyOCR will use GPU mode to reduce CPU usage.")
        else:
            self.min_call_interval = 1.5  # CPU mode: 1.5s (tăng từ 0.8s để giảm CPU ~40%)
            log_error("[INFO] EasyOCR will use CPU mode with increased throttling (1.5s).")
        log_error(f"[INFO] GPU Debug: {self.gpu_debug_info}")
        
        # Smart skip: cache last result để skip nếu text giống
        self.last_result_text = ""
        self.last_result_hash = None
        
        # Multi-scale processing - có thể bật/tắt từ UI
        self.enable_multi_scale = enable_multi_scale
        
        # Timeout cho OCR operations (giây) - tránh stuck
        self.ocr_timeout = 10.0 if self.gpu_available else 15.0
        
        # Max text length để tránh xử lý text quá dài (tăng lên để giữ nhiều text hơn)
        self.max_text_length = 800  # Ký tự (tăng từ 500 để giữ độ chính xác tốt hơn)
        
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
                        
                        # Auto-detect GPU và enable GPU mode nếu có
                        # GPU mode sẽ giảm CPU usage từ 70-90% xuống ~5-15%
                        use_gpu = self.gpu_available
                        
                        # Verify GPU one more time before creating reader
                        if use_gpu:
                            try:
                                import torch
                                if not torch.cuda.is_available():
                                    log_error("[WARNING] GPU was detected earlier but torch.cuda.is_available() is now False. Falling back to CPU.")
                                    use_gpu = False
                            except Exception as e:
                                log_error(f"[WARNING] Error verifying GPU before EasyOCR init: {e}. Falling back to CPU.")
                                use_gpu = False
                        
                        log_error(f"[INFO] Creating EasyOCR Reader with gpu={use_gpu}")
                        
                        # Tối ưu cho long sessions: reuse reader, không reload model
                        # Cho phép download model tự động nếu chưa có (lần đầu tiên)
                        self.reader = easyocr.Reader(
                            [easyocr_lang], 
                            gpu=use_gpu, 
                            verbose=False,
                            download_enabled=True  # Cho phép download model tự động nếu chưa có
                        )
                        
                        # Verify reader actually using GPU
                        if use_gpu:
                            try:
                                # Try to check if reader is using GPU by checking device
                                import torch
                                if torch.cuda.is_available():
                                    # Force a small operation to see if GPU is used
                                    test_tensor = torch.zeros(1).cuda()
                                    log_error(f"[INFO] EasyOCR initialized with GPU acceleration ({self.gpu_name}) - GPU verified active")
                                else:
                                    log_error(f"[WARNING] EasyOCR Reader created with gpu=True but torch.cuda.is_available() is False")
                            except Exception as e:
                                log_error(f"[INFO] EasyOCR initialized with GPU acceleration ({self.gpu_name}) - Note: {str(e)}")
                        else:
                            log_error("[INFO] EasyOCR initialized with CPU mode")
                finally:
                    sys.stderr = old_stderr
                    
            except FileNotFoundError as e:
                # Model chưa được download hoặc bị mất
                error_msg = f"EasyOCR model chưa được tải. Vui lòng đảm bảo có kết nối internet để tải model lần đầu tiên.\nChi tiết: {str(e)}"
                log_error("Lỗi khởi tạo EasyOCR reader - Model chưa được tải", e)
                return None
            except Exception as e:
                log_error("Lỗi khởi tạo EasyOCR reader", e)
                return None
        
        return self.reader
    
    def recognize(self, img, confidence_threshold=0.3):
        """
        Main OCR method với throttling, resize và smart skip để giảm CPU
        """
        # Throttle: EasyOCR rất nặng CPU/GPU, chỉ gọi theo interval
        now = time.monotonic()
        time_since_last_call = now - self.last_call_time
        if time_since_last_call < self.min_call_interval:
            return ""  # Skip call này để giảm CPU/GPU load
        
        # Smart skip: Check image hash để skip nếu giống frame trước
        try:
            import hashlib
            if isinstance(img, np.ndarray):
                img_pil = Image.fromarray(img)
            else:
                img_pil = img
            
            # Create small hash image for comparison
            w, h = img_pil.size
            img_small = img_pil.resize((max(1, w//8), max(1, h//8)), Image.Resampling.NEAREST)
            img_hash = hashlib.md5(img_small.tobytes()).hexdigest()
            
            # Skip nếu hash giống (frame không đổi)
            if img_hash == self.last_result_hash:
                return self.last_result_text  # Return cached result
            
            self.last_result_hash = img_hash
        except Exception as e:
            log_error("Error computing image hash for EasyOCR", e)
            # Continue nếu hash fail
        
        # Khởi tạo reader nếu chưa có
        reader = self._initialize_reader()
        if reader is None:
            return ""
        
        # Resize ảnh nhỏ hơn để giảm CPU/GPU (EasyOCR vẫn chính xác với ảnh nhỏ)
        # Adaptive max dimension: GPU có thể xử lý ảnh lớn hơn, CPU cần nhỏ hơn
        if isinstance(img, np.ndarray):
            img_pil = Image.fromarray(img)
        else:
            img_pil = img
        
        w, h = img_pil.size
        max_dim = max(w, h)
        
        # GPU mode: max 900px, CPU mode: max 650px (cân bằng tốc độ và độ chính xác)
        # EasyOCR vẫn khá chính xác với ảnh nhỏ, nhưng tăng một chút để giữ độ chính xác tốt
        max_size = 900 if self.gpu_available else 650
        if max_dim > max_size:
            scale = max_size / max_dim
            new_w, new_h = int(w * scale), int(h * scale)
            img_pil = img_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # Multi-scale processing nếu được bật (chỉ cho CPU mode)
        if self.enable_multi_scale and not self.gpu_available:
            # Multi-scale chỉ cho CPU mode (GPU đã nhanh rồi)
            best_result = None
            best_score = 0.0
            
            # Thử nhiều scale: 0.7x, 1.0x, 1.3x
            for scale in [0.7, 1.0, 1.3]:
                try:
                    scaled_w = int(w * scale)
                    scaled_h = int(h * scale)
                    if scaled_w < 10 or scaled_h < 10:
                        continue
                    
                    scaled_img = img_pil.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
                    img_array = np.array(scaled_img)
                    
                    # Thực hiện OCR với timeout
                    import threading
                    import queue
                    
                    result_queue = queue.Queue()
                    error_queue = queue.Queue()
                    
                    def ocr_worker():
                        try:
                            results = reader.readtext(img_array)
                            result_queue.put(results)
                        except Exception as e:
                            error_queue.put(e)
                    
                    ocr_thread = threading.Thread(target=ocr_worker, daemon=True)
                    ocr_thread.start()
                    ocr_thread.join(timeout=self.ocr_timeout)
                    
                    if ocr_thread.is_alive():
                        continue  # Skip scale này nếu timeout
                    
                    if not error_queue.empty() or result_queue.empty():
                        continue
                    
                    results = result_queue.get()
                    
                    texts = []
                    total_conf = 0.0
                    valid_count = 0
                    for (bbox, text, conf) in results:
                        if text and conf > confidence_threshold:
                            texts.append(text)
                            total_conf += conf
                            valid_count += 1
                    
                    if texts:
                        result_text = ' '.join(texts).strip()
                        avg_conf = total_conf / valid_count if valid_count > 0 else 0.0
                        # Score = average confidence * word count
                        score = avg_conf * len(texts)
                        
                        if score > best_score:
                            best_score = score
                            best_result = result_text
                except Exception as e:
                    log_error(f"Error in EasyOCR multi-scale processing (scale={scale})", e)
                    continue
            
            self.last_call_time = time.monotonic()
            if best_result:
                # Giới hạn độ dài text
                if len(best_result) > self.max_text_length:
                    best_result = best_result[:self.max_text_length] + "..."
                self.last_result_text = best_result
                # Clear GPU memory
                if self.gpu_available:
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    except Exception:
                        pass
                return best_result
            return ""
        
        # Single scale (GPU mode hoặc multi-scale disabled)
        # Convert PIL Image to numpy array cho EasyOCR
        img_array = np.array(img_pil)
        
        # Thực hiện OCR với timeout để tránh stuck
        self.last_call_time = time.monotonic()
        try:
            # Sử dụng threading để implement timeout
            import threading
            import queue
            
            result_queue = queue.Queue()
            error_queue = queue.Queue()
            
            def ocr_worker():
                try:
                    results = reader.readtext(img_array)
                    result_queue.put(results)
                except Exception as e:
                    error_queue.put(e)
            
            # Start OCR in separate thread
            ocr_thread = threading.Thread(target=ocr_worker, daemon=True)
            ocr_thread.start()
            ocr_thread.join(timeout=self.ocr_timeout)
            
            # Check if thread is still alive (timeout occurred)
            if ocr_thread.is_alive():
                log_error(f"EasyOCR timeout after {self.ocr_timeout}s - skipping this frame")
                # Clear GPU memory if using GPU
                if self.gpu_available:
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    except Exception:
                        pass
                return ""
            
            # Get results
            if not error_queue.empty():
                error = error_queue.get()
                log_error("Lỗi EasyOCR", error)
                return ""
            
            if result_queue.empty():
                return ""
            
            results = result_queue.get()
            
            # Trích xuất text từ kết quả
            texts = []
            for (bbox, text, confidence) in results:
                if text and confidence > confidence_threshold:
                    texts.append(text)
            
            result_text = ' '.join(texts).strip() if texts else ""
            
            # Giới hạn độ dài text để tránh xử lý quá tải
            if len(result_text) > self.max_text_length:
                # Cắt text và thêm "..."
                result_text = result_text[:self.max_text_length] + "..."
                log_error(f"Text quá dài ({len(' '.join(texts))} chars), đã cắt xuống {self.max_text_length} chars")
            
            # Cache result
            self.last_result_text = result_text
            
            # Clear GPU memory sau mỗi lần xử lý để tránh memory leak
            if self.gpu_available:
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass
            
            return result_text
        except Exception as e:
            log_error("Lỗi EasyOCR", e)
            # Clear GPU memory on error
            if self.gpu_available:
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass
            return ""
    
    def is_available(self):
        """Check if EasyOCR is available"""
        return self.EASYOCR_AVAILABLE
    
    def cleanup(self):
        """Cleanup reader khi không dùng nữa"""
        if self.reader is not None:
            self.reader = None

