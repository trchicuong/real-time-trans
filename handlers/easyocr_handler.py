"""EasyOCR Handler cho OCR"""
import time
import numpy as np
from PIL import Image
import sys
import os
import cv2

try:
    from modules import log_error, log_debug
except ImportError:
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
    """Phát hiện GPU"""
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
        
        gpu_name = torch.cuda.get_device_name(0)
        cuda_version = getattr(torch.version, 'cuda', 'Unknown')
        device_count = torch.cuda.device_count()
        debug_info += f", CUDA version: {cuda_version}, GPU devices: {device_count}, GPU: {gpu_name}"
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
    """Handler cho EasyOCR với hỗ trợ CPU/GPU"""
    
    def __init__(self, source_language='eng', use_gpu=None, enable_multi_scale=False):
        """Khởi tạo handler"""
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
            else:
                self.gpu_available = False
                self.gpu_name = None
                self.gpu_debug_info = f"{gpu_debug_info} (GPU requested but not available)"
        elif use_gpu is False:
            self.gpu_available = False
            self.gpu_name = None
            self.gpu_debug_info = f"{gpu_debug_info} (CPU mode forced by user)"
        else:
            self.gpu_available = detected_gpu_available
            self.gpu_name = detected_gpu_name
            self.gpu_debug_info = gpu_debug_info
        
        # Throttling intervals - giảm xuống để không skip dialogue
        if self.gpu_available:
            self.min_call_interval = 0.4  # 2.5 FPS - giảm từ 0.6s
            self.stable_text_interval = 0.8  # Khi text ổn định
        else:
            self.min_call_interval = 0.8  # Giảm từ 1.0s
            self.stable_text_interval = 1.2
        
        # Smart skip: cache last result để skip nếu text giống
        self.last_result_text = ""
        self.last_result_hash = None
        
        # Text stability tracking
        self.text_stability_buffer = []
        self.stability_buffer_size = 2  # Giảm từ 3 để responsive hơn
        self.text_change_threshold = 0.97  # 97% để tránh skip text mới
        
        # Multi-scale processing - có thể bật/tắt từ UI
        self.enable_multi_scale = enable_multi_scale
        
        # GPU memory optimization - CRITICAL for gaming
        self.frame_count = 0
        self.gpu_cache_clear_interval = 20  # AGGRESSIVE: Clear mỗi 20 frames (giảm từ 100)
        
        # GPU Performance Monitoring (detect game rendering load)
        self.last_ocr_durations = []  # Track OCR execution times
        self.ocr_duration_window = 5   # Track last 5 OCRs
        self.high_load_threshold = 0.5  # Nếu OCR > 500ms = high load
        self.consecutive_high_load = 0  # Counter for consecutive high loads
        
        # GPU Memory Pressure Detection
        self.vram_usage_history = []
        self.vram_check_interval = 10  # Check VRAM every 10 frames
        self.vram_warning_threshold = 0.85  # 85% VRAM usage = warning
        
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
        
    def _compute_text_similarity(self, text1, text2):
        """
        Tính similarity giữa 2 text strings (0.0 - 1.0)
        Dùng simple character-level comparison (nhanh)
        """
        if text1 == text2:
            return 1.0
        if not text1 or not text2:
            return 0.0
        
        # Simple approach: common characters ratio
        set1 = set(text1.lower())
        set2 = set(text2.lower())
        
        if not set1 or not set2:
            return 0.0
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0
    
    def _is_text_stable(self, new_text):
        """
        Kiểm tra xem text có ổn định hay không (debouncing)
        Text được coi là stable khi xuất hiện liên tục trong buffer
        """
        if not new_text:
            return False
        
        # Add to buffer
        self.text_stability_buffer.append(new_text)
        
        # Keep buffer size limited
        if len(self.text_stability_buffer) > self.stability_buffer_size:
            self.text_stability_buffer.pop(0)
        
        # Need at least stability_buffer_size samples
        if len(self.text_stability_buffer) < self.stability_buffer_size:
            return False
        
        # Check if all texts in buffer are similar
        reference_text = self.text_stability_buffer[-1]
        
        for text in self.text_stability_buffer:
            similarity = self._compute_text_similarity(text, reference_text)
            if similarity < self.text_change_threshold:
                return False  # Found a different text → not stable
        
        # All texts in buffer are similar → stable
        return True
    
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
        """Khởi tạo EasyOCR reader (lazy initialization) với GPU optimization"""
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
                                else:
                                    torch.cuda.empty_cache()
                                    os.environ['PYTORCH_ALLOC_CONF'] = 'max_split_size_mb:128'
                            except Exception as e:
                                log_error(f"[WARNING] Error verifying GPU before EasyOCR init: {e}. Falling back to CPU.")
                                use_gpu = False
                        
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
                                    torch.cuda.set_stream(torch.cuda.Stream(priority=-1))
                                    
                                    # Force a small operation to see if GPU is used
                                    test_tensor = torch.zeros(1).cuda()
                                    del test_tensor
                                    torch.cuda.empty_cache()
                            except Exception as e:
                                log_error(f"GPU init issue: {str(e)}")
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
        ENHANCED: Advanced deduplication, text debouncing, adaptive throttling, GPU pressure detection
        EasyOCR-specific preprocessing khác với Tesseract
        """
        self.stats['total_ocr_calls'] += 1
        
        # Throttle: EasyOCR rất nặng CPU/GPU, chỉ gọi theo interval
        # ADAPTIVE: Điều chỉnh interval dựa trên text stability VÀ GPU pressure
        now = time.monotonic()
        time_since_last_call = now - self.last_call_time
        
        gpu_under_pressure = False
        if self.gpu_available:
            gpu_under_pressure = self._is_gpu_under_pressure()
            if gpu_under_pressure:
                self.consecutive_high_load += 1
            else:
                self.consecutive_high_load = 0
        
        # Adaptive throttling dựa trên:
        # 1. Text length của last result
        # 2. Text stability (nếu text ổn định → throttle nhiều hơn)
        # 3. GPU pressure (nếu GPU bận → throttle NHIỀU HƠN để không giựt game)
        last_text_len = len(self.last_result_text) if self.last_result_text else 0
        
        # Base interval dựa trên text length
        if last_text_len < 50:
            base_interval = self.min_call_interval * 0.7  # Tăng từ 0.5 để không bỏ sót
        elif last_text_len > 200:
            base_interval = self.min_call_interval * 1.2  # Giảm từ 1.3
        else:
            base_interval = self.min_call_interval
        
        # Adjust based on text stability - ít aggressive hơn
        is_stable = self._is_text_stable(self.last_result_text)
        if is_stable:
            effective_interval = base_interval * 1.3  # Nhẹ hơn, không dùng stable_text_interval
        else:
            effective_interval = base_interval
        
        if gpu_under_pressure:
            if self.consecutive_high_load >= 3:
                # GPU consistently under pressure → AGGRESSIVE throttle
                effective_interval *= 3.0  # 3x throttle
                # Only log once when entering aggressive mode
                if self.consecutive_high_load == 3:
                    log_error(f"[GPU PRESSURE] Aggressive throttling activated")
            else:
                # GPU occasionally busy → moderate throttle
                effective_interval *= 2.0  # 2x throttle
        
        if time_since_last_call < effective_interval:
            self.stats['skipped_due_to_throttle'] += 1
            return ""  # Skip call này để giảm CPU/GPU load
        
        # Smart skip: Check image hash để skip nếu giống frame trước
        # ENHANCED: Improved hash comparison với perceptual hashing
        try:
            import hashlib
            if isinstance(img, np.ndarray):
                img_pil = Image.fromarray(img)
            else:
                img_pil = img
            
            # Create small hash image for comparison
            # Resize to small size for faster hash computation
            w, h = img_pil.size
            img_small = img_pil.resize((max(1, w//8), max(1, h//8)), Image.Resampling.NEAREST)
            
            # Convert to grayscale for better comparison
            if img_small.mode != 'L':
                img_small = img_small.convert('L')
            
            img_hash = hashlib.md5(img_small.tobytes()).hexdigest()
            
            # Skip nếu hash giống (frame không đổi)
            if img_hash == self.last_result_hash:
                # Frame giống hệt → return cached result ngay
                return self.last_result_text
            
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
        if self.gpu_available:
            # Cleanup mỗi 20 frames
            if self.frame_count % self.gpu_cache_clear_interval == 0:
                self._cleanup_gpu_memory()
                
                # Log VRAM usage nếu cao
                if self.frame_count % 100 == 0:
                    used, total, percentage = self._check_vram_usage()
                    if used is not None and percentage > 0.7:
                        log_error(f"[VRAM] High usage: {percentage*100:.0f}%")
        
        # Resize ảnh - AGGRESSIVE downscale cho GPU để giảm VRAM
        w, h = img_pil.size
        max_dim = max(w, h)
        
        max_size = 800 if self.gpu_available else 800
        
        # Chỉ giảm resolution khi GPU thực sự stressed (>=3 lần liên tục)
        if self.gpu_available and self.consecutive_high_load >= 3:
            max_size = 700  # Giảm nhẹ hơn, từ 600->700
            if self.consecutive_high_load == 3:
                log_error(f"[GPU PRESSURE] Reducing resolution to 700px")
        
        if max_dim > max_size:
            scale = max_size / max_dim
            new_w, new_h = int(w * scale), int(h * scale)
            img_pil = img_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # Multi-scale processing - optimized cho cả CPU và GPU
        if self.enable_multi_scale:
            best_result = None
            best_score = 0.0
            
            scales = [0.7, 1.0, 1.3]
            
            for scale in scales:
                try:
                    scaled_w = int(w * scale)
                    scaled_h = int(h * scale)
                    if scaled_w < 10 or scaled_h < 10:
                        continue
                    
                    scaled_img = img_pil.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
                    img_array = np.array(scaled_img)
                    
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
                    log_error(f"Error in multi-scale processing (scale={scale})", e)
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
        ocr_start_time = time.monotonic()  # Track OCR duration
        
        try:
            # Sử dụng threading để implement timeout
            import threading
            import queue
            
            result_queue = queue.Queue()
            error_queue = queue.Queue()
            
            def ocr_worker():
                try:
                    import os
                    if hasattr(os, 'nice'):
                        try:
                            os.nice(10)
                        except:
                            pass
                    
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
                result_text = result_text[:self.max_text_length] + "..."
            
            # TEXT DEBOUNCING: Chỉ skip nếu text thực sự giống hệt
            if self.last_result_text and result_text:
                # Chỉ so sánh nếu text không rỗng
                if len(result_text) > 0:
                    similarity = self._compute_text_similarity(result_text, self.last_result_text)
                    # Chỉ skip nếu gần như identical VÀ cùng độ dài
                    if similarity >= 0.97 and abs(len(result_text) - len(self.last_result_text)) <= 2:
                        return self.last_result_text
            
            # Cache result (text thực sự khác)
            self.last_result_text = result_text
            
            # Update stability buffer
            self.text_stability_buffer.append(result_text)
            if len(self.text_stability_buffer) > self.stability_buffer_size:
                self.text_stability_buffer.pop(0)
            
            # Track OCR duration for GPU pressure detection
            ocr_duration = time.monotonic() - ocr_start_time
            self.last_ocr_durations.append(ocr_duration)
            if len(self.last_ocr_durations) > self.ocr_duration_window:
                self.last_ocr_durations.pop(0)
            
            # Log slow OCRs only if very slow (>1s)
            if ocr_duration > 1.0:
                log_error(f"[SLOW OCR] {ocr_duration:.1f}s")
            
            # AGGRESSIVE GPU cleanup after each OCR
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
    
    def _check_vram_usage(self):
        """
        Check VRAM usage để detect memory pressure
        Returns: (used_gb, total_gb, percentage)
        """
        if not self.gpu_available:
            return None, None, None
        
        try:
            import torch
            if torch.cuda.is_available():
                # Get memory stats
                allocated = torch.cuda.memory_allocated(0) / (1024**3)  # GB
                reserved = torch.cuda.memory_reserved(0) / (1024**3)    # GB
                total = torch.cuda.get_device_properties(0).total_memory / (1024**3)  # GB
                
                # Use reserved memory as the "used" metric (more accurate)
                used = reserved
                percentage = (used / total) if total > 0 else 0
                
                return used, total, percentage
        except Exception as e:
            log_error(f"Error checking VRAM usage: {e}", e)
            return None, None, None
    
    def _is_gpu_under_pressure(self):
        """
        Kiểm tra GPU có đang under pressure không (game rendering nhiều)
        Dựa trên:
        1. OCR execution time (nếu tăng đột ngột = GPU busy)
        2. VRAM usage (nếu cao = game đang dùng nhiều)
        """
        # Check recent OCR durations
        if len(self.last_ocr_durations) >= 3:
            avg_duration = sum(self.last_ocr_durations[-3:]) / 3
            if avg_duration > self.high_load_threshold:
                return True
        
        # Check VRAM usage (every N frames)
        if self.frame_count % self.vram_check_interval == 0:
            used, total, percentage = self._check_vram_usage()
            if percentage is not None and percentage > self.vram_warning_threshold:
                # Only log if not already logged recently (avoid spam)
                if not hasattr(self, '_last_vram_warning') or (time.monotonic() - self._last_vram_warning) > 30:
                    log_error(f"[WARNING] High VRAM usage: {percentage*100:.0f}%")
                    self._last_vram_warning = time.monotonic()
                return True
        
        return False
    
    def _cleanup_gpu_memory(self):
        """
        AGGRESSIVE GPU memory cleanup - gọi định kỳ để tránh memory leak
        CRITICAL for gaming: Free memory ASAP để game không bị giựt
        """
        if not self.gpu_available:
            return
        try:
            import torch
            if torch.cuda.is_available():
                # AGGRESSIVE cleanup
                torch.cuda.empty_cache()
                torch.cuda.synchronize()  # Wait for all operations to complete
                
                # Optional: Force garbage collection on GPU tensors
                import gc
                gc.collect()
                torch.cuda.empty_cache()  # Clear again after GC
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
            if min(h, w) < 300:
                # Small image/text → upscale to minimum 300px
                scale_factor = max(300.0 / h, 300.0 / w)
                new_w = int(w * scale_factor)
                new_h = int(h * scale_factor)
                gray = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
                # Removed log spam: scale applied silently
            
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
