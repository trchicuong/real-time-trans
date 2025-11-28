"""
Dependency test script for Real-Time Screen Translator
Run this before building the exe to ensure all dependencies are available
CPU-only mode optimized for real-time gaming translation
"""
import sys
import io

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def test_imports():
    """Test if all required modules can be imported"""
    print("=" * 60)
    print("Testing Core Dependencies")
    print("=" * 60)
    errors = []
    
    # Core dependencies
    core_deps = [
        ('tkinter', 'tkinter'),
        ('PIL', 'PIL (Pillow)'),
        ('mss', 'mss'),
        ('numpy', 'numpy'),
        ('pytesseract', 'pytesseract'),
        ('deep_translator', 'deep_translator'),
        ('cv2', 'cv2 (OpenCV)'),
        ('imagehash', 'imagehash'),
        ('pynput', 'pynput'),
    ]
    
    for module_name, display_name in core_deps:
        try:
            __import__(module_name)
            print(f"✓ {display_name}")
        except ImportError as e:
            errors.append(f"✗ {display_name}: {e}")
            print(f"✗ {display_name}: MISSING")
    
    # Optional dependencies
    print("\n" + "=" * 60)
    print("Testing Optional Dependencies")
    print("=" * 60)
    
    EASYOCR_AVAILABLE = False
    try:
        import easyocr
        EASYOCR_AVAILABLE = True
        print("✓ easyocr (optional - for accurate OCR)")
    except ImportError:
        print("⚠ easyocr not installed (optional - will use Tesseract only)")
    
    try:
        import deepl
        print("✓ deepl (optional - for DeepL API)")
    except ImportError:
        print("⚠ deepl not installed (optional - will use Google Translate only)")
    
    try:
        import chardet
        print("✓ chardet (optional - encoding detection)")
    except ImportError:
        print("⚠ chardet not installed (optional)")
    
    try:
        import torch
        print(f"✓ torch (optional - PyTorch {torch.__version__})")
        print("  → CPU-only mode (optimal for gaming)")
    except ImportError:
        print("⚠ torch not installed (optional - EasyOCR won't work without it)")
    
    # Test handlers package
    print("\n" + "=" * 60)
    print("Testing Handlers Package")
    print("=" * 60)
    
    try:
        from handlers import TesseractOCRHandler, EasyOCRHandler
        print("✓ handlers package")
        print("  ✓ TesseractOCRHandler")
        print("  ✓ EasyOCRHandler")
        
        # Test EasyOCRHandler CPU-only mode
        if EASYOCR_AVAILABLE:
            try:
                handler_cpu = EasyOCRHandler(source_language='eng', use_gpu=False)
                print(f"  ✓ CPU-only mode initialized: GPU={handler_cpu.gpu_available}")
            except Exception as e:
                print(f"  ⚠ EasyOCRHandler error: {e}")
    except ImportError as e:
        print(f"⚠ handlers package error: {e}")
    
    # Test modules package
    print("\n" + "=" * 60)
    print("Testing Modules Package")
    print("=" * 60)
    
    try:
        from modules import (
            log_error, log_debug,
            NetworkCircuitBreaker,
            post_process_ocr_text_general,
            translate_batch_google,
            DeepLContextManager,
            AdvancedDeduplicator,
            HotkeyManager
        )
        print("✓ modules package")
        print("  ✓ logger")
        print("  ✓ circuit_breaker")
        print("  ✓ ocr_postprocessing")
        print("  ✓ batch_translation")
        print("  ✓ deepl_context")
        print("  ✓ advanced_deduplication")
        print("  ✓ hotkey_manager")
    except ImportError as e:
        errors.append(f"✗ modules package: {e}")
        print(f"✗ modules package: {e}")
    
    return len(errors) == 0, errors

def test_tesseract():
    """Test if Tesseract is accessible"""
    print("\n" + "=" * 60)
    print("Testing Tesseract OCR")
    print("=" * 60)
    
    try:
        import pytesseract
        import shutil
        
        # Check if tesseract is in PATH
        tesseract_cmd = shutil.which('tesseract')
        if tesseract_cmd:
            print(f"✓ Tesseract found: {tesseract_cmd}")
        else:
            print("⚠ Tesseract not in PATH")
            print("  Common locations:")
            print("    C:\\Program Files\\Tesseract-OCR\\tesseract.exe")
            print("    C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe")
        
        # Try to get version
        try:
            version = pytesseract.get_tesseract_version()
            print(f"✓ Tesseract version: {version}")
            return True
        except Exception as e:
            print(f"⚠ Cannot get Tesseract version: {e}")
            print("  You can set the path manually in the application")
            return False
    except Exception as e:
        print(f"✗ Error testing Tesseract: {e}")
        return False

def test_performance():
    """Quick performance test"""
    print("\n" + "=" * 60)
    print("Performance Information")
    print("=" * 60)
    
    import multiprocessing
    import platform
    
    print(f"Python version: {platform.python_version()}")
    print(f"Platform: {platform.platform()}")
    print(f"CPU cores: {multiprocessing.cpu_count()}")
    
    try:
        import psutil
        memory = psutil.virtual_memory()
        print(f"RAM: {memory.total / (1024**3):.1f} GB (Available: {memory.available / (1024**3):.1f} GB)")
    except ImportError:
        print("RAM: Unknown (psutil not installed)")
    
    print("\nOptimization mode:")
    print("  → CPU-only for EasyOCR (better for real-time gaming)")
    print("  → Adaptive throttling (6-7 FPS)")
    print("  → Perceptual hash deduplication")
    print("  → Simple in-memory cache (max 1000 entries)")

def main():
    print("\n" + "=" * 70)
    print(" Real-Time Screen Translator - Dependency Check")
    print(" CPU-only mode optimized for real-time gaming")
    print("=" * 70)
    print()
    
    imports_ok, errors = test_imports()
    tesseract_ok = test_tesseract()
    test_performance()
    
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    
    if imports_ok and tesseract_ok:
        print("✓ All core dependencies OK! Ready to build or run.")
        print("\nNext steps:")
        print("  - Run: python translator.py")
        print("  - Build: build.bat (Windows)")
        return 0
    else:
        print("⚠ Some dependencies missing or issues found.")
        print("\nTo fix:")
        if not imports_ok:
            print("  1. Install missing packages:")
            print("     pip install -r requirements.txt")
            if errors:
                print("\n  Missing modules:")
                for error in errors:
                    print(f"     {error}")
        if not tesseract_ok:
            print("  2. Install Tesseract OCR:")
            print("     https://github.com/UB-Mannheim/tesseract/wiki")
        return 1

if __name__ == "__main__":
    sys.exit(main())
