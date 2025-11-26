# -*- coding: utf-8 -*-
"""
Test script for MarianMT handler
Usage: python test_marianmt.py
"""

import time
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

def test_marianmt():
    """Test MarianMT handler"""
    print("=" * 80)
    print("MarianMT Handler Test")
    print("=" * 80)
    
    # Test 1: Import check
    print("\n[Test 1] Checking imports...")
    try:
        from handlers.marianmt_handler import MarianMTHandler, MARIANMT_AVAILABLE
        print(f"✓ MarianMT available: {MARIANMT_AVAILABLE}")
        if not MARIANMT_AVAILABLE:
            print("✗ MarianMT dependencies not installed")
            print("  Install: pip install transformers torch sentencepiece")
            return
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return
    
    # Test 2: Handler initialization
    print("\n[Test 2] Initializing handler...")
    try:
        handler = MarianMTHandler(num_beams=2, use_gpu=None)  # Auto-detect
        stats = handler.get_stats()
        print(f"✓ Handler initialized")
        print(f"  Device: {stats['device']}")
        print(f"  GPU enabled: {stats['gpu_enabled']}")
        print(f"  GPU name: {stats['gpu_name']}")
    except Exception as e:
        print(f"✗ Initialization failed: {e}")
        return
    
    # Test 3: Check supported pairs
    print("\n[Test 3] Checking supported language pairs...")
    pairs = handler.get_supported_pairs()
    print(f"✓ {len(pairs)} language pairs supported")
    print("  Common pairs:")
    for pair in [('en', 'vi'), ('vi', 'en'), ('en', 'ja'), ('ja', 'en'), 
                 ('en', 'ko'), ('ko', 'en'), ('en', 'zh'), ('zh', 'en')]:
        if pair in pairs:
            print(f"    {pair[0]} -> {pair[1]} ✓")
        else:
            print(f"    {pair[0]} -> {pair[1]} ✗")
    
    # Test 4: Translation test (en -> vi)
    print("\n[Test 4] Testing English -> Vietnamese translation...")
    test_texts = [
        "Hello, how are you?",
        "This is a game dialogue.",
        "Press any key to continue."
    ]
    
    for text in test_texts:
        print(f"\n  Source: {text}")
        try:
            start_time = time.time()
            result = handler.translate(text, 'en', 'vi')
            duration = time.time() - start_time
            
            if result and not result.startswith("Error:"):
                print(f"  Translation: {result}")
                print(f"  Time: {duration*1000:.0f}ms")
            else:
                print(f"  ✗ Translation failed: {result}")
        except Exception as e:
            print(f"  ✗ Exception: {e}")
    
    # Test 5: Performance benchmark
    print("\n[Test 5] Performance benchmark...")
    benchmark_text = "The quick brown fox jumps over the lazy dog."
    times = []
    
    print(f"  Running 5 translations of: {benchmark_text}")
    for i in range(5):
        start_time = time.time()
        result = handler.translate(benchmark_text, 'en', 'vi')
        duration = time.time() - start_time
        times.append(duration)
        print(f"    Run {i+1}: {duration*1000:.0f}ms")
    
    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)
    
    print(f"\n  Average: {avg_time*1000:.0f}ms")
    print(f"  Min: {min_time*1000:.0f}ms")
    print(f"  Max: {max_time*1000:.0f}ms")
    
    # Test 6: Final stats
    print("\n[Test 6] Handler statistics...")
    final_stats = handler.get_stats()
    print(f"  Total translations: {final_stats['translations']}")
    print(f"  Average time: {final_stats['avg_time']*1000:.0f}ms")
    print(f"  Active model: {final_stats['active_model']}")
    
    # Cleanup
    print("\n[Cleanup] Releasing resources...")
    handler.cleanup()
    print("✓ Cleanup complete")
    
    print("\n" + "=" * 80)
    print("Test complete!")
    print("=" * 80)

if __name__ == "__main__":
    test_marianmt()
