# 🖥️ Real-Time Screen Translator - Việt Nam

Tool Python mã nguồn mở dịch văn bản thời gian thực trên màn hình bằng OCR và dịch thuật. Hỗ trợ đa luồng, nhiều engine OCR, dịch vụ dịch thuật, và hotkeys toàn cục.

## ✨ Tính Năng

- 🚀 Đa luồng xử lý (capture, OCR, translation)
- 🔄 2 Engine OCR:
  - **Tesseract** (miễn phí, nhanh) với multi-scale và text region detection
  - **EasyOCR** (neural network, chính xác hơn) với CPU-only mode tối ưu cho gaming
- ⚡ CPU-only mode: Tối ưu cho real-time gaming với hiệu suất ổn định
- 🌐 2 Dịch vụ dịch: Google Translate (miễn phí), DeepL (chất lượng cao)
- 💾 Cache đơn giản: In-memory dict cache (max 1000 entries, LRU eviction)
- ⚡ Tối ưu hiệu suất: Perceptual hashing, adaptive throttling, batch translation, CPU-only mode
- ⌨️ Global Hotkeys: Phím tắt toàn cục tùy chỉnh (Windows/macOS/Linux)

### 🆕 Cập nhật v1.3.1

**Game Mode - Advanced Preprocessing for AAA Graphics**:

- **Game Mode toggle**: Advanced preprocessing pipeline cho game AAA với đồ họa phức tạp
  - **Color Text Extraction**: Trích xuất text màu (white/yellow/cyan) từ nền nhiễu qua HSV color space
  - **Background Noise Detection**: Phát hiện nhiễu nền (particles, effects, animation) bằng FFT analysis
  - **Adaptive Denoising**: Khử nhiễu thông minh khi noise_level > 40% (bilateral filter + NLM)
  - **Stroke Width Transform**: Phát hiện text qua độ dày nét vẽ nhất quán (SWT algorithm)
- **Hiệu quả**: Tăng 40-60% độ chính xác OCR cho game modern với nền động/phức tạp
- **Trade-off**: +30-50ms overhead (balanced for accuracy)
- **UI integration**: Checkbox trong tab Cài Đặt, mặc định BẬT
- **Documentation**: Hướng dẫn chi tiết trong UI và HUONG_DAN.txt

### 🆕 Cập nhật v1.3.0

**Major Performance Optimization & Text Processing**:

- **CPU-only mode**: EasyOCR forced CPU mode - better real-time performance than GPU for gaming
- **Emotion markers support**: Preserves [action], **emotion**, (sound), ~ markers in game dialogues
- **Smart text processing**: Fragment detection, em dash normalization, punctuation handling
- **Advanced deduplication**: Hybrid text+image similarity with normalized comparison
- **Removed MarianMT**: Simplified to Google Translate + DeepL only (faster, more reliable)
- **Simplified cache**: Single in-memory dict cache (no disk I/O overhead)
- **Immediate translation**: stable_threshold=1 (no warmup delay) - catches short dialogues
- **Optimized throttling**: 0.15s intervals = 6-7 FPS (responsive for dialogue)
- **Perceptual hashing**: imagehash library for better duplicate detection
- **Text normalization**: Basic normalization in handlers, advanced in post-processing

## Yêu Cầu

- Python 3.8+
- Tesseract OCR (bắt buộc)
- EasyOCR (tùy chọn - độ chính xác cao hơn, CPU-only mode)

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

# Cài đặt dependencies
pip install -r requirements.txt

# (Tùy chọn) EasyOCR cho độ chính xác cao hơn
pip install easyocr

# (Tùy chọn) DeepL API
pip install deepl
```

**Lưu ý**:

- EasyOCR sẽ tự động cài PyTorch (CPU version)
- Tesseract OCR cần cài riêng (xem phần dưới)
- Nếu Tesseract không có trong PATH, cấu hình trong UI hoặc set `pytesseract.pytesseract.tesseract_cmd` trong code

## Sử Dụng

```bash
# Test dependencies trước
python test_dependencies.py

# Chạy ứng dụng
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

### Log Files

- `error_log.txt`: Runtime error logs với full traceback (gửi file này khi báo lỗi)
- `translator_debug.log`: Debug logs (info messages, có thể tắt trong settings)

**Lưu ý**: Translation cache chỉ lưu trong memory (dict with max 1000 entries, LRU eviction). Cache sẽ mất khi thoát app.

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

### Hiệu suất

- **EasyOCR CPU cao**: Đã tối ưu CPU-only mode cho real-time gaming
- Tăng scan interval (100ms → 200ms), giảm vùng chụp
- Dùng Tesseract nếu không cần độ chính xác cao

### Hotkeys không hoạt động

- Kiểm tra tab "Phím Tắt" đã bật
- Đảm bảo không conflict với hotkeys khác
- Thử thay đổi tổ hợp phím
- Xem `error_log.txt` để biết chi tiết lỗi

### EXE không chạy

1. Kiểm tra dependencies: `python test_dependencies.py`
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

## 📁 Cấu Trúc Dự Án

```
real-time-trans/
├── translator.py # Main file: UI, OCR, translation logic (~5300 lines)
├── modules/ # Utility modules (10 files)
│ ├── logger.py # Centralized logging (error_log.txt + debug)
│ ├── circuit_breaker.py # Network circuit breaker (~200 lines)
│ ├── ocr_postprocessing.py # OCR post-processing with emotion markers (~284 lines)
│ ├── batch_translation.py # Batch translation for long text (~235 lines)
│ ├── deepl_context.py # DeepL context window manager (~185 lines)
│ ├── text_validator.py # Dialogue-aware text validation (~287 lines)
│ ├── advanced_deduplication.py # Hybrid text+image dedup (~265 lines)
│ ├── hotkey_manager.py # Global hotkeys system (~150 lines)
│ ├── image_processing.py # Game Mode - Advanced preprocessing (~494 lines)
│ └── __init__.py # Package exports
├── handlers/ # OCR handlers (3 files)
│ ├── tesseract_ocr_handler.py # Tesseract with optimizations (~602 lines)
│ ├── easyocr_handler.py # EasyOCR CPU-only + adaptive (~747 lines)
│ └── __init__.py # Handler exports
├── test_dependencies.py # Dependency checker (all-in-one)
├── package.py # Auto build + package script
├── build.bat # Windows build script
├── build.spec # PyInstaller config
├── requirements.txt # All dependencies
├── config.json # User settings (auto-saved)
├── error_log.txt # Runtime errors with traceback
├── translator_debug.log # Debug logs (can be disabled)
├── README.md # Developer documentation
├── HUONG_DAN.txt # User guide
└── LICENSE
```

### File Chính

- **`translator.py`** (~5300 dòng): File chính chứa UI và logic xử lý, 8 threads, cache 1000 entries
- **`modules/`** (9 modules + 1 **init**):
  - Text processing: `ocr_postprocessing.py`, `text_validator.py`
  - Translation: `batch_translation.py`, `deepl_context.py`
  - Optimization: `advanced_deduplication.py`, `circuit_breaker.py`
  - Image processing: `image_processing.py` (Game Mode - SWT, color extraction, noise detection)
  - System: `logger.py`, `hotkey_manager.py`
- **`handlers/`** (2 handlers + 1 **init**):
  - `tesseract_ocr_handler.py`: Fast, multi-scale, text region detection, Game Mode integration
  - `easyocr_handler.py`: Accurate, CPU-only, adaptive throttling, fast path, Game Mode integration
- **`test_dependencies.py`**: Kiểm tra tất cả dependencies
- **`build.bat`, `package.py`, `build.spec`**: Công cụ build exe

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

# Test dependencies
python test_dependencies.py  # Check all dependencies

# Run application
python translator.py

# Build executable
build.bat               # Windows (interactive: Release/Debug)
# hoặc: python package.py  # Auto build + zip packaging
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
- [PyTorch](https://pytorch.org/) - BSD License (tùy chọn, cho EasyOCR CPU mode)
- [pynput](https://github.com/moses-palmer/pynput) - LGPL-3.0 (Global hotkeys)
- [chardet](https://github.com/chardet/chardet) - LGPL License (tùy chọn, cho encoding detection)
- [DeepL API](https://www.deepl.com/docs-api) - Proprietary (tùy chọn, có phí)
- [imagehash](https://github.com/JohannesBuchner/imagehash) - BSD License (perceptual hashing)

### Kiến Trúc

- **Thiết kế module**: 2 OCR handlers, 9 utility modules, 1 main file (modular, maintainable)
- **Text processing pipeline**:
  - OCR → Basic normalization (handlers) → Post-processing (ocr_postprocessing.py)
  - Advanced features: Emotion markers, fragment detection, dash normalization
  - Validation: Dialogue-aware (text_validator.py) with pattern recognition
- **Image preprocessing pipeline** (Game Mode):
  - Color extraction → Noise detection → Adaptive denoising → Optional SWT
  - HSV-based color segmentation for white/yellow/cyan text
  - FFT-based background noise detection (particles, effects, animation)
  - Conditional aggressive denoising when noise_level > 40%
- **Xử lý lỗi**: Log tập trung vào `error_log.txt`, debug logs riêng, full traceback
- **Cache**: Dict trong memory, max 1000 entries, LRU eviction, không ghi đĩa
- **Tối ưu hiệu suất**:
  - OCR: Fast path, bilateral filter, adaptive throttling, CPU-only mode, Game Mode preprocessing
  - Translation: Batch translation, circuit breaker, DeepL context window
  - Deduplication: Hybrid text+image similarity, perceptual hash, normalized comparison
- **Hotkeys**: Global keyboard hooks dùng pynput, thread-safe, customizable

## Lưu Ý

- Yêu cầu kết nối internet cho Google Translate và DeepL
- Chất lượng dịch phụ thuộc vào độ chính xác OCR (độ rõ văn bản, tương phản, font, resolution)
- Hotkeys có thể conflict với phím tắt của ứng dụng khác, hãy tùy chỉnh trong tab "Phím Tắt"
- CPU-only mode được tối ưu cho real-time gaming, không cần GPU
