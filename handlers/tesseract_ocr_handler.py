"""
Tesseract OCR Handler - tối ưu cho free engine
"""
import cv2
import numpy as np
import pytesseract

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


class TesseractOCRHandler:
    """Handler cho Tesseract OCR với các kỹ thuật tối ưu"""
    
    def __init__(self, source_language='eng'):
        self.source_language = source_language
        self.cached_prep_mode = None
        self.cached_tess_params = None
        # Tắt mặc định để tránh chậm - có thể bật khi cần
        self.enable_text_region_detection = False  # Text region detection (tốn thời gian)
        self.enable_multi_scale = False  # Multi-scale processing (tốn thời gian)
        
    def set_source_language(self, lang):
        """Cập nhật source language và reset cache"""
        if lang != self.source_language:
            self.source_language = lang
            self.cached_prep_mode = None
            self.cached_tess_params = None
    
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
    
    def preprocess_for_ocr(self, img, mode='adaptive', block_size=41, c_value=-60):
        """
        Preprocess image cho OCR với các kỹ thuật nâng cao
        """
        if img is None or img.size == 0:
            return np.zeros((10, 10), dtype=np.uint8)
        
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()
        
        try:
            # CLAHE (Contrast Limited Adaptive Histogram Equalization) - cải thiện contrast
            # Đặc biệt hữu ích cho text trên nền phức tạp
            # Tối ưu: chỉ dùng CLAHE cho ảnh lớn (>500px) để tránh chậm
            h, w = gray.shape[:2]
            if max(h, w) > 500:
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                gray = clahe.apply(gray)
            
            if mode == 'adaptive':
                # Đảm bảo block_size là số lẻ
                if block_size % 2 == 0:
                    block_size += 1
                processed = cv2.adaptiveThreshold(
                    gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY_INV, block_size, c_value
                )
                
                # Morphological operations để tách text khỏi nền tốt hơn
                # Dilation để làm dày text, erosion để loại bỏ noise
                kernel = np.ones((2, 2), np.uint8)
                processed = cv2.morphologyEx(processed, cv2.MORPH_CLOSE, kernel, iterations=1)
                processed = cv2.morphologyEx(processed, cv2.MORPH_OPEN, kernel, iterations=1)
                
            elif mode == 'binary':
                _, processed = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
                # Apply morphological operations
                kernel = np.ones((2, 2), np.uint8)
                processed = cv2.morphologyEx(processed, cv2.MORPH_CLOSE, kernel, iterations=1)
            elif mode == 'binary_inv':
                _, processed = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
                kernel = np.ones((2, 2), np.uint8)
                processed = cv2.morphologyEx(processed, cv2.MORPH_CLOSE, kernel, iterations=1)
            elif mode == 'none':
                processed = gray
            else:
                processed = gray
            
            return processed
        except Exception as e:
            log_error(f"Preprocessing error (mode: {mode}): {e}", e)
            return gray
    
    def scale_for_ocr(self, img, scale_factor=1.0):
        """
        Scale ảnh với scale_factor tùy chỉnh (cho multi-scale processing)
        """
        if img is None:
            return img
        if isinstance(img, np.ndarray):
            if img.size == 0 or len(img.shape) < 2:
                return img
        h, w = img.shape[:2]
        
        # Minimum dimension check
        min_dim = 300
        if h < min_dim or w < min_dim:
            base_scale = max(min_dim / h, min_dim / w)
            final_scale = base_scale * scale_factor
        else:
            final_scale = scale_factor
        
        if abs(final_scale - 1.0) > 0.01:  # Only resize if scale is significantly different
            scaled = cv2.resize(img, None, fx=final_scale, fy=final_scale, interpolation=cv2.INTER_CUBIC)
            return scaled
        return img
    
    def detect_text_regions(self, img, min_area=100):
        """
        Phát hiện vùng có text sử dụng contour detection
        Returns: List of (x, y, w, h) regions
        """
        if img is None:
            return []
        
        # Check if image is empty (numpy array)
        if isinstance(img, np.ndarray):
            if img.size == 0 or len(img.shape) < 2:
                return []
        else:
            # PIL Image
            if img.size[0] == 0 or img.size[1] == 0:
                return []
        
        try:
            # Convert to grayscale if needed
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                gray = img.copy()
            
            # Apply threshold để tách text
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            
            # Morphological operations để kết nối text
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            dilated = cv2.dilate(binary, kernel, iterations=2)
            
            # Find contours
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Filter và merge regions
            regions = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                area = w * h
                if area >= min_area and w >= 10 and h >= 10:  # Minimum size
                    # Expand region slightly để capture full text
                    padding = 5
                    x = max(0, x - padding)
                    y = max(0, y - padding)
                    w = min(img.shape[1] - x, w + padding * 2)
                    h = min(img.shape[0] - y, h + padding * 2)
                    regions.append((x, y, w, h))
            
            # Merge overlapping regions
            if len(regions) > 1:
                merged_regions = []
                regions = sorted(regions, key=lambda r: (r[1], r[0]))  # Sort by y, then x
                
                for region in regions:
                    merged = False
                    for i, merged_region in enumerate(merged_regions):
                        mx, my, mw, mh = merged_region
                        rx, ry, rw, rh = region
                        
                        # Check overlap
                        if not (rx + rw < mx or rx > mx + mw or ry + rh < my or ry > my + mh):
                            # Merge regions
                            new_x = min(mx, rx)
                            new_y = min(my, ry)
                            new_w = max(mx + mw, rx + rw) - new_x
                            new_h = max(my + mh, ry + rh) - new_y
                            merged_regions[i] = (new_x, new_y, new_w, new_h)
                            merged = True
                            break
                    
                    if not merged:
                        merged_regions.append(region)
                
                return merged_regions
            
            return regions
        except Exception as e:
            log_error(f"Text region detection error: {e}", e)
            return []
    
    def ocr_region_with_confidence(self, img, region, confidence_threshold=50, scale_factor=1.0):
        """
        OCR region với confidence filtering và multi-scale support
        """
        x, y, w, h = region
        if len(img.shape) == 3:
            roi = img[y:y+h, x:x+w]
        else:
            roi = img[y:y+h, x:x+w]
        
        # Scale for OCR với scale_factor
        scaled_roi = self.scale_for_ocr(roi, scale_factor)
        
        try:
            # Dùng cached config
            config = self.cached_tess_params if self.cached_tess_params else self.get_tesseract_config('gaming')
            
            data = pytesseract.image_to_data(
                scaled_roi,
                lang=self.source_language,
                config=config,
                output_type=pytesseract.Output.DICT
            )
            
            filtered_text = []
            total_confidence = 0.0
            valid_count = 0
            
            for i in range(len(data['text'])):
                if not data['text'][i].strip():
                    continue
                conf = float(data['conf'][i])
                if conf >= confidence_threshold:
                    filtered_text.append(data['text'][i])
                    total_confidence += conf
                    valid_count += 1
            
            avg_confidence = total_confidence / valid_count if valid_count > 0 else 0.0
            result_text = ' '.join(filtered_text)
            
            return result_text, avg_confidence, valid_count
        except Exception as e:
            log_error(f"OCR error in region {region}: {e}", e)
            return "", 0.0, 0
    
    def recognize(self, img_cv_bgr, prep_mode='adaptive', block_size=41, c_value=-60, confidence_threshold=50):
        """
        Main OCR method với optimizations:
        - Text region detection
        - Multi-scale processing
        - Adaptive confidence thresholds
        """
        # Preprocess
        processed_cv_img = self.preprocess_for_ocr(img_cv_bgr, prep_mode, block_size, c_value)
        
        # Cache config
        if self.cached_prep_mode != prep_mode:
            self.cached_prep_mode = prep_mode
            # Map prep_mode to tesseract mode
            if prep_mode in ['gaming', 'document', 'subtitle']:
                tess_mode = prep_mode
            else:
                tess_mode = 'general'
            self.cached_tess_params = self.get_tesseract_config(tess_mode)
        
        # Full image OCR (text region detection tắt mặc định để tránh chậm)
        full_img_region = (0, 0, processed_cv_img.shape[1], processed_cv_img.shape[0])
        
        # Multi-scale chỉ khi được bật (tắt mặc định)
        if self.enable_multi_scale:
            best_result = None
            best_score = 0.0
            
            # Thử ít scales hơn để nhanh hơn: chỉ 1.0x và 1.2x
            for scale in [1.0, 1.2]:
                text, avg_conf, word_count = self.ocr_region_with_confidence(
                    processed_cv_img, full_img_region, confidence_threshold, scale_factor=scale
                )
                
                if text:
                    score = avg_conf * word_count
                    if score > best_score:
                        best_score = score
                        best_result = text
            
            return best_result if best_result else ""
        else:
            # Single scale - nhanh nhất
            text, _, _ = self.ocr_region_with_confidence(
                processed_cv_img, full_img_region, confidence_threshold, scale_factor=1.0
            )
            return text

