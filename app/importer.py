"""Read-only Excel parsing, preview and conservative transactional import.

The caller owns the SQLite transaction. Workbook instructions and formula caches
are never executed. Source verification labels are retained only in provenance.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timezone
from hashlib import sha256
from io import BytesIO
import json
import re
import sqlite3
import unicodedata
from uuid import uuid4
import zipfile

import openpyxl


SHEETS = (
    "00_TONG_HOP", "01_VO_SINH", "02_GIAI_DAU", "03_THANH_TICH",
    "04_VO_SINH_THANH_TICH", "05_CAN_XAC_MINH", "06_DANH_MUC", "07_HUONG_DAN",
)
HEADERS = {
    "01_VO_SINH": ("Mã võ sinh", "Họ và tên", "Ngày sinh", "Năm sinh (tự động)", "Cơ sở hiện tại", "Đội đại diện", "Trạng thái", "Ghi chú", "Kiểm tra dữ liệu", "Số lượt huy chương (tự động)", "Lượt theo tài liệu (chưa xác minh)"),
    "02_GIAI_DAU": ("Mã giải", "Tên giải đấu", "Năm tổ chức", "Ngày bắt đầu", "Ngày kết thúc", "Cấp giải", "Địa điểm", "Đơn vị tổ chức", "URL kết quả/nguồn", "Trạng thái giải", "Ghi chú", "Kiểm tra dữ liệu", "Số kết quả đã xác minh"),
    "03_THANH_TICH": ("Mã thành tích", "Mã giải", "Tên giải (tự động)", "Năm (tự động)", "Nhóm nội dung", "Hình thức", "Giới tính", "Nội dung thi chi tiết", "Lứa tuổi / nhóm", "Hạng cân", "Cấp đai / hệ", "Huy chương", "Cơ sở / Đội đại diện", "Tên đội (nếu có)", "URL minh chứng", "Trạng thái xác minh", "Số võ sinh liên kết", "Kiểm tra dữ liệu", "Dòng nguồn Word", "Nguyên văn tài liệu", "Ghi chú phân loại / đối chiếu"),
    "04_VO_SINH_THANH_TICH": ("Mã thành tích", "Mã võ sinh", "Họ tên (tự động)", "Mã giải (tự động)", "Tên giải (tự động)", "Năm (tự động)", "Huy chương (tự động)", "Hình thức (tự động)", "Cơ sở (tự động)", "Xác minh (tự động)", "Kiểm tra liên kết", "Ghi chú", "Loại ID"),
    "05_CAN_XAC_MINH": ("Mã chờ xác minh", "Tên giải gốc", "Năm (nếu rõ)", "Người nhận gốc (nếu có)", "Huy chương (nếu rõ)", "Nội dung/nhóm thi", "Vấn đề cần xác minh", "Link nguồn", "Văn bản gốc / mô tả", "Trạng thái xử lý", "Ghi chú xử lý", "Mã giải", "Số lượng theo nguồn", "Dòng nguồn Word"),
    "06_DANH_MUC": ("Huy chương", "Hình thức", "Nhóm nội dung", "Cấp giải", "Cơ sở (bổ sung thực tế)", "Trạng thái võ sinh", "Xác minh kết quả", "Lý do chờ xác minh", "Trạng thái xử lý", "Giới tính nội dung", "Trạng thái giải"),
}
MEDALS = {"HCV", "HCB", "HCĐ"}
PARTICIPATION_TYPES = {"Cá nhân", "Đôi", "Đồng đội", "Chưa xác định"}
MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_SHEET_ROWS = 20000
MAX_SHEET_COLUMNS = 100


def _dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _raw(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return value


def _formula(value):
    return isinstance(value, str) and value.startswith("=")


def _text(value):
    if value is None or _formula(value):
        return None
    return str(value).strip() or None


def _norm(value):
    return " ".join(unicodedata.normalize("NFC", str(value or "")).casefold().split())


def _int(value):
    if value is None or value == "" or _formula(value) or isinstance(value, bool):
        return None
    try:
        number = float(value)
        return int(number) if number.is_integer() else None
    except (ValueError, TypeError, OverflowError):
        return None


def _date(value):
    if value is None or _formula(value):
        return None
    if isinstance(value, (datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (ValueError, TypeError):
        return None


def _medal_conflict(value, normalized_medal):
    text = str(value or "")
    word = {x.upper() for x in re.findall(r"\b(?:HCV|HCB|HCĐ)\b", text, re.I)}
    emoji = {medal for symbol, medal in {"🥇": "HCV", "🥈": "HCB", "🥉": "HCĐ"}.items() if symbol in text}
    # A summary may mention several recipients/medals. Without a per-recipient
    # span we cannot assign one token to the current normalized result.
    if len(word) > 1 or len(emoji) > 1:
        return False
    if len(word) == 1 and len(emoji) == 1 and word != emoji:
        return True
    if normalized_medal in MEDALS:
        if len(word) == 1 and normalized_medal not in word:
            return True
        if len(emoji) == 1 and len(word) <= 1 and normalized_medal not in emoji:
            return True
    return False


def _multiple_medals_in_source(value):
    text = str(value or "")
    words = {x.upper() for x in re.findall(r"\b(?:HCV|HCB|HCĐ)\b", text, re.I)}
    emoji = {symbol for symbol in ["🥇", "🥈", "🥉"] if symbol in text}
    return len(words) > 1 or len(emoji) > 1


def _message(container, sheet, row, code, message):
    container.append({"sheet": sheet, "row": row, "code": code, "message": message})


def _parse(data, filename):
    result = {
        "sheets": [], "counts": {"athletes": 0, "tournaments": 0, "achievements": 0, "links": 0, "queue": 0},
        "warnings": [], "errors": [], "existing_file": False, "hash": sha256(data).hexdigest(),
        "sample_rows": {}, "policy": "Kết quả luôn nhập chờ xác minh; hàng chờ luôn mở để đối chiếu; không gộp theo tên.",
    }
    parsed = {"workbook": {"filename": filename, "sha256": result["hash"], "sheets": []}, "records": {}}
    if not data or len(data) > MAX_FILE_BYTES:
        _message(result["errors"], None, None, "FILE_SIZE", "File trống hoặc vượt giới hạn 20 MB.")
        return result, parsed
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > 10000 or sum(item.file_size for item in infos) > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("Dữ liệu giải nén vượt giới hạn 100 MB.")
        workbook = openpyxl.load_workbook(BytesIO(data), read_only=True, data_only=False, keep_links=False)
        if set(workbook.sheetnames) != set(SHEETS) or len(workbook.sheetnames) != len(SHEETS):
            _message(result["errors"], None, None, "SHEET_STRUCTURE", "File cần đúng 8 sheet: " + ", ".join(SHEETS))
        for sheet in workbook:
            if sheet.max_row > MAX_SHEET_ROWS or sheet.max_column > MAX_SHEET_COLUMNS:
                raise ValueError("Sheet vượt giới hạn 20.000 dòng hoặc 100 cột.")
            raw_rows = list(sheet.values)
            source_rows = []
            data_rows = []
            for row_num, row in enumerate(raw_rows, 1):
                source_rows.append({"row_number": row_num, "raw_cells": [_raw(v) for v in row]})
                if row_num > 1 and sheet.title in HEADERS and any(v is not None and not _formula(v) for v in row):
                    if sheet.title == "06_DANH_MUC":
                        continue
                    data_rows.append({"row": row_num, "cells": list(row)})
            headers = HEADERS.get(sheet.title)
            if headers and (not raw_rows or tuple(raw_rows[0][:len(headers)]) != headers):
                _message(result["errors"], sheet.title, 1, "HEADER_MISMATCH", "Tên hoặc thứ tự cột khác cấu trúc nguồn. Chưa ghi dữ liệu.")
            parsed["records"][sheet.title] = data_rows
            parsed["workbook"]["sheets"].append({"name": sheet.title, "max_row": sheet.max_row, "max_column": sheet.max_column, "rows": source_rows})
            result["sheets"].append({"name": sheet.title, "rows": len(data_rows) if sheet.title in HEADERS and sheet.title != "06_DANH_MUC" else len(source_rows), "columns": sheet.max_column})
            result["sample_rows"][sheet.title] = [{"row": r["row"], "cells": [_raw(v) for v in r["cells"]]} for r in data_rows[:5]]
        workbook.close()
    except Exception as exc:
        _message(result["errors"], None, None, "WORKBOOK_READ", "Không đọc được file Excel hợp lệ: " + str(exc)[:200])
        return result, parsed
    if result["errors"]:
        return result, parsed
    rows = parsed["records"]
    for sheet, key in [("01_VO_SINH", "athletes"), ("02_GIAI_DAU", "tournaments"), ("03_THANH_TICH", "achievements"), ("04_VO_SINH_THANH_TICH", "links"), ("05_CAN_XAC_MINH", "queue")]:
        result["counts"][key] = len(rows.get(sheet, []))
    id_sets = {}
    for sheet in ["01_VO_SINH", "02_GIAI_DAU", "03_THANH_TICH", "05_CAN_XAC_MINH"]:
        ids = Counter(_text(row["cells"][0]) for row in rows[sheet])
        id_sets[sheet] = set(ids)
        for row in rows[sheet]:
            value = _text(row["cells"][0])
            if not value:
                _message(result["errors"], sheet, row["row"], "MISSING_ID", "Thiếu mã gốc.")
            elif ids[value] > 1:
                _message(result["errors"], sheet, row["row"], "DUPLICATE_ID", "Trùng mã gốc: " + value)
    names = Counter(_norm(row["cells"][1]) for row in rows["01_VO_SINH"])
    for row in rows["01_VO_SINH"]:
        c, number = row["cells"], row["row"]
        if not _text(c[1]):
            _message(result["errors"], "01_VO_SINH", number, "MISSING_NAME", "Thiếu họ tên võ sinh.")
        if c[2] is not None and not _date(c[2]):
            _message(result["errors"], "01_VO_SINH", number, "INVALID_DOB", "Ngày sinh không hợp lệ; không tự suy đoán định dạng ngày.")
        if names[_norm(c[1])] > 1:
            _message(result["warnings"], "01_VO_SINH", number, "SAME_NAME", "Tên trùng với hồ sơ khác. Giữ riêng các hồ sơ.")
        _message(result["warnings"], "01_VO_SINH", number, "IDENTITY_PENDING", "Mã gốc được giữ để đối chiếu; danh tính chưa được hệ thống xác thực.")
    for row in rows["02_GIAI_DAU"]:
        c, number = row["cells"], row["row"]
        year = _int(c[2])
        if not _text(c[1]) or year is None or not 1900 <= year <= 2200:
            _message(result["errors"], "02_GIAI_DAU", number, "TOURNAMENT_FIELDS", "Thiếu tên giải hoặc năm tổ chức hợp lệ.")
        for index in [3, 4]:
            if c[index] is not None and not _date(c[index]):
                _message(result["errors"], "02_GIAI_DAU", number, "INVALID_DATE", "Ngày giải không hợp lệ.")
        start, end = _date(c[3]), _date(c[4])
        if start and year is not None and int(start[:4]) != year:
            _message(result["errors"], "02_GIAI_DAU", number, "YEAR_MISMATCH", "Năm bắt đầu khác năm tổ chức giải.")
        if start and end and end < start:
            _message(result["errors"], "02_GIAI_DAU", number, "DATE_ORDER", "Ngày kết thúc trước ngày bắt đầu.")
    pairs = Counter((_text(row["cells"][0]), _text(row["cells"][1])) for row in rows["04_VO_SINH_THANH_TICH"])
    members = defaultdict(list)
    for row in rows["04_VO_SINH_THANH_TICH"]:
        c, number = row["cells"], row["row"]
        achievement_id, athlete_id = _text(c[0]), _text(c[1])
        if achievement_id not in id_sets["03_THANH_TICH"] or athlete_id not in id_sets["01_VO_SINH"]:
            _message(result["errors"], "04_VO_SINH_THANH_TICH", number, "INVALID_FK", "Mã thành tích hoặc võ sinh không tồn tại.")
        if pairs[(achievement_id, athlete_id)] > 1:
            _message(result["errors"], "04_VO_SINH_THANH_TICH", number, "DUPLICATE_LINK", "Trùng cặp võ sinh–thành tích.")
        members[achievement_id].append(athlete_id)
    signatures = defaultdict(list)
    for row in rows["03_THANH_TICH"]:
        c, number = row["cells"], row["row"]
        legacy_id = _text(c[0])
        member_count = len(members[legacy_id])
        if _text(c[1]) not in id_sets["02_GIAI_DAU"]:
            _message(result["errors"], "03_THANH_TICH", number, "INVALID_FK", "Mã giải không tồn tại.")
        if _text(c[11]) not in MEDALS:
            _message(result["errors"], "03_THANH_TICH", number, "MISSING_MEDAL", "Thiếu hoặc không hợp lệ loại huy chương; cần đối chiếu trước khi nhập.")
        if not member_count:
            _message(result["errors"], "03_THANH_TICH", number, "MISSING_RECIPIENT", "Chưa có người nhận. Chuyển thông tin tổng hợp vào hàng chờ xác minh.")
        if not _text(c[4]) or not _text(c[7]):
            _message(result["errors"], "03_THANH_TICH", number, "MISSING_EVENT", "Thiếu nhóm nội dung hoặc nội dung thi đấu.")
        if _text(c[5]) not in PARTICIPATION_TYPES or _text(c[5]) == "Chưa xác định":
            _message(result["warnings"], "03_THANH_TICH", number, "UNKNOWN_PARTICIPATION", "Chưa xác định hình thức thi. Thành tích chưa đủ điều kiện phê duyệt.")
        if _text(c[5]) == "Cá nhân" and member_count != 1:
            _message(result["warnings"], "03_THANH_TICH", number, "MEMBER_COUNT", "Nội dung cá nhân cần đúng một người nhận.")
        if _text(c[5]) == "Đôi" and member_count != 2:
            _message(result["warnings"], "03_THANH_TICH", number, "MEMBER_COUNT", "Nội dung đôi cần đúng hai người nhận.")
        if _text(c[5]) == "Đồng đội":
            _message(result["warnings"], "03_THANH_TICH", number, "TEAM_ROSTER_PENDING", "Chưa có số thành viên dự kiến và xác nhận đủ đội. Không suy ra từ số liên kết.")
        if not _text(c[14]):
            _message(result["warnings"], "03_THANH_TICH", number, "MISSING_EVIDENCE", "Thiếu nguồn minh chứng, chưa đủ điều kiện phê duyệt.")
        if _medal_conflict(c[19], _text(c[11])):
            _message(result["warnings"], "03_THANH_TICH", number, "SOURCE_CONFLICT", "Emoji, chữ huy chương hoặc cột chuẩn hóa mâu thuẫn. Giữ nguyên và chặn phê duyệt đến khi đối chiếu.")
        elif _multiple_medals_in_source(c[19]):
            _message(result["warnings"], "03_THANH_TICH", number, "MULTI_MEDAL_SOURCE", "Nguyên văn nêu nhiều loại huy chương. Cần đối chiếu đúng người/nội dung; không tự quy emoji hoặc chữ cho bản ghi này.")
        # Literal years must agree; formula cells are never evaluated or trusted.
        if not _formula(c[3]) and c[3] is not None:
            target = next((r for r in rows["02_GIAI_DAU"] if _text(r["cells"][0]) == _text(c[1])), None)
            if target and _int(c[3]) != _int(target["cells"][2]):
                _message(result["errors"], "03_THANH_TICH", number, "YEAR_MISMATCH", "Năm thành tích không khớp năm của giải.")
        _message(result["warnings"], "03_THANH_TICH", number, "VERIFICATION_RESET", "Trạng thái nguồn «" + str(c[15] or "trống") + "» chỉ được lưu để truy vết. Trạng thái nhập là Chờ xác minh.")
        signature = tuple(_norm(c[i]) for i in [1, 4, 5, 7, 8, 9, 10, 11]) + tuple(sorted(members[legacy_id]))
        signatures[signature].append(number)
    for numbers in signatures.values():
        if len(numbers) > 1:
            for number in numbers:
                _message(result["warnings"], "03_THANH_TICH", number, "SUSPECT_DUPLICATE", "Có bản ghi cùng giải/nội dung/huy chương/người nhận ở các dòng " + ", ".join(map(str, numbers)) + ". Giữ riêng, cần kiểm tra trùng.")
    for row in rows["05_CAN_XAC_MINH"]:
        c, number = row["cells"], row["row"]
        if _text(c[11]) and _text(c[11]) not in id_sets["02_GIAI_DAU"]:
            _message(result["errors"], "05_CAN_XAC_MINH", number, "INVALID_FK", "Mã giải trong hàng chờ không tồn tại.")
        if c[12] is not None and (_int(c[12]) is None or _int(c[12]) < 1):
            _message(result["errors"], "05_CAN_XAC_MINH", number, "INVALID_QUANTITY", "Số lượng theo nguồn phải là số nguyên dương.")
        _message(result["warnings"], "05_CAN_XAC_MINH", number, "QUEUE_REOPENED", "Giữ số lượng báo cáo trong hàng chờ, chưa tạo thành tích cá nhân. Trạng thái nhập là Chưa xử lý.")
    return result, parsed


def preview(conn: sqlite3.Connection, data: bytes, filename: str) -> dict:
    """Validate without mutations and return source-row diagnostics."""
    result, parsed = _parse(data, filename)
    existing = conn.execute("SELECT id FROM import_batches WHERE file_hash=?", (result["hash"],)).fetchone()
    result["existing_file"] = bool(existing)
    if existing:
        result["existing_batch_id"] = existing["id"]
        return result
    for sheet, table, column in [
        ("01_VO_SINH", "athletes", "legacy_athlete_id"),
        ("02_GIAI_DAU", "tournaments", "legacy_tournament_id"),
        ("03_THANH_TICH", "achievements", "legacy_achievement_id"),
        ("05_CAN_XAC_MINH", "verification_queue", "legacy_verification_id"),
    ]:
        for row in parsed["records"].get(sheet, []):
            legacy_id = _text(row["cells"][0])
            if legacy_id and conn.execute(f"SELECT id FROM {table} WHERE {column}=?", (legacy_id,)).fetchone():
                _message(result["errors"], sheet, row["row"], "LEGACY_CONFLICT", "Mã gốc đã tồn tại trong hệ thống: " + legacy_id + ". File đã thay đổi; không ghi đè dữ liệu đã nhập.")
    return result


def commit_import(conn: sqlite3.Connection, data: bytes, filename: str, user_id: str) -> dict:
    """Revalidate bytes and insert a whole batch; caller commits or rolls back."""
    result = preview(conn, data, filename)
    if result["existing_file"]:
        return {"imported": False, "existing_file": True, "batch_id": result.get("existing_batch_id"), "counts": result["counts"], "hash": result["hash"]}
    if result["errors"]:
        raise ValueError("Không thể nhập: " + _dump(result["errors"][:20]))
    _, parsed = _parse(data, filename)
    records = parsed["records"]
    batch_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    summary = {key: result[key] for key in ["counts", "warnings", "errors", "hash"]}
    conn.execute("INSERT INTO import_batches(id,file_hash,filename,imported_at,imported_by,summary_json,workbook_json) VALUES(?,?,?,?,?,?,?)", (batch_id, result["hash"], filename, now, user_id, _dump(summary), _dump(parsed["workbook"])))

    def insert(table, fields):
        columns = list(fields)
        conn.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})", [fields[column] for column in columns])

    def source_record(sheet, row, entity_type, entity_id):
        insert("source_records", {"batch_id": batch_id, "sheet": sheet, "excel_row": row["row"], "entity_type": entity_type, "entity_id": entity_id, "original_json": _dump({"row_number": row["row"], "headers": HEADERS[sheet], "raw_cells": [_raw(v) for v in row["cells"]]})})

    branch_ids = {}
    for row in records["01_VO_SINH"]:
        branch_name = _text(row["cells"][4])
        if not branch_name or branch_name == "Chưa xác định" or branch_name in branch_ids:
            continue
        found = conn.execute("SELECT id FROM branches WHERE name=?", (branch_name,)).fetchone()
        branch_id = found["id"] if found else str(uuid4())
        if not found:
            insert("branches", {"id": branch_id, "name": branch_name, "notes": "Tên cơ sở có trong file nguồn; chưa bổ sung thông tin khác."})
        branch_ids[branch_name] = branch_id
    athlete_ids, tournament_ids, achievement_ids = {}, {}, {}
    for row in records["01_VO_SINH"]:
        c = row["cells"]
        internal_id = str(uuid4())
        athlete_ids[_text(c[0])] = internal_id
        dob = _date(c[2])
        insert("athletes", {"id": internal_id, "legacy_athlete_id": _text(c[0]), "full_name": _text(c[1]), "date_of_birth": dob, "birth_year": int(dob[:4]) if dob else None, "current_branch_id": branch_ids.get(_text(c[4])), "representative_team": _text(c[5]), "status": _text(c[6]) or "Chưa xác định", "identity_verification_status": "pending", "notes": _text(c[7])})
        source_record("01_VO_SINH", row, "athletes", internal_id)
    for row in records["02_GIAI_DAU"]:
        c = row["cells"]
        internal_id = str(uuid4())
        tournament_ids[_text(c[0])] = internal_id
        insert("tournaments", {"id": internal_id, "legacy_tournament_id": _text(c[0]), "tournament_name": _text(c[1]), "year": _int(c[2]), "start_date": _date(c[3]), "end_date": _date(c[4]), "competition_level": _text(c[5]), "location": _text(c[6]), "organizer": _text(c[7]), "source_url": _text(c[8]), "status": _text(c[9]), "notes": _text(c[10])})
        source_record("02_GIAI_DAU", row, "tournaments", internal_id)
    for row in records["03_THANH_TICH"]:
        c = row["cells"]
        internal_id = str(uuid4())
        achievement_ids[_text(c[0])] = internal_id
        tournament_source = next(r for r in records["02_GIAI_DAU"] if _text(r["cells"][0]) == _text(c[1]))
        insert("achievements", {"id": internal_id, "legacy_achievement_id": _text(c[0]), "tournament_id": tournament_ids[_text(c[1])], "discipline": _text(c[4]), "participation_type": _text(c[5]) or "Chưa xác định", "gender_category": _text(c[6]), "event_name": _text(c[7]), "age_category": _text(c[8]), "weight_category": _text(c[9]), "belt_category": _text(c[10]), "medal_type": _text(c[11]), "representative_branch": _text(c[12]), "team_name": _text(c[13]), "evidence_url": _text(c[14]), "verification_status": "pending", "source_row": _text(c[18]), "source_original_text": _text(c[19]), "review_notes": _text(c[20]), "competition_year": _int(tournament_source["cells"][2]), "roster_confirmed": 0, "publication_allowed": 0, "source_conflict": int(_medal_conflict(c[19], _text(c[11])))})
        source_record("03_THANH_TICH", row, "achievements", internal_id)
    for row in records["04_VO_SINH_THANH_TICH"]:
        c = row["cells"]
        achievement_id, athlete_id = achievement_ids[_text(c[0])], athlete_ids[_text(c[1])]
        insert("athlete_achievements", {"achievement_id": achievement_id, "athlete_id": athlete_id, "link_status": "pending", "notes": _text(c[11])})
        source_record("04_VO_SINH_THANH_TICH", row, "athlete_achievements", achievement_id + ":" + athlete_id)
    for row in records["05_CAN_XAC_MINH"]:
        c = row["cells"]
        internal_id = str(uuid4())
        insert("verification_queue", {"id": internal_id, "legacy_verification_id": _text(c[0]), "tournament_id": tournament_ids.get(_text(c[11])), "original_name": _text(c[3]), "medal_type": _text(c[4]), "event_description": _text(c[5]), "issue_type": _text(c[6]), "reported_quantity": _int(c[12]), "source_url": _text(c[7]), "source_original_text": _text(c[8]), "source_row": _text(c[13]), "resolution_status": "unresolved", "resolution_notes": _text(c[10])})
        source_record("05_CAN_XAC_MINH", row, "verification_queue", internal_id)
    return {"imported": True, "existing_file": False, "batch_id": batch_id, "counts": result["counts"], "warning_count": len(result["warnings"]), "hash": result["hash"]}
