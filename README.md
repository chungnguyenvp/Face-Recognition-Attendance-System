# Face Lab System

![Python](https://img.shields.io/badge/Python-3.10-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115.6-009688)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-lightgrey)
![Database](https://img.shields.io/badge/Database-SQLite-0f80cc)
![Tests](https://img.shields.io/badge/tests-123%20passed-brightgreen)

Face Lab System là hệ thống quản lý phòng lab dùng nhận diện khuôn mặt để check-in/check-out. Hệ thống kết hợp quản lý sinh viên, FaceID, lịch làm việc, chấm công, đơn nghỉ phép, báo cáo sinh viên, cảnh báo và xuất báo cáo Excel trong một ứng dụng FastAPI.

Backend sử dụng FastAPI và SQLite; giao diện được viết bằng HTML/CSS/JavaScript thuần; nhận diện khuôn mặt chạy bằng InsightFace và ONNX Runtime trên CPU.

> Dự án hiện được phát triển và kiểm thử chủ yếu trên Windows 10/11 với Python 3.10. Camera chấm công do backend trực tiếp quản lý; camera trình duyệt chỉ dùng để chụp ảnh đăng ký FaceID.

## Mục lục

- [Đánh giá trạng thái dự án](#đánh-giá-trạng-thái-dự-án)
- [Tính năng](#tính-năng)
- [Kiến trúc](#kiến-trúc)
- [Vai trò và phân quyền](#vai-trò-và-phân-quyền)
- [Cài đặt và khởi chạy](#cài-đặt-và-khởi-chạy)
- [Cấu hình](#cấu-hình)
- [Quy trình sử dụng ban đầu](#quy-trình-sử-dụng-ban-đầu)
- [FaceID, nhận diện và liveness](#faceid-nhận-diện-và-liveness)
- [Camera chấm công](#camera-chấm-công)
- [Lịch làm việc và chấm công](#lịch-làm-việc-và-chấm-công)
- [Đơn nghỉ và báo cáo sinh viên](#đơn-nghỉ-và-báo-cáo-sinh-viên)
- [Xuất báo cáo chấm công](#xuất-báo-cáo-chấm-công)
- [Database và migration](#database-và-migration)
- [Bảo mật, lưu trữ và sao lưu](#bảo-mật-lưu-trữ-và-sao-lưu)
- [Tổng quan API](#tổng-quan-api)
- [Kiểm thử](#kiểm-thử)
- [Cấu trúc thư mục](#cấu-trúc-thư-mục)
- [Triển khai thực tế](#triển-khai-thực-tế)
- [Lỗi thường gặp](#lỗi-thường-gặp)
- [Giới hạn và giấy phép](#giới-hạn-và-giấy-phép)

## Đánh giá trạng thái dự án

### Điểm mạnh

- Backend tách thành Router → Service → Repository, thuận lợi cho kiểm thử và bảo trì.
- Có ba vai trò rõ ràng: `admin`, `lab_manager`, `student`.
- Session lưu phía server và được thu hồi khi đổi mật khẩu, khóa hoặc xóa tài khoản.
- Có CSRF, giới hạn đăng nhập sai, PBKDF2, security headers và audit log.
- File khuôn mặt, ảnh bằng chứng và báo cáo sinh viên nằm ngoài `web/static`.
- Migration SQLite có version, kiểm tra số lượng dữ liệu và foreign key sau nâng cấp.
- Camera check-in/check-out dùng session realtime độc lập, tránh trộn trạng thái giữa hai nguồn.
- Có quy trình đầy đủ cho FaceID, đơn nghỉ, báo cáo sinh viên và xuất Excel.
- Baseline hiện tại: `123 passed`, 4 subtest; Ruff và 14 file JavaScript đều đạt.

### Giới hạn cần biết

- Phù hợp nhất với một máy chủ nội bộ hoặc một phòng lab, chưa phải kiến trúc phân tán.
- SQLite và camera worker chạy trong cùng tiến trình; không nên chạy nhiều Uvicorn worker.
- InsightFace và liveness dùng CPU, hiệu năng phụ thuộc máy và độ phân giải camera.
- Chưa có Dockerfile, pipeline CI/CD hoặc bộ cài Windows trong repository.
- API docs bị tắt mặc định.
- Repository chưa có file `LICENSE`; README cũ ghi MIT nhưng chưa có căn cứ trong repository để xác nhận.

## Tính năng

- Đăng nhập bằng session cookie, CSRF token và giới hạn đăng nhập sai.
- Quản lý sinh viên, tài khoản và liên kết mỗi tài khoản student với đúng một hồ sơ.
- Đăng ký FaceID trực tiếp hoặc qua quy trình sinh viên gửi yêu cầu 5 góc mặt.
- Nhận diện realtime từ webcam/USB hoặc RTSP/IP camera do backend quản lý.
- Kiểm tra chất lượng ảnh và liveness trước khi chấp nhận nhận diện.
- Log check-in/check-out, ảnh bằng chứng, cảnh báo unknown và spoof.
- Chấm công theo lịch tuần, ngày đặc biệt, đơn nghỉ và giờ làm riêng.
- Xử lý thiếu check-out tự động hoặc thủ công.
- Đơn nghỉ phép và báo cáo sinh viên có lịch sử xử lý/version.
- Xuất báo cáo chấm công Excel gồm tổng hợp và chi tiết.
- Audit log cho các thao tác quan trọng.

## Kiến trúc

```mermaid
flowchart TB
    subgraph Client["Trình duyệt"]
        StaffUI["Dashboard staff"]
        StudentUI["Cổng sinh viên"]
        BrowserCamera["Camera trình duyệt - chỉ đăng ký FaceID"]
    end
    subgraph Server["FastAPI"]
        Router["Router + Auth + CSRF"]
        Service["Service nghiệp vụ"]
        Repository["Repository SQLite"]
        CameraManager["Server Camera Manager"]
        FaceEngine["InsightFace"]
        Liveness["ONNX Liveness"]
        Worker["Missing-checkout scheduler"]
    end
    subgraph Storage["Lưu trữ local"]
        DB[("SQLite")]
        Private["storage/private"]
        Models["Model ONNX + cache InsightFace"]
    end
    Webcam["Webcam / USB"] --> CameraManager
    RTSP["RTSP / IP"] --> CameraManager
    StaffUI --> Router
    StudentUI --> Router
    BrowserCamera --> Router
    Router --> Service --> Repository --> DB
    CameraManager --> FaceEngine --> Liveness
    FaceEngine --> Models
    Service --> Private
    Worker --> DB
```

Khi ứng dụng khởi động, lifespan khởi tạo/migrate database, quét thiếu check-out, chạy scheduler, nạp model AI và tự mở camera nếu `AUTO_START_CAMERAS=true`.

## Vai trò và phân quyền

| Chức năng | `admin` | `lab_manager` | `student` |
| --- | --- | --- | --- |
| Dashboard vận hành | Có | Có | Không |
| Cổng sinh viên | Không | Không | Có |
| Xem/tạo/sửa hồ sơ sinh viên | Có | Có | Không |
| Xóa hồ sơ sinh viên | Có | Không | Không |
| Quản lý tài khoản student | Có | Có | Không |
| Quản lý admin/lab manager | Có | Không | Không |
| Đăng ký FaceID trực tiếp | Có | Có | Không |
| Gửi yêu cầu FaceID | Không | Không | Có |
| Duyệt yêu cầu FaceID | Có | Có | Không |
| Điều khiển camera chấm công | Có | Có | Không |
| Xem log và chấm công | Có | Có | Chỉ dữ liệu của mình |
| Sửa lịch làm việc/ngày đặc biệt | Có | Chỉ xem | Không |
| Xử lý thiếu check-out | Có | Có | Không |
| Xóa log/cảnh báo | Có | Không | Không |
| Cập nhật cài đặt | Có | Chỉ xem | Không |
| Xem audit log | Có | Không | Không |
| Đơn nghỉ phép | Quản lý/thu hồi | Duyệt/từ chối | Tạo/theo dõi/hủy |
| Báo cáo sinh viên | Xem/xử lý | Xem/xử lý | Nộp/nộp lại |
| Xuất báo cáo chấm công | Có | Có | Không |

Lab manager chỉ nhìn thấy và quản lý tài khoản `student`. Hệ thống không cho khóa hoặc xóa admin active cuối cùng.

## Cài đặt và khởi chạy

### Yêu cầu

- Windows 10/11, Python 3.10 64-bit.
- Webcam/USB hoặc camera RTSP nếu dùng realtime.
- Internet trong lần đầu nếu máy chưa có InsightFace `buffalo_l`.
- Model liveness tại `models/anti_spoofing/best_model_quantized.onnx`.

Model InsightFace thường được cache tại:

```text
C:\Users\<username>\.insightface\models\buffalo_l
```

### Cài bằng conda

```powershell
conda create -n python10 python=3.10 -y
conda activate python10
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

### Cài bằng venv

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Nếu PowerShell chặn script kích hoạt:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

### Chạy local để phát triển

```powershell
python run.py
```

Ứng dụng mở tại `http://localhost:8002`. `run.py` bật `reload=True`, chỉ phù hợp cho phát triển.

### Chạy không reload

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

### Truy cập trong LAN

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8002
```

Khi mở ra LAN, phải cấu hình `TRUSTED_HOSTS`, firewall và HTTPS/reverse proxy. Chỉ chạy một worker cho instance quản lý SQLite/camera này.

| Địa chỉ | Ý nghĩa |
| --- | --- |
| `/login` | Đăng nhập |
| `/` | Dashboard theo vai trò |
| `/health` | Health check |
| `/docs`, `/redoc` | Chỉ có khi `PUBLIC_DOCS_ENABLED=true` |

Admin mặc định được tạo khi khởi tạo database lần đầu:

```env
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=admin123
```

> Đổi các biến trên sau khi database đã tồn tại không tự đổi tài khoản hiện có. Hãy đổi mật khẩu trong trang quản lý tài khoản.

## Cấu hình

Tạo `.env` từ `.env.example`. Không commit hoặc chia sẻ công khai file này.

### Ứng dụng và xác thực

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `APP_NAME` | `Face Lab System` | Tên ứng dụng |
| `SECRET_KEY` | Giá trị mẫu không an toàn | Ký session token |
| `DATABASE_PATH` | `data/face_lab.db` | SQLite database |
| `TRUSTED_HOSTS` | `127.0.0.1,localhost` | Host được phép |
| `PUBLIC_DOCS_ENABLED` | `false` | Bật OpenAPI docs |
| `HEALTH_DETAILS_ENABLED` | `false` | Trả trạng thái model trong `/health` |
| `HTTPS_ENABLED` | `false` | Cookie Secure và HSTS |
| `SESSION_MAX_AGE_SECONDS` | `28800` | Session 8 giờ |
| `LOGIN_MAX_FAILED_ATTEMPTS` | `10` | Số lần sai trước khóa tạm |
| `LOGIN_ATTEMPT_WINDOW_SECONDS` | `900` | Cửa sổ đếm lỗi |
| `LOGIN_LOCKOUT_SECONDS` | `900` | Thời gian khóa |
| `PASSWORD_PBKDF2_ITERATIONS` | `600000` | Số vòng PBKDF2 |

### Nhận diện và camera

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `INSIGHTFACE_MODEL` | `buffalo_l` | Model InsightFace |
| `INSIGHTFACE_DET_SIZE` | `640` | Kích thước detection |
| `FACE_THRESHOLD` | `0.55` | Ngưỡng similarity ban đầu |
| `CHECK_COOLDOWN_SECONDS` | `30` | Chống ghi sự kiện lặp |
| `FRAME_SKIP` | `2` trong `.env.example` | Chu kỳ bỏ frame |
| `AUTO_START_CAMERAS` | `false` | Tự mở camera khi server chạy |
| `CHECK_IN_CAMERA_SOURCE` | `0` | Webcam index hoặc RTSP |
| `CHECK_OUT_CAMERA_SOURCE` | trống | Camera check-out |
| `SERVER_CAMERA_PROCESS_INTERVAL_SECONDS` | `0.25` | Nhịp xử lý |
| `SERVER_CAMERA_PREVIEW_FPS` | `8` | FPS MJPEG |
| `SERVER_CAMERA_JPEG_QUALITY` | `80` | Chất lượng preview |
| `CAMERA_RECONNECT_SECONDS` | `5` | Thời gian kết nối lại |

Nguồn camera chỉ lấy từ `.env`, không lưu trong database hoặc trang Settings. Đổi nguồn camera cần khởi động lại backend.

### Chấm công

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `WORK_START_TIME` | `08:00` | Giờ bắt đầu |
| `WORK_END_TIME` | `17:00` | Giờ kết thúc |
| `LATE_GRACE_MINUTES` | `5` | Phút cho phép đi muộn |
| `EARLY_LEAVE_GRACE_MINUTES` | `10` | Phút cho phép về sớm |
| `MISSING_CHECKOUT_CUTOFF_TIME` | `23:59` | Giờ chốt thiếu check-out |
| `MISSING_CHECKOUT_SCAN_INTERVAL_SECONDS` | `60` | Chu kỳ quét, tối thiểu 30 giây |

Admin có thể lưu lịch có ngày hiệu lực trong giao diện; lịch này được ưu tiên khi tính công.

### Liveness

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `LIVENESS_ENABLED` | `true` | Bật chống giả mạo |
| `ANTI_SPOOF_MODEL_PATH` | `models/anti_spoofing/best_model_quantized.onnx` | Model ONNX |
| `LIVENESS_THRESHOLD` | `0.5` trong `.env.example` | Ngưỡng mặt thật |
| `LIVENESS_REAL_CLASS_INDEX` | `0` | Class mặt thật |
| `LIVENESS_INPUT_SIZE` | `128` | Input dự phòng |
| `LIVENESS_CROP_SCALE` | `1.5` | Hệ số crop |
| `LIVENESS_MIN_FACE_SIZE` | `80` | Kích thước mặt tối thiểu |
| `LIVENESS_MIN_BRIGHTNESS` | `35` | Độ sáng tối thiểu |
| `LIVENESS_MIN_BLUR` | `18` | Độ nét tối thiểu |
| `LIVENESS_EDGE_MARGIN` | `5` | Khoảng cách tới mép |

Nhiều cài đặt được seed vào bảng `settings` khi database tạo lần đầu. Với database đã tồn tại, đổi `.env` không nhất thiết ghi đè giá trị trong bảng; hãy kiểm tra trang Settings hoặc database.

## Quy trình sử dụng ban đầu

1. Đăng nhập admin và đổi mật khẩu.
2. Tạo hồ sơ sinh viên.
3. Tạo tài khoản `student`, liên kết đúng hồ sơ.
4. Tạo `lab_manager` nếu cần người vận hành.
5. Cấu hình lịch làm việc và ngày nghỉ.
6. Đăng ký FaceID hoặc để sinh viên gửi yêu cầu.
7. Cấu hình camera trong `.env` rồi khởi động lại server.
8. Kiểm tra camera, liveness, log và cảnh báo.
9. Thiết lập sao lưu database cùng private storage.

## FaceID, nhận diện và liveness

### FaceID

- Chấp nhận JPEG/PNG, mỗi file tối đa 5 MB.
- Scan yêu cầu 5 ảnh: thẳng, trái, phải, ngẩng, cúi.
- Mỗi sinh viên lưu tối đa 10 mẫu embedding.
- Ảnh phải chứa đúng một khuôn mặt.
- Hệ thống cảnh báo embedding gần giống sinh viên khác.
- Khi hồ sơ chuyển `inactive`, FaceID của sinh viên đó bị xóa.

### Nhận diện realtime

```mermaid
flowchart LR
    Frame["Frame"] --> Detect["Detection"]
    Detect --> Quality{"Đủ sáng, nét, đúng vị trí?"}
    Quality -- Không --> Reject["Uncertain / chặn"]
    Quality -- Có --> Live["Liveness"]
    Live --> IsLive{"Mặt thật?"}
    IsLive -- Không --> Alert["Spoof alert"]
    IsLive -- Có --> Match["So khớp embedding"]
    Match --> Known{"Đạt threshold?"}
    Known -- Không --> Unknown["Unknown alert"]
    Known -- Có --> Event["Check-in/check-out"]
```

InsightFace dùng `detection`, `recognition`, `CPUExecutionProvider` và `ctx_id=-1`.

Model liveness nhận ảnh RGB `128x128`, pixel `0..1`, output `[real, spoof]`. Hệ thống fail-safe: nếu liveness đang bật nhưng model lỗi, kết quả bị chặn. Ảnh quá tối, mờ, mặt nhỏ hoặc sát mép cũng bị đánh dấu `uncertain`.

Kiểm tra trạng thái:

```text
GET /health
GET /api/settings/liveness-status
```

## Camera chấm công

Camera check-in/check-out luôn do backend đọc bằng OpenCV `VideoCapture`. Camera trình duyệt không tham gia chấm công.

Webcam/USB:

```env
AUTO_START_CAMERAS=true
CHECK_IN_CAMERA_SOURCE=0
CHECK_OUT_CAMERA_SOURCE=1
```

RTSP:

```env
AUTO_START_CAMERAS=true
CHECK_IN_CAMERA_SOURCE=rtsp://user:password@192.168.1.50:554/stream1
CHECK_OUT_CAMERA_SOURCE=rtsp://user:password@192.168.1.51:554/stream1
```

Không đưa URL RTSP thật vào Git, README, ảnh chụp hoặc log hỗ trợ. API status che credential trong URL trả về.

Dashboard xem preview MJPEG từ camera thread đang chạy; mỗi người xem không mở thêm `VideoCapture`. Đóng trình duyệt không dừng camera backend. Mỗi lần start camera tạo một realtime session riêng, không dùng chung trạng thái giữa check-in và check-out.

## Lịch làm việc và chấm công

Admin cấu hình ngày làm việc trong tuần, giờ bắt đầu/kết thúc, phút cho phép đi muộn/về sớm, giờ chốt thiếu check-out và ngày đặc biệt. Staff có thể đặt giờ làm riêng cho từng sinh viên.

| Trạng thái | Ý nghĩa |
| --- | --- |
| `pending` | Chưa check-in, ngày chưa kết thúc |
| `unfinalized` | Đã check-in nhưng ca chưa chốt |
| `present_on_time` | Đúng giờ |
| `late` | Đi muộn |
| `early_leave` | Về sớm |
| `late_and_early_leave` | Đi muộn và về sớm |
| `missing_checkout` | Thiếu check-out |
| `absent` | Không check-in sau khi ngày kết thúc |
| `leave_pending` | Đơn nghỉ chờ duyệt |
| `leave_approved` | Nghỉ có phép |
| `off_day` | Ngày không tính chuyên cần |

Tổng thời gian được tính từ các cặp check-in/check-out hợp lệ. Hệ thống cũng thống kê số lần và thời gian ra ngoài.

Thiếu check-out có thể chốt theo giờ kết thúc ca, nhập giờ ra thực tế hoặc giữ thiếu check-out và tính 0 giờ. Scheduler quét khi server khởi động và tiếp tục chạy nền.

## Đơn nghỉ và báo cáo sinh viên

### Đơn nghỉ

Loại đơn: `sick`, `personal`, `study`, `family`, `other`.

Sinh viên tạo và có thể hủy đơn chờ; lab manager/admin duyệt hoặc từ chối; admin có thể thu hồi. Chấm công trong khoảng ngày được tính lại sau thay đổi. Không thể xóa hồ sơ đã có lịch sử đơn nghỉ; hãy chuyển sang `inactive`.

### Báo cáo sinh viên

Sinh viên chọn một lab manager active, sau đó nộp file hoặc link `http/https`. Trạng thái gồm `submitted`, `revision_requested`, `approved`; lịch sử version và phản hồi được giữ.

Định dạng:

```text
PDF, DOC, DOCX, PPT, PPTX, XLSX, ZIP, PNG, JPG, JPEG
```

Giới hạn:

- File tối đa 20 MB.
- Office/ZIP được kiểm tra signature.
- Archive tối đa 2.000 entry và 100 MB sau giải nén.
- Tên file được làm sạch, file lưu thực tế đổi thành UUID.
- Chỉ chủ sở hữu và staff có quyền mới tải được.

## Xuất báo cáo chấm công

Admin/lab manager mở **Điểm danh → Xuất Excel**.

- Khoảng ngày bắt buộc, tối đa 366 ngày.
- Trạng thái tùy chọn.
- Mã sinh viên hoặc họ tên tùy chọn; để trống để xuất tất cả.
- Chọn `Tong_hop`, `Chi_tiet` hoặc cả hai.

`Tong_hop` thống kê theo sinh viên; `Chi_tiet` chứa từng bản ghi, bao gồm lớp nhưng không dùng lớp làm bộ lọc xuất. Giới hạn tối đa 50.000 dòng.

Thao tác xuất không tự tính lại chấm công, được audit, chống Excel formula injection và không chứa ảnh, embedding, bằng chứng camera hoặc credential.

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

## Database và migration

Database mặc định: `data/face_lab.db`.

Ứng dụng tự tạo schema và ghi migration vào `schema_migrations`. Migration hiện xử lý:

- Foreign key `users.student_id → students.id`, `ON DELETE SET NULL`.
- Một hồ sơ sinh viên chỉ liên kết một tài khoản.
- Tài khoản student mồ côi.
- Ràng buộc yêu cầu FaceID.
- Loại bỏ cài đặt camera browser/database cũ.

### Tài khoản student mồ côi

Đây là tài khoản `student` có `student_id` trỏ tới hồ sơ không còn tồn tại. Migration sẽ:

1. Giữ ID, username, password hash và lịch sử.
2. Đặt `student_id=NULL`.
3. Chuyển tài khoản sang `inactive`.
4. Thu hồi session đang hoạt động.

Tài khoản không bị xóa. Admin có thể liên kết lại với hồ sơ hợp lệ và kích hoạt lại. Nếu nhiều tài khoản cùng liên kết một sinh viên, migration dừng để yêu cầu xử lý thủ công thay vì tự đoán.

Khi admin xóa một hồ sơ hợp lệ, tài khoản liên kết cũng bị vô hiệu hóa và session bị thu hồi. Hồ sơ có lịch sử đơn nghỉ không được xóa.

## Bảo mật, lưu trữ và sao lưu

### Bảo mật hiện có

- Session cookie `HttpOnly`, `SameSite=Lax`, Secure khi bật HTTPS.
- CSRF cookie/header cho request thay đổi dữ liệu.
- PBKDF2 và tự rehash khi số vòng tăng.
- Rate limit đăng nhập theo IP + username.
- Thu hồi session khi logout, đổi mật khẩu, khóa/xóa hoặc sửa orphan account.
- Trusted Host, CSP, X-Frame-Options, nosniff, Referrer/Permissions Policy.
- HSTS khi `HTTPS_ENABLED=true`.
- Audit log và file response `no-store`.

### File riêng tư

```text
storage/private/faces/            Ảnh FaceID
storage/private/face_requests/    Ảnh yêu cầu FaceID
storage/private/evidence/         Ảnh bằng chứng/cảnh báo
storage/private/student_reports/  Báo cáo sinh viên
```

Database chứa embedding, dữ liệu sinh viên, lịch sử ra/vào, đơn nghỉ và audit. Không đưa dữ liệu thật vào repository công khai.

### Sao lưu

Sao lưu đồng thời `data/face_lab.db`, `storage/private/` và `.env` ở nơi bảo mật. Phải dừng backend trước khi copy SQLite để tránh bản sao không nhất quán do WAL.

```powershell
New-Item -ItemType Directory -Force data\backups
Copy-Item data\face_lab.db data\backups\face_lab_backup.db
Copy-Item storage\private data\backups\private -Recurse -Force
```

Với hệ thống không thể dừng, dùng SQLite Backup API hoặc snapshot nhất quán; không copy nóng riêng file database.

## Tổng quan API

| Nhóm | Prefix/endpoint | Quyền chính |
| --- | --- | --- |
| Auth | `/api/auth/*` | Login public, còn lại dùng session |
| Dashboard | `/api/dashboard` | Admin, lab manager |
| Sinh viên | `/api/students/*` | Staff; xóa chỉ admin |
| Tài khoản | `/api/users/*` | Admin; lab manager chỉ quản lý student |
| FaceID trực tiếp | `/api/students/{id}/faces/*` | Staff |
| FaceID sinh viên | `/api/student/face-registration/*` | Student sở hữu |
| Duyệt FaceID | `/api/face-registration-requests/*` | Staff |
| Camera | `/api/server-cameras/*` | Staff |
| Log/chấm công/cảnh báo | `/api/access-logs`, `/api/attendance-records*`, `/api/alerts*` | Staff; xóa chỉ admin |
| Lịch làm việc | `/api/work-schedule/*` | Xem staff, sửa admin |
| Đơn nghỉ | `/api/leave-requests/*`, `/api/student/leave-requests/*` | Theo vai trò |
| Báo cáo | `/api/reports/*`, `/api/student/reports/*` | Theo vai trò |
| Xuất Excel | `/api/exports/attendance` | Staff |
| Audit | `/api/audit-logs` | Admin |
| File riêng tư | `/api/files/*` | Chủ sở hữu hoặc staff |
| Student portal | `/api/student/*` | Student đã liên kết |
| Health | `/health` | Public, chi tiết tắt mặc định |

Request `POST`, `PUT`, `PATCH`, `DELETE` sau đăng nhập phải gửi:

```http
X-CSRF-Token: <giá trị cookie csrf_token>
```

Bật OpenAPI trong môi trường phát triển:

```env
PUBLIC_DOCS_ENABLED=true
```

## Kiểm thử

```powershell
python -m pip install -r requirements-dev.txt
python -m compileall app tests
python -m pytest -q
python -m ruff check app tests
Get-ChildItem web\static\js -Filter *.js | ForEach-Object { node --check $_.FullName }
```

Baseline nhánh `test` khi cập nhật README:

```text
123 passed, 4 subtests passed
Ruff passed
14 JavaScript files passed syntax check
```

Test dùng database tạm, không được trỏ vào `data/face_lab.db` thật.

## Cấu trúc thư mục

```text
app/
├── ai/                    InsightFace, liveness, embedding cache
├── core/                  Config, middleware, lifespan
├── repositories/          Truy vấn SQLite
├── routers/               HTTP API
├── schemas/               Pydantic validation
├── services/              Nghiệp vụ
├── workers/               Tác vụ nền
├── db.py                  Schema và kết nối SQLite
├── main.py                FastAPI app
└── migrations.py          Migration có version

web/
├── static/css/            CSS
├── static/js/             Frontend JavaScript
└── templates/             HTML

models/anti_spoofing/      Model ONNX
tests/                     Automated tests
data/                      SQLite local, bị ignore
storage/private/           File riêng tư, bị ignore
.env.example               Mẫu cấu hình
requirements.txt           Dependency runtime
requirements-dev.txt       Test/lint
run.py                     Entry point local
```

File `.zip` bị ignore bởi `.gitignore` và không phải thành phần runtime.

## Triển khai thực tế

- [ ] Đổi `SECRET_KEY`, username và mật khẩu admin mặc định.
- [ ] Giữ `PUBLIC_DOCS_ENABLED=false`, `HEALTH_DETAILS_ENABLED=false`.
- [ ] Cấu hình `TRUSTED_HOSTS`, firewall và HTTPS đúng trước khi bật `HTTPS_ENABLED=true`.
- [ ] Không đưa credential RTSP vào source/log.
- [ ] Giới hạn quyền filesystem của `.env`, database và private storage.
- [ ] Chạy một Uvicorn worker.
- [ ] Sao lưu và thử khôi phục định kỳ.
- [ ] Theo dõi dung lượng database, ảnh và báo cáo.
- [ ] Kiểm tra `/health`, liveness và camera sau deploy.
- [ ] Chạy toàn bộ test trước khi cập nhật production.

## Lỗi thường gặp

### Không import được InsightFace

```powershell
conda activate python10
python -m pip install -r requirements.txt
python -c "import insightface; print(insightface.__version__)"
```

Kết quả mong đợi: `1.0.1`.

### Không tải được `buffalo_l`

Kiểm tra internet lần đầu, cache InsightFace và đảm bảo server chạy bằng đúng user Windows sở hữu cache.

### Liveness báo lỗi

Kiểm tra model path, `onnxruntime` và gọi `/api/settings/liveness-status` bằng tài khoản staff. Khi bật liveness nhưng model lỗi, hệ thống chủ động chặn nhận diện.

### Camera không mở

Thử index `0`, `1`, `2`; đóng ứng dụng đang giữ webcam; kiểm tra RTSP/firewall/credential; khởi động lại backend sau khi sửa `.env`.

### Camera chạy nhưng không ghi nhận

Kiểm tra sinh viên active, FaceID, liveness, ánh sáng, `FACE_THRESHOLD`, cooldown và chiều check-in/check-out. Xem access log và alert để biết lý do.

### Request thay đổi dữ liệu trả 403

API client chưa gửi `X-CSRF-Token` khớp cookie `csrf_token`.

### Student báo chưa liên kết hồ sơ

Tài khoản có `student_id=NULL`, hồ sơ đã bị xóa hoặc migration đã vô hiệu hóa liên kết mồ côi. Admin cần liên kết lại và kích hoạt tài khoản.

### Migration báo duplicate student link

Nhiều tài khoản đang trỏ cùng một hồ sơ. Sao lưu database, giữ một liên kết đúng, gỡ các liên kết trùng rồi chạy lại.

### `/docs` trả 404

Đây là mặc định. Chỉ bật `PUBLIC_DOCS_ENABLED=true` trong môi trường phát triển.

## Giới hạn và giấy phép

Giới hạn hiện tại:

- Chưa hỗ trợ PostgreSQL/MySQL.
- Chưa có queue/worker tách tiến trình, Docker, CI hoặc metrics tập trung.
- Xuất báo cáo chỉ có XLSX, chưa có PDF hoặc lịch chạy tự động.
- AI chạy CPU, chưa có cấu hình GPU chính thức.
- Hướng dẫn Linux/macOS chưa được kiểm thử chính thức.

Repository chưa có file `LICENSE` ở thư mục gốc. Chủ dự án cần chọn và thêm giấy phép trước khi phát hành công khai hoặc cho bên thứ ba sử dụng.

Model anti-spoofing có nguồn từ `facenox/face-antispoof-onnx` và giữ giấy phép riêng:

```text
https://github.com/facenox/face-antispoof-onnx
Apache-2.0
```

Model InsightFace `buffalo_l` tuân theo điều khoản sử dụng riêng của InsightFace. Cần kiểm tra điều khoản trước khi dùng cho sản phẩm thương mại hoặc dữ liệu thật.
