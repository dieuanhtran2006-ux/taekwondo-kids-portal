# Taekwondo Kids Portal

MVP quản lý và tra cứu thành tích võ sinh theo mô hình sổ liên lạc điện tử.

- **Backend:** Python 3.11+, WSGI, SQLite.
- **Frontend:** HTML, CSS, JavaScript; giao diện tiếng Việt, responsive.
- **Chức năng:** hồ sơ võ sinh, giải đấu, kết quả cá nhân/đôi/đồng đội, xác minh, import Excel có xem trước, báo cáo, tài khoản/phạm vi, minh chứng riêng tư và lịch sử chỉnh sửa.
- **Trang chủ và /dang-nhap:** bắt buộc đăng nhập bằng tài khoản do CLB cấp; đổi mật khẩu lần đầu trước khi mở hồ sơ. Không còn tra cứu ẩn danh.
- **Khu gia đình:** thông tin cá nhân của võ sinh được gán, cơ sở, trạng thái học tập, thành tích được phép xem, điểm danh và đề nghị bổ sung.
- **Khu quản trị /admin/:** Admin/HLV nhập và sửa điểm danh, trạng thái tập luyện theo phạm vi; Admin cấp tài khoản, quản lý xác minh và dữ liệu.
- **Điểm danh:** từng buổi (ngày, giờ, lớp, cơ sở), có mặt/vắng có phép/vắng không phép. Không tự tính vắng khi chưa nhập dữ liệu.

## Phạm vi mã nguồn

**Link kiểm thử đăng nhập:** [Taekwondo Kids · Hồ sơ võ sinh](https://dieuanhtran2006-ux.github.io/taekwondo-kids-preview/).

Bản GitHub Pages chỉ dùng **một hồ sơ kiểm thử tổng hợp**: Võ sinh mẫu 01 / MAU-TKD-001. Trang chủ mở màn hình đăng nhập. Đã bỏ snapshot public-data.json và các tài nguyên tìm kiếm cũ. Đây vẫn là mô phỏng phía trình duyệt: mọi tệp mẫu có thể đọc được, vì vậy không chứa dữ liệu thật. Dữ liệu thật phải đặt ở backend có kiểm tra quyền phía server.

Mục **Bổ sung thành tích** trong bản thử cho phép nhập → kiểm tra → lưu đề nghị mẫu trên trình duyệt. Tải lại trên cùng trình duyệt vẫn xem được, có nút xóa dữ liệu thử. **Chưa gửi đề nghị mẫu tới CLB**, không cộng huy chương và không đồng bộ sang trang quản trị. Để nhận đề nghị thật từ phụ huynh qua Internet, cần triển khai backend Python theo [DEPLOYMENT.md](docs/DEPLOYMENT.md).

Repository chỉ chứa mã nguồn, logo được cung cấp, tài liệu và kiểm thử. **Không kèm database thật, tài khoản, session, file Excel nguồn, ảnh chụp có tên võ sinh hoặc minh chứng.** Lần chạy đầu có database trống và trang tạo quản trị viên cục bộ.

Bản Pages có trang `dang-nhap.html` và **tài khoản kiểm thử công khai**: `MAU-TKD-001` / `TKD-Mau!2026`. Chỉ mô phỏng trên thiết bị: đăng nhập → đổi mật khẩu lần đầu → xem hồ sơ mẫu 01. Mật khẩu mẫu sau khi đổi được lưu bằng PBKDF2 trong trình duyệt, phiên thử nằm trong `sessionStorage`; không đồng bộ thiết bị và không bảo vệ dữ liệu thật. Không dùng mật khẩu thật ở đây. Có nút **Đặt lại tài khoản mẫu** nếu cần thử lại.

Các fixture kiểm thử là dữ liệu tổng hợp; dữ liệu mẫu của bản Pages được tạo riêng bởi script dựng preview, không đọc database thật. Logo là tài sản thương hiệu của đơn vị cung cấp; repository không cấp quyền sử dụng thương hiệu cho bên thứ ba.

## Cài đặt và chạy

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe server.py
```

Mở **http://127.0.0.1:8765** để đăng nhập hồ sơ. Mở **http://127.0.0.1:8765/admin/** để tạo tài khoản quản trị đầu tiên bằng mật khẩu ít nhất 12 ký tự. Không có tài khoản hoặc mật khẩu mặc định.

Sau khi cài dependencies, có thể nhấp đúp **Mo-TKD-Portal.cmd** để mở server chạy nền và trình duyệt. `Start-Portal.ps1` chạy trực tiếp trong terminal; đóng terminal đó sẽ dừng server trực tiếp. Sau khi khởi động lại máy, mở lại tệp khởi động. Dữ liệu vẫn được giữ trong `data/`.

### macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python server.py
```

## Nhập dữ liệu

Đăng nhập quản trị viên → **Nhập dữ liệu** → chọn `.xlsx` đúng cấu trúc tám sheet → xem trước lỗi/cảnh báo → xác nhận nhập. Không phụ thuộc giá trị tính sẵn của công thức Excel. Nhập lại cùng tệp không tạo bản ghi trùng.

Mã nguồn tạm và nội dung/dòng nguồn được bảo toàn. Tên trùng không tự gộp. Ngày sinh, cơ sở và thông tin còn thiếu không được tự đoán. Kết quả nhập luôn chờ xác minh; số huy chương chính thức bằng 0 khi chưa có kết quả được duyệt.

## Xác minh và phân quyền

1. Đối chiếu danh tính và bổ sung mã chính thức của võ sinh.
2. Bổ sung đủ nội dung, hình thức thi, người nhận và minh chứng.
3. Người có quyền xác minh kiểm tra, ghi căn cứ và phê duyệt hoặc trả lại.
4. Cấp quyền hiển thị cho kết quả và từng minh chứng được phép.

Một huy chương đồng đội được lưu thành một kết quả và nhiều liên kết võ sinh. Tổng huy chương CLB và lượt võ sinh nhận huy chương được tính riêng. Tài khoản viewer chỉ đọc hồ sơ được gán, thành tích đã duyệt và được phép hiển thị. Quyền được kiểm tra ở backend.

## Cấp tài khoản võ sinh

Quản trị viên mở **Võ sinh → Hồ sơ → Cấp tài khoản** sau khi đã xác thực danh tính và mã chính thức. Hệ thống tạo mã đăng nhập theo mã võ sinh, mật khẩu tạm ngẫu nhiên riêng và liên kết đúng một hồ sơ bằng ID ổn định. Mật khẩu tạm chỉ hiển thị một lần cho admin; chuyển trực tiếp tới người được cấp quyền.

Người dùng mở `/dang-nhap`, đăng nhập bằng mật khẩu tạm, đổi sang mật khẩu riêng từ 12 đến 256 ký tự rồi mới mở hồ sơ. Backend chặn API hồ sơ trước khi đổi; đổi mật khẩu thu hồi các phiên cũ và cấp phiên/CSRF mới. **Tài khoản & quyền → Chỉnh sửa** cho phép admin đặt lại mật khẩu khi người dùng quên; tài khoản viewer phải đổi lại ở lần đăng nhập tiếp theo.

Database cũ được bổ sung cột tài khoản khi nâng cấp; viewer cũ cần đổi mật khẩu một lần, không thay mật khẩu đang có hoặc sửa dữ liệu thành tích. Xem [STUDENT_LOGIN.md](docs/STUDENT_LOGIN.md).

## Quyền riêng tư bắt buộc

Mọi hồ sơ, thành tích, điểm danh và minh chứng đều cần phiên đăng nhập hợp lệ. Các API cũ /api/public/* bị đóng: khách nhận 401, tài khoản đã đăng nhập nhận 410. Các cờ công bố cũ giữ lại để không phá database/audit nhưng không cấp quyền xem ẩn danh; API bật công bố đã đóng. Trang chủ, /tra-cuu và đường dẫn hồ sơ cũ đều mở đăng nhập, không nhúng dữ liệu.

Backend kiểm tra hồ sơ được gán/cơ sở cho từng yêu cầu, kể cả khi gọi API trực tiếp. Võ sinh không được xem thông tin của người khác. Ngày sinh đầy đủ chỉ được trả trong hồ sơ riêng đã đăng nhập đúng quyền; ghi chú nội bộ, mã nguồn Excel và xét duyệt không được gửi cho gia đình.

Lệnh build không cho xuất database thật ra GitHub Pages. Không thể dùng giao diện đăng nhập bằng JavaScript để bảo vệ JSON chứa thông tin trẻ em.

## Trạng thái học tập và điểm danh

Admin/HLV mở **Võ sinh → Chỉnh sửa hồ sơ → Trạng thái tập luyện**. Không tự suy luận từ thành tích. Chuyển cơ sở không xóa lịch sử.

Vào **Điểm danh → Nhập điểm danh**, chọn võ sinh, ngày/giờ, lớp, cơ sở và trạng thái. Ghi chú ở đây sẽ hiển thị cho gia đình, không dùng cho nhận xét nội bộ. Có thể lọc theo võ sinh, ngày, trạng thái; sửa có kiểm tra phiên bản, lưu trữ bản nhập sai và xem lịch sử trong Audit. Coach chỉ thao tác trong phạm vi được cấp.

Mỗi võ sinh có tối đa một bản ghi đang hoạt động cho cùng ngày, giờ và lớp. Không ghi nhận tương lai, không tự tính vắng khi chưa nhập, không có lịch học/điểm danh tự động. Cơ sở buổi học lưu cả ID và tên tại thời điểm ghi nhận; việc đổi tên/chuyển cơ sở không sửa lịch sử này. Danh sách gia đình có phân trang và tổng số buổi được ghi nhận. Database cũ tự thêm bảng rỗng khi khởi động; không sinh điểm danh giả từ Excel.

Chi tiết: [ATTENDANCE.md](docs/ATTENDANCE.md).

## Phụ huynh bổ sung thành tích

Đăng nhập → đổi mật khẩu lần đầu nếu được yêu cầu → mở hồ sơ → **Bổ sung thành tích** → nhập thông tin/minh chứng → kiểm tra → gửi. Backend kiểm tra hồ sơ được cấp quyền và lấy tên/mã từ hồ sơ; không cho gửi cho võ sinh ngoài phạm vi. POST /api/student/submissions yêu cầu phiên và CSRF, tối đa 5 lần/giờ/tài khoản.

Đề nghị được lưu bền trong SQLite, có mã tiếp nhận chống gửi trùng khi thử lại. Quản trị viên vào **Đề nghị phụ huynh** để xem nguyên văn, ghi chú/từ chối, hoặc nhận diện người nhận và kiểm tra trùng trước khi tạo kết quả nháp/liên kết kết quả hiện có. Tạo từ đề nghị luôn **chờ xác minh, chưa công bố**; vẫn phải qua quy trình phê duyệt và cấp quyền hiển thị riêng. Thông tin liên hệ tùy chọn chỉ quản trị viên được đọc; không xây dựng danh bạ phụ huynh.

MVP nhận **đường dẫn minh chứng**, chưa nhận tệp tải lên ẩn danh. Không tự tải URL hoặc tự mở quyền Google Drive. Nếu cần liên hệ làm rõ, quản trị viên dùng thông tin người gửi tự nguyện cung cấp.

Chi tiết luồng, API và cấu hình bản thử: [PARENT_CONTRIBUTIONS.md](docs/PARENT_CONTRIBUTIONS.md).

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/public_preview.test.cjs
node --test tests/student_demo.test.cjs
```

Một bài kiểm tra file Excel thật chỉ chạy khi đặt biến môi trường `TKD_SOURCE_XLSX` trỏ đến file cục bộ; mặc định bài này được bỏ qua. Không cần đưa dữ liệu thật lên repository để chạy các kiểm thử còn lại.

## Cấu trúc

```text
app/             Lược đồ quan hệ, nghiệp vụ, import và adapter Google
static/          Giao diện web và logo
tests/           Kiểm thử nghiệp vụ, API, phân quyền và khởi động
docs/            Phân tích Excel, ERD và hướng dẫn triển khai
data/.gitkeep    Thư mục dữ liệu trống; nội dung vận hành được Git bỏ qua
server.py        REST API, xác thực, server phát triển và WSGI factory
```

## Đưa mã nguồn lên GitHub

Tạo repository trên GitHub, chọn **Add file → Upload files**, rồi tải toàn bộ nội dung thư mục mã nguồn này lên. Không tải file ZIP như một tệp duy nhất. Giữ nguyên cấu trúc `app/`, `static/`, `tests/` và các tệp ở thư mục gốc.

Hoặc dùng Git sau khi tạo repository rỗng:

```bash
git init
git add .
git commit -m "Initial Taekwondo Kids Portal source"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

Thay `YOUR_USERNAME/YOUR_REPOSITORY` bằng repository của bạn. `.gitignore` đã loại database, credentials, log, file Excel và minh chứng. Không dùng `git add -f` để đưa dữ liệu vận hành lên GitHub.

**Đăng mã nguồn lên GitHub chưa tự đưa ứng dụng lên online.** GitHub Pages chỉ phục vụ tệp tĩnh và không chạy backend Python này. Nếu cần hosting sau này, dùng WSGI server và lưu trữ bền theo [DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Cấu hình Google và môi trường

`.env.example` liệt kê các biến môi trường tham khảo; server không tự đọc file `.env`. Đặt biến trong môi trường backend. Google Sheets/Drive cần credentials riêng và chưa được kết nối sẵn. Không đặt credentials trong frontend hoặc repository.

- [ERD](docs/ERD.md)
- [Cấu trúc và ánh xạ Excel](docs/PHAN_TICH_EXCEL.md)
- [Triển khai WSGI, HTTPS và sao lưu](docs/DEPLOYMENT.md)
