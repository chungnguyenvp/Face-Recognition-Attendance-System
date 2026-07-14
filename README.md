# Face Lab System

![Python](https://img.shields.io/badge/Python-3.10-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Uvicorn-009688)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-lightgrey)
![InsightFace](https://img.shields.io/badge/InsightFace-1.0.1-orange)
![License](https://img.shields.io/badge/License-MIT-green)

**Face Lab System** là hệ thống quản lý phòng lab dùng nhận diện khuôn mặt để check-in/check-out, quản lý sinh viên, quản lý FaceID, chống giả mạo khuôn mặt, xử lý đơn nghỉ phép và quản lý báo cáo sinh viên.

Dự án chạy bằng FastAPI, giao diện HTML/CSS/JavaScript thuần, SQLite và InsightFace trên CPU.

> ⚠️ **Hiện chỉ hỗ trợ Windows 10/11.** Hướng dẫn bên dưới dùng PowerShell. Có thể chạy trên Linux/macOS nếu tự điều chỉnh lệnh shell và đường dẫn cache InsightFace tương ứng.

---

## Mục Lục

- [Tính Năng Chính](#tính-năng-chính)
- [Kiến Trúc Hệ Thống](#kiến-trúc-hệ-thống)
- [Luồng Nhận Diện Khuôn Mặt](#luồng-nhận-diện-khuôn-mặt)
- [Công Nghệ](#công-nghệ)
- [Yêu Cầu Môi Trường](#yêu-cầu-môi-trường)
- [Cài Đặt Nhanh](#cài-đặt-nhanh)
- [Chạy Ứng Dụng](#chạy-ứng-dụng)
- [Cấu Hình Quan Trọng](#cấu-hình-quan-trọng)
- [Luồng Sử Dụng Cơ Bản](#luồng-sử-dụng-cơ-bản)
- [Vai Trò Và Quyền](#vai-trò-và-quyền)
- [Nhận Diện Khuôn Mặt](#nhận-diện-khuôn-mặt)
- [Chống Giả Mạo Khuôn Mặt](#chống-giả-mạo-khuôn-mặt)
- [Camera Và RTSP](#camera-và-rtsp)
- [Báo Cáo Sinh Viên](#báo-cáo-sinh-viên)
- [Xuất Báo Cáo Chấm Công](#xuất-báo-cáo-chấm-công)
- [Lưu Trữ Dữ Liệu Riêng Tư](#lưu-trữ-dữ-liệu-riêng-tư)
- [Kiểm Thử](#kiểm-thử)
- [Cấu Trúc Thư Mục](#cấu-trúc-thư-mục)
- [Sao Lưu Và Chia Sẻ Project](#sao-lưu-và-chia-sẻ-project)
- [Lỗi Thường Gặp](#lỗi-thường-gặp)
- [Đóng Góp](#đóng-góp)
- [License](#license)

---

## Tính Năng Chính

- Đăng nhập bằng session cookie, có CSRF và giới hạn số lần thử mật khẩu.
- Phân quyền 3 vai trò: `admin`, `lab_manager`, `student`.
- Quản lý hồ sơ sinh viên, tài khoản người dùng và ảnh FaceID.
- Đăng ký/cập nhật FaceID trực tiếp hoặc qua quy trình sinh viên gửi yêu cầu để lab manager duyệt.
- Nhận diện camera realtime cho check-in/check-out.
- Hỗ trợ camera trình duyệt, webcam/USB camera và camera RTSP/IP camera.
- Chống giả mạo khuôn mặt bằng model ONNX liveness/anti-spoofing.
- Quản lý lịch sử ra/vào, cảnh báo khuôn mặt lạ và xử lý thiếu checkout.
- Quản lý đơn nghỉ phép: sinh viên tạo đơn, lab manager duyệt/từ chối, admin có thể thu hồi.
- Quản lý báo cáo sinh viên: nộp file hoặc link, phản hồi, yêu cầu chỉnh sửa, duyệt và lưu lịch sử các lần nộp.
- Xuất báo cáo chấm công Excel theo ngày, trạng thái và sinh viên.
- Ghi audit log cho các hành động quan trọng.

---

## Kiến Trúc Hệ Thống

```mermaid
flowchart TB
    subgraph Client["Trình duyệt / Camera"]
        BC[Camera trình duyệt]
        UI[Giao diện HTML/CSS/JS]
    end

    subgraph Server["Backend FastAPI (Uvicorn)"]
        R[Router / API]
        AUTH[Auth & Session + CSRF]
        SVC[Service Layer]
        REPO[Repository Layer]
        SCAM[Server Camera - OpenCV VideoCapture]
        FACE[Face Engine - InsightFace]
        LIVE[Liveness - ONNX Runtime CPU]
    end

    subgraph Storage["Lưu trữ"]
        DB[(SQLite - face_lab.db)]
        PRIV[storage/private]
    end

    RTSP[RTSP / IP Camera]
    WEBCAM[Webcam / USB Camera]

    UI --> R
    BC --> R
    RTSP --> SCAM
    WEBCAM --> SCAM
    R --> AUTH --> SVC --> REPO --> DB
    SCAM --> FACE --> LIVE
    SVC --> FACE
    SVC --> PRIV
```

Phân tầng backend: **Router → Service → Repository**. Router nhận request và kiểm tra session/quyền, Service chứa logic nghiệp vụ, Repository thao tác với SQLite. File nhạy cảm nằm ngoài `web/static` và chỉ được phục vụ qua API sau khi kiểm quyền.

---

## Luồng Nhận Diện Khuôn Mặt

```mermaid
flowchart LR
    A[Khung hình camera] --> B[Detection - tìm khuôn mặt]
    B --> C{Có khuôn mặt?}
    C -- Không --> A
    C -- Có --> D[Liveness / Anti-spoofing]
    D --> E{Thật hay giả?}
    E -- Giả --> F[Từ chối + cảnh báo]
    E -- Thật --> G[Recognition - trích embedding]
    G --> H{So khớp >= FACE_THRESHOLD?}
    H -- Không --> I[Khuôn mặt lạ + cảnh báo]
    H -- Có --> J[Ghi check-in / check-out + log]
```

---

## Công Nghệ

| Thành phần | Công nghệ |
| --- | --- |
| Backend | FastAPI, Uvicorn |
| Frontend | HTML, CSS, JavaScript |
| Database | SQLite |
| Nhận diện khuôn mặt | InsightFace 1.0.1 |
| Runtime AI | ONNX Runtime CPU |
| Xử lý ảnh/camera | OpenCV, Pillow, NumPy |
| Cấu hình | `.env`, pydantic-settings |

---

## Yêu Cầu Môi Trường

- Windows 10/11.
- Python 3.10, khuyến nghị dùng conda environment tên `python10`.
- Webcam, USB camera hoặc RTSP/IP camera nếu dùng điểm danh realtime.
- Internet cho lần chạy đầu nếu máy chưa có model InsightFace `buffalo_l`.
- File model anti-spoofing nếu bật liveness: `models/anti_spoofing/best_model_quantized.onnx`.

---

## Cài Đặt Nhanh

Mở PowerShell tại thư mục dự án chứa file `run.py`, sau đó chạy:

```powershell
conda create -n python10 python=3.10 -y
conda activate python10
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Nếu không dùng conda, có thể dùng virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

---

## Chạy Ứng Dụng

```powershell
conda activate python10
python run.py
```

Mở trình duyệt tại:

```text
http://localhost:8002
```

Tài khoản admin mặc định được lấy từ `.env`:

```env
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=admin123
```

> 🔐 Giá trị `admin/admin123` chỉ nên dùng ở máy local. Khi chạy thật, hãy đổi `SECRET_KEY`, `DEFAULT_ADMIN_USERNAME` và `DEFAULT_ADMIN_PASSWORD`.

---

## Cấu Hình Quan Trọng

File cấu hình local là `.env`, được tạo từ `.env.example`.

```env
APP_NAME=Face Lab System
SECRET_KEY=change-this-to-a-long-random-secret-key
DATABASE_PATH=data/face_lab.db
INSIGHTFACE_MODEL=buffalo_l
INSIGHTFACE_DET_SIZE=640
FACE_THRESHOLD=0.55
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=admin123
HTTPS_ENABLED=false
```

Các cấu hình nên đổi khi triển khai thật:

```env
SECRET_KEY=<chuoi-ngau-nhien-dai>
DEFAULT_ADMIN_USERNAME=<ten-admin>
DEFAULT_ADMIN_PASSWORD=<mat-khau-manh>
HTTPS_ENABLED=true
TRUSTED_HOSTS=<domain-hoac-ip-duoc-phep>
```

> ⚠️ Không đưa file `.env` lên Git, không gửi qua chat và không đóng gói vào ZIP chia sẻ công khai.

---

## Luồng Sử Dụng Cơ Bản

1. Đăng nhập bằng tài khoản admin.
2. Tạo hồ sơ sinh viên trong mục quản lý sinh viên.
3. Tạo tài khoản `student` và liên kết với đúng hồ sơ sinh viên.
4. Tạo tài khoản `lab_manager` nếu cần người vận hành phòng lab.
5. Đăng ký FaceID cho sinh viên hoặc để sinh viên gửi yêu cầu đăng ký FaceID.
6. Cấu hình webcam hoặc RTSP camera trong file `.env`.
7. Dùng camera realtime để check-in/check-out.
8. Sinh viên nộp báo cáo, lab manager phản hồi hoặc duyệt báo cáo.

---

## Vai Trò Và Quyền

| Chức năng | admin | lab_manager | student |
| --- | --- | --- | --- |
| Dashboard quản trị/vận hành | Có | Có | Không |
| Camera realtime | Có | Có | Không |
| Quản lý sinh viên | Có | Có, nhưng không xóa sinh viên | Không |
| Đăng ký FaceID | Có | Có | Gửi yêu cầu |
| Duyệt yêu cầu FaceID | Có | Có | Không |
| Xem logs và điểm danh | Có | Có | Chỉ dữ liệu của mình |
| Xử lý thiếu checkout/cảnh báo | Có | Có | Không |
| Xóa logs/cảnh báo | Có | Không | Không |
| Cài đặt threshold/model/camera | Có | Chỉ đọc một phần | Không |
| Tạo admin/lab_manager | Có | Không | Không |
| Tạo tài khoản student | Có | Có | Không |
| Đơn nghỉ phép | Quản lý/thu hồi | Duyệt/từ chối | Tạo và theo dõi |
| Báo cáo sinh viên | Giám sát/xử lý | Phản hồi và duyệt | Nộp và nộp lại |
| Xuất báo cáo chấm công Excel | Có | Có | Không |

---

## Nhận Diện Khuôn Mặt

Dự án dùng `insightface==1.0.1` trong `requirements.txt`.

Cấu hình model mặc định:

```env
INSIGHTFACE_MODEL=buffalo_l
INSIGHTFACE_DET_SIZE=640
FACE_THRESHOLD=0.55
```

Trong code, Face Lab dùng `FaceAnalysis` với:

```text
allowed_modules=["detection", "recognition"]
providers=["CPUExecutionProvider"]
```

Model `buffalo_l` thường không nằm trong thư mục project. InsightFace lưu model ở cache của user Windows sau lần tải đầu:

```text
C:\Users\<ten-user>\.insightface\models\buffalo_l
```

Nếu copy project sang máy khác và máy đó không có internet, hãy chuẩn bị sẵn thư mục `buffalo_l` ở cache tương ứng. Nếu muốn đóng gói model vào trong project, cần chỉnh code để truyền `root` cho `FaceAnalysis` và đặt đúng cấu trúc `<root>/models/buffalo_l`.

---

## Chống Giả Mạo Khuôn Mặt

Dự án hỗ trợ liveness/anti-spoofing bằng ONNX Runtime CPU.

Cấu hình mặc định:

```env
LIVENESS_ENABLED=true
ANTI_SPOOF_MODEL_PATH=models/anti_spoofing/best_model_quantized.onnx
LIVENESS_THRESHOLD=0.5
LIVENESS_REAL_CLASS_INDEX=0
LIVENESS_INPUT_SIZE=128
LIVENESS_CROP_SCALE=1.5
LIVENESS_MIN_FACE_SIZE=80
LIVENESS_MIN_BRIGHTNESS=35
LIVENESS_MIN_BLUR=18
LIVENESS_EDGE_MARGIN=5
```

Model mặc định cần ảnh RGB `128x128`, giá trị pixel `0..1` và output 2 logits dạng:

```text
[real, spoof]
```

Model `models/anti_spoofing/best_model_quantized.onnx` được lấy từ:

```text
https://github.com/facenox/face-antispoof-onnx
License: Apache-2.0
```

File model này nhỏ, đang được giữ trong project để người khác clone về có thể chạy liveness ngay mà không cần tải thêm model anti-spoofing. Nếu kết quả real/fake bị đảo, kiểm tra lại `LIVENESS_REAL_CLASS_INDEX`.

---

## Camera Và RTSP

Camera chấm công luôn do backend đọc bằng OpenCV `VideoCapture`, dùng cho
webcam/USB camera hoặc RTSP/IP camera. Camera trình duyệt chỉ còn được dùng cho
tính năng đăng ký khuôn mặt và không tham gia luồng chấm công.

Cấu hình webcam laptop:

```env
AUTO_START_CAMERAS=true
CHECK_IN_CAMERA_SOURCE=0
CHECK_OUT_CAMERA_SOURCE=
```

Cấu hình RTSP/IP camera:

```env
AUTO_START_CAMERAS=true
CHECK_IN_CAMERA_SOURCE=rtsp://user:pass@192.168.1.50:554/stream1
CHECK_OUT_CAMERA_SOURCE=rtsp://user:pass@192.168.1.51:554/stream1
SERVER_CAMERA_PREVIEW_FPS=8
SERVER_CAMERA_JPEG_QUALITY=80
```

Lưu ý:

- `0`, `1`, `2` là webcam/USB camera trên máy.
- URL `rtsp://...` dùng cho IP camera.
- Khi `AUTO_START_CAMERAS=true`, server tự start camera sau khi khởi động.
- Nguồn camera và chế độ tự khởi động chỉ được cấu hình trong `.env`; trang Settings không lưu các giá trị này.
- Sau khi đổi nguồn camera trong `.env`, cần khởi động lại backend.
- Không ghi URL RTSP chứa mật khẩu vào README, source code hoặc `.env.example`.

API điều khiển server camera. Tất cả endpoint yêu cầu session hợp lệ với quyền `admin` hoặc `lab_manager`:

```text
GET  /api/server-cameras/status
GET  /api/server-cameras/check_in/stream
GET  /api/server-cameras/check_out/stream
POST /api/server-cameras/check_in/start
POST /api/server-cameras/check_in/stop
POST /api/server-cameras/check_out/start
POST /api/server-cameras/check_out/stop
POST /api/server-cameras/start-all
POST /api/server-cameras/stop-all
```

Dashboard luôn dùng camera do backend quản lý: hình ảnh được phát bằng MJPEG,
nút bật/tắt gọi API server camera và canvas lấy `last_result` từ API trạng thái
để vẽ bounding box. API trạng thái được gọi mỗi giây. Đóng trình duyệt không
dừng camera backend; khi `AUTO_START_CAMERAS=true`, camera vẫn nhận diện và ghi
log dù không có người mở dashboard.

Endpoint MJPEG dùng chung camera thread đang chạy, không mở thêm `VideoCapture`
cho từng người xem. Endpoint yêu cầu tài khoản `admin` hoặc `lab_manager`, không
cache hình ảnh và API trạng thái che thông tin đăng nhập nằm trong URL RTSP.

Mỗi lần khởi động camera có một realtime session scope riêng. Phiếu liveness,
trạng thái người chưa nhận diện và cleanup chỉ hoạt động trong scope đó, nên
nhiều nguồn không cộng dồn phiếu của nhau. Session được xóa khi camera dừng.

---

## Báo Cáo Sinh Viên

Sinh viên có thể nộp báo cáo cho một tài khoản `lab_manager`.

Luồng chính:

1. Sinh viên nhập tiêu đề, loại báo cáo, giáo viên/lab manager nhận và mô tả.
2. Sinh viên đính kèm file hoặc link GitHub/Google Drive.
3. Lab manager xem báo cáo, phản hồi, yêu cầu chỉnh sửa hoặc duyệt.
4. Khi bị yêu cầu chỉnh sửa, sinh viên nộp lại bản mới.
5. Hệ thống giữ lịch sử các lần nộp và phản hồi.

Định dạng file hỗ trợ:

```text
PDF, DOC, DOCX, PPT, PPTX, XLSX, ZIP, PNG, JPG, JPEG
```

Mỗi file tối đa 20 MB.

---

## Xuất Báo Cáo Chấm Công

Admin và lab manager có thể mở mục **Điểm danh**, chọn **Xuất Excel**, sau đó lọc theo khoảng ngày, trạng thái hoặc một sinh viên cụ thể. Để trống ô sinh viên để xuất tất cả.

File `.xlsx` gồm tối đa hai trang tùy lựa chọn:

- `Tong_hop`: thống kê theo sinh viên, gồm ngày cần hiện diện, ngày có mặt, đi muộn, về sớm, vắng, nghỉ phép, thiếu checkout và tỷ lệ hiện diện.
- `Chi_tiet`: từng bản ghi chấm công, giờ vào/ra, trạng thái, số phút vi phạm, tổng giờ và ghi chú.

API tương ứng:

```http
POST /api/exports/attendance
Content-Type: application/json
X-CSRF-Token: <csrf_token>
```

```json
{
  "date_from": "2026-07-01",
  "date_to": "2026-07-31",
  "status": null,
  "q": null,
  "include_summary": true,
  "include_details": true
}
```

Mỗi lần xuất tối đa 366 ngày và 50.000 dòng. Thao tác xuất không tự tính lại dữ liệu chấm công, được ghi audit log, và file không chứa ảnh, embedding khuôn mặt, bằng chứng camera hay thông tin đăng nhập.

---

## Lưu Trữ Dữ Liệu Riêng Tư

Các file nhạy cảm không nằm trong `web/static` và không được truy cập trực tiếp bằng URL.

```text
data/face_lab.db
storage/private/faces/            # Ảnh FaceID đã duyệt
storage/private/face_requests/    # Ảnh yêu cầu FaceID chờ duyệt
storage/private/evidence/         # Ảnh bằng chứng camera/cảnh báo
storage/private/student_reports/  # File báo cáo sinh viên
```

API kiểm tra session và quyền trước khi trả file. Khi sao lưu dữ liệu, cần sao lưu cả database SQLite và thư mục `storage/private`.

> 🔐 **Dữ liệu cá nhân:** `data/face_lab.db` và `storage/private` có thể chứa dữ liệu sinh viên thật (ảnh khuôn mặt, embedding, lịch sử ra/vào). Cân nhắc kỹ trước khi chia sẻ công khai; với dữ liệu thật cần tuân thủ quy định bảo vệ dữ liệu cá nhân hiện hành.

### Nâng Cấp Database

Ứng dụng lưu lịch sử migration trong bảng `schema_migrations`. Trước lần khởi động đầu tiên sau khi cập nhật code, hãy dừng server và tạo một bản sao lưu SQLite nhất quán cùng thư mục `storage/private`.

Migration sửa liên kết tài khoản sinh viên sẽ:

- Giữ nguyên ID, username, password hash, vai trò và dữ liệu hợp lệ.
- Chuyển tài khoản `student` có liên kết hồ sơ không tồn tại sang `inactive`.
- Xóa liên kết `student_id` không hợp lệ và thu hồi session của tài khoản đó.
- Bổ sung foreign key `users.student_id -> students.id` với `ON DELETE SET NULL`.
- Bổ sung ràng buộc `request_type IN ('initial', 'update')` cho yêu cầu FaceID.

Không copy nóng riêng file `face_lab.db` khi WAL đang hoạt động. Nên dùng SQLite Backup API hoặc dừng ứng dụng trước khi sao lưu.

---

## Kiểm Thử

Chạy bằng đúng interpreter của môi trường dự án:

```powershell
conda activate python10
python -m compileall app tests
python -m pytest
```

Nếu đã cài dependency dev:

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check app tests
```

---

## Cấu Trúc Thư Mục

```text
app/                    Backend FastAPI: router, service, repository, schema
app/migrations.py       Migration SQLite có version và kiểm tra toàn vẹn
web/                    Giao diện HTML/CSS/JavaScript
data/                   SQLite database local
storage/private/        File riêng tư, chỉ truy cập qua API có kiểm quyền
models/anti_spoofing/   Model ONNX chống giả mạo khuôn mặt
tests/                  Automated tests
run.py                  Điểm khởi động local
requirements.txt        Dependency chính
requirements-dev.txt    Dependency phục vụ kiểm thử/lint
.env.example            Mẫu cấu hình, không chứa secret thật
```

---

## Sao Lưu Và Chia Sẻ Project

Khi đóng gói project cho máy khác, nên giữ:

```text
app/
web/
tests/
models/
requirements*.txt
run.py
.env.example
data/face_lab.db
storage/private/faces/
```

Không nên đóng gói:

```text
.env
__pycache__/
.pytest_cache/
.ruff_cache/
log file
backup tạm
URL RTSP có mật khẩu
```

Nếu máy nhận project chưa có `buffalo_l`, cần internet cho lần chạy đầu hoặc copy sẵn cache InsightFace:

```text
C:\Users\<ten-user>\.insightface\models\buffalo_l
```

---

## Lỗi Thường Gặp

### `ModuleNotFoundError: No module named 'insightface'`

Bạn đang chạy sai Python environment. Kiểm tra lại:

```powershell
conda activate python10
python -c "import insightface; print(insightface.__version__)"
```

Kết quả mong muốn:

```text
1.0.1
```

### Không load được model `buffalo_l`

Máy có thể chưa có cache model InsightFace. Chạy lần đầu với internet hoặc copy thư mục `buffalo_l` vào:

```text
C:\Users\<ten-user>\.insightface\models\buffalo_l
```

### Camera không mở được

Kiểm tra `CHECK_IN_CAMERA_SOURCE`, `CHECK_OUT_CAMERA_SOURCE`, quyền truy cập camera của Windows và URL RTSP. Với webcam laptop, thử lần lượt `0`, `1`, `2`.

### Liveness luôn báo sai

Kiểm tra `ANTI_SPOOF_MODEL_PATH`, `LIVENESS_REAL_CLASS_INDEX`, ánh sáng, độ nét ảnh và kích thước mặt trong khung hình.

---

## Đóng Góp

1. Fork repository và tạo branch mới: `git checkout -b feature/ten-tinh-nang`.
2. Cài dependency dev và đảm bảo test + lint xanh trước khi commit:

   ```powershell
   python -m pip install -r requirements-dev.txt
   python -m pytest
   python -m ruff check app tests
   ```

3. Không commit `.env`, secret, dữ liệu sinh viên thật hay URL RTSP có mật khẩu.
4. Mở Pull Request kèm mô tả thay đổi rõ ràng.

---

## License

Mã nguồn dự án phát hành theo **MIT License** (xem file `LICENSE`).

Model anti-spoofing đi kèm thuộc về dự án gốc và giữ nguyên license riêng:

```text
https://github.com/facenox/face-antispoof-onnx
License: Apache-2.0
```

Model nhận diện khuôn mặt `buffalo_l` thuộc về InsightFace, tuân theo điều khoản sử dụng của InsightFace.
