# 🖥️ Real-Time Screen Translator - Việt Nam

Tool Python mã nguồn mở dịch văn bản thời gian thực trên màn hình bằng OCR và dịch thuật. Hỗ trợ đa luồng, nhiều engine OCR và dịch vụ dịch thuật.

## ✨ Tính Năng

- 🚀 Đa luồng xử lý (capture, OCR, translation)
- 🔄 2 Engine OCR: Tesseract (mặc định) và EasyOCR (tùy chọn)
- 🎮 GPU acceleration cho EasyOCR (tự động phát hiện)
- 🌐 2 Dịch vụ dịch: Google Translate (miễn phí) và DeepL (chất lượng cao)
- 💾 Cache thông minh: LRU cache và preset cache
- ⚡ Tối ưu hiệu suất: Adaptive intervals, multi-scale processing, batch translation

## Yêu Cầu

- Python 3.7+
- Tesseract OCR (hoặc EasyOCR nếu muốn dùng)

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

# (Tùy chọn) EasyOCR
pip install easyocr

# (Tùy chọn) GPU support cho EasyOCR (Windows)
install_pytorch_cuda.bat
# Hoặc thủ công:
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130

# (Tùy chọn) DeepL API
pip install deepl
```

**Lưu ý**: Nếu Tesseract không có trong PATH, cấu hình trong UI hoặc set `pytesseract.pytesseract.tesseract_cmd` trong code.

## Sử Dụng

```bash
python translator.py
```

Xem `HUONG_DAN.txt` để biết hướng dẫn chi tiết cho người dùng cuối.

## Cấu Hình

Cài đặt được lưu tự động vào `config.json` (vùng chụp, ngôn ngữ, engine OCR, dịch vụ, giao diện, v.v.).

### Cache Files

- `translation_cache.txt`: File-based translation cache
- `preset_cache.txt`: Preset cache (bundle vào exe, tự động extract)
- `error_log.txt`: Runtime error logs với full traceback
- `translator_debug.log`: Debug logs

**Lưu ý**: Unified translation cache (LRU) được lưu trong memory. Có thể chỉnh sửa `preset_cache.txt` để thêm các bản dịch phổ biến.

## Packaging

Tạo file `.exe`:

```bash
# Cách 1: build.bat (khuyến nghị)
build.bat

# Cách 2: PyInstaller trực tiếp
pip install pyinstaller
pyinstaller --onefile --windowed --name "RealTimeScreenTranslator" translator.py

# Cách 3: build.spec
pyinstaller build.spec

# Cách 4: package.py (tự động build + zip)
python package.py
```

**Lưu ý**: Exe ~50-100MB. Người dùng vẫn cần cài Tesseract OCR riêng.

## Xử Lý Sự Cố

### OCR không hoạt động

- Kiểm tra Tesseract đã cài đúng và có trong PATH
- Đảm bảo văn bản rõ ràng, không quá nhỏ/mờ

### Lỗi dịch

- Kiểm tra kết nối internet
- Tool tự động retry khi gặp rate limit

### Hiệu suất

- **EasyOCR CPU cao (70-90%)**: Cài PyTorch với CUDA (`install_pytorch_cuda.bat`)
- Tăng scan interval, giảm vùng chụp, dùng Tesseract nếu không cần độ chính xác cao

### EXE không chạy

1. Kiểm tra dependencies: `python test_exe.py`
2. Build DEBUG: `build.bat` → chọn option 2
3. Kiểm tra `error_log.txt`
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

### Ngôn Ngữ Đích:

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
├── translator.py              # Main file: UI, OCR, translation logic
├── modules/                   # Utility modules
│   ├── logger.py              # Centralized logging
│   ├── circuit_breaker.py     # Network circuit breaker
│   ├── ocr_postprocessing.py # OCR post-processing
│   ├── unified_translation_cache.py # LRU cache
│   ├── batch_translation.py  # Batch translation
│   └── deepl_context.py      # DeepL context manager
├── handlers/                  # OCR và cache handlers
│   ├── tesseract_ocr_handler.py
│   ├── easyocr_handler.py
│   └── cache_manager.py
├── package.py                 # Auto build + package script
├── build.bat                  # Windows build script
├── build.spec                 # PyInstaller config
├── test_exe.py               # Dependency checker
├── test_gpu.py                # GPU checker
├── install_pytorch_cuda.bat   # PyTorch CUDA installer
├── requirements.txt
├── preset_cache.txt           # Bundle vào exe
├── README.md                  # This file (for developers)
├── LICENSE
└── HUONG_DAN.txt             # User guide (for end users)
```

### File Chính

- **`translator.py`**: `ScreenTranslator` class, multi-threading (3 threads), DPI-aware region selector
- **`modules/`**: Logger, circuit breaker, OCR post-processing, unified cache, batch translation, DeepL context
- **`handlers/`**: TesseractOCRHandler, EasyOCRHandler, TranslationCacheManager
- **Build scripts**: `build.bat`, `package.py`, `build.spec`

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
python test_gpu.py      # Check GPU (if using EasyOCR)
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

### Credit

- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) - Apache License 2.0
- [deep-translator](https://github.com/nidhaloff/deep-translator) - MIT License
- [OpenCV](https://opencv.org/) - Apache License 2.0
- [Pillow](https://python-pillow.org/) - PIL License
- [mss](https://github.com/BoboTiG/python-mss) - MIT License
- [EasyOCR](https://github.com/JaidedAI/EasyOCR) - Apache License 2.0 (tùy chọn)
- [PyTorch](https://pytorch.org/) - BSD License (tùy chọn, cho EasyOCR GPU support)
- [chardet](https://github.com/chardet/chardet) - LGPL License (tùy chọn, cho encoding detection)
- [DeepL API](https://www.deepl.com/docs-api) - Proprietary (tùy chọn, có phí)

### Kiến Trúc

- **Modular design**: OCR handlers (`handlers/`), utilities (`modules/`), main logic (`translator.py`)
- **Error handling**: Centralized logging với multiple fallbacks
- **Cache**: Unified LRU cache + file cache + preset cache
- **Optimization**: Batch translation, circuit breaker, adaptive intervals, GPU support

## Lưu Ý

- Yêu cầu kết nối internet để dịch
- Chất lượng dịch phụ thuộc vào độ chính xác OCR (độ rõ văn bản, tương phản, font, resolution)
