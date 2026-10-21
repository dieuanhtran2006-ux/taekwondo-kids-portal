# Taekwondo Kids Portal

MVP quản lý và tra cứu thành tích võ sinh theo mô hình sổ liên lạc điện tử.

- **Backend:** Python 3.11+, WSGI, SQLite.
- **Frontend:** HTML, CSS, JavaScript; giao diện tiếng Việt, responsive.
- **Chức năng:** hồ sơ võ sinh, giải đấu, kết quả cá nhân/đôi/đồng đội, xác minh, import Excel có xem trước, báo cáo, tài khoản/phạm vi, minh chứng riêng tư và lịch sử chỉnh sửa.
- **Trang khách `/`:** tra cứu công khai không cần đăng nhập, tìm tên có dấu/không dấu hoặc mã chính thức, phân trang, hồ sơ huy chương và lịch sử theo năm/giải/huy chương/hình thức. Chỉ hồ sơ và kết quả được cấp quyền công bố riêng mới xuất hiện.
- **Trang quản trị `/admin/`:** đăng nhập để quản lý dữ liệu và cấp/thu hồi quyền công bố.

## Phạm vi mã nguồn

Repository chỉ chứa mã nguồn, logo được cung cấp, tài liệu và kiểm thử. **Không kèm database thật, tài khoản, session, file Excel nguồn, ảnh chụp có tên võ sinh hoặc minh chứng.** Lần chạy đầu có database trống và trang tạo quản trị viên cục bộ.

Các fixture kiểm thử là dữ liệu tổng hợp, chỉ tồn tại trong database tạm. Logo là tài sản thương hiệu của đơn vị cung cấp; repository không cấp quyền sử dụng thương hiệu cho bên thứ ba.

## Cài đặt và chạy

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe server.py
```

Mở **http://127.0.0.1:8765** để xem trang khách. Mở **http://127.0.0.1:8765/admin/** để tạo tài khoản quản trị đầu tiên bằng mật khẩu ít nhất 12 ký tự. Không có tài khoản hoặc mật khẩu mặc định.

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

## Công bố thành tích cho khách tra cứu

Quyền xem của tài khoản viewer **không phải** quyền công khai trên Internet. Database cũ tự bổ sung các cột quyền công bố khi khởi động; giá trị mặc định là tắt, dữ liệu và trạng thái xác minh được giữ nguyên.

1. Vào `/admin/`, mở **Võ sinh → Hồ sơ → Công bố hồ sơ**. Chỉ bật sau khi danh tính và mã chính thức đã được xác thực, có quyền công bố tên/mã.
2. Mở chi tiết một thành tích đã xác minh, đã bật quyền hiển thị → **Công bố cho khách**. Bật quyền công bố kết quả.
3. Nếu cần công bố URL minh chứng, kiểm tra quyền chia sẻ của tài liệu và nội dung được phép; bật quyền mở URL cho người xem và quyền công bố URL cho khách. Tệp tải lên có hai quyền riêng: **Cho phép người xem** và **Công bố cho khách** trong chi tiết thành tích.
4. Mở `/`, tìm tên hoặc mã và chọn hồ sơ. Khách xem huy chương, lọc lịch sử, mở chi tiết và minh chứng được phép. Liên kết `/ho-so/<id>` có thể chia sẻ.

Ngày sinh, năm sinh, cơ sở hiện tại, ghi chú, mã tạm, tài liệu nguồn và thông tin xét duyệt không nằm trong API công khai. Tên thành viên đội chỉ hiển thị nếu hồ sơ của từng người đã được công bố. Số liệu trên trang khách chỉ tính phần dữ liệu được công bố, không phải toàn bộ dữ liệu nội bộ.

Tắt quyền để gỡ thông tin khỏi trang khách ngay ở yêu cầu tiếp theo. Thao tác này được ghi audit và không hủy xác minh thành tích. Sửa nội dung kết quả/đổi danh tính sẽ tạm ẩn và cần cấp lại quyền công bố sau khi đối chiếu. Minh chứng đã được khách tải về không thể thu hồi bằng cách tắt quyền trên website.

Các endpoint `/api/public/*` chỉ đọc, giới hạn 60 yêu cầu/phút/địa chỉ kết nối và không cấp danh sách toàn bộ võ sinh khi bỏ trống từ khóa. API nội bộ vẫn yêu cầu đăng nhập và kiểm tra quyền. Chi tiết xem [PUBLIC_PORTAL.md](docs/PUBLIC_PORTAL.md).

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
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
