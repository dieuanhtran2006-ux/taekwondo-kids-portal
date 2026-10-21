# Đề nghị bổ sung thành tích và bản kiểm thử

## Hai chế độ

| Chế độ | Lưu ở đâu | Ai xem | Có tính huy chương không |
|---|---|---|---|
| GitHub Pages · dữ liệu mẫu | `localStorage` trên trình duyệt đang thử | Người dùng thiết bị đó | Không; số liệu minh họa giữ nguyên |
| Ứng dụng Python có backend | SQLite `achievement_submissions` | Quản trị viên | Chưa; cần tạo/liên kết, xác minh và cấp quyền riêng |

Bản Pages không có máy chủ tiếp nhận đề nghị. Không ghi “đã gửi CLB” khi chỉ lưu trên trình duyệt. Dữ liệu mẫu có tên/mã riêng, `verification_status=sample`, không đi qua hoặc thay đổi database thật. Biểu mẫu mẫu khóa tên/mã mẫu, bỏ trường liên hệ, không chấp nhận danh tính thật.

## Luồng vận hành thật

1. Khách tra cứu và mở biểu mẫu dưới kết quả tìm kiếm hoặc lịch sử hồ sơ. Không tìm thấy hồ sơ vẫn có thể gửi lời khai bằng tên/mã; không cần công khai dữ liệu trẻ em để tiếp nhận đề nghị.
2. Nhập giải, năm, nội dung, hình thức, huy chương và liên kết minh chứng nếu có. Cho phép “Chưa xác định”; thiếu thông tin vẫn là lời khai chờ làm rõ. Không suy luận huy chương từ emoji hoặc thành viên.
3. Người gửi đồng ý cho CLB đối chiếu, xem lại và gửi. UUID giữ nguyên trong lần thử gửi lại; cùng UUID với nội dung khác bị từ chối. Mã tiếp nhận không cấp quyền đọc thông tin.
4. Quản trị viên mở **Đề nghị phụ huynh**. Tên, mã, URL và người gửi đều chưa được kiểm chứng. Không tự động gắn hồ sơ kể cả trùng tên/mã; tham chiếu hồ sơ công khai cũng chỉ là lời khai.
5. Ghi chú đang đối chiếu/từ chối, hoặc xác nhận đã kiểm tra người nhận và trùng lặp. Có thể chọn kết quả hiện có để ghi quan hệ hoặc chọn giải/người nhận đã nhận diện để tạo kết quả mới.
6. Tạo mới luôn `pending`, các quyền công bố tắt. Nguồn được sao chép vào `source_original_text` và `source_row` trỏ tới mã đề nghị; thông tin liên hệ không sao chép sang nguồn thành tích. Quy trình xác minh, minh chứng và công bố hiện có tiếp tục áp dụng.

Đề nghị đã tiếp nhận/từ chối không được xử lý lần nữa. Sửa quyết định dùng đối chiếu quản trị và audit, không sửa nguyên văn lời khai. MVP chưa có cổng theo dõi trạng thái theo mã cho khách; liên hệ tùy chọn phục vụ làm rõ.

## API

- `POST /api/public/submissions`: JSON tối đa 16 KB, cùng nguồn, 5 lần/giờ/địa chỉ kết nối; honeypot và kiểm tra kiểu/độ dài/danh mục/URL. Trả `receipt_id`, `status=received`, `duplicate`, không trả dữ liệu cá nhân hoặc trạng thái xử lý nội bộ.
- `GET /api/submissions?status=&q=&page=&limit=` và `GET /api/submissions/<id>`: chỉ admin, phân trang, tìm kiếm literal.
- `PATCH /api/submissions/<id>`: admin, CSRF, `version`, trạng thái `pending/reviewing/rejected`, lý do bắt buộc. Không được sửa dữ liệu nguồn.
- `POST /api/submissions/<id>/convert`: admin, CSRF, `version`, `identity_checked=true`, `duplicate_checked=true`, `resolution_notes`, `action=create|link`. Tạo mới nhận `achievement`; liên kết nhận `achievement_id`.

Danh sách và chi tiết không có API ẩn danh. Không CORS, không secrets trên frontend. Đường dẫn minh chứng không được backend tự fetch. Giới hạn IP dùng địa chỉ kết nối thật, không tin tùy tiện `X-Forwarded-For`; khi triển khai reverse proxy cần rate limit thêm ở proxy theo IP khách để tránh tất cả khách dùng chung hạn mức. Giới hạn in-memory đặt lại khi restart và không chia sẻ giữa nhiều worker; cần rate limit chung trước khi vận hành lưu lượng lớn.

## Dựng bản Pages mẫu

```powershell
python scripts/build_public_preview.py --sample --base-path /taekwondo-kids-preview/ --output ../tkd-github-pages-preview
```

Chế độ `--sample` không mở database. Mặc định không có `--sample` hoặc `--db` thì xuất bản trống. Muốn xuất dữ liệu thật đã cấp quyền, dùng `--db /duong-dan/portal.sqlite3`; lớp `PublicPortal` vẫn lọc theo các quyền công bố. Không tải database, Excel nội bộ, contact hoặc minh chứng tải lên vào repository Pages. Bản snapshot thật chưa có backend sẽ ghi rõ tính năng gửi chưa kết nối.

Triển khai đầy đủ bằng backend cùng nguồn, HTTPS, SQLite trên đĩa bền, tài khoản admin và cấu hình host/cookie theo `DEPLOYMENT.md`. Không cần Google credentials để lưu đề nghị. Google Drive chỉ là URL minh chứng, chưa tự xác thực quyền hoặc đồng bộ.
