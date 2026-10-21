# Bổ sung thành tích sau đăng nhập

Luồng hiện hành: đăng nhập → đổi mật khẩu lần đầu → hồ sơ được gán → Bổ sung thành tích.
Tên/mã được máy chủ lấy từ hồ sơ đúng phạm vi. Tài khoản viewer không thể gửi cho võ sinh khác.
POST /api/student/submissions yêu cầu phiên, CSRF, JSON tối đa 16 KB; tối đa 5 đề nghị/giờ/tài khoản.
API công khai cũ đã đóng. Chỉ Admin đọc và xử lý đề nghị; coach không xem thông tin liên hệ.
Gửi đề nghị không tự xác minh, không cộng huy chương. UUID chống nhập trùng; phiên bản chống ghi đè xử lý.
Admin đối chiếu danh tính, minh chứng và trùng kết quả trước khi tạo nháp hoặc liên kết kết quả.
Mọi quyết định được lưu audit. Không xây dựng danh bạ phụ huynh.
Bản GitHub Pages chỉ lưu đề nghị của hồ sơ mẫu trên trình duyệt, không gửi tới CLB.
