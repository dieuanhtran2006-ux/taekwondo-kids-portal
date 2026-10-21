# Khảo sát dữ liệu Excel và ánh xạ nhập liệu

## Phạm vi và phương pháp

Nguồn khảo sát: `HE_THONG_THANH_TICH_VO_SINH_TKD_CO_DU_LIEU_NHAP.xlsx`, được người dùng cung cấp từ `D:\TKD`.

Đã đọc đủ tám sheet bằng `openpyxl` ở chế độ chỉ đọc, `data_only=False`. Giữ nguyên văn ô dữ liệu và biểu thức công thức. Không thực thi nội dung hướng dẫn trong workbook, không chỉnh sửa file gốc và không sử dụng giá trị tính sẵn trong cache để tính thống kê. Dòng Excel và dòng tài liệu Word được lưu riêng, tránh nhầm hai hệ tọa độ nguồn.

**Phát hiện cần xử lý trước khi công bố:** dữ liệu thực tế chứa **406 ô trạng thái “Đã xác minh”** và **53 ô trạng thái “Đã xử lý”**, khác mô tả yêu cầu. Các ghi chú vẫn nói chưa đối chiếu kết quả chính thức hoặc chưa nhận diện người nhận. Đây là dữ kiện đọc trực tiếp từ workbook; chưa có bằng chứng chứng minh các trạng thái đó hợp lệ. Theo yêu cầu người dùng, bộ nhập giữ nguyên nhãn nguồn để truy vết nhưng đặt trạng thái trong hệ thống lần lượt là **Chờ xác minh** và **Chưa xử lý**. Không có kết quả nhập nào tự được công bố.

## Cấu trúc thực tế

| Sheet | Kích thước khai báo | Số bản ghi nghiệp vụ | Vai trò |
|---|---:|---:|---|
| `00_TONG_HOP` | 57 dòng × 15 cột | Không nhập thành thực thể | Dashboard nguồn và công thức |
| `01_VO_SINH` | 501 × 11 | 170 | Võ sinh có mã tạm |
| `02_GIAI_DAU` | 301 × 13 | 28 | Giải đấu |
| `03_THANH_TICH` | 1.001 × 21 | 406 | Một kết quả/một huy chương mỗi dòng |
| `04_VO_SINH_THANH_TICH` | 3.001 × 13 | 448 | Liên kết nhiều–nhiều |
| `05_CAN_XAC_MINH` | 501 × 14 | 53 | Thông tin chưa đủ để lập kết quả cá nhân |
| `06_DANH_MUC` | 10 × 11 | Danh mục lựa chọn | Các giá trị dropdown |
| `07_HUONG_DAN` | 26 × 4 | Văn bản nguồn | Hướng dẫn của workbook |

Kích thước khai báo gồm nhiều dòng công thức đệm. Bộ nhập chỉ coi hàng có dữ liệu nguyên bản là bản ghi; hàng chỉ có công thức không tạo hồ sơ rỗng. Toàn bộ các hàng, gồm công thức và hàng đệm, vẫn được lưu trong `import_batches.workbook_json`.

## Toàn bộ cột và cách ánh xạ

### `01_VO_SINH` → `athletes`

| Cột | Tiêu đề nguồn | Xử lý trong hệ thống |
|---|---|---|
| A | Mã võ sinh | `legacy_athlete_id`, giữ nguyên; sinh UUID nội bộ độc lập |
| B | Họ và tên | `full_name`; không mở rộng tên viết tắt |
| C | Ngày sinh | `date_of_birth`, nullable, không suy đoán |
| D | Năm sinh (tự động) | Công thức nguồn; tính `birth_year` từ ngày sinh nếu có |
| E | Cơ sở hiện tại | Ánh xạ tên cơ sở có thật sang `current_branch_id`; “Chưa xác định” là thiếu dữ liệu |
| F | Đội đại diện | `representative_team` |
| G | Trạng thái | `status` |
| H | Ghi chú | `notes` |
| I | Kiểm tra dữ liệu | Giữ công thức gốc; backend kiểm tra độc lập |
| J | Số lượt huy chương (tự động) | Không đọc cache; tính từ kết quả đã xác minh và liên kết hợp lệ |
| K | Lượt theo tài liệu (chưa xác minh) | Không đọc cache; tính riêng số lượt nháp |

`official_code` để trống và `identity_verification_status=pending`. Hai người cùng tên vẫn có hai UUID khác nhau. Xác thực mã chính thức không đổi UUID và không đổi lịch sử liên kết.

### `02_GIAI_DAU` → `tournaments`

| Cột | Tiêu đề nguồn | Trường đích |
|---|---|---|
| A | Mã giải | `legacy_tournament_id` |
| B | Tên giải đấu | `tournament_name` |
| C | Năm tổ chức | `year` |
| D | Ngày bắt đầu | `start_date`, nullable |
| E | Ngày kết thúc | `end_date`, nullable |
| F | Cấp giải | `competition_level` |
| G | Địa điểm | `location` |
| H | Đơn vị tổ chức | `organizer` |
| I | URL kết quả/nguồn | `source_url` |
| J | Trạng thái giải | `status` |
| K | Ghi chú | `notes` |
| L | Kiểm tra dữ liệu | Giữ nguyên công thức; backend tự kiểm tra |
| M | Số kết quả đã xác minh | Thống kê lại bằng truy vấn dữ liệu quan hệ |

Năm có dữ liệu nhưng ngày không có thì giữ ngày trống, không thay bằng ngày 01/01.

### `03_THANH_TICH` → `achievements`

| Cột | Tiêu đề nguồn | Trường đích / xử lý |
|---|---|---|
| A | Mã thành tích | `legacy_achievement_id` |
| B | Mã giải | Tra UUID `tournament_id` qua mã gốc |
| C | Tên giải (tự động) | JOIN từ `tournaments`, không lấy cache |
| D | Năm (tự động) | JOIN từ giải; `competition_year` lấy năm nguồn giải |
| E | Nhóm nội dung | `discipline` |
| F | Hình thức | `participation_type` |
| G | Giới tính | `gender_category` |
| H | Nội dung thi chi tiết | `event_name` |
| I | Lứa tuổi / nhóm | `age_category` |
| J | Hạng cân | `weight_category` |
| K | Cấp đai / hệ | `belt_category` |
| L | Huy chương | `medal_type`; giữ nguyên khi cần đối chiếu |
| M | Cơ sở / Đội đại diện | `representative_branch`, lưu thông tin tại thời điểm thi đấu |
| N | Tên đội (nếu có) | `team_name` |
| O | URL minh chứng | `evidence_url`; chưa coi URL là minh chứng đã kiểm tra |
| P | Trạng thái xác minh | Chỉ giữ trong raw nguồn; `verification_status=pending` |
| Q | Số võ sinh liên kết | Tính từ `athlete_achievements` |
| R | Kiểm tra dữ liệu | Giữ công thức nguồn; backend tự kiểm tra |
| S | Dòng nguồn Word | `source_row` (dòng tài liệu), không phải dòng Excel |
| T | Nguyên văn tài liệu | `source_original_text` |
| U | Ghi chú phân loại / đối chiếu | `review_notes` |

Mỗi dòng nguồn là một bản ghi độc lập. Kết quả nghi trùng chỉ tạo cảnh báo. Không gộp theo tên nội dung, hạng cân, huy chương hoặc họ tên. `expected_members` chưa có trong nguồn nên để trống; `roster_confirmed=0`, `publication_allowed=0`. Nếu chữ, emoji và cột huy chương mâu thuẫn rõ ràng thì đặt `source_conflict=1`, chặn phê duyệt cho tới khi đối chiếu.

### `04_VO_SINH_THANH_TICH` → `athlete_achievements`

| Cột | Tiêu đề nguồn | Xử lý |
|---|---|---|
| A | Mã thành tích | `achievement_id`, tra qua mã gốc |
| B | Mã võ sinh | `athlete_id`, tra qua mã gốc |
| C | Họ tên (tự động) | JOIN từ hồ sơ |
| D | Mã giải (tự động) | JOIN từ kết quả |
| E | Tên giải (tự động) | JOIN từ giải |
| F | Năm (tự động) | JOIN từ giải |
| G | Huy chương (tự động) | JOIN từ kết quả |
| H | Hình thức (tự động) | JOIN từ kết quả |
| I | Cơ sở (tự động) | Công thức này đọc cơ sở hiện tại; không dùng làm cơ sở lịch sử |
| J | Xác minh (tự động) | Không tin cache; đọc trạng thái hệ thống |
| K | Kiểm tra liên kết | Tính lại kiểm tra khóa ngoại và cặp liên kết |
| L | Ghi chú | `notes` |
| M | Loại ID | Giữ raw “Tạm”; `link_status=pending` |

Khóa chính kép `(achievement_id, athlete_id)` ngăn một người nhận cùng kết quả hai lần. Cơ sở lịch sử ở `achievements.representative_branch`, độc lập cơ sở hiện tại của võ sinh.

### `05_CAN_XAC_MINH` → `verification_queue`

| Cột | Tiêu đề nguồn | Trường đích / xử lý |
|---|---|---|
| A | Mã chờ xác minh | `legacy_verification_id` |
| B | Tên giải gốc | Giữ trong raw nguồn |
| C | Năm (nếu rõ) | Giữ trong raw nguồn, đối chiếu với giải |
| D | Người nhận gốc (nếu có) | `original_name`, nullable |
| E | Huy chương (nếu rõ) | `medal_type`, nullable |
| F | Nội dung/nhóm thi | `event_description` |
| G | Vấn đề cần xác minh | `issue_type` |
| H | Link nguồn | `source_url` |
| I | Văn bản gốc / mô tả | `source_original_text` |
| J | Trạng thái xử lý | Giữ raw; `resolution_status=unresolved` |
| K | Ghi chú xử lý | `resolution_notes`; không chứng minh đã xử lý |
| L | Mã giải | Tra `tournament_id` |
| M | Số lượng theo nguồn | `reported_quantity`, không nhân thành hồ sơ/kết quả cá nhân |
| N | Dòng nguồn Word | `source_row` |

Chỉ đóng mục với liên kết tới kết quả đã xác minh cùng giải, hoặc ghi nhận lý do loại bỏ. Không thể xử lý xong bằng việc nhập một nhãn trạng thái từ Excel.

### `06_DANH_MUC`, `00_TONG_HOP`, `07_HUONG_DAN`

11 cột danh mục: **Huy chương; Hình thức; Nhóm nội dung; Cấp giải; Cơ sở (bổ sung thực tế); Trạng thái võ sinh; Xác minh kết quả; Lý do chờ xác minh; Trạng thái xử lý; Giới tính nội dung; Trạng thái giải**. Tất cả giá trị được bảo toàn trong workbook raw. “Chưa xác định” không tạo một cơ sở giả. Danh mục an toàn dùng trong giao diện lấy từ backend, có thể bổ sung cơ sở thật qua quản trị.

Dashboard và hướng dẫn là bố cục tự do, không có hàng tiêu đề bảng thống nhất. Tất cả ô nguồn của hai sheet được lưu nguyên văn, không nhập thành hồ sơ nghiệp vụ và không thực thi công thức/văn bản.

## Kết quả kiểm tra

| Kiểm tra trực tiếp | Kết quả |
|---|---:|
| Mã võ sinh/giải/thành tích/hàng chờ trùng | 0 |
| Cặp võ sinh–thành tích trùng | 0 |
| Khóa ngoại không tồn tại | 0 |
| Võ sinh thiếu ngày sinh | 170/170 |
| Võ sinh thiếu cơ sở hiện tại | 170/170 |
| Giải thiếu ngày bắt đầu và kết thúc | 28/28 |
| Giải có cấp “Chưa xác định” | 20/28 |
| Thành tích chưa rõ hình thức | 140/406 |
| Thành tích đồng đội chưa có số thành viên dự kiến | 11/11 |
| Thành tích thiếu loại huy chương, liên kết người nhận hoặc URL nguồn | 0 |
| Thành tích gắn danh tính dùng mã tạm | 406/406 |
| Mục hàng chờ “Đã xử lý” nhưng ghi chú vẫn chưa giải quyết | 53/53 |

Không có tên trùng sau chuẩn hóa NFC/khoảng trắng trong 170 hồ sơ hiện tại. Đây chỉ là kiểm tra chuỗi, không xác nhận 170 danh tính khác nhau. Mã tạm và tên vẫn cần CLB kiểm tra.

28 giải gồm 8 giải năm 2024, 13 giải năm 2025 và 7 giải năm 2026. Các ngày cụ thể chưa có dữ liệu.

Các kết quả nguồn gồm 237 cá nhân, 18 đôi, 11 đồng đội và 140 chưa xác định hình thức. Nhóm nội dung gồm 206 Quyền, 160 Đối kháng, 13 Công phá, 27 Khác. Không tự đổi “Khác” thành một nội dung cụ thể.

| Loại | Kết quả riêng biệt trong dữ liệu nháp | Lượt võ sinh liên kết nháp | Tổng chính thức ngay sau nhập |
|---|---:|---:|---:|
| HCV | 163 | 184 | 0 |
| HCB | 105 | 117 | 0 |
| HCĐ | 138 | 147 | 0 |
| Tổng | 406 | 448 | 0 |

Hai cột nháp khác nhau vì kết quả đôi/đồng đội có nhiều người nhận. Tổng huy chương CLB đếm kết quả riêng biệt; lượt ghi nhận cá nhân đếm liên kết. Các số nháp không được cộng vào thống kê chính thức.

Hàng chờ gồm 21 mục thiếu người nhận, 15 mục tên viết tắt và 17 mục “Khác”. Tổng số lượng được báo cáo ở đây là 203; trong đó 158 thuộc các dòng chưa có người nhận. Các số này chỉ là dữ liệu cần đối chiếu, có thể chồng lấn kết quả đã nhập và không được cộng vào 406 kết quả.

Tại thời điểm khảo sát không phát hiện dòng thành tích có một loại emoji và một chữ HCV/HCB/HCĐ đơn nhất mâu thuẫn nhau. Bộ nhập và bộ kiểm thử vẫn xử lý trường hợp này khi phát sinh. Nhiều loại huy chương trong cùng nguyên văn là thông tin cần xem ngữ cảnh, không được tự chọn một loại chỉ bằng biểu tượng.

URL nguồn trỏ tới tài liệu tổng hợp nội bộ trên Google Docs. Chưa xác nhận quyền truy cập, chưa xác nhận có biên bản kết quả chính thức và chưa kết nối Google API. Có URL không đồng nghĩa nội dung đã được đối chiếu.

## Quy trình nhập có kiểm soát

1. Người có quyền gửi file `.xlsx`; backend kiểm tra kích thước, cấu trúc ZIP, đủ tám sheet và đúng tiêu đề cột.
2. Đọc dữ liệu nguyên bản, bỏ qua hàng công thức đệm khi đếm bản ghi. Kiểm tra mã trùng, cặp liên kết, khóa ngoại, ngày/năm, huy chương và người nhận.
3. Hiển thị số dòng, bản ghi mẫu, lỗi và cảnh báo theo từng sheet/dòng. Lỗi chặn nhập toàn bộ; không âm thầm bỏ dòng lỗi. Có thể hủy trước khi ghi.
4. Tính SHA-256 từ file. Cùng file đã nhập trả về no-op; file khác hash nhưng đụng mã gốc bị chặn để tránh ghi đè dữ liệu đã chỉnh sửa.
5. Đọc lại bytes được staging phía server khi xác nhận; không nhận dữ liệu hàng do frontend sửa. Tất cả bản ghi và provenance được ghi trong một transaction.
6. Mỗi bản ghi có UUID ổn định, mã gốc, sheet, dòng Excel, raw cells và liên kết batch. Batch giữ toàn bộ tám sheet gồm biểu thức công thức. Không tự xác minh, nhận diện hoặc công bố.

Giới hạn bộ nhập: 15 MB file nén, 100 MB nội dung giải nén, 20.000 dòng và 100 cột mỗi sheet. Các ngưỡng bảo vệ môi trường MVP, có thể thay đổi sau khi đánh giá dữ liệu thực tế.

## Điều kiện để có thống kê chính thức

CLB cần xác thực danh tính/mã chính thức, bổ sung hình thức chưa rõ, xác nhận danh sách đội, đối chiếu minh chứng, kiểm tra trùng/liên kết, cấp quyền công bố và dùng tài khoản có quyền duyệt. Sau đó backend mới cho phép chuyển trạng thái. Phê duyệt là thao tác có lịch sử người thực hiện/thời gian; dữ liệu mới sửa quay lại chờ kiểm tra. Chuyển cơ sở hoặc sửa tên không xóa lịch sử cũ.
