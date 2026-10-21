# Sơ đồ quan hệ và nguyên tắc dữ liệu

```mermaid
erDiagram
    BRANCHES ||--o{ ATHLETES : "cơ sở hiện tại"
    TOURNAMENTS ||--o{ ACHIEVEMENTS : "có kết quả"
    ATHLETES ||--o{ ATHLETE_ACHIEVEMENTS : "nhận"
    ACHIEVEMENTS ||--o{ ATHLETE_ACHIEVEMENTS : "có người nhận"
    TOURNAMENTS ||--o{ VERIFICATION_QUEUE : "cần đối chiếu"
    ACHIEVEMENTS o|--o{ VERIFICATION_QUEUE : "kết quả được đối chiếu"
    ACHIEVEMENTS ||--o{ EVIDENCE_FILES : "có minh chứng"
    ACHIEVEMENTS o|--o{ ACHIEVEMENT_SUBMISSIONS : "đề nghị đã tiếp nhận"
    USERS o|--o{ ACHIEVEMENT_SUBMISSIONS : "đối chiếu"
    USERS ||--o{ IMPORT_BATCHES : "nhập"
    IMPORT_BATCHES ||--o{ SOURCE_RECORDS : "bảo toàn nguồn"
    USERS ||--o{ AUDIT_LOGS : "thực hiện"
    USERS ||--o{ USER_ATHLETES : "được cấp hồ sơ"
    ATHLETES ||--o{ USER_ATHLETES : "được xem"
    ATHLETES o|--o| USERS : "tài khoản theo mã võ sinh"
    USERS ||--o{ USER_BRANCHES : "được cấp cơ sở"
    BRANCHES ||--o{ USER_BRANCHES : "phạm vi cán bộ"

    ACHIEVEMENT_SUBMISSIONS {
        text id PK
        text client_request_id UK "chống gửi trùng"
        text payload_hash
        text payload_json "lời khai bất biến, chỉ admin đọc"
        text status "pending reviewing converted rejected"
        text linked_achievement_id FK "nullable"
        text reviewed_by FK "nullable"
        text resolution_notes
        text created_at
        text reviewed_at
        integer version
    }
    BRANCHES {
        text id PK
        text name UK
        text notes
        integer version
        integer archived
    }
    ATHLETES {
        text id PK
        text legacy_athlete_id UK
        text official_code UK
        text full_name
        text date_of_birth "nullable, nội bộ"
        integer birth_year "chỉ suy ra từ DOB có thật"
        text current_branch_id FK
        text representative_team
        text status
        text identity_verification_status
        integer public_profile_allowed "mặc định 0, admin cấp quyền công khai"
        text notes
        integer version
        integer archived
    }
    TOURNAMENTS {
        text id PK
        text legacy_tournament_id UK
        text tournament_name
        integer year
        text start_date "nullable"
        text end_date "nullable"
        text competition_level
        text location
        text organizer
        text source_url
        text status
        text notes
        integer version
        integer archived
    }
    ACHIEVEMENTS {
        text id PK
        text legacy_achievement_id UK
        text tournament_id FK
        text discipline
        text participation_type
        text gender_category
        text event_name
        text age_category
        text weight_category
        text belt_category
        text medal_type
        text representative_branch "thông tin lịch sử"
        text team_name
        text evidence_url
        integer evidence_publication_allowed
        integer public_evidence_allowed "mặc định 0, URL cho khách"
        text verification_status
        integer competition_year
        integer expected_members "nullable"
        integer roster_confirmed
        integer publication_allowed
        integer public_search_allowed "mặc định 0, kết quả cho khách"
        integer source_conflict
        text source_row "dòng tài liệu gốc"
        text source_original_text
        text review_notes
        text verified_by
        text verified_at
        integer version
        integer archived
    }
    ATHLETE_ACHIEVEMENTS {
        text achievement_id PK,FK
        text athlete_id PK,FK
        text link_status
        text notes
    }
    VERIFICATION_QUEUE {
        text id PK
        text legacy_verification_id UK
        text tournament_id FK
        text original_name
        text medal_type
        text event_description
        text issue_type
        integer reported_quantity
        text source_url
        text source_original_text
        text source_row
        text resolution_status
        text resolution_notes
        text reviewed_by
        text reviewed_at
        text linked_achievement_id FK
        integer version
        integer archived
    }
    IMPORT_BATCHES {
        text id PK
        text file_hash UK
        text filename
        text imported_at
        text imported_by FK
        text summary_json
        text workbook_json "đủ 8 sheet, raw và công thức"
    }
    SOURCE_RECORDS {
        integer id PK
        text batch_id FK
        text sheet
        integer excel_row
        text entity_type
        text entity_id "tham chiếu đa hình chỉ để truy vết"
        text original_json
    }
    USERS {
        text id PK
        text username UK
        text password_hash
        text role "admin, coach, viewer"
        integer can_verify
        integer must_change_password "bắt buộc đổi lần đầu"
        text password_changed_at
        text login_athlete_id FK,UK "nullable, hồ sơ ổn định"
        integer version
    }
    USER_ATHLETES {
        text user_id PK,FK
        text athlete_id PK,FK
    }
    USER_BRANCHES {
        text user_id PK,FK
        text branch_id PK,FK
    }
    EVIDENCE_FILES {
        text id PK
        text achievement_id FK
        text filename
        text storage_name "riêng tư, ngoài static"
        text mime_type
        integer publication_allowed
        integer public_access_allowed "mặc định 0, tải tệp cho khách"
    }
    AUDIT_LOGS {
        integer id PK
        text actor FK
        text action
        text entity_type
        text entity_id
        text created_at
        text before_json
        text after_json
    }
```

Sơ đồ thể hiện quan hệ nghiệp vụ và những trường chính. `app/schema.sql` là nguồn chuẩn cho tên cột, ràng buộc, index và các bảng phiên đăng nhập trong bản triển khai.

## Khóa, quyền và lịch sử

- UUID nội bộ không phụ thuộc tên/mã tạm. `official_code` được cấp sau khi nhận diện, duy nhất khi có giá trị. Tên không phải khóa duy nhất.
- `UNIQUE(achievement_id, athlete_id)` ngăn đếm cùng liên kết hai lần. Khóa ngoại không cho nhập mã tham chiếu không tồn tại.
- `file_hash` duy nhất giúp nhập lại cùng file không tạo trùng. File đổi nhưng dùng lại mã gốc phải được kiểm tra, không ghi đè tự động.
- `version` thực hiện khóa lạc quan: lưu với phiên bản cũ bị trả lỗi xung đột. Chỉnh sửa/xác minh ghi audit. Xóa nghiệp vụ dùng lưu trữ (`archived`), giữ dữ liệu lịch sử.
- `source_records` là hồ sơ nguồn bất biến theo batch, gồm tên sheet, dòng Excel, raw và công thức. `source_row` ở kết quả/hàng chờ là dòng tài liệu Word gốc, không thay thế `excel_row`.
- Cơ sở hiện tại thuộc võ sinh. Cơ sở/đội thi đấu thuộc từng kết quả. Đổi cơ sở hiện tại không làm thay đổi thông tin tại giải cũ.
- Tài khoản viewer chỉ truy cập UUID võ sinh được cấp. Backend kiểm tra quyền ở từng API và file minh chứng; dữ liệu ngày sinh đầy đủ và nguyên văn nội bộ không nằm trong payload viewer.
- Student Portal chỉ đọc kết quả đã xác minh và được phép công bố. Tên đồng đội khác và minh chứng chỉ được trả khi quyền tương ứng cho phép.

## Công thức thống kê

```sql
-- Một huy chương đôi/đồng đội được đếm một lần cho CLB.
SELECT medal_type, COUNT(*)
FROM achievements
WHERE verification_status = 'verified' AND archived = 0
GROUP BY medal_type;

-- Tổng lượt ghi nhận cho võ sinh được tính riêng.
SELECT a.medal_type, COUNT(*)
FROM achievements a
JOIN athlete_achievements aa ON aa.achievement_id = a.id
WHERE a.verification_status = 'verified' AND a.archived = 0
  AND aa.link_status = 'verified'
GROUP BY a.medal_type;
```

Ví dụ ba võ sinh nhận cùng HCV đồng đội: một dòng `achievements`, ba dòng `athlete_achievements`, tổng CLB bằng 1, tổng lượt cá nhân bằng 3. Tổng võ sinh/giải của một hồ sơ đếm UUID giải khác nhau, không đếm số dòng kết quả.

Các truy vấn vận hành còn áp dụng phạm vi được cấp, điều kiện dữ liệu hợp lệ và điều kiện công bố của người xem. Dữ liệu pending có thống kê riêng và không cộng vào tổng chính thức.

## Lớp dữ liệu và tích hợp

Giao diện gọi API xác thực; logic nghiệp vụ kiểm tra quyền, điều kiện xác minh, version và audit; repository SQLite lưu quan hệ và truy xuất nguồn. Importer chỉ nhận kết nối SQLite từ caller, không tự commit transaction, không chạy công thức và không gọi Google.

Google Sheets là lớp tích hợp tùy chọn phía backend. Google Drive lưu minh chứng theo quyền. Chưa có credentials thì hệ thống tiếp tục vận hành bằng SQLite và Excel, không giả định đã đồng bộ. Xem cấu hình tích hợp trong README và adapter. Dữ liệu kéo từ Google cần qua staging/đối chiếu version trước khi ghi; đường dẫn tài liệu không tự cấp quyền truy cập hoặc quyền công bố.
## Mở rộng điểm danh

```mermaid
erDiagram
    athletes ||--o{ attendance_records : records
    branches o|--o{ attendance_records : session_branch
    users ||--o{ attendance_records : records_and_edits
```

attendance_records lưu ngày, giờ, lớp, cơ sở tại buổi học, trạng thái, ghi chú cho gia đình, người nhập/sửa, phiên bản và dấu lưu trữ. Unique (athlete_id, session_date, start_time, class_name) với bản ghi chưa lưu trữ. Không tạo danh bạ phụ huynh hoặc lịch học.
