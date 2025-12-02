"""EasyOCR Handler cho OCR"""
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


class EasyOCRHandler:
    """Handler cho EasyOCR - CPU-only mode"""
    
    def __init__(self, source_language='eng', use_gpu=None, enable_multi_scale=False, enable_game_mode=False, game_mode_fast=True):
        """Khởi tạo handler"""
        self.source_language = source_language
        self.reader = None
        self.last_call_time = 0.0
        self.EASYOCR_AVAILABLE = EASYOCR_AVAILABLE
        
        # CPU-only mode
        self.gpu_available = False
        self.gpu_name = None
        self.gpu_debug_info = "CPU-only mode"
        
        # Throttling - 200ms = 5 FPS max
        self.min_call_interval = 0.2
        
        # Cache để skip duplicate frames
        self.last_result_text = ""
        self.last_result_hash = None
        
        # Text stability
        self.text_stability_buffer = []
        self.stability_buffer_size = 1
        self.text_change_threshold = 0.85
        
        # Options từ UI
        self.enable_multi_scale = enable_multi_scale
        self.enable_game_mode = enable_game_mode
        self.game_mode_fast = game_mode_fast  # Fast mode = CLAHE only
        
        # Advanced processor cho game mode (chỉ khi không dùng fast mode)
        if ADVANCED_PROCESSING_AVAILABLE and self.enable_game_mode and not self.game_mode_fast:
            try:
                self.advanced_processor = AdvancedImageProcessor()
            except Exception as e:
                log_error("Lỗi khởi tạo AdvancedImageProcessor", e)
                self.advanced_processor = None
        else:
            self.advanced_processor = None
        
        self.frame_count = 0
        
        # CPU Load Monitoring
        self.last_ocr_durations = []
        self.ocr_duration_window = 5
        self.high_load_threshold = 0.8  # 800ms = high load
        
        # Image quality thresholds
        self.high_quality_sharpness_threshold = 100.0
        self.high_quality_contrast_threshold = 40.0
        
        # OCR settings
        self.ocr_timeout = 5.0
        self.max_text_length = 600
        
        # Stats
        self.stats = {
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
                        
                        # CPU-only EasyOCR reader
                        self.reader = easyocr.Reader(
                            [easyocr_lang], 
                            gpu=False,
                            verbose=False,
                            download_enabled=True
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
        Main OCR method - TỐI ƯU cho GAME/CUTSCENE
        Hash chỉ vùng text (phần dưới) để detect thay đổi subtitle
        """
        self.stats['total_ocr_calls'] += 1
        
        now = time.monotonic()
        time_since_last_call = now - self.last_call_time
        
        # THROTTLE cơ bản - không quá 5 FPS
        if time_since_last_call < self.min_call_interval:
            self.stats['skipped_due_to_throttle'] += 1
            return self.last_result_text if self.last_result_text else ""
        
        # Convert to PIL nếu cần
        try:
            if isinstance(img, np.ndarray):
                img_pil = Image.fromarray(img)
            else:
                img_pil = img
        except Exception:
            return self.last_result_text if self.last_result_text else ""
        
        # SMART HASH: Chỉ hash vùng TEXT (1/3 dưới ảnh - nơi subtitle thường xuất hiện)
        # Cutscene thay đổi background nhưng subtitle ở vùng cố định
        try:
            import imagehash
            w, h = img_pil.size
            # Crop 1/3 dưới (vùng subtitle) - hoặc 40% nếu ảnh nhỏ
            crop_ratio = 0.35
            text_region = img_pil.crop((0, int(h * (1 - crop_ratio)), w, h))
            
            # Hash vùng text với size nhỏ hơn (nhanh hơn + nhạy hơn với text change)
            text_hash = str(imagehash.average_hash(text_region, hash_size=12))
            
            if text_hash == self.last_result_hash:
                # Vùng text giống hệt → skip OCR
                return self.last_result_text
            
            # Text region changed → update hash và chạy OCR
            self.last_result_hash = text_hash
        except ImportError:
            pass  # Không có imagehash → luôn chạy OCR
        except Exception:
            pass  # Lỗi → luôn chạy OCR để safe
        
        # Update call time
        self.last_call_time = now
        
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
        
        # Resize ảnh - aggressive resize for CPU mode to reduce load
        w, h = img_pil.size
        max_dim = max(w, h)
        
        # GIẢM max_size từ 800 xuống 600 để giảm CPU load
        # Game text thường to và rõ, không cần resolution cao
        max_size = 600  # Giảm từ 800, vẫn đủ cho game text
        
        if max_dim > max_size:
            scale = max_size / max_dim
            new_w, new_h = int(w * scale), int(h * scale)
            # Dùng BILINEAR thay LANCZOS - nhanh hơn nhiều, chất lượng đủ dùng
            img_pil = img_pil.resize((new_w, new_h), Image.Resampling.BILINEAR)
        
        # Multi-scale processing - TẮT khi CPU cao để tránh overload
        # Multi-scale chạy OCR 3 lần = 3x CPU load!
        if self.enable_multi_scale and not self._is_cpu_under_pressure():
            ocr_start_time = time.monotonic()
            best_result = None
            best_score = 0.0
            
            # Giảm từ 3 scales xuống 2 scales khi CPU trung bình
            # Khi CPU thấp mới dùng 3 scales
            if self._get_avg_ocr_duration() < 0.3:  # OCR nhanh, CPU thoải mái
                scales = [0.8, 1.0, 1.2]  # 3 scales, range hẹp hơn
            else:
                scales = [1.0]  # Chỉ 1 scale khi CPU trung bình
            
            for scale in scales:
                try:
                    if scale != 1.0:
                        scaled_w = int(img_pil.size[0] * scale)
                        scaled_h = int(img_pil.size[1] * scale)
                        if scaled_w < 10 or scaled_h < 10:
                            continue
                        scaled_img = img_pil.resize((scaled_w, scaled_h), Image.Resampling.BILINEAR)
                        img_array = np.array(scaled_img)
                    else:
                        img_array = np.array(img_pil)
                    
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
            
            # Track OCR duration
            ocr_duration = time.monotonic() - ocr_start_time
            self.last_ocr_durations.append(ocr_duration)
            if len(self.last_ocr_durations) > self.ocr_duration_window:
                self.last_ocr_durations.pop(0)
            
            # Update last call time
            self.last_call_time = time.monotonic()
            
            if best_result:
                best_result = ' '.join(best_result.split())
                best_result = best_result.strip()
                
                if len(best_result) > self.max_text_length:
                    best_result = best_result[:self.max_text_length] + "..."
                self.last_result_text = best_result
                self.last_successful_ocr_time = time.monotonic()  # Track successful OCR
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
            self.last_successful_ocr_time = time.monotonic()  # Track successful OCR
            
            # Update stability buffer
            self.text_stability_buffer.append(result_text)
            if len(self.text_stability_buffer) > self.stability_buffer_size:
                self.text_stability_buffer.pop(0)
            
            # Track OCR duration for CPU load detection
            ocr_duration = time.monotonic() - ocr_start_time
            self.last_ocr_durations.append(ocr_duration)
            if len(self.last_ocr_durations) > self.ocr_duration_window:
                self.last_ocr_durations.pop(0)
            
            # Update last call time
            self.last_call_time = time.monotonic()
            
            return result_text
        except Exception as e:
            log_error("Lỗi EasyOCR", e)
            return ""
    
    def _is_cpu_under_pressure(self):
        """Kiểm tra CPU có đang bận không (OCR > 800ms)"""
        if len(self.last_ocr_durations) >= 2:
            avg_duration = sum(self.last_ocr_durations[-2:]) / 2
            return avg_duration > self.high_load_threshold
        return False
    
    def _preprocess_for_easyocr(self, img):
        """
        Preprocessing cho EasyOCR với FAST PATH optimization + Game Mode
        
        GAME MODE FAST: CLAHE only - rất nhanh
        GAME MODE FULL: Color extraction → Noise detection → Adaptive denoising
        STANDARD MODE: Quality-based preprocessing (fast path vs full)
        
        Neural networks thích contrast cao, ít thích heavy morphology
        """
        try:
            # GAME MODE FAST: Chỉ CLAHE, rất nhanh
            if self.enable_game_mode and self.game_mode_fast:
                if len(img.shape) == 3:
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                else:
                    gray = img.copy()
                
                # CLAHE nhẹ cho EasyOCR
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                enhanced = clahe.apply(gray)
                return enhanced
            
            # GAME MODE FULL: Advanced preprocessing pipeline
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
            
            # AUTO-SCALE: Detect small text và upscale
            h, w = gray.shape[:2]
            if min(h, w) < 300:
                scale_factor = max(300.0 / h, 300.0 / w)
                new_w = int(w * scale_factor)
                new_h = int(h * scale_factor)
                gray = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
            
            # Check image quality
            quality_info = self._detect_image_quality(gray)
            
            # High quality image → minimal processing
            if not quality_info['needs_preprocessing']:
                clahe = cv2.createCLAHE(clipLimit=1.2, tileGridSize=(8, 8))
                enhanced = clahe.apply(gray)
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
                enhanced = cv2.morphologyEx(enhanced, cv2.MORPH_CLOSE, kernel, iterations=1)
                return enhanced
            
            # Low/Medium quality → full preprocessing
            if quality_info['quality'] == 'low':
                # Low quality: aggressive preprocessing
                if gray.shape[0] > 200 or gray.shape[1] > 200:
                    gray = cv2.bilateralFilter(gray, d=5, sigmaColor=50, sigmaSpace=50)
                
                clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
                enhanced = clahe.apply(gray)
                
                blurred = cv2.GaussianBlur(enhanced, (0, 0), 2.0)
                sharpened = cv2.addWeighted(enhanced, 1.5, blurred, -0.5, 0)
                
                # MORPHOLOGY: Kết nối fragmented text
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
        skip_rate = (self.stats['skipped_due_to_throttle'] / total_calls * 100) if total_calls > 0 else 0
        
        return {
            **self.stats,
            'skip_rate': skip_rate,
            'gpu_available': self.gpu_available
        }
    
    def cleanup(self):
        """Cleanup reader khi không dùng nữa"""
        if self.reader is not None:
            self.reader = None
