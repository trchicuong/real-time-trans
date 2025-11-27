"""
Test script chuyên sâu để so sánh độ chính xác và tính ổn định của EasyOCR giữa CPU và GPU mode.

Script này sẽ:
1. Test với nhiều loại ảnh khác nhau (rõ, mờ, nhiễu, game text style)
2. Test tính ổn định: chạy nhiều lần với cùng 1 ảnh, kiểm tra kết quả có giống nhau không
3. Test với ảnh thực tế từ game (nếu có)
4. Phân tích chi tiết sự khác biệt giữa CPU và GPU

Run: python test_easyocr_cpu_gpu_stability.py
"""
import os
import sys
import time
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import hashlib

# Add parent dir to path
sys.path.insert(0, os.path.dirname(__file__))

# Import handlers
try:
    from handlers.easyocr_handler import EasyOCRHandler
    print("✓ EasyOCR Handler imported")
except ImportError as e:
    print(f"✗ Failed to import EasyOCR Handler: {e}")
    sys.exit(1)

def create_test_image(text, width=500, height=120, quality='high', text_style='normal'):
    """
    Create test image with various quality levels and styles
    
    quality: 'high', 'medium', 'low'
    text_style: 'normal', 'shadow', 'outline', 'glow' (game-like effects)
    """
    # Create base image
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Try to load a proper font
    try:
        # Try multiple font paths
        font_paths = [
            "C:/Windows/Fonts/arial.ttf",
            "arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ]
        font = None
        for font_path in font_paths:
            if os.path.exists(font_path):
                font = ImageFont.truetype(font_path, 36)
                break
        
        if font is None:
            font = ImageFont.load_default()
    except:
        font = ImageFont.load_default()
    
    # Apply text style (game-like effects)
    if text_style == 'shadow':
        # Text with shadow (common in games)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        
        # Shadow
        draw.text((x+2, y+2), text, fill='gray', font=font)
        # Main text
        draw.text((x, y), text, fill='black', font=font)
    
    elif text_style == 'outline':
        # Text with outline (common in subtitles)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        
        # Outline (8-direction)
        for dx in [-2, 0, 2]:
            for dy in [-2, 0, 2]:
                if dx != 0 or dy != 0:
                    draw.text((x+dx, y+dy), text, fill='black', font=font)
        # Main text
        draw.text((x, y), text, fill='white', font=font)
    
    else:
        # Normal text
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        draw.text((x, y), text, fill='black', font=font)
    
    # Apply quality degradation
    if quality == 'low':
        # Add blur
        img = img.filter(ImageFilter.GaussianBlur(radius=1.5))
        # Add noise
        img_array = np.array(img)
        noise = np.random.randint(-30, 31, img_array.shape, dtype=np.int16)
        img_array = np.clip(img_array.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        img = Image.fromarray(img_array)
        # Reduce resolution then upscale (simulate low quality)
        small_size = (width // 2, height // 2)
        img = img.resize(small_size, Image.Resampling.BILINEAR)
        img = img.resize((width, height), Image.Resampling.BILINEAR)
    
    elif quality == 'medium':
        # Light blur
        img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
        # Light noise
        img_array = np.array(img)
        noise = np.random.randint(-10, 11, img_array.shape, dtype=np.int16)
        img_array = np.clip(img_array.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        img = Image.fromarray(img_array)
    
    # High quality: no degradation
    
    return np.array(img)

def compute_image_hash(img):
    """Compute a hash of the image for comparison"""
    return hashlib.md5(img.tobytes()).hexdigest()

def compute_text_similarity(text1, text2):
    """
    Compute similarity between two texts (0-100%)
    Simple character-level similarity
    """
    if text1 == text2:
        return 100.0
    
    if not text1 or not text2:
        return 0.0
    
    # Levenshtein distance (simplified)
    len1, len2 = len(text1), len(text2)
    if len1 == 0:
        return 0.0
    if len2 == 0:
        return 0.0
    
    # Create matrix
    matrix = [[0] * (len2 + 1) for _ in range(len1 + 1)]
    
    for i in range(len1 + 1):
        matrix[i][0] = i
    for j in range(len2 + 1):
        matrix[0][j] = j
    
    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            cost = 0 if text1[i-1] == text2[j-1] else 1
            matrix[i][j] = min(
                matrix[i-1][j] + 1,      # deletion
                matrix[i][j-1] + 1,      # insertion
                matrix[i-1][j-1] + cost  # substitution
            )
    
    distance = matrix[len1][len2]
    max_len = max(len1, len2)
    similarity = (1 - distance / max_len) * 100
    
    return similarity

def test_stability_deep(handler, img, num_runs=10, mode_name="Unknown"):
    """
    Test độ ổn định của OCR handler
    Chạy nhiều lần với cùng 1 ảnh, xem kết quả có giống nhau không
    """
    print(f"\n{'='*70}")
    print(f"Testing {mode_name} Mode - Stability Test (Deep)")
    print(f"{'='*70}")
    
    results = []
    times = []
    
    img_hash = compute_image_hash(img)
    print(f"Image hash: {img_hash[:16]}...")
    
    for i in range(num_runs):
        # Reset handler's cache để force OCR
        handler.last_result_hash = None
        handler.last_call_time = 0.0
        
        start = time.time()
        result = handler.recognize(img, confidence_threshold=0.3)
        elapsed = time.time() - start
        
        results.append(result)
        times.append(elapsed)
        
        print(f"  Run {i+1:2d}: '{result}' ({elapsed*1000:6.1f}ms)")
        
        # Sleep để đảm bảo không bị throttle
        time.sleep(1.5)
    
    # Analyze results
    print(f"\n{'='*70}")
    print(f"Analysis:")
    print(f"{'='*70}")
    
    unique_results = list(set(results))
    print(f"\nUnique results: {len(unique_results)}")
    
    if len(unique_results) == 1:
        print(f"✓ PERFECTLY STABLE - All {num_runs} runs returned identical results")
        print(f"  Result: '{unique_results[0]}'")
        stability_score = 100.0
    else:
        print(f"⚠ UNSTABLE - Got {len(unique_results)} different results:")
        
        # Count occurrences
        from collections import Counter
        counter = Counter(results)
        
        for idx, (result_text, count) in enumerate(counter.most_common(), 1):
            percentage = (count / num_runs) * 100
            print(f"  {idx}. '{result_text}' - {count}/{num_runs} times ({percentage:.1f}%)")
        
        # Calculate stability score (percentage of most common result)
        most_common_count = counter.most_common(1)[0][1]
        stability_score = (most_common_count / num_runs) * 100
        
        # Calculate average similarity between all results
        total_similarity = 0
        comparison_count = 0
        for i in range(len(results)):
            for j in range(i+1, len(results)):
                similarity = compute_text_similarity(results[i], results[j])
                total_similarity += similarity
                comparison_count += 1
        
        avg_similarity = total_similarity / comparison_count if comparison_count > 0 else 0
        print(f"\n  Average text similarity: {avg_similarity:.1f}%")
    
    # Timing stats
    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)
    
    print(f"\nTiming Statistics:")
    print(f"  Average: {avg_time*1000:6.1f}ms")
    print(f"  Min:     {min_time*1000:6.1f}ms")
    print(f"  Max:     {max_time*1000:6.1f}ms")
    print(f"  Range:   {(max_time-min_time)*1000:6.1f}ms")
    
    return {
        'unique_results': len(unique_results),
        'all_results': results,
        'stability_score': stability_score,
        'avg_time': avg_time,
        'min_time': min_time,
        'max_time': max_time
    }

def main():
    print("="*70)
    print("EasyOCR CPU vs GPU - Chuyên Sâu về Độ Chính Xác và Ổn Định")
    print("="*70)
    
    # Check GPU availability
    try:
        import torch
        gpu_available = torch.cuda.is_available()
        if gpu_available:
            gpu_name = torch.cuda.get_device_name(0)
            print(f"\n✓ GPU Available: {gpu_name}")
        else:
            print(f"\n✗ GPU Not Available")
            print("  Test sẽ chỉ chạy với CPU mode")
    except Exception as e:
        print(f"\n✗ Error checking GPU: {e}")
        gpu_available = False
    
    # Create test images with various conditions
    print("\n" + "="*70)
    print("1. Creating Test Images...")
    print("="*70)
    
    test_cases = [
        # (name, text, quality, text_style)
        ("High_Quality_Normal", "Hello World", "high", "normal"),
        ("High_Quality_Shadow", "Testing OCR", "high", "shadow"),
        ("High_Quality_Outline", "Game Subtitle", "high", "outline"),
        ("Medium_Quality", "Medium Quality Text", "medium", "normal"),
        ("Low_Quality", "Low Quality", "low", "normal"),
        ("Short_Text", "Hi!", "high", "normal"),
        ("Long_Text", "This is a longer text for testing stability", "high", "normal"),
        ("Numbers", "1234567890", "high", "normal"),
        ("Mixed", "Test 123 OK!", "high", "normal"),
    ]
    
    test_images = {}
    for name, text, quality, style in test_cases:
        img = create_test_image(text, quality=quality, text_style=style)
        test_images[name] = {
            'image': img,
            'expected_text': text,
            'quality': quality,
            'style': style
        }
        print(f"  ✓ Created: {name} (quality={quality}, style={style})")
    
    print(f"\n  Total: {len(test_images)} test images")
    
    # Test CPU mode
    print("\n" + "="*70)
    print("2. Testing CPU Mode...")
    print("="*70)
    
    print("\nInitializing CPU handler...")
    cpu_handler = EasyOCRHandler(source_language='eng', use_gpu=False)
    time.sleep(3)
    
    cpu_results = {}
    
    for test_name, test_data in test_images.items():
        print(f"\n{'='*70}")
        print(f"Test Case: {test_name}")
        print(f"Expected: '{test_data['expected_text']}'")
        print(f"Quality: {test_data['quality']}, Style: {test_data['style']}")
        print(f"{'='*70}")
        
        result = test_stability_deep(
            cpu_handler,
            test_data['image'],
            num_runs=5,
            mode_name="CPU"
        )
        
        cpu_results[test_name] = result
    
    # Cleanup CPU handler
    cpu_handler.cleanup()
    del cpu_handler
    time.sleep(2)
    
    # Test GPU mode (if available)
    if not gpu_available:
        print("\n" + "="*70)
        print("GPU không khả dụng - bỏ qua GPU tests")
        print("="*70)
        
        # Print CPU results summary
        print("\n" + "="*70)
        print("CPU Mode - Summary")
        print("="*70)
        
        print(f"\n{'Test Case':<30} {'Stability':<15} {'Avg Time'}")
        print("-" * 70)
        
        for test_name, result in cpu_results.items():
            stability = f"{result['stability_score']:.1f}%"
            avg_time = f"{result['avg_time']*1000:.0f}ms"
            print(f"{test_name:<30} {stability:<15} {avg_time}")
        
        print("\n" + "="*70)
        print("Test Completed!")
        print("="*70)
        return
    
    # Test GPU mode
    print("\n" + "="*70)
    print("3. Testing GPU Mode...")
    print("="*70)
    
    print("\nInitializing GPU handler...")
    gpu_handler = EasyOCRHandler(source_language='eng', use_gpu=True)
    time.sleep(3)
    
    gpu_results = {}
    
    for test_name, test_data in test_images.items():
        print(f"\n{'='*70}")
        print(f"Test Case: {test_name}")
        print(f"Expected: '{test_data['expected_text']}'")
        print(f"Quality: {test_data['quality']}, Style: {test_data['style']}")
        print(f"{'='*70}")
        
        result = test_stability_deep(
            gpu_handler,
            test_data['image'],
            num_runs=5,
            mode_name="GPU"
        )
        
        gpu_results[test_name] = result
    
    # Cleanup GPU handler
    gpu_handler.cleanup()
    del gpu_handler
    
    # Compare CPU vs GPU
    print("\n" + "="*70)
    print("4. CPU vs GPU Comparison")
    print("="*70)
    
    print(f"\n{'Test Case':<25} {'CPU Stability':<18} {'GPU Stability':<18} {'Winner'}")
    print("-" * 90)
    
    cpu_wins = 0
    gpu_wins = 0
    ties = 0
    
    for test_name in cpu_results.keys():
        cpu_stability = cpu_results[test_name]['stability_score']
        gpu_stability = gpu_results[test_name]['stability_score']
        
        cpu_str = f"{cpu_stability:.1f}%"
        gpu_str = f"{gpu_stability:.1f}%"
        
        diff = abs(cpu_stability - gpu_stability)
        
        if diff < 1.0:  # Less than 1% difference = tie
            winner = "Tie"
            ties += 1
        elif cpu_stability > gpu_stability:
            winner = f"CPU (+{diff:.1f}%)"
            cpu_wins += 1
        else:
            winner = f"GPU (+{diff:.1f}%)"
            gpu_wins += 1
        
        print(f"{test_name:<25} {cpu_str:<18} {gpu_str:<18} {winner}")
    
    print("-" * 90)
    print(f"\nOverall Stability: CPU wins {cpu_wins}, GPU wins {gpu_wins}, Ties {ties}")
    
    # Speed comparison
    print(f"\n{'Test Case':<25} {'CPU Avg Time':<18} {'GPU Avg Time':<18} {'Speedup'}")
    print("-" * 90)
    
    total_cpu_time = 0
    total_gpu_time = 0
    
    for test_name in cpu_results.keys():
        cpu_time = cpu_results[test_name]['avg_time']
        gpu_time = gpu_results[test_name]['avg_time']
        speedup = cpu_time / gpu_time if gpu_time > 0 else 0
        
        total_cpu_time += cpu_time
        total_gpu_time += gpu_time
        
        cpu_str = f"{cpu_time*1000:.0f}ms"
        gpu_str = f"{gpu_time*1000:.0f}ms"
        speedup_str = f"{speedup:.2f}x"
        
        print(f"{test_name:<25} {cpu_str:<18} {gpu_str:<18} {speedup_str}")
    
    avg_speedup = total_cpu_time / total_gpu_time if total_gpu_time > 0 else 0
    
    print("-" * 90)
    print(f"{'Average':<25} {total_cpu_time*1000/len(cpu_results):.0f}ms{'':<12} {total_gpu_time*1000/len(gpu_results):.0f}ms{'':<12} {avg_speedup:.2f}x")
    
    # Detailed analysis
    print("\n" + "="*70)
    print("5. Detailed Analysis & Recommendations")
    print("="*70)
    
    # Calculate overall stability scores
    cpu_avg_stability = sum(r['stability_score'] for r in cpu_results.values()) / len(cpu_results)
    gpu_avg_stability = sum(r['stability_score'] for r in gpu_results.values()) / len(gpu_results)
    
    print(f"\nOverall Stability Scores:")
    print(f"  CPU: {cpu_avg_stability:.1f}%")
    print(f"  GPU: {gpu_avg_stability:.1f}%")
    
    stability_diff = abs(cpu_avg_stability - gpu_avg_stability)
    
    print(f"\nConclusion:")
    
    if stability_diff < 5.0:
        print(f"  ✓ CPU và GPU có độ ổn định TƯƠNG ĐƯƠNG (chênh lệch < 5%)")
        print(f"  → GPU nhanh hơn {avg_speedup:.2f}x, khuyến nghị dùng GPU nếu có")
    elif cpu_avg_stability > gpu_avg_stability:
        print(f"  ⚠ CPU ổn định HƠN GPU ({stability_diff:.1f}% difference)")
        print(f"  → Nguyên nhân có thể:")
        print(f"     1. GPU driver issues")
        print(f"     2. CUDA/cuDNN version không tương thích")
        print(f"     3. GPU memory issues")
        print(f"     4. Floating point precision khác nhau (CPU=FP64, GPU=FP32)")
        print(f"  → Khuyến nghị: Dùng CPU nếu cần độ ổn định cao")
    else:
        print(f"  ✓ GPU ổn định HƠN CPU ({stability_diff:.1f}% difference)")
        print(f"  → GPU nhanh hơn {avg_speedup:.2f}x VÀ ổn định hơn")
        print(f"  → Khuyến nghị: Dùng GPU")
    
    print(f"\nSpeed Analysis:")
    print(f"  GPU nhanh hơn CPU trung bình: {avg_speedup:.2f}x")
    if avg_speedup < 1.5:
        print(f"  ⚠ Speedup thấp - GPU không phát huy hiệu quả")
        print(f"  → Nguyên nhân có thể: GPU yếu, overhead lớn, batch size nhỏ")
    elif avg_speedup > 3.0:
        print(f"  ✓ Speedup cao - GPU hoạt động hiệu quả")
    
    print("\n" + "="*70)
    print("Test Completed!")
    print("="*70)
    
    # Recommendations
    print("\nKhuyến Nghị Dựa Trên Kết Quả Test:")
    
    if cpu_avg_stability > gpu_avg_stability and stability_diff > 10:
        print("\n✓ Dùng CPU MODE:")
        print("  - Độ ổn định cao hơn rõ rệt")
        print("  - Kết quả dịch chính xác và nhất quán")
        print("  - Phù hợp với game có hội thoại dài và cần độ chính xác cao")
    elif gpu_avg_stability > cpu_avg_stability or stability_diff < 5:
        print("\n✓ Dùng GPU MODE:")
        print("  - Nhanh hơn đáng kể")
        print("  - Độ ổn định tương đương hoặc tốt hơn CPU")
        print("  - Giảm tải CPU, tốt cho gaming")
    else:
        print("\n✓ Tùy Trường Hợp:")
        print("  - CPU: Ưu tiên độ chính xác và ổn định")
        print("  - GPU: Ưu tiên tốc độ và hiệu năng")

if __name__ == "__main__":
    main()
