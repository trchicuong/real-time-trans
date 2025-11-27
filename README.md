# 🖥️ Real-Time Screen Translator - Việt Nam

Tool Python mã nguồn mở dịch văn bản thời gian thực trên màn hình bằng OCR và dịch thuật. Hỗ trợ đa luồng, nhiều engine OCR, dịch vụ dịch thuật, và hotkeys toàn cục.

## ✨ Tính Năng

- 🚀 Đa luồng xử lý (capture, OCR, translation)
- 🔄 2 Engine OCR:
  - **Tesseract** (miễn phí, nhanh) với multi-scale và text region detection
  - **EasyOCR** (neural network, chính xác hơn) với GPU acceleration và multi-scale
- 🎮 GPU acceleration cho EasyOCR (tự động phát hiện + GPU memory management + anti-stutter)
- 🌐 3 Dịch vụ dịch: Google Translate (miễn phí), DeepL (chất lượng cao), MarianMT (cục bộ offline)
- 💾 Cache thông minh: SQLite backend (indexed), LRU cache và preset cache
- ⚡ Tối ưu hiệu suất: Intelligent preprocessing, advanced deduplication, adaptive intervals, batch translation
- ⌨️ Global Hotkeys: Phím tắt toàn cục tùy chỉnh (Windows/macOS/Linux)

### 🆕 Cập nhật v1.2.1

**OCR Engine Improvements**:

- **EasyOCR multi-scale**: Fixed logic để hoạt động đúng khi bật từ UI (test 3 scales: 0.7x, 1.0x, 1.3x)
- **Tesseract text region detection**: Implemented để hoạt động thật sự khi bật (tách vùng text → OCR từng vùng → merge)
- **Tesseract multi-scale**: Đã hoạt động (intelligent scale selection: 1-3 scales dựa trên blur/size analysis)
- **Code cleanup**: Loại bỏ comments thừa, đơn giản hóa logic, không thêm thư viện mới
- **Logging**: Cleaned up log spam, optimized file sizes, UI status tab không spam nữa

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
- **GPU stuttering trong game**: Đã tối ưu: VRAM monitoring, aggressive cache cleanup, dynamic throttling
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
│   ├── hotkey_manager.py      # Global hotkeys system
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
│   ├── marianmt_handler.py    # MarianMT local translation (offline neural MT)
│   ├── tesseract_ocr_handler.py # Tesseract với multi-scale + text region detection
│   ├── easyocr_handler.py     # EasyOCR với GPU optimization + multi-scale
│   ├── cache_manager.py       # Hybrid cache manager (SQLite + file)
│   └── sqlite_cache_backend.py # SQLite backend (indexed, WAL mode)
├── test_marianmt.py           # MarianMT test suite (imports, model loading, translation)
├── test_easyocr_cpu_gpu.py    # CPU vs GPU comparison test cho EasyOCR
├── test_exe.py                # Dependency checker
├── test_gpu.py                # GPU checker
├── package.py                 # Auto build + package script
├── build.bat                  # Windows build script
├── build.spec                 # PyInstaller config
├── install_pytorch_cuda.bat   # PyTorch CUDA installer
├── requirements.txt           # All dependencies
├── preset_cache.txt           # Preset translations (bundled vào exe)
├── config.json                # User settings (auto-saved)
├── error_log.txt              # Runtime errors với traceback
├── translator_debug.log       # Debug logs (có thể tắt)
├── cache/                     # Cache directory
│   └── translations.db        # SQLite cache database
├── marian_models_cache/       # MarianMT models (auto-downloaded)
├── README.md                  # Developer documentation
├── HUONG_DAN.txt              # User guide (Vietnamese)
└── LICENSE
```

### File Chính

- **`translator.py`**: Main UI với multi-threading (3 threads), DPI-aware region selector, 6 hotkey actions, auto-save config
- **`modules/`**: Text processing (validator, normalizer, deduplication), performance (buffer, queue, rate limiter, batch), infrastructure (logger, circuit breaker, cache), features (continuity, DeepL, hotkey manager)
- **`handlers/`**:
  - **Tesseract**: Intelligent preprocessing, multi-scale (1-3), text region detection
  - **EasyOCR**: GPU management, anti-stutter, multi-scale (0.7x/1.0x/1.3x)
  - **MarianMT**: Local neural MT, GPU/CPU auto, 14 pairs
  - **Cache**: Hybrid (SQLite + file), indexed B-tree, thread-safe
- **Test scripts**: `test_marianmt.py`, `test_easyocr_cpu_gpu.py`, `test_exe.py`, `test_gpu.py`
- **Build tools**: `build.bat` (interactive), `package.py` (auto), `build.spec` (config)

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

# Optional: GPU support
install_pytorch_cuda.bat  # Windows với CUDA 13.0
# Hoặc: pip install torch --index-url https://download.pytorch.org/whl/cu130

# Test dependencies
python test_exe.py      # Check all dependencies
python test_gpu.py      # Check GPU availability

# Test OCR engines
python test_easyocr_cpu_gpu.py  # Compare CPU vs GPU performance

# Test MarianMT (optional)
python test_marianmt.py

# Run application
python translator.py

# Build executable
build.bat               # Windows (interactive: Release/Debug)
# hoặc: python package.py  # Auto build + zip packaging
```

**OCR Testing:**

```bash
# Test EasyOCR CPU vs GPU stability
python test_easyocr_cpu_gpu.py
# Output: Stability %, average time, FPS

# Adjust GPU memory (nếu gặp OOM):
# Edit handlers/easyocr_handler.py:
# - gpu_cache_clear_interval (default: 20 frames)
# - max_size resolution (default: 800px, pressure: 700px)
```

**Building:**

```bash
# Debug build (console window visible)
build.bat → chọn option 2

# Release build (no console)
build.bat → chọn option 1

# Auto package
python package.py  # Build + tạo zip trong dist/
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
