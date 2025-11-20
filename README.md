# 🖥️ Real-Time Screen Translator - Việt Nam

Tool Python mã nguồn mở giúp dịch văn bản thời gian thực trên màn hình bằng cách chụp vùng màn hình, nhận dạng văn bản (OCR), và dịch sang nhiều ngôn ngữ. Hỗ trợ đa luồng, nhiều engine OCR và dịch vụ dịch thuật.

## ✨ Tính Năng Nổi Bật

- 🚀 **Đa luồng xử lý**: Chụp màn hình, OCR và dịch thuật song song để tối ưu tốc độ
- 🔄 **Hỗ trợ 2 Engine OCR**: Tesseract (mặc định) và EasyOCR (tùy chọn, chính xác hơn)
- 🎮 **GPU Acceleration**: Tự động phát hiện và sử dụng NVIDIA GPU cho EasyOCR để giảm tải CPU
- 🌐 **Hỗ trợ 2 Dịch vụ**: Google Translate (miễn phí) và DeepL (chất lượng cao)
- 🎨 **Tùy chỉnh giao diện**: Preset nhanh hoặc tùy chỉnh chi tiết
- 📍 **Tự động lưu cài đặt**: Vị trí, kích thước, và tất cả cài đặt
- 🔒 **Khóa màn hình dịch**: Ngăn di chuyển nhầm khi chơi game
- 🌍 **Đa ngôn ngữ**: Hỗ trợ nhiều ngôn ngữ nguồn và đích
- 💾 **Cache thông minh**: LRU cache và preset cache để giảm API calls và tăng tốc độ
- 📜 **Lưu lịch sử dịch**: Tùy chọn lưu và xem lại các bản dịch trước đó
- ⚡ **Tối ưu hiệu suất**: Adaptive scan intervals, image preprocessing nâng cao, multi-scale processing

## Yêu Cầu

- Python 3.7 trở lên
- Tesseract OCR đã cài đặt trên máy (hoặc EasyOCR nếu muốn dùng)

### Cài Đặt Tesseract OCR

#### Windows:

1. Tải trình cài đặt từ: https://github.com/UB-Mannheim/tesseract/wiki
2. Chạy trình cài đặt và ghi nhớ đường dẫn cài đặt (mặc định là `C:\Program Files\Tesseract-OCR`)
3. Thêm Tesseract vào PATH máy, hoặc tool sẽ yêu cầu bạn đặt đường dẫn

#### macOS:

```bash
brew install tesseract
```

#### Linux (Ubuntu/Debian):

```bash
sudo apt-get install tesseract-ocr
```

#### Linux (Fedora):

```bash
sudo dnf install tesseract
```

### Cài Đặt Dữ Liệu Ngôn Ngữ

Đối với các ngôn ngữ không phải tiếng Anh, bạn có thể cần cài đặt thêm dữ liệu ngôn ngữ cho Tesseract:

#### Windows:

- Tải dữ liệu ngôn ngữ từ: https://github.com/tesseract-ocr/tessdata
- Đặt các file `.traineddata` vào `C:\Program Files\Tesseract-OCR\tessdata\`

#### macOS/Linux:

```bash
# Ví dụ cho tiếng Nhật
sudo apt-get install tesseract-ocr-jpn  # Ubuntu/Debian
# hoặc
brew install tesseract-lang  # macOS (bao gồm nhiều ngôn ngữ)
```

## Cài Đặt

1. Clone hoặc tải repository này

2. Cài đặt các thư viện Python cần thiết:

```bash
pip install -r requirements.txt
```

3. (Tùy chọn) Cài đặt EasyOCR để sử dụng engine OCR thay thế:

```bash
pip install easyocr
```

**Lưu ý về GPU cho EasyOCR:**

- EasyOCR mặc định cài PyTorch CPU-only, sẽ sử dụng CPU (70-90% CPU usage)
- Để sử dụng GPU và giảm tải CPU, cần cài PyTorch với CUDA:

  ```bash
  # Windows - Chạy script tự động:
  install_pytorch_cuda.bat

  # Hoặc cài thủ công:
  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130
  ```

- Tool sẽ tự động phát hiện GPU và sử dụng nếu có
- Kiểm tra GPU: `python test_gpu.py`

4. (Tùy chọn) Cài đặt DeepL API để sử dụng dịch vụ dịch thuật chất lượng cao:

```bash
pip install deepl
```

5. (Tùy chọn) Nếu Tesseract không có trong PATH, bạn có thể cần cấu hình:
   - Sử dụng nút "Duyệt" trong tab "Cài Đặt" để chọn đường dẫn Tesseract
   - Hoặc chỉnh sửa `translator.py` và thêm dòng sau phần import:
   ```python
   pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
   ```
   (Điều chỉnh đường dẫn cho phù hợp với cài đặt Tesseract của bạn)

## Sử Dụng

1. Chạy công cụ:

```bash
python translator.py
```

2. **Chọn Vùng Chụp Màn Hình**:

   - Nhấn nút "Chọn Vùng"
   - Màn hình sẽ tối đi và bạn sẽ thấy con trỏ chữ thập
   - Nhấn và kéo để chọn vùng xuất hiện hộp thoại ứng dụng
   - Thả ra để xác nhận lựa chọn

3. **Cấu Hình Cài Đặt** (tùy chọn):

   - **Ngôn ngữ nguồn**: Chọn ngôn ngữ của văn bản trong ứng dụng
   - **Khoảng thời gian cập nhật**: Điều chỉnh tốc độ cập nhật (50-5000ms)
     - Giá trị nhỏ hơn = cập nhật nhanh hơn nhưng tốn CPU hơn
     - Khuyến nghị: 100-200ms cho game, 200-300ms cho ứng dụng thường
   - **Engine OCR**: Chọn Tesseract hoặc EasyOCR
     - Tesseract: Mặc định, cần cài đặt Tesseract OCR, CPU usage thấp
     - EasyOCR: Chính xác hơn cho một số ngôn ngữ, cần cài: `pip install easyocr`
       - **EasyOCR Mode**: Chọn chế độ xử lý (chỉ hiện khi chọn EasyOCR)
         - **Tự động**: Tự động phát hiện và sử dụng GPU nếu có (mặc định)
         - **CPU**: Bắt buộc sử dụng CPU (khi muốn tiết kiệm GPU cho ứng dụng khác)
         - **GPU**: Bắt buộc sử dụng GPU (nếu có GPU và muốn tối ưu hiệu suất)
       - GPU mode giảm CPU usage từ 70-90% xuống <10%
       - CPU mode có throttling để giảm tải (1.5s interval)
   - **Ngôn ngữ đích**: Chọn ngôn ngữ muốn dịch sang
   - **Dịch vụ dịch thuật**: Chọn Google Translate hoặc DeepL
     - Google Translate: Miễn phí, không cần API key
     - DeepL: Chất lượng tốt hơn, cần API key (có phí)
       - Lấy API key tại: https://www.deepl.com/pro-api
       - Cần cài: `pip install deepl`

4. **Tùy Chỉnh Giao Diện Dịch** (tùy chọn):

   - Chọn tab "Giao Diện Dịch"
   - Sử dụng các nút "Cấu Hình Nhanh" để chọn preset (Tối Ưu Tốc Độ, Cân Bằng, Tối Ưu Chất Lượng, Mặc Định)
   - Hoặc tùy chỉnh thủ công: cỡ chữ, phông chữ, màu sắc, kích thước, độ trong suốt, v.v.
   - Tùy chọn "Lưu lịch sử dịch": Cho phép xem lại các bản dịch trước đó
   - Nhấn "Áp Dụng" sau khi thay đổi
   - Nhấn "Đặt Lại Tất Cả" để reset về mặc định (KHÔNG reset vùng chụp màn hình, engine OCR, dịch vụ dịch và DeepL key)

5. **Bắt Đầu Dịch**:

   - Nhấn "Bắt Đầu Dịch"
   - Một cửa sổ overlay trong suốt sẽ xuất hiện hiển thị bản dịch
   - Công cụ sẽ liên tục chụp, nhận dạng và dịch văn bản

6. **Dừng Dịch**:

   - Nhấn "Dừng Dịch" khi không cần dịch nữa

7. **Khóa Màn Hình Dịch**:
   - Chọn tab "Điều Khiển"
   - Tích vào "Khóa màn hình dịch" để ngăn di chuyển nhầm khi chơi game

## Cấu Hình

Công cụ tự động lưu cài đặt của bạn vào `config.json`:

- Tọa độ vùng chụp màn hình
- Ngôn ngữ nguồn và đích
- Engine OCR (Tesseract hoặc EasyOCR)
- EasyOCR Mode (Tự động/CPU/GPU) - nếu sử dụng EasyOCR
- Dịch vụ dịch thuật (Google hoặc DeepL)
- DeepL API Key (nếu sử dụng)
- Khoảng thời gian cập nhật
- Tất cả cài đặt tùy chỉnh giao diện (font, màu sắc, kích thước, v.v.)
- Vị trí và kích thước màn hình dịch
- Trạng thái khóa màn hình dịch
- Tùy chọn lưu lịch sử dịch

### Cache Files

Công cụ tự động tạo và quản lý các file cache:

- **`translation_cache.txt`**: Lưu cache các bản dịch đã thực hiện để giảm API calls
- **`preset_cache.txt`**: File preset cache chứa các bản dịch phổ biến, được load khi khởi động để tăng tốc độ
- **`error_log.txt`**: File log lỗi để debug (tự động tạo khi có lỗi)

**Lưu ý cho Developer:**

- Các file cache được lưu trong cùng thư mục với executable (khi build exe) hoặc thư mục chứa script
- `preset_cache.txt` được bundle vào exe và tự động extract ra thư mục exe khi chạy lần đầu
- Bạn có thể chỉnh sửa `preset_cache.txt` để thêm các bản dịch phổ biến cho ứng dụng của mình

## Đóng Gói Thành File Thực Thi (Packaging)

Để tạo file `.exe` để người dùng có thể chạy trực tiếp mà không cần cài đặt Python:

### Cách 1: Sử dụng build.bat (Khuyến nghị)

1. Mở Command Prompt hoặc PowerShell
2. Chạy lệnh:
   ```batch
   build.bat
   ```
3. File `.exe` sẽ được tạo trong thư mục `dist\RealTimeScreenTranslator.exe`

### Cách 2: Sử dụng PyInstaller trực tiếp

```batch
pip install pyinstaller
pyinstaller --onefile --windowed --name "RealTimeScreenTranslator" translator.py
```

### Cách 3: Sử dụng build.spec

```batch
pyinstaller build.spec
```

### Cách 4: Sử dụng script đóng gói tự động (Khuyến nghị cho production)

```batch
python package.py
```

Script này sẽ:

- Tự động build executable nếu chưa có
- Tạo file zip với tên: `RealTimeTrans-[version]-[timestampcode].zip`
- Bao gồm: `RealTimeScreenTranslator.exe` và `HUONG_DAN.txt`
- Ví dụ: `RealTimeTrans-1.0.1-143052.zip`

**Lưu ý:**

- File `.exe` sẽ khá lớn (khoảng 50-100MB) vì chứa toàn bộ Python và các thư viện
- Người dùng vẫn cần cài đặt Tesseract OCR riêng
- File `error_log.txt` sẽ được tạo tự động khi có lỗi xảy ra
- File `preset_cache.txt` được bundle vào exe và tự động extract ra thư mục exe khi chạy lần đầu
- File `translation_cache.txt` và `preset_cache.txt` được lưu trong cùng thư mục với exe

## Xử Lý Sự Cố

### OCR Không Hoạt Động

- Đảm bảo Tesseract OCR đã được cài đặt đúng và có trong PATH
- Kiểm tra vùng đã chọn có chứa văn bản rõ ràng, dễ đọc
- Thử điều chỉnh cài đặt ngôn ngữ nguồn
- Đảm bảo văn bản cần dịch rõ ràng (không quá nhỏ hoặc mờ)

### Lỗi Dịch

- Kiểm tra kết nối internet (Google Translate API cần internet)
- Nếu gặp giới hạn tốc độ, công cụ sẽ tự động thử lại

### Vấn Đề Hiệu Suất

- **EasyOCR CPU usage cao (70-90%)**:
  - Cài PyTorch với CUDA để sử dụng GPU: `install_pytorch_cuda.bat` hoặc xem hướng dẫn trong phần Cài Đặt
  - Tool sẽ tự động phát hiện và sử dụng GPU nếu có
  - Kiểm tra GPU: `python test_gpu.py`
- Tăng khoảng thời gian cập nhật để giảm sử dụng CPU
- Đảm bảo vùng chụp không quá lớn
- Đóng các ứng dụng tiêu tốn tài nguyên khác
- Sử dụng Tesseract nếu không cần độ chính xác cao (CPU usage thấp hơn nhiều)

### Cửa Sổ Overlay Không Hiển Thị

- Kiểm tra cửa sổ overlay không bị di chuyển ra ngoài màn hình
- Thử dừng và khởi động lại dịch
- Đảm bảo tỷ lệ hiển thị màn hình được đặt ở 100% (Windows)

### File EXE Không Chạy Được

Nếu file `.exe` không mở được hoặc bị crash ngay lập tức:

1. **Kiểm tra Dependencies (Trước khi build)**:

   ```bash
   python test_exe.py
   ```

   Script này sẽ kiểm tra tất cả các thư viện cần thiết.

2. **Build bản DEBUG để xem lỗi**:

   - Chạy `build.bat` và chọn option `2` (Debug)
   - Bản DEBUG sẽ hiển thị cửa sổ console với thông báo lỗi
   - Xem lỗi trong console để biết nguyên nhân

3. **Kiểm tra Error Log**:

   - Nếu exe đã chạy được một chút, kiểm tra file `error_log.txt` trong cùng thư mục với exe
   - File này sẽ chứa thông tin chi tiết về lỗi

4. **Các nguyên nhân thường gặp**:

   - **Thiếu Tesseract OCR**: Exe cần Tesseract được cài đặt trên máy. Tải từ: https://github.com/UB-Mannheim/tesseract/wiki
   - **Thiếu Visual C++ Redistributable**: Một số thư viện Python cần VC++ runtime. Tải từ Microsoft.
   - **Antivirus chặn**: Một số antivirus có thể chặn exe. Thử tắt tạm thời hoặc thêm vào whitelist.
   - **Windows Defender SmartScreen**: Click "More info" > "Run anyway" nếu Windows cảnh báo.

5. **Chạy từ Python thay vì exe**:

   ```bash
   python translator.py
   ```

   Nếu chạy được từ Python nhưng không chạy được exe, vấn đề có thể là do PyInstaller build.

6. **Rebuild exe**:
   - Xóa thư mục `build` và `dist` cũ
   - Chạy lại `build.bat` hoặc `python package.py`
   - Đảm bảo đã cài đặt đầy đủ: `pip install -r requirements.txt`

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

## Chi Tiết Kỹ Thuật

- **Chụp Màn Hình**: Sử dụng thư viện `mss` để chụp màn hình nhanh, hiệu quả
- **Công Cụ OCR**:
  - Tesseract OCR qua `pytesseract` (mặc định) - được quản lý bởi `TesseractOCRHandler`
  - EasyOCR (tùy chọn, chính xác hơn cho một số ngôn ngữ) - được quản lý bởi `EasyOCRHandler`
- **Xử Lý Hình Ảnh**: OpenCV để tiền xử lý hình ảnh (adaptive thresholding, binary thresholding, grayscale conversion, intelligent scaling)
- **Dịch Thuật**:
  - Google Translate API qua `deep-translator` (miễn phí)
  - DeepL API (chất lượng cao, có phí)
- **Giao Diện**: Tkinter (đã có sẵn trong Python)
- **Kiến Trúc**: Đa luồng với 3 threads riêng biệt:
  - Thread chụp màn hình
  - Thread xử lý OCR
  - Thread xử lý dịch thuật
- **Handlers Package**:
  - `TesseractOCRHandler`: Quản lý Tesseract OCR với các kỹ thuật tối ưu
    - Preprocessing: CLAHE (Contrast Limited Adaptive Histogram Equalization), morphological operations
    - Scaling: Tự động scale ảnh nhỏ lên để tăng độ chính xác
    - Confidence filtering: Lọc kết quả OCR dựa trên confidence score
    - Multi-scale processing: Thử nhiều tỷ lệ scale để chọn kết quả tốt nhất (tùy chọn)
  - `EasyOCRHandler`: Quản lý EasyOCR với tối ưu hiệu suất
    - GPU acceleration: Tự động phát hiện và sử dụng NVIDIA GPU (có thể chọn Tự động/CPU/GPU)
    - User control: Người dùng có thể chọn chế độ xử lý (auto-detect, force CPU, force GPU)
    - Throttling: Giới hạn tần suất gọi EasyOCR (1.5s CPU, 0.5s GPU)
    - Image resizing: Resize ảnh để giảm tải xử lý (600px CPU, 800px GPU)
    - Lazy initialization: Chỉ khởi tạo reader khi cần
    - Multi-scale processing: Thử nhiều tỷ lệ scale cho CPU mode (tùy chọn)
  - `TranslationCacheManager`: Quản lý translation cache với LRU cache và file persistence
    - Encoding detection: Tự động phát hiện encoding với `chardet` (fallback nếu không có)
    - Robust file handling: Xử lý file cache bị corrupt, tự động backup và recreate
- **Tối Ưu Hiệu Suất**:
  - Xử lý song song với ThreadPoolExecutor
  - Adaptive scan intervals: Tự động điều chỉnh tốc độ capture dựa trên số lượng OCR calls đang xử lý
  - LRU cache và file cache để giảm API calls
  - Preset cache để load các bản dịch phổ biến khi khởi động
  - Image hashing để bỏ qua frame trùng lặp
  - Throttling và deduplication để tránh rate limits
  - GPU acceleration cho EasyOCR (tự động phát hiện)

## 📁 Cấu Trúc Dự Án

```
real-time-trans/
├── translator.py              # File chính chứa UI và logic chính
├── handlers/                  # Package chứa các handlers cho OCR và cache
│   ├── __init__.py
│   ├── tesseract_ocr_handler.py    # Handler cho Tesseract OCR
│   ├── easyocr_handler.py          # Handler cho EasyOCR
│   └── cache_manager.py            # Handler quản lý translation cache
├── package.py                # Script tự động build và package
├── build.bat                 # Script build cho Windows
├── build.spec                # File cấu hình PyInstaller
├── test_exe.py              # Script kiểm tra dependencies
├── test_gpu.py              # Script kiểm tra GPU và PyTorch CUDA
├── install_pytorch_cuda.bat  # Script tự động cài PyTorch với CUDA
├── requirements.txt          # Danh sách thư viện Python cần thiết
├── preset_cache.txt          # File preset cache (bundle vào exe)
├── LICENSE
├── README.md                 # File này (dành cho developer)
├── HUONG_DAN.txt            # Hướng dẫn cho người dùng phổ thông
├── .gitignore
└── .github/
```

### Mô Tả Các File Chính

- **`translator.py`**: File chính chứa toàn bộ logic của công cụ:

  - Class `ScreenTranslator`: Quản lý UI, OCR, translation, và overlay window
  - Function `find_tesseract()`: Tự động tìm Tesseract OCR (hỗ trợ Windows, macOS, Linux)
  - Function `get_base_dir()`: Lấy thư mục gốc (hỗ trợ cả script và exe)
  - Function `log_error()`: Ghi log lỗi ra file
  - Class `RegionSelector`: Tool chọn vùng màn hình

- **`handlers/`**: Package chứa các handlers modular:

  - **`tesseract_ocr_handler.py`**:

    - Class `TesseractOCRHandler`: Quản lý Tesseract OCR với các kỹ thuật tối ưu
    - Preprocessing: adaptive thresholding, binary thresholding, grayscale conversion
    - Scaling: Tự động scale ảnh nhỏ lên để tăng độ chính xác
    - Confidence filtering: Lọc kết quả OCR dựa trên confidence score
    - Gaming-specific configs: Tối ưu cho game với whitelist characters

  - **`easyocr_handler.py`**:

    - Class `EasyOCRHandler`: Quản lý EasyOCR với tối ưu CPU
    - Throttling: Giới hạn tần suất gọi EasyOCR để giảm CPU
    - Image resizing: Resize ảnh để giảm tải xử lý
    - Lazy initialization: Chỉ khởi tạo reader khi cần
    - Reader reuse: Tái sử dụng reader để tránh reload model

  - **`cache_manager.py`**:
    - Class `TranslationCacheManager`: Quản lý translation cache
    - LRU cache: In-memory cache với LRU eviction
    - File cache: Persistent cache trong `translation_cache.txt`
    - Preset cache: Load `preset_cache.txt` khi khởi động
    - Hỗ trợ cả script và exe: Tự động detect và xử lý đúng đường dẫn

- **`package.py`**: Script tự động build executable và tạo file zip phân phối

- **`build.bat`**: Script build cho Windows, hỗ trợ cả Release và Debug build

- **`build.spec`**: File cấu hình PyInstaller với đầy đủ hidden imports và bundle `preset_cache.txt`

- **`test_exe.py`**: Script kiểm tra dependencies trước khi build exe (bao gồm chardet, torch)

- **`test_gpu.py`**: Script kiểm tra GPU availability, PyTorch CUDA, và EasyOCR GPU mode

- **`install_pytorch_cuda.bat`**: Script tự động uninstall CPU-only PyTorch và cài PyTorch với CUDA support

- **`preset_cache.txt`**: File preset cache chứa các bản dịch phổ biến, được bundle vào exe và load khi khởi động

## 🛠️ Development

Nếu bạn muốn phát triển hoặc đóng góp cho dự án:

1. **Clone repository:**

   ```bash
   git clone https://github.com/trchicuong/real-time-trans.git
   cd real-time-trans
   ```

2. **Tạo virtual environment (khuyến nghị):**

   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Linux/macOS
   source venv/bin/activate
   ```

3. **Cài đặt dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Kiểm tra dependencies:**

   ```bash
   python test_exe.py
   ```

5. **Kiểm tra GPU (nếu dùng EasyOCR):**

   ```bash
   python test_gpu.py
   ```

6. **Chạy công cụ:**

   ```bash
   python translator.py
   ```

7. **Build executable (tùy chọn):**
   ```bash
   # Windows
   build.bat
   # Hoặc
   python package.py
   ```

## 🤝 Đóng góp

Dự án này luôn chào đón các đóng góp! Nếu bạn muốn sửa lỗi, thêm tính năng mới, hoặc cải thiện mã nguồn, hãy thoải mái tạo một `Pull Request`.

### Quy Trình Pull Request

1. Fork repository
2. Clone fork của bạn: `git clone https://github.com/YOUR_USERNAME/real-time-trans.git`
3. Tạo branch: `git checkout -b feature/your-feature-name`
4. Commit changes: `git commit -m "Add: description of changes"`
5. Push to branch: `git push origin feature/your-feature-name`
6. Tạo Pull Request trên GitHub

### Credit

Dự án này sử dụng các thư viện mã nguồn mở:

- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) - Apache License 2.0
- [deep-translator](https://github.com/nidhaloff/deep-translator) - MIT License
- [OpenCV](https://opencv.org/) - Apache License 2.0
- [Pillow](https://python-pillow.org/) - PIL License
- [mss](https://github.com/BoboTiG/python-mss) - MIT License
- [EasyOCR](https://github.com/JaidedAI/EasyOCR) - Apache License 2.0 (tùy chọn)
- [PyTorch](https://pytorch.org/) - BSD License (tùy chọn, cho EasyOCR GPU support)
- [chardet](https://github.com/chardet/chardet) - LGPL License (tùy chọn, cho encoding detection)
- [DeepL API](https://www.deepl.com/docs-api) - Proprietary (tùy chọn, có phí)

### Kiến Trúc Code

Dự án được tổ chức theo mô hình modular với handlers package:

- **Separation of Concerns**: OCR logic được tách riêng vào handlers
- **Easy Extension**: Dễ dàng thêm engine OCR mới bằng cách tạo handler mới
- **Error Handling**: Tất cả lỗi được log vào `error_log.txt` với robust error handling và multiple fallbacks
- **Path Handling**: Tự động detect và xử lý đúng đường dẫn cho cả script và exe, hỗ trợ cross-platform
- **Cache Strategy**: LRU cache + file cache + preset cache với encoding detection và corruption handling
- **GPU Support**: Tự động phát hiện và sử dụng GPU cho EasyOCR, graceful fallback về CPU
- **Performance Optimization**: Adaptive scan intervals, multi-scale processing, intelligent throttling

## 🙏 Lời Cảm Ơn

- Cảm ơn tất cả contributors đã đóng góp cho dự án
- Cảm ơn các maintainers của các thư viện mã nguồn mở được sử dụng
- Cảm ơn cộng đồng open source

## Lưu Ý

- Công cụ yêu cầu kết nối internet để dịch
- Chất lượng dịch phụ thuộc vào độ chính xác OCR, có thể bị ảnh hưởng bởi:
  - Độ rõ và kích thước văn bản
  - Độ tương phản nền
  - Kiểu phông chữ
  - Độ phân giải màn hình
- Để có kết quả tốt nhất, đảm bảo hộp thoại văn bản có độ tương phản tốt và văn bản rõ ràng
