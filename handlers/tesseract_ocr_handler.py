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
        Preprocess image cho OCR
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
    
    def scale_for_ocr(self, img):
        """
        Scale ảnh nhỏ lên nếu < 300px
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
    
    def ocr_region_with_confidence(self, img, region, confidence_threshold=50):
        """
        OCR region với confidence filtering
        """
        x, y, w, h = region
        if len(img.shape) == 3:
            roi = img[y:y+h, x:x+w]
        else:
            roi = img[y:y+h, x:x+w]
        
        # Scale for OCR
        scaled_roi = self.scale_for_ocr(roi)
        
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
            for i in range(len(data['text'])):
                if not data['text'][i].strip():
                    continue
                if float(data['conf'][i]) >= confidence_threshold:
                    filtered_text.append(data['text'][i])
            
            return ' '.join(filtered_text)
        except Exception as e:
            log_error(f"OCR error in region {region}: {e}", e)
            return ""
    
    def recognize(self, img_cv_bgr, prep_mode='adaptive', block_size=41, c_value=-60, confidence_threshold=50):
        """
        Main OCR method
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
        
        # OCR với full image region
        full_img_region = (0, 0, processed_cv_img.shape[1], processed_cv_img.shape[0])
        ocr_raw_text = self.ocr_region_with_confidence(processed_cv_img, full_img_region, confidence_threshold)
        
        return ocr_raw_text

