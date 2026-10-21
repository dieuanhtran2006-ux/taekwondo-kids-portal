"""Opt-in Google REST adapter; no network activity or synchronization on import.

SQLite is authoritative in this MVP. Google changes are compared with an explicit
baseline and outbound proposals are appended to a review sheet, never used to
overwrite the source workbook. Access tokens live only in backend environment.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import re
from typing import Any, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
import uuid


class GoogleAdapterError(Exception):
    def __init__(self, message: str, status: int = 400, details: Any = None):
        super().__init__(message)
        self.message, self.status, self.details = message, status, details


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def row_hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _index(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        record = dict(row)
        identity = str(record.get(key) or "").strip()
        if not identity:
            raise GoogleAdapterError(f"Dòng Google Sheets thiếu khóa {key}.")
        if identity in result:
            raise GoogleAdapterError(f"Trùng khóa {identity}; cần đối chiếu trước khi đồng bộ.", 409)
        result[identity] = record
    return result


def _snapshot(index: Mapping[str, Any]) -> str:
    return row_hash(dict(sorted(index.items())))


def plan_changes(local_rows: Iterable[Mapping[str, Any]],
                 remote_rows: Iterable[Mapping[str, Any]],
                 baseline_rows: Iterable[Mapping[str, Any]] | None = None,
                 key: str = "id") -> dict[str, Any]:
    """Three-way comparison. Divergent rows without a baseline are conflicts.

    Changes and deletions are only proposals. In particular a remote verified
    flag never grants local approval; the core service must validate each row.
    """
    local, remote = _index(local_rows, key), _index(remote_rows, key)
    baseline = _index(baseline_rows, key) if baseline_rows is not None else {}
    changes, conflicts, unchanged = [], [], 0
    for identity in sorted(set(local) | set(remote) | set(baseline)):
        left, right, base = local.get(identity), remote.get(identity), baseline.get(identity)
        if left == right:
            unchanged += 1
            continue
        if baseline_rows is None:
            if left is not None and right is not None:
                conflicts.append({"id": identity, "reason": "missing_baseline", "local": left, "remote": right})
                continue
            direction = "local_to_remote" if left is not None else "remote_to_local"
        else:
            local_changed, remote_changed = left != base, right != base
            if local_changed and remote_changed:
                conflicts.append({"id": identity, "reason": "both_changed", "baseline": base, "local": left, "remote": right})
                continue
            direction = "local_to_remote" if local_changed else "remote_to_local"
        before, after = (right, left) if direction == "local_to_remote" else (left, right)
        # History must never be deleted as a side effect of synchronization.
        if after is None:
            conflicts.append({"id": identity, "reason": "deletion_requires_review", "local": left, "remote": right})
            continue
        changes.append({"id": identity, "direction": direction,
                        "operation": "create" if before is None else "update",
                        "before": before, "after": after, "base_hash": row_hash(before)})
    return {"plan_id": str(uuid.uuid4()), "key": key,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "local_snapshot_hash": _snapshot(local), "remote_snapshot_hash": _snapshot(remote),
            "changes": changes, "conflicts": conflicts, "unchanged": unchanged,
            "applied": False}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not send a backend bearer token to a redirected host.
        raise GoogleAdapterError("Google API trả về chuyển hướng không được phép.", 502)


class GoogleSheetsAdapter:
    def __init__(self, spreadsheet_id: str = "", access_token: str = "",
                 write_enabled: bool = False, staging_range: str = "_TKD_SYNC_INBOX!A:H",
                 timeout: float = 20):
        if spreadsheet_id and not re.fullmatch(r"[A-Za-z0-9_-]+", spreadsheet_id):
            raise GoogleAdapterError("GOOGLE_SHEETS_ID không hợp lệ.")
        self.spreadsheet_id = spreadsheet_id
        self._access_token = access_token
        self.write_enabled = write_enabled
        self.staging_range = staging_range
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "GoogleSheetsAdapter":
        return cls(os.getenv("GOOGLE_SHEETS_ID", ""),
                   os.getenv("GOOGLE_SHEETS_ACCESS_TOKEN", ""),
                   os.getenv("GOOGLE_SHEETS_WRITE_ENABLED", "0") == "1",
                   os.getenv("GOOGLE_SHEETS_STAGING_RANGE", "_TKD_SYNC_INBOX!A:H"))

    def status(self) -> dict[str, Any]:
        missing = [name for name, value in (("GOOGLE_SHEETS_ID", self.spreadsheet_id),
                   ("GOOGLE_SHEETS_ACCESS_TOKEN", self._access_token)) if not value]
        return {"configured": not missing, "connected": False, "sync_enabled": False,
                "write_enabled": self.write_enabled, "mode": "manual_review_staging",
                "missing": missing, "staging_range": self.staging_range,
                "message": "Đã cấu hình; chưa kiểm tra kết nối." if not missing else "Chưa cấu hình Google Sheets. SQLite đang là nguồn dữ liệu hoạt động."}

    def _require_configuration(self) -> None:
        if not self.spreadsheet_id or not self._access_token:
            raise GoogleAdapterError("Chưa cấu hình GOOGLE_SHEETS_ID và GOOGLE_SHEETS_ACCESS_TOKEN.", 503)

    def _request(self, method: str, url: str, body: Any = None) -> Any:
        self._require_configuration()
        payload = _canonical(body).encode("utf-8") if body is not None else None
        req = Request(url, data=payload, method=method,
                      headers={"Authorization": "Bearer " + self._access_token,
                               "Content-Type": "application/json; charset=utf-8",
                               "Accept": "application/json"})
        try:
            with build_opener(_NoRedirect()).open(req, timeout=self.timeout) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise GoogleAdapterError("Phản hồi Google vượt giới hạn 8 MB; hãy đọc từng khoảng nhỏ hơn.", 413)
                return json.loads(raw.decode("utf-8"))
        except HTTPError as exc:
            # Do not expose token or API response contents (may contain PII).
            if exc.code in (401, 403):
                raise GoogleAdapterError("Google từ chối quyền truy cập. Kiểm tra token, scope và quyền chia sẻ tệp.", 502) from None
            if exc.code == 429:
                raise GoogleAdapterError("Google API đang giới hạn tần suất. Hãy thử lại sau.", 503) from None
            raise GoogleAdapterError(f"Google API trả mã HTTP {exc.code}.", 502) from None
        except (URLError, TimeoutError, json.JSONDecodeError, UnicodeError):
            raise GoogleAdapterError("Không đọc được phản hồi Google API. Dữ liệu cục bộ chưa bị thay đổi.", 502) from None

    def read_ranges(self, ranges: Iterable[str]) -> dict[str, Any]:
        chosen = list(ranges)
        if not chosen or len(chosen) > 20 or any(not isinstance(r, str) or len(r) > 300 for r in chosen):
            raise GoogleAdapterError("Cần chọn từ 1 đến 20 khoảng Google Sheets hợp lệ.")
        query = urlencode([*(('ranges', r) for r in chosen),
                           ("majorDimension", "ROWS"), ("valueRenderOption", "FORMULA")])
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{quote(self.spreadsheet_id, safe='')}/values:batchGet?{query}"
        return self._request("GET", url)

    def read_table(self, source_range: str) -> list[dict[str, Any]]:
        raw = self.read_ranges([source_range])
        values = raw.get("valueRanges", [{}])[0].get("values", [])
        if not values:
            return []
        headers = [str(v).strip() for v in values[0]]
        if not all(headers) or len(headers) != len(set(headers)):
            raise GoogleAdapterError("Hàng tiêu đề Google Sheets có cột trống hoặc trùng tên.", 422)
        return [{header: row[i] if i < len(row) else "" for i, header in enumerate(headers)}
                for row in values[1:] if any(v not in (None, "") for v in row)]

    @staticmethod
    def plan(local_rows, remote_rows, baseline_rows=None, key="id"):
        return plan_changes(local_rows, remote_rows, baseline_rows, key)

    def apply(self, plan: Mapping[str, Any], *, user: Mapping[str, Any],
              source_range: str, confirmed: bool = False) -> dict[str, Any]:
        """Append reviewed outbound proposals to a protected staging sheet.

        values APIs have no per-row compare-and-swap. For that reason this method
        never overwrites authoritative rows even after rechecking their hashes.
        A later operator must reconcile inbox rows through the core service.
        """
        if user.get("role") != "admin":
            raise GoogleAdapterError("Chỉ quản trị viên được gửi đề xuất đồng bộ.", 403)
        if not confirmed or not self.write_enabled:
            raise GoogleAdapterError("Cần xác nhận kế hoạch và bật GOOGLE_SHEETS_WRITE_ENABLED=1.", 403)
        if plan.get("conflicts"):
            raise GoogleAdapterError("Kế hoạch còn xung đột; cần đối chiếu trước khi gửi.", 409)
        key = str(plan.get("key") or "id")
        current = _index(self.read_table(source_range), key)
        if _snapshot(current) != plan.get("remote_snapshot_hash"):
            raise GoogleAdapterError("Google Sheets đã thay đổi sau khi xem trước. Hãy lập lại kế hoạch.", 409)
        changes = [c for c in plan.get("changes", []) if c.get("direction") == "local_to_remote"]
        if not changes:
            return {"staged": 0, "applied": False, "message": "Không có đề xuất ghi ra Google Sheets."}
        if len(changes) > 1000:
            raise GoogleAdapterError("Mỗi đợt tối đa 1.000 đề xuất.", 413)
        now = datetime.now(timezone.utc).isoformat()
        rows = [[str(uuid.uuid4()), str(plan["plan_id"]), now, str(user.get("id", "")),
                 c["id"], c["base_hash"], _canonical(c["after"]), "pending_review"] for c in changes]
        staging = quote(self.staging_range, safe="")
        url = (f"https://sheets.googleapis.com/v4/spreadsheets/{quote(self.spreadsheet_id, safe='')}/values/"
               f"{staging}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS")
        result = self._request("POST", url, {"majorDimension": "ROWS", "values": rows})
        return {"staged": len(rows), "applied": False, "source_overwritten": False,
                "plan_id": plan["plan_id"], "updated_range": result.get("updates", {}).get("updatedRange"),
                "message": "Đã gửi đề xuất vào hàng chờ Google Sheets; dữ liệu nguồn và SQLite chưa bị ghi đè."}

    def drive_metadata(self, file_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9_-]{5,200}", file_id):
            raise GoogleAdapterError("Mã tệp Google Drive không hợp lệ.")
        fields = urlencode({"fields": "id,name,mimeType,webViewLink,version,modifiedTime"})
        return self._request("GET", f"https://www.googleapis.com/drive/v3/files/{quote(file_id, safe='')}?{fields}")


def integration_status() -> dict[str, Any]:
    try:
        return GoogleSheetsAdapter.from_env().status()
    except GoogleAdapterError as exc:
        return {"configured": False, "connected": False, "sync_enabled": False, "message": exc.message}
