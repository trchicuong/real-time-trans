# 🖥️ Real-Time Screen Translator - Việt Nam

Tool Python mã nguồn mở dịch văn bản thời gian thực trên màn hình bằng OCR và dịch thuật. Hỗ trợ đa luồng, nhiều engine OCR, dịch vụ dịch thuật, và hotkeys toàn cục.

## ✨ Tính Năng

- 🚀 Đa luồng xử lý (capture, OCR, translation)
- 🔄 2 Engine OCR: Tesseract (mặc định) và EasyOCR (tùy chọn)
- 🎮 GPU acceleration cho EasyOCR (tự động phát hiện + GPU memory management)
- 🌐 3 Dịch vụ dịch: Google Translate (miễn phí), DeepL (chất lượng cao), MarianMT (cục bộ offline)
- 💾 Cache thông minh: SQLite backend (indexed), LRU cache và preset cache
- ⚡ Tối ưu hiệu suất: Intelligent preprocessing, advanced deduplication, adaptive intervals, batch translation
- ⌨️ Global Hotkeys: Phím tắt toàn cục tùy chỉnh (Windows/macOS/Linux)

### 🆕 Cập nhật v1.2.0 (2025-11-26)

**MarianMT Local Translation**:

- GPU neural MT (Helsinki-NLP OPUS-MT) chạy hoàn toàn offline
- Hiệu suất: 50–200ms (GPU) / 100–300ms (CPU) — nhanh hơn API ~60–80%
- 14 cặp ngôn ngữ: en↔vi, en↔ja, en↔ko, en↔zh, en↔de, en↔fr, en↔es
- Auto phát hiện GPU / fallback CPU
- Preload model khi chọn (không delay lượt dịch đầu)
- Thread-safe, OOM protection

**Global Hotkeys**:

- Phím tắt toàn cục tùy chỉnh (pynput)
- 6 actions: Start/Stop, Pause/Resume, Clear History, Toggle Overlay, Select Region, Lock/Unlock
- Mặc định: Ctrl+Alt+S/P/C/O/R/L
- Thread-safe, Windows VK code normalization, edge-trigger để tránh spam

**Improvements**:

- Centralized error logging vào `error_log.txt` (tất cả exceptions được log)
- Tách debug logs vào `translator_debug.log` (có thể tắt)
- Build.spec đã update với pynput hidden imports

### Cập nhật v1.1.0 (2025-11-24)

- Tesseract preprocessing tối ưu (~30-40% faster với intelligent strategy selection)
- Text deduplication nâng cao (SequenceMatcher + dynamic thresholds, ~20% accuracy)
- SQLite cache backend (B-tree indexed, ~50% cache performance boost)
- EasyOCR GPU memory optimization (periodic cleanup, no memory leaks)

## Yêu Cầu

- Python 3.8+
- Tesseract OCR (bắt buộc)
- EasyOCR (tùy chọn - độ chính xác cao hơn)
- MarianMT (tùy chọn - dịch offline)

### Cài Đặt Tesseract OCR

- **Windows**: Tải từ https://github.com/UB-Mannheim/tesseract/wiki
- **macOS**: `brew install tesseract`
- **Linux**: `sudo apt-get install tesseract-ocr` (Ubuntu/Debian) hoặc `sudo dnf install tesseract` (Fedora)

**Lưu ý**: Với ngôn ngữ không phải tiếng Anh, cần cài thêm language data từ https://github.com/tesseract-ocr/tessdata

## Cài Đặt

```bash
# Clone repository
git clone https://github.com/trchicuong/real-time-trans.git
cd real-time-trans

# Cài đặt dependencies cơ bản
pip install -r requirements.txt

# (Tùy chọn) EasyOCR cho độ chính xác cao hơn
pip install easyocr

# (Tùy chọn) GPU support cho EasyOCR (Windows)
install_pytorch_cuda.bat
# Hoặc thủ công:
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130

# (Tùy chọn) DeepL API
pip install deepl

# (Tùy chọn) MarianMT cho dịch offline
pip install transformers>=4.18.0 torch>=1.10.0 sentencepiece>=0.1.96
# GPU (khuyến nghị cho MarianMT):
pip install torch --index-url https://download.pytorch.org/whl/cu130
```

**Lưu ý**: Nếu Tesseract không có trong PATH, cấu hình trong UI hoặc set `pytesseract.pytesseract.tesseract_cmd` trong code.

## Sử Dụng

```bash
python translator.py
```

**Quy trình sử dụng**:

1. Tab "Cài Đặt": Chọn vùng màn hình → Ngôn ngữ nguồn/đích → OCR engine → Dịch vụ
2. Nhấn "Bắt đầu" hoặc dùng hotkey `Ctrl+Alt+S`
3. Văn bản được dịch sẽ hiện trong overlay

**Hotkeys mặc định**:

- `Ctrl+Alt+S`: Bắt đầu/dừng capture
- `Ctrl+Alt+P`: Tạm dừng/tiếp tục (pause/resume)
- `Ctrl+Alt+C`: Xóa lịch sử dịch
- `Ctrl+Alt+O`: Hiện/ẩn overlay
- `Ctrl+Alt+R`: Chọn vùng màn hình mới
- `Ctrl+Alt+L`: Khóa/mở khóa overlay

Xem `HUONG_DAN.txt` để biết hướng dẫn chi tiết cho người dùng cuối.

## Cấu Hình

Cài đặt được lưu tự động vào `config.json` (vùng chụp, ngôn ngữ, engine OCR, dịch vụ, giao diện, hotkeys, v.v.).

### Cache Files

- `cache/translations.db`: SQLite cache database (primary, auto-created, B-tree indexed)
- `translation_cache.txt`: File-based cache (legacy fallback)
- `preset_cache.txt`: Preset cache (bundle vào exe, tự động extract)
- `error_log.txt`: Runtime error logs với full traceback (gửi file này khi báo lỗi)
- `translator_debug.log`: Debug logs (info messages, có thể tắt trong settings)

**Lưu ý**: Unified translation cache (LRU) được lưu trong memory. Có thể chỉnh sửa `preset_cache.txt` để thêm các bản dịch phổ biến.

## Packaging

Tạo file `.exe`:

```bash
# Cách 1: build.bat (khuyến nghị)
build.bat

# Cách 2: PyInstaller trực tiếp
pip install pyinstaller
pyinstaller --onedir --windowed --name "RealTimeScreenTranslator" translator.py

# Cách 3: build.spec (đã config sẵn)
pyinstaller build.spec

# Cách 4: package.py (tự động build + zip)
python package.py
```

**Lưu ý**: Exe ~50-100MB. Người dùng vẫn cần cài Tesseract OCR riêng.

## Xử Lý Sự Cố

### OCR không hoạt động

- Kiểm tra Tesseract đã cài đúng và có trong PATH
- Đảm bảo văn bản rõ ràng, không quá nhỏ/mờ
- Thử tăng độ tương phản hoặc kích thước font

### Lỗi dịch

- Kiểm tra kết nối internet (Google/DeepL)
- Tool tự động retry khi gặp rate limit
- Thử dùng MarianMT để dịch offline

### Hiệu suất

- **EasyOCR CPU cao (70-90%)**: Cài PyTorch với CUDA (`install_pytorch_cuda.bat`)
- Tăng scan interval (200ms → 500ms), giảm vùng chụp
- Dùng Tesseract nếu không cần độ chính xác cao
- Dùng MarianMT GPU mode cho dịch nhanh hơn

### Hotkeys không hoạt động

- Kiểm tra tab "Phím Tắt" đã bật
- Đảm bảo không conflict với hotkeys khác
- Thử thay đổi tổ hợp phím
- Xem `error_log.txt` để biết chi tiết lỗi

### EXE không chạy

1. Kiểm tra dependencies: `python test_exe.py`
2. Build DEBUG: `build.bat` → chọn option 2
3. Kiểm tra `error_log.txt` để xem lỗi chi tiết
4. Nguyên nhân thường gặp: Thiếu Tesseract, thiếu VC++ Redistributable, antivirus chặn
5. Chạy từ Python: `python translator.py` để test
6. Rebuild: Xóa `build/` và `dist/`, chạy lại `build.bat`

## Ngôn Ngữ Được Hỗ Trợ

### Ngôn Ngữ Nguồn (OCR):

- Tiếng Anh (eng)
- Tiếng Nhật (jpn)
- Tiếng Hàn (kor)
- Tiếng Trung Giản Thể (chi_sim)
- Tiếng Trung Phồn Thể (chi_tra)
- Tiếng Pháp (fra)
- Tiếng Đức (deu)
- Tiếng Tây Ban Nha (spa)

### Ngôn Ngữ Đích (Dịch):

- Tiếng Việt (vi)
- Tiếng Anh (en)
- Tiếng Nhật (ja)
- Tiếng Hàn (ko)
- Tiếng Trung (zh)
- Tiếng Pháp (fr)
- Tiếng Đức (de)
- Tiếng Tây Ban Nha (es)

### MarianMT Supported Pairs:

en↔vi, en↔ja, en↔ko, en↔zh, en↔de, en↔fr, en↔es (14 cặp hai chiều)

## 📁 Cấu Trúc Dự Án

```
real-time-trans/
├── translator.py              # Main file: UI, OCR, translation logic
├── modules/                   # Utility modules
│   ├── hotkey_manager.py      # Global hotkeys system (NEW v1.2.0)
│   ├── logger.py              # Centralized logging (error_log.txt + debug)
│   ├── circuit_breaker.py     # Network circuit breaker
│   ├── ocr_postprocessing.py  # OCR post-processing
│   ├── text_validator.py      # Text validation
│   ├── text_normalizer.py     # Text normalization
│   ├── text_deduplication.py  # Advanced deduplication (SequenceMatcher)
│   ├── sentence_buffer.py     # Sentence buffering
│   ├── smart_queue.py         # Smart queue management
│   ├── rate_limiter.py        # Rate limiting
│   ├── translation_continuity.py # Translation continuity
│   ├── unified_translation_cache.py # LRU cache
│   ├── batch_translation.py   # Batch translation
│   ├── deepl_context.py       # DeepL context manager
│   └── advanced_deduplication.py # Image hash + text similarity
├── handlers/                  # OCR và cache handlers
│   ├── marianmt_handler.py    # MarianMT local translation (NEW v1.2.0)
│   ├── tesseract_ocr_handler.py # Optimized Tesseract (intelligent preprocessing)
│   ├── easyocr_handler.py     # EasyOCR with GPU memory management
│   ├── cache_manager.py       # Hybrid cache manager (SQLite + file)
│   └── sqlite_cache_backend.py # SQLite backend (indexed, WAL mode)
├── package.py                 # Auto build + package script
├── build.bat                  # Windows build script
├── build.spec                 # PyInstaller config (updated với pynput)
├── test_exe.py               # Dependency checker
├── test_gpu.py                # GPU checker
├── install_pytorch_cuda.bat   # PyTorch CUDA installer
├── requirements.txt           # All dependencies (including pynput>=1.7.6)
├── preset_cache.txt           # Bundle vào exe
├── README.md                  # This file (for developers)
├── LICENSE
└── HUONG_DAN.txt             # User guide (for end users, updated với hotkeys)
```

### File Chính

- **`translator.py`**: `ScreenTranslator` class, multi-threading (3 threads), DPI-aware region selector, hotkeys integration
- **`modules/`**: Text processing (validator, normalizer, deduplication), sentence buffer, smart queue, rate limiter, translation continuity, logger, circuit breaker, unified cache, batch translation, DeepL context, hotkey manager
- **`handlers/`**: TesseractOCRHandler (optimized preprocessing), EasyOCRHandler (GPU management), MarianMTHandler (local translation), TranslationCacheManager (hybrid), SQLiteCacheBackend (indexed)
- **Build scripts**: `build.bat`, `package.py`, `build.spec` (đã update với pynput hidden imports)

## 🛠️ Development

```bash
# Clone và setup
git clone https://github.com/trchicuong/real-time-trans.git
cd real-time-trans
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Test
python test_exe.py      # Check dependencies
python test_gpu.py      # Check GPU (if using EasyOCR/MarianMT)
python translator.py    # Run app

# Build
build.bat               # Windows
# python package.py     # Auto build + package
```

## 🤝 Đóng góp

Dự án này luôn chào đón các đóng góp! Nếu bạn muốn sửa lỗi, thêm tính năng mới, hoặc cải thiện mã nguồn, hãy thoải mái tạo một `Pull Request`. Fork → Create branch → Commit → Push → PR.

## ✉️ Góp ý & Liên hệ

Nếu bạn có bất kỳ ý tưởng nào để cải thiện công cụ hoặc phát hiện lỗi, đừng ngần ngại mở một `Issue` trên repo này.

Mọi thông tin khác, bạn có thể liên hệ với tôi qua:
[**trchicuong.id.vn**](https://trchicuong.id.vn/)

### Credits

- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) - Apache License 2.0
- [deep-translator](https://github.com/nidhaloff/deep-translator) - MIT License
- [OpenCV](https://opencv.org/) - Apache License 2.0
- [Pillow](https://python-pillow.org/) - PIL License
- [mss](https://github.com/BoboTiG/python-mss) - MIT License
- [EasyOCR](https://github.com/JaidedAI/EasyOCR) - Apache License 2.0 (tùy chọn)
- [PyTorch](https://pytorch.org/) - BSD License (tùy chọn, cho EasyOCR/MarianMT GPU support)
- [Helsinki-NLP OPUS-MT](https://github.com/Helsinki-NLP/Opus-MT) - Apache License 2.0 (MarianMT models)
- [Transformers](https://github.com/huggingface/transformers) - Apache License 2.0 (Hugging Face)
- [pynput](https://github.com/moses-palmer/pynput) - LGPL-3.0 (Global hotkeys)
- [chardet](https://github.com/chardet/chardet) - LGPL License (tùy chọn, cho encoding detection)
- [DeepL API](https://www.deepl.com/docs-api) - Proprietary (tùy chọn, có phí)

### Kiến Trúc

- **Modular design**: OCR handlers (`handlers/`), utilities (`modules/`), main logic (`translator.py`)
- **Error handling**: Centralized logging (`error_log.txt`) với multiple fallbacks, debug logs riêng
- **Cache**: Unified LRU cache + SQLite backend (indexed) + file cache + preset cache
- **Optimization**: Batch translation, circuit breaker, adaptive intervals, GPU support
- **Hotkeys**: pynput-based global keyboard hooks với thread-safe callbacks

## Lưu Ý

- Yêu cầu kết nối internet cho Google Translate và DeepL
- MarianMT hoạt động hoàn toàn offline sau khi tải model lần đầu
- Chất lượng dịch phụ thuộc vào độ chính xác OCR (độ rõ văn bản, tương phản, font, resolution)
- Hotkeys có thể conflict với phím tắt của ứng dụng khác, hãy tùy chỉnh trong tab "Phím Tắt"
