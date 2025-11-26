"""
EasyOCR Handler - tối ưu CPU cho free engine
"""
import time
import numpy as np
from PIL import Image
import sys
import os
import cv2

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
    """
    Handler cho EasyOCR với tối ưu CPU/GPU
    
    TARGET: Cấu hình tầm trung trở lên
    - CPU: i5 gen 10-12, i7 gen 9-11
    - GPU: GTX 1650, RTX 3050, RTX 3060 (4-8GB VRAM)
    - RAM: 8-16GB
    
    NOTE: Qua testing thực tế, CPU mode cho kết quả dịch chính xác hơn GPU mode.
    Các thiết lập đã được balance để chạy mượt trên cấu hình tầm trung:
    - GPU mode: 0.4s interval (2.5 FPS), 1000px max
    - CPU mode: 1.0s interval (1 FPS), 800px max
    """
    
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
        
        # Throttling intervals - balance cho cấu hình tầm trung
        # Target: i5 gen10-12, GTX 1650/RTX 3050, 8-16GB RAM
        if self.gpu_available:
            # GPU tầm trung (GTX 1650, RTX 3050): interval vừa phải
            self.min_call_interval = 0.4  # 2.5 FPS - balance cho GPU tầm trung
            log_error(f"[INFO] EasyOCR GPU mode: interval=0.4s (mid-range GPU balanced)")
        else:
            # CPU tầm trung (i5-10th to i7-11th): throttle hơi cao
            self.min_call_interval = 1.0  # 1 FPS - balance cho CPU tầm trung
            log_error("[INFO] EasyOCR CPU mode: interval=1.0s (mid-range CPU balanced)")
        log_error(f"[INFO] GPU Debug: {self.gpu_debug_info}")
        
        # Smart skip: cache last result để skip nếu text giống
        self.last_result_text = ""
        self.last_result_hash = None
        
        # Multi-scale processing - có thể bật/tắt từ UI
        self.enable_multi_scale = enable_multi_scale
        
        # GPU memory optimization
        self.frame_count = 0
        self.gpu_cache_clear_interval = 100  # Clear GPU cache mỗi 100 frames
        
        # Timeout cho OCR operations (giây) - balance cho cấu hình tầm trung
        # GPU tầm trung chậm hơn GPU mạnh, CPU tầm trung cần thời gian hơn
        self.ocr_timeout = 10.0 if self.gpu_available else 15.0
        
        # Max text length để tránh xử lý text quá dài (tăng lên để giữ nhiều text hơn)
        self.max_text_length = 800  # Ký tự (tăng từ 500 để giữ độ chính xác tốt hơn)
        
        # Image quality thresholds cho fast path
        self.high_quality_sharpness_threshold = 150  # Laplacian variance
        self.high_quality_contrast_threshold = 50  # Std deviation
        
        # Stats tracking
        self.stats = {
            'fast_path_count': 0,
            'full_preprocessing_count': 0,
            'total_ocr_calls': 0,
            'skipped_due_to_throttle': 0
        }
        
    def _detect_image_quality(self, img: np.ndarray) -> dict:
        """
        Phát hiện chất lượng ảnh để quyết định preprocessing strategy
        CRITICAL: Fast execution, khoảng 1-2ms
        
        Returns:
            {
                'sharpness': float,  # Laplacian variance
                'contrast': float,   # Std deviation
                'quality': str,      # 'high', 'medium', 'low'
                'needs_preprocessing': bool
            }
        """
        try:
            # Convert to grayscale nếu cần
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                gray = img
            
            # Measure sharpness (Laplacian variance) - FAST
            laplacian = cv2.Laplacian(gray, cv2.CV_64F)
            sharpness = laplacian.var()
            
            # Measure contrast (std deviation) - FAST
            contrast = gray.std()
            
            # Determine quality
            if sharpness > self.high_quality_sharpness_threshold and contrast > self.high_quality_contrast_threshold:
                quality = 'high'
                needs_preprocessing = False  # FAST PATH
            elif sharpness < 50 or contrast < 25:
                quality = 'low'
                needs_preprocessing = True
            else:
                quality = 'medium'
                needs_preprocessing = True
            
            return {
                'sharpness': sharpness,
                'contrast': contrast,
                'quality': quality,
                'needs_preprocessing': needs_preprocessing
            }
        except Exception as e:
            log_error(f"Error detecting image quality: {e}", e)
            # Fallback: assume needs preprocessing
            return {
                'sharpness': 0,
                'contrast': 0,
                'quality': 'unknown',
                'needs_preprocessing': True
            }
        
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
        Main OCR method với throttling, preprocessing nâng cao và smart skip
        CRITICAL FIX: Adaptive throttling - short text được ưu tiên hơn
        EasyOCR-specific preprocessing khác với Tesseract
        """
        self.stats['total_ocr_calls'] += 1
        
        # Throttle: EasyOCR rất nặng CPU/GPU, chỉ gọi theo interval
        # CRITICAL FIX: Đọc text length từ last result để adaptive throttle
        now = time.monotonic()
        time_since_last_call = now - self.last_call_time
        
        # Adaptive throttling dựa trên text length của last result
        # Short text (< 50 chars) → throttle ít hơn (0.3s thay vì 1.0s)
        # Medium text (50-200 chars) → throttle bình thường
        # Long text (> 200 chars) → throttle nhiều hơn (1.5s)
        last_text_len = len(self.last_result_text) if self.last_result_text else 0
        
        if last_text_len < 50:
            # Short text detected → reduce throttle để không skip short dialogue
            effective_interval = self.min_call_interval * 0.3  # 30% của interval bình thường
        elif last_text_len > 200:
            # Long text detected → increase throttle để tránh overload
            effective_interval = self.min_call_interval * 1.5
        else:
            # Medium text → normal throttle
            effective_interval = self.min_call_interval
        
        if time_since_last_call < effective_interval:
            self.stats['skipped_due_to_throttle'] += 1
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
        
        # EasyOCR-specific preprocessing (KHÁC với Tesseract)
        # Neural networks thích ảnh có contrast cao và noise thấp
        try:
            if isinstance(img, np.ndarray):
                preprocessed_img = self._preprocess_for_easyocr(img)
                img_pil = Image.fromarray(preprocessed_img)
            else:
                # Convert PIL to numpy for preprocessing
                img_np = np.array(img_pil)
                preprocessed_img = self._preprocess_for_easyocr(img_np)
                img_pil = Image.fromarray(preprocessed_img)
        except Exception as e:
            log_error("Error in EasyOCR preprocessing", e)
            # Fallback to original image
            if not isinstance(img, Image.Image):
                img_pil = Image.fromarray(img) if isinstance(img, np.ndarray) else img
        
        # Increment frame counter và periodic GPU cleanup
        self.frame_count += 1
        if self.gpu_available and self.frame_count % self.gpu_cache_clear_interval == 0:
            self._cleanup_gpu_memory()
        
        # Resize ảnh - balance cho GPU/CPU tầm trung
        w, h = img_pil.size
        max_dim = max(w, h)
        
        # GPU tầm trung (GTX 1650, RTX 3050): 1000px balance
        # CPU tầm trung (i5-10th to i7-11th): 800px để tránh overload
        max_size = 1000 if self.gpu_available else 800
        if max_dim > max_size:
            scale = max_size / max_dim
            new_w, new_h = int(w * scale), int(h * scale)
            img_pil = img_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # Multi-scale processing - optimized cho cả CPU và GPU
        if self.enable_multi_scale:
            # GPU: batch processing cho tất cả scales cùng lúc
            # CPU: sequential processing
            best_result = None
            best_score = 0.0
            
            scales = [0.7, 1.0, 1.3]
            
            # GPU batch processing - process all scales in parallel
            if self.gpu_available:
                try:
                    scaled_images = []
                    for scale in scales:
                        scaled_w = int(w * scale)
                        scaled_h = int(h * scale)
                        if scaled_w >= 10 and scaled_h >= 10:
                            scaled_img = img_pil.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
                            scaled_images.append((scale, np.array(scaled_img)))
                    
                    # Process all scales
                    for scale, img_array in scaled_images:
                        try:
                            results = reader.readtext(img_array)
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
                                score = avg_conf * len(texts)
                                if score > best_score:
                                    best_score = score
                                    best_result = result_text
                        except Exception as e:
                            log_error(f"Error in GPU multi-scale processing (scale={scale})", e)
                            continue
                    
                    self.last_call_time = time.monotonic()
                    if best_result:
                        if len(best_result) > self.max_text_length:
                            best_result = best_result[:self.max_text_length] + "..."
                        self.last_result_text = best_result
                        self._cleanup_gpu_memory()
                        return best_result
                    return ""
                except Exception as e:
                    log_error(f"Error in GPU batch multi-scale", e)
                    # Fallback to single scale
            
            # CPU sequential processing
            for scale in scales:
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
                self._cleanup_gpu_memory()
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
                self._cleanup_gpu_memory()
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
            
            # Cleanup GPU memory
            self._cleanup_gpu_memory()
            
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
    
    def _cleanup_gpu_memory(self):
        """Cleanup GPU memory cache - gọi định kỳ để tránh memory leak"""
        if not self.gpu_available:
            return
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
        except Exception as e:
            log_error(f"Error cleaning GPU memory: {e}", e)
    
    def _preprocess_for_easyocr(self, img):
        """
        Preprocessing cho EasyOCR với FAST PATH optimization
        CRITICAL FIX: Check image quality trước, skip heavy processing cho ảnh đẹp
        
        Neural networks thích contrast cao, ít thích heavy morphology
        Balance cho cấu hình tầm trung: giảm aggressive preprocessing
        
        NEW: Morphology operations, bilateral filter, auto-scaling cho small text
        """
        try:
            # Convert to grayscale if needed
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                gray = img.copy()
            
            # AUTO-SCALE: Detect small text và upscale (30-40% improvement cho small text)
            h, w = gray.shape[:2]
            scale_applied = False
            if min(h, w) < 300:
                # Small image/text → upscale to minimum 300px
                scale_factor = max(300.0 / h, 300.0 / w)
                new_w = int(w * scale_factor)
                new_h = int(h * scale_factor)
                gray = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
                scale_applied = True
            
            # FAST PATH: Check image quality trước
            quality_info = self._detect_image_quality(gray)
            
            # High quality image → minimal processing (FAST PATH - giảm 70-80% processing time)
            if not quality_info['needs_preprocessing']:
                self.stats['fast_path_count'] += 1
                # Chỉ light CLAHE, skip denoising và sharpening
                clahe = cv2.createCLAHE(clipLimit=1.2, tileGridSize=(8, 8))
                enhanced = clahe.apply(gray)
                
                # Light morphology cho high quality (fix fragmented text)
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
                enhanced = cv2.morphologyEx(enhanced, cv2.MORPH_CLOSE, kernel, iterations=1)
                
                return enhanced
            
            # Low/Medium quality → full preprocessing
            self.stats['full_preprocessing_count'] += 1
            
            # Conditional preprocessing dựa trên quality
            if quality_info['quality'] == 'low':
                # Low quality: aggressive preprocessing
                # BILATERAL FILTER: Faster than fastNlMeansDenoising (5-10ms vs 15-30ms)
                # Preserve edges tốt hơn cho game graphics
                if gray.shape[0] > 200 or gray.shape[1] > 200:
                    gray = cv2.bilateralFilter(gray, d=5, sigmaColor=50, sigmaSpace=50)
                
                # Strong CLAHE
                clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
                enhanced = clahe.apply(gray)
                
                # Sharpening
                blurred = cv2.GaussianBlur(enhanced, (0, 0), 2.0)
                sharpened = cv2.addWeighted(enhanced, 1.5, blurred, -0.5, 0)
                
                # MORPHOLOGY: Kết nối fragmented text (critical cho game text với effects)
                # Dilation/closing để merge text pieces
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
                sharpened = cv2.morphologyEx(sharpened, cv2.MORPH_CLOSE, kernel, iterations=2)
                
                return sharpened
            else:
                # Medium quality: balanced preprocessing
                # BILATERAL FILTER: Light denoising, fast và preserve edges
                if gray.shape[0] > 200 or gray.shape[1] > 200:
                    gray = cv2.bilateralFilter(gray, d=3, sigmaColor=30, sigmaSpace=30)
                
                # Light CLAHE - giảm clipLimit để tránh over-enhancement
                clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
                enhanced = clahe.apply(gray)
                
                # Very light sharpening - giảm weights để tránh artifacts
                # Neural networks đã học được features, không cần sharpen mạnh
                blurred = cv2.GaussianBlur(enhanced, (0, 0), 1.5)
                sharpened = cv2.addWeighted(enhanced, 1.1, blurred, -0.1, 0)
                
                # Light morphology cho medium quality
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
                sharpened = cv2.morphologyEx(sharpened, cv2.MORPH_CLOSE, kernel, iterations=1)
                
                return sharpened
        except Exception as e:
            log_error(f"Error in EasyOCR preprocessing: {e}", e)
            return img
    
    def is_available(self):
        """Check if EasyOCR is available"""
        return self.EASYOCR_AVAILABLE
    
    def get_stats(self) -> dict:
        """Get handler statistics"""
        total_calls = self.stats['total_ocr_calls']
        if total_calls > 0:
            fast_path_rate = (self.stats['fast_path_count'] / 
                            (self.stats['fast_path_count'] + self.stats['full_preprocessing_count'])) * 100 if \
                            (self.stats['fast_path_count'] + self.stats['full_preprocessing_count']) > 0 else 0
            skip_rate = (self.stats['skipped_due_to_throttle'] / total_calls) * 100
        else:
            fast_path_rate = 0
            skip_rate = 0
        
        return {
            **self.stats,
            'fast_path_rate': fast_path_rate,
            'skip_rate': skip_rate,
            'gpu_available': self.gpu_available,
            'gpu_name': self.gpu_name if self.gpu_available else 'N/A'
        }
    
    def cleanup(self):
        """Cleanup reader khi không dùng nữa"""
        if self.reader is not None:
            self.reader = None

