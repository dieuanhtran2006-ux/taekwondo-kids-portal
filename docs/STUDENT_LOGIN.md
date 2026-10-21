# Đăng nhập hồ sơ võ sinh

## Tài khoản mẫu trên GitHub Pages

- Link: `https://dieuanhtran2006-ux.github.io/taekwondo-kids-preview/dang-nhap.html`.
- Mã võ sinh: `MAU-TKD-001`.
- Mật khẩu ban đầu: `TKD-Mau!2026`.
- Đăng nhập thành công → đổi mật khẩu bắt buộc → mở hồ sơ mẫu 01 → lọc lịch sử/xem chi tiết → đăng xuất → đăng nhập lại bằng mật khẩu mới.
- Mật khẩu mới khác mật khẩu cũ và mã đăng nhập, từ 12 đến 256 ký tự; hai ô nhập mới cần khớp.
- Nếu quên mật khẩu thử, dùng **Đặt lại tài khoản mẫu**. Chỉ xóa dữ liệu tài khoản/phiên thử, không xóa đề nghị thành tích mẫu hoặc dữ liệu ứng dụng khác.

Đây là mô phỏng cho dữ liệu tổng hợp. Tệp JavaScript chứa hồ sơ tổng hợp mẫu vẫn đọc được công khai; không còn snapshot tra cứu public-data.json. Kiểm tra trong JavaScript/localStorage không phải ranh giới bảo mật; không đặt hồ sơ thật, mật khẩu thật hoặc khóa API trong bản Pages. Không nhận mật khẩu hoặc đổi mật khẩu ở máy chủ online khi chạy bản tĩnh. Mật khẩu mẫu sau đổi chỉ lưu dạng PBKDF2 SHA-256 với salt riêng, 600.000 vòng; phiên thử hết hạn sau 8 giờ và bị vô hiệu khi đổi mật khẩu/đặt lại mẫu. Dữ liệu thử không đồng bộ giữa thiết bị. Tài khoản mẫu không tồn tại mặc định trong backend thật.

## Backend thật

1. Admin tạo/nhận diện hồ sơ và mã chính thức; không cấp tài khoản theo tên viết tắt/mã tạm.
2. **Hồ sơ → Cấp tài khoản** gọi `POST /api/athletes/<id>/account`, yêu cầu admin, CSRF, phiên bản hồ sơ. Username lấy từ mã chính thức tại lúc cấp. `login_athlete_id` duy nhất trỏ tới ID hồ sơ, `user_athletes` chỉ có hồ sơ đó. Không suy luận quan hệ từ người trùng tên.
3. Mật khẩu tạm được sinh ngẫu nhiên ở backend, chỉ trả một lần cho admin. Database chỉ lưu hash PBKDF2. Audit không chứa mật khẩu. Đóng hộp thoại cấp tài khoản sẽ xóa thông tin tạm khỏi DOM.
4. `POST /api/student/login` chỉ nhận viewer, kiểm tra hash/mật khẩu, dùng cùng bộ đếm 8 lần sai/15 phút theo địa chỉ kết nối và username chuẩn hóa với `/api/login`. Thông báo sai không phân biệt tài khoản có tồn tại hay không.
5. Phiên HttpOnly, SameSite=Strict, CSRF; bật Secure khi triển khai HTTPS. `must_change_password=1` cho tài khoản viewer mới; quản trị viên không thể gửi cờ false để bỏ qua. `/api/session` không trả danh sách hồ sơ khi còn bắt buộc đổi.
6. Trước khi đổi, các API nội bộ trả 403 với `details.code=PASSWORD_CHANGE_REQUIRED`. Chỉ cho phép đọc phiên, đổi mật khẩu, đăng xuất; các API công khai cũ đều bị đóng. Gọi thẳng API hoặc chuyển sang giao diện quản trị không bỏ qua bước đổi mật khẩu.
7. `POST /api/password` kiểm tra mật khẩu hiện tại, xác nhận mật khẩu mới khi bắt buộc đổi, độ dài và cấm dùng lại mật khẩu/mã đăng nhập. Cập nhật hash và `password_changed_at`, xóa toàn bộ session của tài khoản, xoay cookie và CSRF, trả phiên mới với cờ bắt buộc tắt.
8. `GET /api/student/athletes/<id>` kiểm tra phạm vi trên server. Trả whitelist thông tin cơ bản, kết quả đã xác minh và được phép xem. Không cần quyền công khai Internet. Ngày sinh đầy đủ chỉ trả trong hồ sơ riêng đúng quyền. Mã nguồn, ghi chú nội bộ/xét duyệt và thông tin riêng của đồng đội không được trả. Hồ sơ bao gồm trạng thái học tập và lịch sử điểm danh được Admin/HLV ghi nhận.
9. `GET /api/student/achievements/<id>` và `/api/evidence/<id>` tiếp tục kiểm tra scope và quyền xem kết quả/minh chứng. Đổi ID sang hồ sơ khác bị chặn.
10. Admin đặt lại mật khẩu trong quản lý tài khoản sẽ thu hồi session, bắt buộc viewer đổi lại. Tài khoản cấp theo mã không được mở rộng sang vai trò khác, thêm hồ sơ hoặc cơ sở qua PATCH thông thường.

Tài khoản quản trị/coach vẫn dùng `/admin/`. Viewer đăng nhập từ giao diện cũ được chuyển tới `/dang-nhap`. Tên và cơ sở thay đổi không làm đổi ID liên kết tài khoản.

## Nâng cấp và triển khai

`init_db` tạo `must_change_password`, `password_changed_at`, `login_athlete_id` và unique index một cách idempotent. Viewer đã có trong database cũ được yêu cầu đổi mật khẩu một lần khi lần đầu thêm cột; hash đang có, dữ liệu và liên kết không bị thay. Khởi động lại không ép đổi lặp lại.

Triển khai Python cùng origin, HTTPS, đĩa bền, `TKD_SECURE_COOKIE=1`, `TKD_ALLOW_SETUP=0` sau khi khởi tạo, danh sách `TKD_ALLOWED_HOSTS` phù hợp. Không đưa SQLite thật/credentials vào GitHub. Bổ sung giới hạn đăng nhập ở reverse proxy khi nhiều worker; bộ đếm ứng dụng hiện nằm trong RAM theo tiến trình. Không ghi nhận IP proxy như IP khách nếu chưa cấu hình giới hạn tại proxy. Xem `DEPLOYMENT.md`.

MVP chưa có tự đăng ký, quên mật khẩu bằng email/SMS, danh bạ phụ huynh hoặc xác minh quyền giám hộ tự động. CLB chịu trách nhiệm nhận diện người được cấp quyền và chuyển mật khẩu tạm qua kênh phù hợp.
