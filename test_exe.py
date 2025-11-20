"""
Simple test script to check if all dependencies are available
Run this before building the exe to ensure everything works
"""
import sys
import io

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def test_imports():
    """Test if all required modules can be imported"""
    print("Testing imports...")
    errors = []
    
    try:
        import tkinter
        print("✓ tkinter")
    except ImportError as e:
        errors.append(f"✗ tkinter: {e}")
    
    try:
        from PIL import Image
        print("✓ PIL (Pillow)")
    except ImportError as e:
        errors.append(f"✗ PIL: {e}")
    
    try:
        import mss
        print("✓ mss")
    except ImportError as e:
        errors.append(f"✗ mss: {e}")
    
    try:
        import numpy
        print("✓ numpy")
    except ImportError as e:
        errors.append(f"✗ numpy: {e}")
    
    try:
        import pytesseract
        print("✓ pytesseract")
    except ImportError as e:
        errors.append(f"✗ pytesseract: {e}")
    
    try:
        from deep_translator import GoogleTranslator
        print("✓ deep_translator")
    except ImportError as e:
        errors.append(f"✗ deep_translator: {e}")
    
    try:
        import cv2
        print("✓ cv2 (OpenCV)")
    except ImportError as e:
        errors.append(f"✗ cv2: {e}")
    
    # Test optional dependencies
    print("\nTesting optional dependencies...")
    EASYOCR_AVAILABLE = False
    try:
        import easyocr
        EASYOCR_AVAILABLE = True
        print("✓ easyocr (optional)")
    except ImportError:
        print("⚠ easyocr not installed (optional)")
    
    try:
        import deepl
        print("✓ deepl (optional)")
    except ImportError:
        print("⚠ deepl not installed (optional)")
    
    try:
        import chardet
        print("✓ chardet (optional - for encoding detection)")
    except ImportError:
        print("⚠ chardet not installed (optional - encoding detection may be limited)")
    
    try:
        import torch
        print(f"✓ torch (optional - PyTorch version: {torch.__version__})")
        if torch.cuda.is_available():
            print(f"  ✓ CUDA available: {torch.cuda.get_device_name(0)}")
        else:
            print("  ⚠ CUDA not available (CPU-only mode)")
    except ImportError:
        print("⚠ torch not installed (optional - EasyOCR will use CPU mode)")
    
    # Test handlers package
    print("\nTesting handlers package...")
    try:
        from handlers import TesseractOCRHandler, EasyOCRHandler, TranslationCacheManager
        print("✓ handlers package")
        print("  ✓ TesseractOCRHandler")
        print("  ✓ EasyOCRHandler")
        print("  ✓ TranslationCacheManager")
        
        # Test EasyOCRHandler với các GPU options
        if EASYOCR_AVAILABLE:
            print("\n  Testing EasyOCRHandler GPU options...")
            try:
                # Test auto-detect (None)
                handler_auto = EasyOCRHandler(source_language='eng', use_gpu=None)
                print(f"    ✓ Auto-detect mode: GPU={handler_auto.gpu_available}")
                
                # Test CPU mode
                handler_cpu = EasyOCRHandler(source_language='eng', use_gpu=False)
                print(f"    ✓ CPU mode: GPU={handler_cpu.gpu_available}")
                
                # Test GPU mode (nếu có GPU)
                try:
                    import torch
                    if torch.cuda.is_available():
                        handler_gpu = EasyOCRHandler(source_language='eng', use_gpu=True)
                        print(f"    ✓ GPU mode: GPU={handler_gpu.gpu_available}")
                    else:
                        print("    ⚠ GPU mode test skipped (no GPU available)")
                except ImportError:
                    print("    ⚠ GPU mode test skipped (torch not available)")
            except Exception as e:
                print(f"    ⚠ EasyOCRHandler test error: {e}")
    except ImportError as e:
        print(f"⚠ handlers package not available: {e}")
        print("  (This is OK if running from source, but needed for exe)")
    
    if errors:
        print("\nErrors found:")
        for error in errors:
            print(f"  {error}")
        return False
    else:
        print("\n✓ All required imports successful!")
        return True

def test_tesseract():
    """Test if Tesseract is accessible"""
    print("\nTesting Tesseract OCR...")
    try:
        import pytesseract
        import shutil
        
        # Check if tesseract is in PATH
        tesseract_cmd = shutil.which('tesseract')
        if tesseract_cmd:
            print(f"✓ Tesseract found in PATH: {tesseract_cmd}")
        else:
            print("⚠ Tesseract not found in PATH")
            print("  Common locations:")
            print("    C:\\Program Files\\Tesseract-OCR\\tesseract.exe")
            print("    C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe")
        
        # Try to get version
        try:
            version = pytesseract.get_tesseract_version()
            print(f"✓ Tesseract version: {version}")
            return True
        except Exception as e:
            print(f"✗ Cannot access Tesseract: {e}")
            print("  You may need to set the path manually in the application")
            return False
    except Exception as e:
        print(f"✗ Error testing Tesseract: {e}")
        return False

def main():
    print("=" * 60)
    print("Real-Time Screen Translator - Dependency Check")
    print("=" * 60)
    print()
    
    imports_ok = test_imports()
    tesseract_ok = test_tesseract()
    
    print("\n" + "=" * 60)
    if imports_ok and tesseract_ok:
        print("✓ All checks passed! Ready to build exe.")
        return 0
    else:
        print("⚠ Some checks failed. Please fix issues before building exe.")
        print("\nTo fix:")
        if not imports_ok:
            print("  1. Install missing packages: pip install -r requirements.txt")
        if not tesseract_ok:
            print("  2. Install Tesseract OCR from: https://github.com/UB-Mannheim/tesseract/wiki")
            print("     Or set the path manually in the application after building.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

