# Điểm danh và trạng thái học tập

Admin/HLV nhập trực tiếp trên website trong phạm vi hồ sơ được cấp; không có dữ liệu sinh tự động.
Hồ sơ → Chỉnh sửa hồ sơ → Trạng thái tập luyện: đang tập, tạm nghỉ, chuyển cơ sở hoặc trạng thái được CLB ghi nhận.
Điểm danh → Nhập điểm danh: võ sinh, ngày, giờ bắt đầu, lớp, cơ sở (nullable), trạng thái và ghi chú cho gia đình.
Trạng thái: present (có mặt), excused_absent (vắng có phép), unexcused_absent (vắng không phép).
Không có bản ghi nghĩa là chưa cập nhật, không phải vắng. Không nhập cho buổi tương lai.
Sửa qua nút Sửa; lưu trữ bản sai bằng Lưu trữ bản ghi sai. Mọi thao tác giữ audit.
Cặp võ sinh/ngày/giờ/lớp duy nhất với bản chưa lưu trữ; hỗ trợ nhiều buổi trong ngày.
Tên cơ sở tại thời điểm ghi nhận được giữ khi đổi tên cơ sở/chuyển nơi tập.
Gia đình xem thông tin của con, tổng số buổi theo trạng thái và lịch sử phân trang, không sửa được.

## API (đều yêu cầu phiên đăng nhập)

- GET /api/attendance: staff; phân trang, lọc athlete_id, status, from_date, to_date.
- POST /api/attendance: staff; nhập buổi.
- GET/PATCH/DELETE /api/attendance/<id>: staff đúng phạm vi. PATCH/DELETE bắt buộc version. DELETE lưu trữ, không xóa lịch sử.
- GET /api/athletes/<id>/attendance: đúng phạm vi, cho viewer xem con mình.
- GET /api/student/athletes/<id>: viewer, thông tin cá nhân + thành tích + điểm danh.

Mọi thao tác ghi yêu cầu CSRF. Coach không sửa danh tính/cơ sở qua endpoint điểm danh.
SQLite tự tạo bảng attendance_records rỗng khi nâng cấp. Sao lưu database và evidence trước khi nâng cấp/triển khai.
Bản Pages không có máy chủ điểm danh; hồ sơ mẫu hiển thị trạng thái chưa cập nhật và lịch sử trống.
