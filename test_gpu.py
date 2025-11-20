"""
Script để test GPU detection và EasyOCR GPU mode
Chạy: python test_gpu.py
"""
import sys
import os

# Fix encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

print("=" * 60)
print("GPU Detection Test for EasyOCR")
print("=" * 60)

# Test 1: PyTorch installation
print("\n1. Testing PyTorch installation...")
try:
    import torch
    print(f"   ✓ PyTorch version: {torch.__version__}")
except ImportError:
    print("   ✗ PyTorch not installed")
    print("   → Install: pip install torch")
    sys.exit(1)

# Test 2: CUDA availability
print("\n2. Testing CUDA availability...")
try:
    cuda_available = torch.cuda.is_available()
    print(f"   torch.cuda.is_available() = {cuda_available}")
    
    if cuda_available:
        print(f"   ✓ CUDA is available!")
        cuda_version = getattr(torch.version, 'cuda', 'Unknown')
        print(f"   CUDA version: {cuda_version}")
        device_count = torch.cuda.device_count()
        print(f"   GPU device count: {device_count}")
        
        for i in range(device_count):
            gpu_name = torch.cuda.get_device_name(i)
            props = torch.cuda.get_device_properties(i)
            print(f"   GPU {i}: {gpu_name}")
            print(f"      Memory: {props.total_memory / 1024**3:.2f} GB")
    else:
        cuda_version = getattr(torch.version, 'cuda', None)
        if cuda_version:
            print(f"   ✗ CUDA version: {cuda_version}, but torch.cuda.is_available() = False")
            print("   → Possible issues:")
            print("     - CUDA drivers not installed")
            print("     - CUDA version mismatch")
            print("     - GPU not detected by system")
        else:
            print("   ✗ PyTorch installed without CUDA support (CPU-only)")
            print("   → Install PyTorch with CUDA:")
            print("     Option 1 (CUDA 12.1 - recommended for CUDA 13.0):")
            print("     pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")
            print("     ")
            print("     Option 2 (CUDA 11.8 - more stable):")
            print("     pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118")
            print("     ")
            print("     Or run: install_pytorch_cuda.bat")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Test 3: EasyOCR GPU mode
print("\n3. Testing EasyOCR GPU mode...")
try:
    import easyocr
    print("   ✓ EasyOCR installed")
    
    # Test GPU detection
    try:
        import torch
        use_gpu = torch.cuda.is_available()
        print(f"   Will create EasyOCR Reader with gpu={use_gpu}")
        
        if use_gpu:
            print("   Creating EasyOCR Reader with GPU...")
            reader = easyocr.Reader(['en'], gpu=True, verbose=True)
            print("   ✓ EasyOCR Reader created with GPU mode")
            
            # Test a simple image
            import numpy as np
            test_img = np.ones((100, 200, 3), dtype=np.uint8) * 255
            print("   Testing OCR on simple image...")
            results = reader.readtext(test_img)
            print(f"   ✓ OCR test completed (results: {len(results)})")
        else:
            print("   ⚠ GPU not available, will use CPU mode")
            print("   Creating EasyOCR Reader with CPU...")
            reader = easyocr.Reader(['en'], gpu=False, verbose=True)
            print("   ✓ EasyOCR Reader created with CPU mode")
    except Exception as e:
        print(f"   ✗ Error creating EasyOCR Reader: {e}")
        import traceback
        traceback.print_exc()
        
except ImportError:
    print("   ✗ EasyOCR not installed")
    print("   → Install: pip install easyocr")

print("\n" + "=" * 60)
print("Test completed!")
print("=" * 60)

