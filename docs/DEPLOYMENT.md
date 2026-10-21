# Triển khai và vận hành

## Phạm vi bản bàn giao

Bản mã nguồn chạy cục bộ và tạo database SQLite trống. Repository không kèm dữ liệu vận hành, tài khoản hoặc minh chứng. Hosting, tên miền/HTTPS và Google cần được cấu hình riêng trước khi sử dụng online.

`server.py` dùng máy chủ `wsgiref` của thư viện chuẩn để chạy môi trường phát triển. Theo [tài liệu Python](https://docs.python.org/3.11/library/wsgiref.html), máy chủ này chỉ có kiểm tra bảo mật cơ bản và không được khuyến nghị cho production. Ứng dụng đã có WSGI factory `server:create_application`; khi triển khai thực tế, dùng WSGI server có duy trì, đặt sau reverse proxy HTTPS; kiểm thử lại luồng đăng nhập, upload và các cờ cookie qua proxy.

Ví dụ khởi chạy Waitress ở backend (cần cài Waitress trong môi trường production):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-production.txt
$env:TKD_DB = 'D:\TKD-Portal-Data\portal.sqlite3'
$env:TKD_ALLOWED_HOSTS = 'portal.ten-mien-clb.vn'
$env:TKD_SECURE_COOKIE = '1'
$env:TKD_ALLOW_SETUP = '0'
.\.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:8765 --url-scheme=https --call server:create_application
```

Thay tên miền và đường dẫn bằng cấu hình thật. Ví dụ trên giả định chỉ có HTTPS đi qua reverse proxy, dùng `--url-scheme=https` theo [tài liệu Waitress](https://docs.pylonsproject.org/projects/waitress/en/stable/runner.html). Reverse proxy cần chuyển `Host` đã kiểm tra đúng tên miền. Nếu cấu hình nhiều scheme, dùng danh sách proxy/header tin cậy cụ thể theo [Waitress arguments](https://docs.pylonsproject.org/projects/waitress/en/stable/arguments.html); không tin forwarded headers từ Internet. Nếu backend hiểu scheme là HTTP trong khi trình duyệt dùng HTTPS, kiểm tra Origin sẽ từ chối yêu cầu ghi. Khởi tạo tài khoản admin bằng server dev cục bộ trước, sau đó tắt `TKD_ALLOW_SETUP` khi đưa qua proxy.

## Cấu hình vận hành

- Python 3.11+ và phiên bản `openpyxl` trong `requirements.txt`.
- Tài khoản hệ điều hành riêng, chỉ được đọc mã và ghi thư mục dữ liệu.
- Đường dẫn SQLite và thư mục minh chứng không nằm trong thư mục static hoặc web root.
- TLS trên reverse proxy, giới hạn body upload và timeout; chỉ proxy được truy cập backend.
- Cookie `Secure` khi chạy HTTPS; không bật debug hoặc trả stack trace cho người dùng.
- Không tin `X-Forwarded-*` từ người dùng ngoài proxy. Không lưu token trong file frontend hoặc trình quản lý localStorage.
- Đặt giới hạn tốc độ đăng nhập tại ứng dụng/proxy; không bật CORS rộng cho API có session.

Giá trị cấu hình cụ thể của máy chủ bàn giao xem `python server.py --help`. Mặc định chỉ lắng nghe trên máy cục bộ. Tạo tài khoản admin đầu tiên trước khi cho người khác tiếp cận hệ thống.

## Quyền và dữ liệu cá nhân

| Vai trò | Phạm vi | Quyền thao tác |
|---|---|---|
| Admin | Toàn hệ thống | Quản trị, import, cấp quyền, xác minh, xuất báo cáo và audit |
| Coach | Võ sinh/cơ sở được giao | Tra cứu và nhập/sửa trong phạm vi; chỉ xác minh khi được cấp quyền |
| Viewer | Hồ sơ được gán | Chỉ đọc kết quả đã duyệt, được phép công bố; không đọc nguồn nội bộ hoặc ngày sinh đầy đủ |

Xác minh danh tính trước khi gán tài khoản viewer vào hồ sơ. Quyền được kiểm tra tại server cho cả API chi tiết, danh sách, thống kê, minh chứng và xuất file. Dùng tài khoản cá nhân để audit có ý nghĩa. Khi cán bộ ngừng phụ trách, thu hồi quyền và kết thúc session.

Phê duyệt thành tích là thao tác có lưu người duyệt, thời điểm và ghi chú. Đối chiếu nội dung, mã người nhận, huy chương, hình thức, đủ thành viên và minh chứng; không phê duyệt chỉ dựa trên một emoji. Thay đổi trọng yếu sau phê duyệt phải quay về chờ xác minh. Không sửa hoặc xóa log để che lịch sử.

## Sao lưu SQLite và tệp

Dùng API backup của SQLite hoặc dừng ứng dụng khi sao chép. Không chỉ sao chép một tệp `.sqlite3` trong lúc ghi mà bỏ qua trạng thái WAL. Ví dụ sao lưu nhất quán phần cơ sở dữ liệu:

```python
from contextlib import closing
from pathlib import Path
import sqlite3

Path("backups").mkdir(exist_ok=True)
with closing(sqlite3.connect("data/portal.sqlite3")) as source:
    with closing(sqlite3.connect("backups/portal-backup.sqlite3")) as destination:
        source.backup(destination)
```

Sao lưu thư mục minh chứng và ghi thời điểm cùng đợt. Giữ ít nhất một bản ngoài máy chủ có kiểm soát quyền, mã hóa và chính sách lưu trữ phù hợp. Kiểm tra phục hồi bằng bản sao độc lập: chạy `PRAGMA integrity_check`, mở hồ sơ, kiểm đếm kết quả và thử tệp minh chứng. Không dùng bản backup thật làm fixture kiểm thử công khai.

## Google Sheets và Drive

Credentials chỉ được cấp cho backend. Access token cần scope đủ cho thao tác và quyền trên tệp cụ thể. Tạo hàng chờ `_TKD_SYNC_INBOX` trước khi bật ghi; bảo vệ sheet này. Không đồng bộ cột password/session hoặc ngày sinh đầy đủ sang bảng chia sẻ rộng.

`GoogleSheetsAdapter` hỗ trợ đọc REST, đối chiếu 3 chiều và gửi đề xuất staging có xác nhận. Không chạy lịch nền, không tự ghi đè SQLite, không tự ghi đè các bảng Sheets chính. Mỗi kế hoạch phải lưu snapshot làm baseline để phát hiện xung đột lần sau; dữ liệu đọc về vẫn phải qua validator và quyền phê duyệt của `core.Service`.

Sheets Values API không hỗ trợ cập nhật có điều kiện nguyên tử trên từng dòng. Nếu giai đoạn tiếp theo cần ghi trực tiếp dữ liệu chính, phải có quy trình một nguồn ghi, khóa được cả người sửa trực tiếp và worker, hoặc đổi sang cơ sở dữ liệu trung tâm rồi dùng Sheets như giao diện biên tập. Đọc lại hash trước khi ghi chưa đủ để loại bỏ mọi cuộc đua giữa các lần ghi.

MVP không tự làm mới OAuth token, chưa có luồng đăng nhập Google, chưa có tải tệp lên Drive và chưa có lịch đồng bộ. Thiếu credentials không ảnh hưởng Excel + SQLite. Không báo kết nối thành công cho đến khi yêu cầu API thực trả về thành công.

## Kiểm tra trước khi sử dụng chính thức

1. Chạy toàn bộ tests và rà các cảnh báo Excel; xác nhận các huy chương chờ duyệt không nằm trong số liệu chính thức.
2. Thử bằng ít nhất một tài khoản mỗi vai trò; viewer không mở được ID khác, file khác hoặc export nội bộ.
3. Xác nhận HTTPS, cookie Secure/HttpOnly/SameSite, CSRF, hết hạn phiên và thu hồi đăng nhập.
4. Thử tải minh chứng đúng/sai định dạng, vượt kích thước và kiểm tra quyền công bố.
5. Thử phục hồi backup và xác minh log thay đổi.
6. Chốt với CLB quy trình đối chiếu, người có quyền duyệt và phạm vi công bố trước khi gán tài khoản thật.
