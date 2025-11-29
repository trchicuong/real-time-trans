"""
Advanced Image Processing cho Game Graphics
Tối ưu cho text extraction từ complex backgrounds, animated effects, semi-transparent dialog boxes
"""
import cv2
import numpy as np
from typing import Tuple, Optional, List
try:
    from .logger import log_error, log_debug
except ImportError:
    def log_error(msg, exception=None):
        pass
    def log_debug(msg):
        pass


class StrokeWidthTransform:
    """
    Stroke Width Transform (SWT) - Phát hiện text dựa trên consistent stroke width
    Rất hiệu quả với complex game backgrounds vì text có stroke width đồng nhất
    """
    
    def __init__(self):
        self.min_stroke_width = 2
        self.max_stroke_width = 50
    
    def apply(self, img: np.ndarray, dark_on_light: bool = False) -> np.ndarray:
        """
        Apply SWT để tạo text mask
        
        Args:
            img: Grayscale image
            dark_on_light: True nếu text tối trên nền sáng (uncommon trong games)
        
        Returns:
            SWT map (lower values = likely text regions)
        """
        try:
            if len(img.shape) == 3:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Edge detection với Canny
            edges = cv2.Canny(img, 50, 150)
            
            # Gradient direction (dùng Sobel)
            sobelx = cv2.Sobel(img, cv2.CV_64F, 1, 0, ksize=3)
            sobely = cv2.Sobel(img, cv2.CV_64F, 0, 1, ksize=3)
            
            # Gradient magnitude và direction
            gradient_mag = np.sqrt(sobelx**2 + sobely**2)
            gradient_dir = np.arctan2(sobely, sobelx)
            
            # Initialize SWT map với giá trị lớn
            h, w = img.shape
            swt_map = np.full((h, w), np.inf, dtype=np.float64)
            
            # Ray casting từ mỗi edge pixel
            edge_pixels = np.argwhere(edges > 0)
            
            for y, x in edge_pixels:
                # Ray direction dựa trên gradient
                if dark_on_light:
                    ray_dir = gradient_dir[y, x]
                else:
                    ray_dir = gradient_dir[y, x] + np.pi
                
                dx = np.cos(ray_dir)
                dy = np.sin(ray_dir)
                
                # Ray casting
                ray_x, ray_y = x, y
                ray_pixels = [(y, x)]
                
                for step in range(1, self.max_stroke_width):
                    ray_x += dx
                    ray_y += dy
                    
                    rx = int(round(ray_x))
                    ry = int(round(ray_y))
                    
                    # Out of bounds
                    if rx < 0 or rx >= w or ry < 0 or ry >= h:
                        break
                    
                    ray_pixels.append((ry, rx))
                    
                    # Tìm edge pixel đối diện
                    if edges[ry, rx] > 0:
                        # Check gradient direction tương tự (opposite)
                        opposite_dir = gradient_dir[ry, rx]
                        angle_diff = abs(opposite_dir - ray_dir)
                        
                        # Normalize angle diff
                        if angle_diff > np.pi:
                            angle_diff = 2 * np.pi - angle_diff
                        
                        # Nếu gradient ngược chiều (text stroke)
                        if angle_diff > np.pi / 2:
                            stroke_width = len(ray_pixels)
                            
                            if self.min_stroke_width <= stroke_width <= self.max_stroke_width:
                                # Cập nhật SWT cho tất cả pixels trên ray
                                for py, px in ray_pixels:
                                    swt_map[py, px] = min(swt_map[py, px], stroke_width)
                        break
            
            # Replace inf với max value
            swt_map[swt_map == np.inf] = self.max_stroke_width * 2
            
            return swt_map.astype(np.float32)
            
        except Exception as e:
            log_error("Error in SWT apply", e)
            # Fallback: return zeros
            return np.zeros_like(img, dtype=np.float32)
    
    def create_text_mask(self, swt_map: np.ndarray, threshold_percentile: int = 30) -> np.ndarray:
        """
        Tạo binary mask từ SWT map
        
        Args:
            swt_map: SWT map từ apply()
            threshold_percentile: Percentile để threshold (lower = more text detected)
        
        Returns:
            Binary mask (255 = text, 0 = background)
        """
        try:
            # Tính threshold dựa trên percentile
            valid_values = swt_map[swt_map < self.max_stroke_width * 2]
            
            if len(valid_values) == 0:
                return np.zeros_like(swt_map, dtype=np.uint8)
            
            threshold = np.percentile(valid_values, threshold_percentile)
            
            # Create mask
            mask = np.zeros_like(swt_map, dtype=np.uint8)
            mask[swt_map <= threshold] = 255
            
            # Morphology để connect components
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
            
            return mask
            
        except Exception as e:
            log_error("Error creating text mask from SWT", e)
            return np.zeros_like(swt_map, dtype=np.uint8)


class ColorTextExtractor:
    """
    Color-based text extraction cho game subtitles
    Phát hiện text theo màu dominant (white, yellow, cyan...) trước khi grayscale
    """
    
    def __init__(self):
        # Define HSV ranges cho màu text phổ biến trong game
        self.color_ranges = {
            'white': [(0, 0, 200), (180, 30, 255)],      # White text (most common)
            'yellow': [(20, 100, 100), (30, 255, 255)],  # Yellow subtitles
            'cyan': [(85, 100, 100), (95, 255, 255)],    # Cyan text
            'light_gray': [(0, 0, 150), (180, 40, 220)], # Light gray text
        }
    
    def extract_by_color(self, img: np.ndarray, colors: Optional[List[str]] = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        Extract text regions dựa trên màu
        
        Args:
            img: BGR image
            colors: List màu muốn detect (None = detect all)
        
        Returns:
            (extracted_img, mask) - Ảnh đã extract và mask
        """
        try:
            if len(img.shape) != 3:
                return img, np.ones(img.shape[:2], dtype=np.uint8) * 255
            
            # Convert sang HSV
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            
            # Combine masks từ các màu
            combined_mask = np.zeros(img.shape[:2], dtype=np.uint8)
            
            colors_to_use = colors if colors else list(self.color_ranges.keys())
            
            for color_name in colors_to_use:
                if color_name not in self.color_ranges:
                    continue
                
                lower, upper = self.color_ranges[color_name]
                mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
                combined_mask = cv2.bitwise_or(combined_mask, mask)
            
            # Morphology để clean mask
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel, iterations=1)
            
            # Apply mask lên ảnh gốc
            result = cv2.bitwise_and(img, img, mask=combined_mask)
            
            return result, combined_mask
            
        except Exception as e:
            log_error("Error in color-based text extraction", e)
            return img, np.ones(img.shape[:2], dtype=np.uint8) * 255
    
    def extract_dominant_text_color(self, img: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Tự động detect màu text dominant và extract
        
        Args:
            img: BGR image
        
        Returns:
            (extracted_img, mask)
        """
        try:
            if len(img.shape) != 3:
                return img, np.ones(img.shape[:2], dtype=np.uint8) * 255
            
            # Thử từng màu và tính coverage
            best_mask = None
            best_coverage = 0
            
            for color_name, (lower, upper) in self.color_ranges.items():
                hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
                
                coverage = np.count_nonzero(mask) / mask.size
                
                if coverage > best_coverage:
                    best_coverage = coverage
                    best_mask = mask
            
            if best_mask is None:
                return img, np.ones(img.shape[:2], dtype=np.uint8) * 255
            
            # Apply best mask
            result = cv2.bitwise_and(img, img, mask=best_mask)
            
            return result, best_mask
            
        except Exception as e:
            log_error("Error extracting dominant text color", e)
            return img, np.ones(img.shape[:2], dtype=np.uint8) * 255


class BackgroundNoiseDetector:
    """
    Background noise detection dựa trên frequency analysis
    Detect high-frequency noise từ animated backgrounds, particles, effects
    """
    
    def __init__(self):
        self.noise_threshold = 45.0  # Threshold cho high freq noise
    
    def detect_noise_level(self, img: np.ndarray) -> float:
        """
        Detect noise level dựa trên high frequency components (FFT)
        
        Args:
            img: Grayscale image
        
        Returns:
            Noise score (0-100, higher = more noise)
        """
        try:
            if len(img.shape) == 3:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Fourier transform
            f = np.fft.fft2(img)
            fshift = np.fft.fftshift(f)
            
            # Magnitude spectrum (log scale)
            magnitude = 20 * np.log(np.abs(fshift) + 1)
            
            h, w = img.shape
            
            # Create mask để exclude center (low freq - main content)
            center_mask = np.zeros((h, w), np.uint8)
            center_radius = min(h, w) // 6  # Center 1/6 là low freq
            cv2.circle(center_mask, (w//2, h//2), center_radius, 1, -1)
            
            # High freq region (outside center)
            high_freq_mask = 1 - center_mask
            
            # Tính noise score từ high freq magnitude
            noise_score = magnitude[high_freq_mask == 1].mean()
            
            # Normalize về 0-100
            noise_score = min(100, max(0, (noise_score - 30) * 2))
            
            return noise_score
            
        except Exception as e:
            log_error("Error detecting noise level", e)
            return 0.0
    
    def needs_aggressive_denoising(self, img: np.ndarray) -> bool:
        """
        Kiểm tra có cần aggressive denoising không
        
        Args:
            img: Grayscale image
        
        Returns:
            True nếu cần aggressive denoising
        """
        noise_score = self.detect_noise_level(img)
        return noise_score > self.noise_threshold
    
    def adaptive_denoise(self, img: np.ndarray, noise_level: Optional[float] = None) -> np.ndarray:
        """
        Adaptive denoising dựa trên noise level
        
        Args:
            img: Image to denoise
            noise_level: Pre-computed noise level (None = auto detect)
        
        Returns:
            Denoised image
        """
        try:
            if noise_level is None:
                noise_level = self.detect_noise_level(img)
            
            if noise_level < 30:
                # Low noise - minimal denoising
                return cv2.fastNlMeansDenoising(img, h=3, templateWindowSize=5, searchWindowSize=11)
            elif noise_level < 60:
                # Medium noise - standard denoising
                return cv2.fastNlMeansDenoising(img, h=7, templateWindowSize=7, searchWindowSize=21)
            else:
                # High noise - aggressive denoising
                # Bilateral filter (preserve edges better)
                denoised = cv2.bilateralFilter(img, 9, 75, 75)
                # + Non-local means
                denoised = cv2.fastNlMeansDenoising(denoised, h=10, templateWindowSize=7, searchWindowSize=21)
                return denoised
            
        except Exception as e:
            log_error("Error in adaptive denoising", e)
            return img


class AdvancedImageProcessor:
    """
    Main processor kết hợp tất cả techniques
    """
    
    def __init__(self):
        self.swt = StrokeWidthTransform()
        self.color_extractor = ColorTextExtractor()
        self.noise_detector = BackgroundNoiseDetector()
    
    def process_for_game_ocr(self, img: np.ndarray, mode: str = 'auto') -> Tuple[np.ndarray, dict]:
        """
        Full processing pipeline cho game graphics OCR
        
        Args:
            img: Input image (BGR hoặc grayscale)
            mode: 'auto', 'color_first', 'swt_first', 'aggressive'
        
        Returns:
            (processed_img, info_dict)
        """
        try:
            info = {
                'noise_level': 0.0,
                'color_coverage': 0.0,
                'swt_applied': False,
                'aggressive_denoise': False
            }
            
            # Convert sang BGR nếu cần
            if len(img.shape) == 2:
                img_bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            else:
                img_bgr = img.copy()
            
            # Step 1: Color-based extraction (nếu có màu)
            color_extracted, color_mask = self.color_extractor.extract_dominant_text_color(img_bgr)
            color_coverage = np.count_nonzero(color_mask) / color_mask.size
            info['color_coverage'] = color_coverage
            
            # Chọn ảnh tốt hơn (color extracted vs original)
            if color_coverage > 0.05:  # Có ít nhất 5% text pixels
                working_img = color_extracted
            else:
                working_img = img_bgr
            
            # Convert sang grayscale
            if len(working_img.shape) == 3:
                gray = cv2.cvtColor(working_img, cv2.COLOR_BGR2GRAY)
            else:
                gray = working_img
            
            # Step 2: Noise detection
            noise_level = self.noise_detector.detect_noise_level(gray)
            info['noise_level'] = noise_level
            
            # Step 3: Adaptive denoising nếu cần
            if noise_level > 40:
                gray = self.noise_detector.adaptive_denoise(gray, noise_level)
                info['aggressive_denoise'] = True
            
            # Step 4: SWT-based enhancement (optional, chỉ khi mode aggressive)
            if mode == 'aggressive' or mode == 'swt_first':
                swt_map = self.swt.apply(gray, dark_on_light=False)
                swt_mask = self.swt.create_text_mask(swt_map, threshold_percentile=30)
                
                # Apply SWT mask
                gray = cv2.bitwise_and(gray, gray, mask=swt_mask)
                info['swt_applied'] = True
            
            return gray, info
            
        except Exception as e:
            log_error("Error in game OCR processing pipeline", e)
            # Fallback: return grayscale
            if len(img.shape) == 3:
                return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), info
            return img, info
