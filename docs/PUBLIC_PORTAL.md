# Tra cứu công khai đã đóng

Theo yêu cầu bắt buộc đăng nhập, hệ thống không còn cung cấp tra cứu võ sinh ẩn danh.
Các API /api/public/* trả 401 khi chưa đăng nhập, 410 khi đã đăng nhập; các cờ public cũ không mở lại truy cập.
Trang chủ, /tra-cuu, /ho-so/<id> hiển thị đăng nhập. Không có dữ liệu nhúng trong HTML.
Dùng /api/student/athletes/<id> và /api/student/achievements/<id> sau đăng nhập và đổi mật khẩu lần đầu.
Mọi yêu cầu đều kiểm tra phạm vi tại backend. Không có danh sách võ sinh toàn CLB cho gia đình.
GitHub Pages chỉ chứa một hồ sơ giả lập được ghi rõ dữ liệu mẫu; không bảo vệ dữ liệu thật.
scripts/build_public_preview.py từ chối xuất database thật và dọn public-data.json cùng tài nguyên tìm kiếm cũ.
