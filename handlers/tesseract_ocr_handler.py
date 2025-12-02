"""
Tesseract OCR Handler - tối ưu cho free engine
Tích hợp advanced image processing cho game AAA graphics
"""
import cv2
import numpy as np
import pytesseract
import sys
import os

try:
    from modules import log_error, log_debug
    from modules import AdvancedImageProcessor
    ADVANCED_PROCESSING_AVAILABLE = True
except ImportError:
    # Fallback if modules not available
    def log_error(msg, exception=None):
        pass
    def log_debug(msg):
        pass
    ADVANCED_PROCESSING_AVAILABLE = False


class TesseractOCRHandler:
    """Handler cho Tesseract OCR với các kỹ thuật tối ưu"""
    
    def __init__(self, source_language='eng', enable_multi_scale=False, enable_text_region_detection=False, enable_game_mode=False, game_mode_fast=True):
        """
        Args:
            source_language: Ngôn ngữ nguồn cho OCR
            enable_multi_scale: True = enable multi-scale processing (chính xác hơn nhưng chậm hơn)
            enable_text_region_detection: True = enable text region detection (tốn thời gian)
            enable_game_mode: True = enable advanced game graphics processing
            game_mode_fast: True = fast mode (CLAHE only), False = full pipeline
        """
        self.source_language = source_language
        self.cached_prep_mode = None
        self.cached_tess_params = None
        # Tất cả TẮT mặc định để tối ưu tốc độ
        self.enable_text_region_detection = enable_text_region_detection
        self.enable_multi_scale = enable_multi_scale
        self.enable_game_mode = enable_game_mode
        self.game_mode_fast = game_mode_fast
        
        # Advanced image processor cho game graphics (chỉ khi không dùng fast mode)
        if ADVANCED_PROCESSING_AVAILABLE and self.enable_game_mode and not self.game_mode_fast:
            try:
                self.advanced_processor = AdvancedImageProcessor()
            except Exception as e:
                log_error("Lỗi khởi tạo AdvancedImageProcessor", e)
                self.advanced_processor = None
        else:
            self.advanced_processor = None
        
    def set_source_language(self, lang):
        """Cập nhật source language và reset cache"""
        if lang != self.source_language:
            self.source_language = lang
            self.cached_prep_mode = None
            self.cached_tess_params = None
    
    def get_tesseract_config(self, mode='gaming'):
        """
        Lấy Tesseract config dựa trên mode
        PSM modes:
        - PSM 6: Assume a single uniform block of text (default, tốt cho dialogues)
        - PSM 7: Treat the image as a single text line (tốt cho subtitle 1 dòng)
        """
        if mode == 'subtitle':
            return '--psm 7 --oem 3 -c preserve_interword_spaces=1'
        elif mode == 'gaming':
            # Gaming: PSM 6 cho dialogue boxes
            return '--psm 6 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,!?\'":;()[]{}*~-_/<>\\$%&@+= '
        elif mode == 'document':
            return '--psm 3 --oem 3'
        else:
            return '--psm 6 --oem 3'
    
    def _detect_blur(self, img):
        """Detect blur level using Laplacian variance. Higher = sharper"""
        laplacian_var = cv2.Laplacian(img, cv2.CV_64F).var()
        return laplacian_var
    
    def _measure_contrast(self, img):
        """Measure contrast level (0-100)"""
        return img.std()
    
    def _select_preprocessing_strategy(self, img):
        """
        Intelligent preprocessing selection - chỉ xử lý khi cần thiết
        Returns: strategy name
        """
        blur_score = self._detect_blur(img)
        contrast = self._measure_contrast(img)
        
        # High quality image - minimal processing (FAST PATH)
        if blur_score > 100 and contrast > 40:
            return 'minimal'
        # Blurry image - need sharpening
        elif blur_score < 50:
            return 'sharpen'
        # Low contrast - need enhancement
        elif contrast < 25:
            return 'contrast'
        # Normal processing
        else:
            return 'standard'
    
    def preprocess_for_ocr(self, img, mode='adaptive', block_size=41, c_value=-60):
        """
        Simplified intelligent preprocessing - giảm ~30-40% processing time
        Tự động chọn strategy dựa trên image quality
        
        TỐI ƯU CHO GAME AAA:
        - Game mode: Color extraction → Noise detection → Advanced denoising
        - Standard mode: Legacy preprocessing
        """
        if img is None or img.size == 0:
            return np.zeros((10, 10), dtype=np.uint8)
        
        # GAME MODE FAST: Chỉ CLAHE + threshold, rất nhanh (~10-30ms)
        if self.enable_game_mode and self.game_mode_fast:
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                gray = img.copy()
            
            # CLAHE nhẹ để tăng contrast
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            
            # Otsu threshold - nhanh và hiệu quả
            _, processed = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            return processed
        
        # GAME MODE FULL: Advanced preprocessing pipeline (chậm hơn nhưng ổn định hơn)
        if self.enable_game_mode and self.advanced_processor:
            try:
                # Full game graphics processing: color extraction + noise detection + adaptive denoising
                processed, info = self.advanced_processor.process_for_game_ocr(img, mode='auto')
                
                # Apply final thresholding
                if mode == 'adaptive':
                    if block_size % 2 == 0:
                        block_size += 1
                    processed = cv2.adaptiveThreshold(
                        processed, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                        cv2.THRESH_BINARY_INV, block_size, c_value
                    )
                elif mode == 'binary':
                    _, processed = cv2.threshold(processed, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                
                return processed
                
            except Exception as e:
                log_error("Lỗi advanced preprocessing, fallback về standard", e)
                # Fallback về standard preprocessing
        
        # STANDARD MODE: Legacy preprocessing
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()
        
        try:
            h, w = gray.shape[:2]
            
            # Intelligent strategy selection
            strategy = self._select_preprocessing_strategy(gray)
            
            # FAST PATH: Minimal processing cho ảnh chất lượng cao
            if strategy == 'minimal':
                if mode == 'adaptive':
                    if block_size % 2 == 0:
                        block_size += 1
                    processed = cv2.adaptiveThreshold(
                        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                        cv2.THRESH_BINARY_INV, block_size, c_value
                    )
                else:
                    _, processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                return processed
            
            # Conditional processing dựa trên strategy
            if strategy == 'sharpen':
                # Chỉ sharpen khi blur
                gray = self._adaptive_sharpen(gray)
            elif strategy == 'contrast':
                # Chỉ CLAHE khi low contrast
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                gray = clahe.apply(gray)
            else:
                # Standard: light denoising + CLAHE
                if max(h, w) > 300:
                    gray = cv2.fastNlMeansDenoising(gray, h=5, templateWindowSize=5, searchWindowSize=15)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                gray = clahe.apply(gray)
            
            
            # Thresholding
            if mode == 'adaptive':
                if block_size % 2 == 0:
                    block_size += 1
                processed = cv2.adaptiveThreshold(
                    gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY_INV, block_size, c_value
                )
                
                # Conditional morphology - chỉ khi cần
                # Detect nếu text bị fragmented
                if self._needs_morphology(processed):
                    kernel_size = 2 if max(h, w) > 500 else 2
                    kernel = np.ones((kernel_size, kernel_size), np.uint8)
                    processed = cv2.morphologyEx(processed, cv2.MORPH_CLOSE, kernel, iterations=1)
                
            elif mode == 'binary':
                _, processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                
            elif mode == 'binary_inv':
                _, processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                
            elif mode == 'none':
                processed = gray
            else:
                processed = gray
            
            return processed

        except Exception as e:
            log_error(f"Preprocessing error (mode: {mode}): {e}", e)
            return gray
    
    def _needs_morphology(self, binary_img):
        """Check if morphology is needed - detect fragmented text"""
        # Count small contours - nhiều contour nhỏ = fragmented
        contours, _ = cv2.findContours(binary_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        small_contours = sum(1 for c in contours if cv2.contourArea(c) < 50)
        return small_contours > 10
    
    def _adaptive_sharpen(self, img):
        """
        Simplified sharpening - faster unsharp masking
        """
        try:
            blurred = cv2.GaussianBlur(img, (0, 0), 2)  # Reduced sigma
            sharpened = cv2.addWeighted(img, 1.3, blurred, -0.3, 0)  # Less aggressive
            return sharpened
        except Exception as e:
            log_error(f"Sharpening error: {e}", e)
            return img
    
    def _get_adaptive_kernel_size(self, height, width):
        """
        Tính kernel size tối ưu dựa trên kích thước ảnh
        Ảnh lớn -> kernel lớn hơn
        """
        max_dim = max(height, width)
        if max_dim > 1000:
            return 3
        elif max_dim > 500:
            return 2
        else:
            return 2
    
    def _estimate_background_complexity(self, img):
        """
        Đánh giá độ phức tạp của background
        Sử dụng Laplacian variance - high variance = phức tạp
        Returns: complexity score (0-100)
        """
        try:
            laplacian = cv2.Laplacian(img, cv2.CV_64F)
            variance = laplacian.var()
            # Normalize về 0-100
            complexity = min(100, variance / 10)
            return complexity
        except Exception as e:
            log_error(f"Complexity estimation error: {e}", e)
            return 50  # Default medium complexity
    
    def scale_for_ocr(self, img, scale_factor=1.0):
        """
        Scale ảnh với scale_factor tùy chỉnh (cho multi-scale processing)
        AUTO-SCALE: Detect small text và upscale tự động (30-40% improvement)
        """
        try:
            if img is None:
                return img
            if isinstance(img, np.ndarray):
                if img.size == 0 or len(img.shape) < 2:
                    return img
            h, w = img.shape[:2]
            
            # AUTO-SCALE: Minimum dimension check - critical cho small text
            # Text height < 16px rất khó OCR → upscale lên 300px minimum
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
        except Exception as e:
            log_error(f"Error scaling image for OCR (scale_factor={scale_factor})", e)
            return img
    
    def detect_text_regions(self, img, min_area=100):
        """
        Phát hiện vùng có text sử dụng contour detection nâng cao
        Tối ưu cho game graphics với nền phức tạp
        Returns: List of (x, y, w, h) regions sorted by position
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
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                gray = img.copy()
            
            # Bước 1: Denoising trước khi threshold
            # BILATERAL FILTER: Faster (5-10ms) và preserve edges tốt hơn cho game graphics
            gray = cv2.bilateralFilter(gray, d=5, sigmaColor=50, sigmaSpace=50)
            
            # Bước 2: CLAHE để tăng contrast
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
            
            # Bước 3: Otsu's threshold để tách text tốt hơn
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            
            # Bước 4: Morphological operations để kết nối text
            # Adaptive kernel dựa trên image size
            h, w = gray.shape
            kernel_size = 3 if max(h, w) > 500 else 2
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
            dilated = cv2.dilate(binary, kernel, iterations=2)
            
            # Bước 5: Find contours với RETR_EXTERNAL
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Bước 6: Filter và collect regions với criteria nâng cao
            regions = []
            img_area = h * w
            
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                area = w * h
                
                # Filter criteria nâng cao
                # 1. Minimum size
                if area < min_area or w < 10 or h < 10:
                    continue
                
                # 2. Aspect ratio check (text thường không quá vuông hoặc quá dài)
                aspect_ratio = w / h if h > 0 else 0
                if aspect_ratio < 0.1 or aspect_ratio > 50:
                    continue
                
                # 3. Not too large (không phải whole image)
                if area > img_area * 0.8:
                    continue
                
                # 4. Solidity check (text region không quá thưa thớt)
                hull = cv2.convexHull(contour)
                hull_area = cv2.contourArea(hull)
                if hull_area > 0:
                    solidity = area / hull_area
                    if solidity < 0.3:  # Quá thưa thớt, không phải text
                        continue
                
                # Expand region slightly để capture full text
                padding = 5
                x = max(0, x - padding)
                y = max(0, y - padding)
                w = min(img.shape[1] - x, w + padding * 2)
                h = min(img.shape[0] - y, h + padding * 2)
                regions.append((x, y, w, h))
            
            # Bước 7: Merge overlapping/nearby regions
            if len(regions) > 1:
                regions = self._merge_text_regions(regions, img.shape)
            
            # Bước 8: Sort by position (top to bottom, left to right)
            regions = sorted(regions, key=lambda r: (r[1], r[0]))
            
            return regions
        except Exception as e:
            log_error(f"Text region detection error: {e}", e)
            return []
    
    def _merge_text_regions(self, regions, img_shape):
        """
        Merge các text regions gần nhau hoặc overlap
        Thuật toán nâng cao với distance threshold
        """
        if not regions:
            return []
        
        merged = []
        regions = sorted(regions, key=lambda r: (r[1], r[0]))  # Sort by y, then x
        
        for region in regions:
            rx, ry, rw, rh = region
            merged_with_existing = False
            
            for i, merged_region in enumerate(merged):
                mx, my, mw, mh = merged_region
                
                # Kiểm tra overlap hoặc gần nhau
                # Distance threshold: regions cách nhau < 20px sẽ được merge
                distance_threshold = 20
                
                # Check horizontal distance
                h_distance = min(abs((rx + rw) - mx), abs((mx + mw) - rx))
                # Check vertical distance
                v_distance = min(abs((ry + rh) - my), abs((my + mh) - ry))
                
                # Overlap or nearby
                overlap = not (rx + rw < mx or rx > mx + mw or ry + rh < my or ry > my + mh)
                nearby = (overlap or (h_distance < distance_threshold and v_distance < distance_threshold))
                
                if nearby:
                    # Merge regions
                    new_x = min(mx, rx)
                    new_y = min(my, ry)
                    new_w = max(mx + mw, rx + rw) - new_x
                    new_h = max(my + mh, ry + rh) - new_y
                    merged[i] = (new_x, new_y, new_w, new_h)
                    merged_with_existing = True
                    break
            
            if not merged_with_existing:
                merged.append(region)
        
        return merged
    
    def ocr_region_with_confidence(self, img, region, confidence_threshold=50, scale_factor=1.0):
        """
        OCR region với adaptive confidence filtering và multi-scale support
        Confidence threshold được điều chỉnh dựa trên background complexity
        """
        try:
            x, y, w, h = region
            if len(img.shape) == 3:
                roi = img[y:y+h, x:x+w]
            else:
                roi = img[y:y+h, x:x+w]
            
            # Validate ROI
            if roi.size == 0 or roi.shape[0] == 0 or roi.shape[1] == 0:
                return "", 0.0, 0
            
            # Adaptive confidence threshold dựa trên background complexity
            complexity = self._estimate_background_complexity(roi)
            adjusted_threshold = self._adjust_confidence_threshold(confidence_threshold, complexity)
            
            # Scale for OCR với scale_factor
            scaled_roi = self.scale_for_ocr(roi, scale_factor)
            
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
                
                # Sử dụng adjusted threshold
                if conf >= adjusted_threshold:
                    filtered_text.append(data['text'][i])
                    total_confidence += conf
                    valid_count += 1
            
            avg_confidence = total_confidence / valid_count if valid_count > 0 else 0.0
            result_text = ' '.join(filtered_text)
            
            return result_text, avg_confidence, valid_count
        except Exception as e:
            log_error(f"OCR error in region {region}: {e}", e)
            return "", 0.0, 0
    
    def _adjust_confidence_threshold(self, base_threshold, complexity):
        """
        Điều chỉnh confidence threshold dựa trên background complexity
        Background phức tạp -> threshold thấp hơn (chấp nhận text có confidence thấp hơn)
        Background đơn giản -> threshold cao hơn (chỉ lấy text có confidence cao)
        """
        if complexity < 30:
            # Background đơn giản - tăng threshold 10%
            return min(90, base_threshold + 10)
        elif complexity > 70:
            # Background phức tạp - giảm threshold 15%
            return max(30, base_threshold - 15)
        else:
            # Medium complexity - giữ nguyên
            return base_threshold
    
    def recognize(self, img_cv_bgr, prep_mode='adaptive', block_size=41, c_value=-60, confidence_threshold=40):
        """
        Main OCR method với optimizations:
        - Intelligent multi-scale processing
        - Text region detection
        - Adaptive confidence thresholds (giảm xuống 40 để không bỏ sót text ngắn)
        """
        try:
            processed_cv_img = self.preprocess_for_ocr(img_cv_bgr, prep_mode, block_size, c_value)
            
            # Cache config
            if self.cached_prep_mode != prep_mode:
                self.cached_prep_mode = prep_mode
                if prep_mode in ['gaming', 'document', 'subtitle']:
                    tess_mode = prep_mode
                else:
                    tess_mode = 'general'
                self.cached_tess_params = self.get_tesseract_config(tess_mode)
            
            # Text region detection (nếu được bật)
            if self.enable_text_region_detection:
                regions = self.detect_text_regions(processed_cv_img, min_area=100)
                
                if regions:
                    all_texts = []
                    
                    for region in regions:
                        if self.enable_multi_scale:
                            optimal_scales = self._select_optimal_scales(processed_cv_img)
                            best_result = None
                            best_score = 0.0
                            
                            for scale in optimal_scales:
                                try:
                                    text, avg_conf, word_count = self.ocr_region_with_confidence(
                                        processed_cv_img, region, confidence_threshold, scale_factor=scale
                                    )
                                    
                                    if text:
                                        scale_weight = 1.2 if scale in [1.0, 1.2] else 1.0
                                        score = avg_conf * word_count * scale_weight
                                        
                                        if score > best_score:
                                            best_score = score
                                            best_result = text
                                except Exception as e:
                                    log_error(f"Error in multi-scale region OCR (scale={scale})", e)
                                    continue
                            
                            if best_result:
                                all_texts.append(best_result)
                        else:
                            text, _, _ = self.ocr_region_with_confidence(
                                processed_cv_img, region, confidence_threshold, scale_factor=1.0
                            )
                            if text:
                                all_texts.append(text)
                    
                    return ' '.join(all_texts)
                else:
                    # Không phát hiện được regions -> fallback to full image
                    pass
            
            # Full image OCR (default hoặc fallback)
            full_img_region = (0, 0, processed_cv_img.shape[1], processed_cv_img.shape[0])
            
            if self.enable_multi_scale:
                optimal_scales = self._select_optimal_scales(processed_cv_img)
                
                best_result = None
                best_score = 0.0
                
                for scale in optimal_scales:
                    try:
                        text, avg_conf, word_count = self.ocr_region_with_confidence(
                            processed_cv_img, full_img_region, confidence_threshold, scale_factor=scale
                        )
                        
                        if text:
                            scale_weight = 1.2 if scale in [1.0, 1.2] else 1.0
                            score = avg_conf * word_count * scale_weight
                            
                            if score > best_score:
                                best_score = score
                                best_result = text
                    except Exception as e:
                        log_error(f"Error in multi-scale OCR (scale={scale})", e)
                        continue
                
                return best_result if best_result else ""
            else:
                text, _, _ = self.ocr_region_with_confidence(
                    processed_cv_img, full_img_region, confidence_threshold, scale_factor=1.0
                )
                
                # Basic text normalization trước khi return
                if text:
                    import re
                    # Collapse multiple spaces
                    text = re.sub(r'\s+', ' ', text)
                    text = text.strip()
                
                return text if text else ""
        except Exception as e:
            log_error(f"Error in Tesseract OCR recognize (prep_mode={prep_mode})", e)
            return ""
    
    def _select_optimal_scales(self, img):
        """
        Chọn scales tối ưu dựa trên image analysis
        Tránh waste time trên scales không cần thiết
        """
        h, w = img.shape[:2]
        scales = []
        
        # Luôn có 1.0x baseline
        scales.append(1.0)
        
        # Phân tích sharpness/blur của ảnh
        sharpness = self._estimate_sharpness(img)
        
        # Nếu ảnh blur -> thử scale lớn hơn
        if sharpness < 100:  # Low sharpness = blur
            scales.append(1.2)
            if sharpness < 50:  # Very blur
                scales.append(1.5)
        
        # Nếu text nhỏ (based on image size) -> thử scale lớn hơn
        if max(h, w) < 400:
            if 1.2 not in scales:
                scales.append(1.2)
            scales.append(1.5)
        
        # Giới hạn số scales để tránh quá chậm
        return scales[:3]  # Max 3 scales
    
    def _estimate_sharpness(self, img):
        """
        Ước tính độ sắc nét của ảnh sử dụng Laplacian variance
        Higher value = sharper image
        """
        try:
            laplacian = cv2.Laplacian(img, cv2.CV_64F)
            variance = laplacian.var()
            return variance
        except Exception as e:
            log_error(f"Sharpness estimation error: {e}", e)
            return 100  # Default medium sharpness

