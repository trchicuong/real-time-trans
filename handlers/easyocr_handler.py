"""EasyOCR Handler cho OCR - Tối ưu cho game AAA graphics"""
import time
import numpy as np
from PIL import Image
import sys
import os
import cv2

try:
    from modules import log_error, log_debug
    from modules import AdvancedImageProcessor
    ADVANCED_PROCESSING_AVAILABLE = True
except ImportError:
    def log_error(msg, exception=None):
        pass
    def log_debug(msg):
        pass
    ADVANCED_PROCESSING_AVAILABLE = False

EASYOCR_AVAILABLE = False
try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    pass

# GPU detection removed - CPU-only mode

class EasyOCRHandler:
    """Handler cho EasyOCR với hỗ trợ CPU/GPU"""
    
    def __init__(self, source_language='eng', use_gpu=None, enable_multi_scale=False, enable_game_mode=True):
        """Khởi tạo handler - CPU-ONLY mode"""
        self.source_language = source_language
        self.reader = None
        self.last_call_time = 0.0
        self.EASYOCR_AVAILABLE = EASYOCR_AVAILABLE
        
        # FORCE CPU-ONLY MODE (user confirmed CPU performs better than GPU for EasyOCR)
        self.gpu_available = False
        self.gpu_name = None
        self.gpu_debug_info = "CPU-only mode (forced - better performance than GPU for this use case)"
        
        # Throttling intervals - CPU-only mode, minimal throttling
        self.min_call_interval = 0.15  # 6-7 FPS for CPU - balanced for responsiveness
        self.stable_text_interval = 0.3  # When text is stable, slower polling
        
        # Smart skip: cache last result để skip nếu text giống
        self.last_result_text = ""
        self.last_result_hash = None
        
        # Text stability tracking - MINIMAL buffering for fast response
        self.text_stability_buffer = []
        self.stability_buffer_size = 1  # No buffering - immediate response
        self.text_change_threshold = 0.90  # 90% - more lenient to catch short dialogues
        
        # Multi-scale processing - có thể bật/tắt từ UI
        self.enable_multi_scale = enable_multi_scale
        
        # Game mode - advanced preprocessing
        self.enable_game_mode = enable_game_mode
        
        # Advanced image processor cho game graphics
        if ADVANCED_PROCESSING_AVAILABLE and self.enable_game_mode:
            try:
                self.advanced_processor = AdvancedImageProcessor()
            except Exception as e:
                log_error("Lỗi khởi tạo AdvancedImageProcessor", e)
                self.advanced_processor = None
        else:
            self.advanced_processor = None
        
        # Frame counter for stats
        self.frame_count = 0
        
        # CPU Performance Monitoring
        self.last_ocr_durations = []  # Track OCR execution times
        self.ocr_duration_window = 10   # Track last 10 OCRs
        self.high_load_threshold = 0.5  # OCR > 500ms = high load for CPU
        self.consecutive_high_load = 0  # Counter for consecutive high loads
        
        # Adaptive processing - dynamically adjust based on actual performance
        self.adaptive_enabled = True
        self.target_fps = 6.0  # Target OCR FPS for CPU mode (realistic)
        self.actual_fps = 0.0  # Measured actual FPS
        self.fps_samples = []
        self.fps_window = 20  # Calculate FPS over 20 samples
        
        # Timeout cho OCR operations (giây) - CPU only
        self.ocr_timeout = 12.0  # CPU needs more time than GPU
        
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
                        
                        # FORCE CPU-ONLY MODE (better performance for this use case)
                        use_gpu = False
                        
                        # CPU-only EasyOCR reader - no GPU code needed
                        self.reader = easyocr.Reader(
                            [easyocr_lang], 
                            gpu=False,  # Force CPU
                            verbose=False,
                            download_enabled=True  # Auto-download model if needed
                        )
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
        ENHANCED: Advanced deduplication, text debouncing, adaptive throttling, CPU load detection
        EasyOCR-specific preprocessing khác với Tesseract
        """
        self.stats['total_ocr_calls'] += 1
        
        # Throttle: EasyOCR rất nặng CPU, chỉ gọi theo interval
        # ADAPTIVE: Điều chỉnh interval dựa trên text stability VÀ CPU load
        now = time.monotonic()
        time_since_last_call = now - self.last_call_time
        
        # CPU load detection (simplified, no GPU)
        cpu_under_pressure = self._is_cpu_under_pressure()
        if cpu_under_pressure:
            self.consecutive_high_load += 1
        else:
            self.consecutive_high_load = 0
        
        # Adaptive throttling dựa trên:
        # 1. Text length của last result
        # 2. Text stability (nếu text ổn định → throttle nhiều hơn)
        # 3. CPU pressure (nếu CPU bận → throttle hơn để không giựt game)
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
        
        # Adaptive throttling based on actual performance
        # Measure FPS and adjust interval dynamically
        if self.adaptive_enabled and len(self.fps_samples) >= 3:
            # Calculate actual FPS
            if self.fps_samples:
                avg_interval = sum(self.fps_samples) / len(self.fps_samples)
                self.actual_fps = 1.0 / avg_interval if avg_interval > 0 else 0
                
                # Adjust throttle based on target vs actual FPS
                if self.actual_fps < self.target_fps * 0.8:
                    # Running slower than target - reduce interval
                    effective_interval *= 0.7
                elif self.actual_fps > self.target_fps * 1.2:
                    # Running faster than target - increase interval slightly
                    effective_interval *= 1.1
        
        if cpu_under_pressure:
            if self.consecutive_high_load >= 5:
                # CPU consistently under pressure → moderate throttle
                effective_interval *= 1.4  # 1.4x throttle
                if self.consecutive_high_load == 5:
                    log_error(f"[CPU PRESSURE] Moderate throttling activated")
            elif self.consecutive_high_load >= 2:
                # CPU occasionally busy → light throttle
                effective_interval *= 1.15  # 1.15x throttle
        
        if time_since_last_call < effective_interval:
            self.stats['skipped_due_to_throttle'] += 1
            return ""  # Skip call này để giảm CPU load
        
        # Smart skip: Use perceptual hash (imagehash) for better duplicate detection
        # Much better than MD5 for detecting visually similar frames
        try:
            import imagehash
            if isinstance(img, np.ndarray):
                img_pil = Image.fromarray(img)
            else:
                img_pil = img
            
            # Use average hash - fast and good for frame comparison
            # Perceptual hash detects similar images even with small changes
            img_hash = str(imagehash.average_hash(img_pil, hash_size=8))
            
            # Skip nếu hash giống (frame không đổi hoặc rất giống)
            if img_hash == self.last_result_hash:
                # Frame giống hệt → return cached result ngay
                return self.last_result_text
            
            self.last_result_hash = img_hash
        except ImportError:
            # Fallback to MD5 if imagehash not available
            try:
                import hashlib
                w, h = img_pil.size if hasattr(img_pil, 'size') else (img.shape[1], img.shape[0])
                img_small = img_pil.resize((max(1, w//8), max(1, h//8)), Image.Resampling.NEAREST)
                if img_small.mode != 'L':
                    img_small = img_small.convert('L')
                img_hash = hashlib.md5(img_small.tobytes()).hexdigest()
                if img_hash == self.last_result_hash:
                    return self.last_result_text
                self.last_result_hash = img_hash
            except Exception as e:
                log_error("Error computing image hash", e)
        
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
        
        # Increment frame counter for stats
        self.frame_count += 1
        
        # Resize ảnh - standard resize for CPU mode
        w, h = img_pil.size
        max_dim = max(w, h)
        
        max_size = 800  # Standard max size for CPU
        
        if max_dim > max_size:
            scale = max_size / max_dim
            new_w, new_h = int(w * scale), int(h * scale)
            img_pil = img_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # Multi-scale processing - optimized for CPU
        if self.enable_multi_scale:
            ocr_start_time = time.monotonic()  # Track start time for multi-scale
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
            
            # Track OCR duration and update FPS samples
            ocr_duration = time.monotonic() - ocr_start_time
            self.last_ocr_durations.append(ocr_duration)
            if len(self.last_ocr_durations) > self.ocr_duration_window:
                self.last_ocr_durations.pop(0)
            
            # Track actual call interval for FPS calculation
            actual_interval = now - self.last_call_time
            self.fps_samples.append(actual_interval)
            if len(self.fps_samples) > self.fps_window:
                self.fps_samples.pop(0)
            
            # Update last call time
            self.last_call_time = time.monotonic()
            
            if best_result:
                # Basic text normalization
                best_result = ' '.join(best_result.split())  # Collapse whitespace
                best_result = best_result.strip()
                
                # Giới hạn độ dài text
                if len(best_result) > self.max_text_length:
                    best_result = best_result[:self.max_text_length] + "..."
                self.last_result_text = best_result
                return best_result
            return ""
        
        # Single scale (multi-scale disabled)
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
            
            # Basic text normalization
            if result_text:
                result_text = ' '.join(result_text.split())  # Collapse whitespace
                result_text = result_text.strip()
            
            # Giới hạn độ dài text để tránh xử lý quá tải
            if len(result_text) > self.max_text_length:
                result_text = result_text[:self.max_text_length] + "..."
            
            # TEXT DEBOUNCING: More lenient to avoid skipping short dialogues
            if self.last_result_text and result_text:
                # Chỉ so sánh nếu text không rỗng
                if len(result_text) > 0:
                    similarity = self._compute_text_similarity(result_text, self.last_result_text)
                    # Skip only if very similar AND exact same length
                    if similarity >= 0.85 and len(result_text) == len(self.last_result_text):
                        return self.last_result_text
            
            # Cache result (text thực sự khác)
            self.last_result_text = result_text
            
            # Update stability buffer
            self.text_stability_buffer.append(result_text)
            if len(self.text_stability_buffer) > self.stability_buffer_size:
                self.text_stability_buffer.pop(0)
            
            # Track OCR duration for CPU load detection
            ocr_duration = time.monotonic() - ocr_start_time
            self.last_ocr_durations.append(ocr_duration)
            if len(self.last_ocr_durations) > self.ocr_duration_window:
                self.last_ocr_durations.pop(0)
            
            # Track actual call interval for FPS calculation
            actual_interval = now - self.last_call_time
            self.fps_samples.append(actual_interval)
            if len(self.fps_samples) > self.fps_window:
                self.fps_samples.pop(0)
            
            # Log slow OCRs only if very slow (>1s)
            if ocr_duration > 1.0:
                log_error(f"[SLOW OCR] {ocr_duration:.1f}s")
            
            # Update last call time
            self.last_call_time = time.monotonic()
            
            return result_text
        except Exception as e:
            log_error("Lỗi EasyOCR", e)
            return ""
    
    def _is_cpu_under_pressure(self):
        """
        Kiểm tra CPU có đang under pressure không
        Dựa trên OCR execution time
        """
        # Check recent OCR durations
        if len(self.last_ocr_durations) >= 3:
            avg_duration = sum(self.last_ocr_durations[-3:]) / 3
            if avg_duration > self.high_load_threshold:
                return True
        
        return False
    
    def _preprocess_for_easyocr(self, img):
        """
        Preprocessing cho EasyOCR với FAST PATH optimization + Game Mode
        
        GAME MODE: Color extraction → Noise detection → Adaptive denoising
        STANDARD MODE: Quality-based preprocessing (fast path vs full)
        
        Neural networks thích contrast cao, ít thích heavy morphology
        """
        try:
            # GAME MODE: Advanced preprocessing pipeline
            if self.enable_game_mode and self.advanced_processor:
                try:
                    # Full game graphics processing: color extraction + noise detection + adaptive denoising
                    processed, info = self.advanced_processor.process_for_game_ocr(img, mode='auto')
                    
                    # EasyOCR-specific enhancement: light CLAHE only
                    clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
                    processed = clahe.apply(processed)
                    
                    return processed
                    
                except Exception as e:
                    log_error("Lỗi advanced preprocessing, fallback về standard", e)
                    # Fallback về standard preprocessing
            
            # STANDARD MODE: Legacy preprocessing
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
