#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script to verify MarianMT functionality before building exe
Run this to ensure all imports and model loading work correctly
"""

import sys
import os
import time

def test_imports():
    """Test all necessary imports"""
    print("=" * 60)
    print("TEST 1: Checking imports...")
    print("=" * 60)
    
    try:
        print("✓ Importing torch...")
        import torch
        print(f"  PyTorch version: {torch.__version__}")
        print(f"  CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"  CUDA version: {torch.version.cuda}")
            print(f"  GPU: {torch.cuda.get_device_name(0)}")
        
        print("✓ Importing transformers...")
        import transformers
        from transformers import MarianMTModel, MarianTokenizer
        print(f"  Transformers version: {transformers.__version__}")
        
        print("✓ Importing sentencepiece...")
        import sentencepiece
        
        print("✓ Importing huggingface_hub...")
        import huggingface_hub
        print(f"  HF Hub version: {huggingface_hub.__version__}")
        
        print("✓ Importing tokenizers...")
        import tokenizers
        
        print("\n✅ All imports successful!\n")
        return True
    except Exception as e:
        print(f"\n❌ Import failed: {e}\n")
        import traceback
        traceback.print_exc()
        return False

def test_marianmt_handler():
    """Test MarianMT handler initialization"""
    print("=" * 60)
    print("TEST 2: Testing MarianMT Handler...")
    print("=" * 60)
    
    try:
        from handlers.marianmt_handler import MarianMTHandler, MARIANMT_AVAILABLE
        
        if not MARIANMT_AVAILABLE:
            print("❌ MarianMT not available")
            return False
        
        print("✓ Initializing MarianMT handler...")
        handler = MarianMTHandler(num_beams=2, use_gpu=None)
        
        print("✓ Getting stats...")
        stats = handler.get_stats()
        print(f"  Device: {'GPU: ' + stats['gpu_name'] if stats['gpu_enabled'] else 'CPU'}")
        print(f"  Supported pairs: {stats['supported_pairs']}")
        print(f"  Beam search: {stats['beam_search']}")
        
        print("\n✅ Handler initialization successful!\n")
        return True
    except Exception as e:
        print(f"\n❌ Handler test failed: {e}\n")
        import traceback
        traceback.print_exc()
        return False

def test_model_loading():
    """Test model loading for a common language pair"""
    print("=" * 60)
    print("TEST 3: Testing Model Loading (en->vi)...")
    print("=" * 60)
    
    try:
        from handlers.marianmt_handler import MarianMTHandler
        
        print("✓ Initializing handler...")
        handler = MarianMTHandler(num_beams=2, use_gpu=None)
        
        print("✓ Checking if en->vi is supported...")
        if not handler.is_language_pair_supported('en', 'vi'):
            print("❌ Language pair en->vi not supported")
            return False
        
        print("✓ Loading model (this may take 1-5 minutes on first run)...")
        start_time = time.time()
        success = handler._load_model('en', 'vi')
        load_time = time.time() - start_time
        
        if not success:
            print("❌ Model loading failed")
            return False
        
        print(f"  Model loaded in {load_time:.2f}s")
        
        print("\n✅ Model loading successful!\n")
        return True
    except Exception as e:
        print(f"\n❌ Model loading failed: {e}\n")
        import traceback
        traceback.print_exc()
        return False

def test_translation():
    """Test actual translation"""
    print("=" * 60)
    print("TEST 4: Testing Translation...")
    print("=" * 60)
    
    try:
        from handlers.marianmt_handler import MarianMTHandler
        
        print("✓ Initializing handler...")
        handler = MarianMTHandler(num_beams=2, use_gpu=None)
        
        test_text = "Hello, how are you?"
        print(f"✓ Translating: '{test_text}'")
        
        start_time = time.time()
        result = handler.translate(test_text, 'en', 'vi')
        trans_time = time.time() - start_time
        
        if not result:
            print("❌ Translation returned empty result")
            return False
        
        print(f"  Result: '{result}'")
        print(f"  Translation time: {trans_time*1000:.0f}ms")
        
        print("\n✅ Translation successful!\n")
        return True
    except Exception as e:
        print(f"\n❌ Translation failed: {e}\n")
        import traceback
        traceback.print_exc()
        return False

def test_cache_path():
    """Test cache directory path handling"""
    print("=" * 60)
    print("TEST 5: Testing Cache Path...")
    print("=" * 60)
    
    try:
        from modules import get_base_dir
        from handlers.marianmt_handler import MarianMTHandler
        
        base_dir = get_base_dir()
        print(f"✓ Base directory: {base_dir}")
        
        handler = MarianMTHandler()
        print(f"✓ Cache directory: {handler.cache_dir}")
        
        expected_cache = os.path.join(base_dir, "marian_models_cache")
        if handler.cache_dir == expected_cache:
            print(f"  ✅ Cache path correct!")
        else:
            print(f"  ⚠ Cache path differs from expected")
            print(f"    Expected: {expected_cache}")
            print(f"    Got: {handler.cache_dir}")
        
        print("\n✅ Cache path test passed!\n")
        return True
    except Exception as e:
        print(f"\n❌ Cache path test failed: {e}\n")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("MarianMT Build Verification Tests")
    print("=" * 60 + "\n")
    
    results = []
    
    # Test 1: Imports
    results.append(("Imports", test_imports()))
    
    # Test 2: Handler initialization
    results.append(("Handler Init", test_marianmt_handler()))
    
    # Test 3: Cache path
    results.append(("Cache Path", test_cache_path()))
    
    # Test 4: Model loading (optional - takes time)
    print("\nℹ️  Model loading test will download ~300MB on first run.")
    response = input("Run model loading test? (y/n, default=n): ").strip().lower()
    if response == 'y':
        results.append(("Model Loading", test_model_loading()))
        results.append(("Translation", test_translation()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:20s}: {status}")
    
    all_passed = all(result for _, result in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ ALL TESTS PASSED - Ready to build exe!")
    else:
        print("❌ SOME TESTS FAILED - Fix issues before building")
    print("=" * 60 + "\n")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
