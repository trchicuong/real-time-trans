# 🖥️ Real-Time Screen Translator - Việt Nam

Tool Python mã nguồn mở giúp dịch văn bản thời gian thực trên màn hình bằng cách chụp vùng màn hình, nhận dạng văn bản (OCR), và dịch sang tiếng Việt.

## Yêu Cầu

- Python 3.7 trở lên
- Tesseract OCR đã cài đặt trên máy

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

3. (Tùy chọn) Nếu Tesseract không có trong PATH, bạn có thể cần cấu hình:
   - Sử dụng nút "Duyệt" trong giao diện để chọn đường dẫn Tesseract
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

   - Chọn ngôn ngữ nguồn của văn bản ứng dụng
   - Điều chỉnh khoảng thời gian cập nhật (thấp hơn = cập nhật thường xuyên hơn, nhưng tốn CPU hơn)

4. **Tùy Chỉnh Giao Diện Dịch** (tùy chọn):

   - Chọn tab "Giao Diện Dịch"
   - Sử dụng các nút "Cấu Hình Nhanh" để chọn preset (Tối Ưu Tốc Độ, Cân Bằng, Tối Ưu Chất Lượng, Mặc Định)
   - Hoặc tùy chỉnh thủ công: cỡ chữ, phông chữ, màu sắc, kích thước, độ trong suốt, v.v.
   - Nhấn "Áp Dụng" sau khi thay đổi
   - Nhấn "Đặt Lại Tất Cả" để reset về mặc định

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

- Tọa độ vùng chụp
- Ngôn ngữ nguồn
- Khoảng thời gian cập nhật
- Tất cả cài đặt tùy chỉnh giao diện
- Vị trí và kích thước màn hình dịch
- Trạng thái khóa màn hình dịch

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
- Ví dụ: `RealTimeTrans-v1.0.0-143052.zip`

**Lưu ý:**

- File `.exe` sẽ khá lớn (khoảng 50-100MB) vì chứa toàn bộ Python và các thư viện
- Người dùng vẫn cần cài đặt Tesseract OCR riêng
- File `error_log.txt` sẽ được tạo tự động khi có lỗi xảy ra

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

- Tăng khoảng thời gian cập nhật để giảm sử dụng CPU
- Đảm bảo vùng chụp không quá lớn
- Đóng các ứng dụng tiêu tốn tài nguyên khác

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

- Tiếng Việt (vi) - cố định

## Chi Tiết Kỹ Thuật

- **Chụp Màn Hình**: Sử dụng thư viện `mss` để chụp màn hình nhanh, hiệu quả
- **Công Cụ OCR**: Tesseract OCR qua `pytesseract`
- **Xử Lý Hình Ảnh**: OpenCV để tiền xử lý hình ảnh (thresholding, chuyển đổi grayscale)
- **Dịch**: Google Translate API qua `deep-translator`
- **Giao Diện**: Tkinter (đã có sẵn trong Python)

## 📁 Cấu Trúc Dự Án

```
real-time-trans/
├── translator.py
├── package.py
├── build.bat
├── build.spec
├── test_exe.py
├── requirements.txt
├── LICENSE
├── README.md
├── HUONG_DAN.txt
├── .gitignore
└── .github/
```

### Mô Tả Các File Chính

- **`translator.py`**: File chính chứa toàn bộ logic của công cụ:

  - Class `ScreenTranslator`: Quản lý UI, OCR, translation, và overlay window
  - Function `find_tesseract()`: Tự động tìm Tesseract OCR
  - Function `log_error()`: Ghi log lỗi ra file
  - Class `RegionSelector`: Tool chọn vùng màn hình

- **`package.py`**: Script tự động build executable và tạo file zip phân phối

- **`build.bat`**: Script build cho Windows, hỗ trợ cả Release và Debug build

- **`build.spec`**: File cấu hình PyInstaller với đầy đủ hidden imports

- **`test_exe.py`**: Script kiểm tra dependencies trước khi build exe

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

5. **Chạy công cụ:**

   ```bash
   python translator.py
   ```

6. **Build executable (tùy chọn):**
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
