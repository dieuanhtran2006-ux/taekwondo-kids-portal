"""Exercise actual WSGI request handling without sockets or external services."""
from __future__ import annotations

import base64
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import urlsplit
from unittest.mock import patch
from wsgiref.util import setup_testing_defaults

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from app import core
from test_business_rules import workbook_bytes

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jJ0kAAAAASUVORK5CYII=")


class HttpSecurityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "portal.sqlite3"
        self.app = server.Application(self.db)
        self.cookie = ""
        self.csrf = ""
        status, headers, data = self.request("POST", "/api/setup", {"username": "admin", "password": "Mat-khau-admin-2026"})
        self.assertEqual(200, status, data)
        self.admin = data["user"]
        self.cookie = headers["set-cookie"].split(";", 1)[0]
        self.csrf = data["csrf"]
        self.admin_cookie, self.admin_csrf = self.cookie, self.csrf

    def tearDown(self):
        self.temp.cleanup()

    def request(self, method, url, payload=None, *, raw=None, auth=True, csrf=True, headers=None, remote="127.0.0.1"):
        env = {}
        setup_testing_defaults(env)
        target = urlsplit(url)
        env.update(REQUEST_METHOD=method, PATH_INFO=target.path, QUERY_STRING=target.query,
                   HTTP_HOST="127.0.0.1:8765", REMOTE_ADDR=remote)
        if raw is not None:
            body = raw
            env["CONTENT_TYPE"] = "application/octet-stream"
        elif payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            env["CONTENT_TYPE"] = "application/json"
        else:
            body = b""
        env["wsgi.input"] = BytesIO(body)
        env["CONTENT_LENGTH"] = str(len(body))
        if auth and self.cookie:
            env["HTTP_COOKIE"] = self.cookie
        if csrf and self.csrf:
            env["HTTP_X_CSRF_TOKEN"] = self.csrf
        env.update(headers or {})
        response = {}
        def start(status, returned_headers):
            response["status"] = int(status.split()[0])
            response["headers"] = {key.lower(): value for key, value in returned_headers}
        content = b"".join(self.app(env, start))
        if "application/json" in response["headers"].get("content-type", ""):
            content = json.loads(content.decode("utf-8"))
        return response["status"], response["headers"], content

    def create_record(self):
        status, _, profile = self.request("POST", "/api/athletes", {"full_name": "Hồ sơ HTTP kiểm thử",
            "official_code": "TKD-HTTP-001", "identity_verification_status": "verified", "date_of_birth": "2015-02-03"})
        self.assertEqual(200, status, profile)
        status, _, tournament = self.request("POST", "/api/tournaments", {"tournament_name": "Giải HTTP", "year": 2024})
        self.assertEqual(200, status, tournament)
        status, _, result = self.request("POST", "/api/achievements", {"tournament_id": tournament["tournament"]["id"],
            "event_name": "Quyền", "discipline": "Quyền", "participation_type": "Cá nhân", "medal_type": "HCV",
            "athlete_ids": [profile["athlete"]["id"]], "publication_allowed": True})
        self.assertEqual(200, status, result)
        return profile["athlete"], result

    def viewer_login(self, athlete_id):
        status, _, data = self.request("POST", "/api/users", {"username": "viewer", "password": "Mat-khau-viewer-2026",
            "role": "viewer", "athlete_ids": [athlete_id]})
        self.assertEqual(200, status, data)
        status, headers, data = self.request("POST", "/api/login", {"username": "viewer", "password": "Mat-khau-viewer-2026"}, auth=False, csrf=False)
        self.assertEqual(200, status, data)
        self.cookie, self.csrf = headers["set-cookie"].split(";", 1)[0], data["csrf"]
        status, headers, data = self.request('POST','/api/password',{'current_password':'Mat-khau-viewer-2026',
            'password':'Mat-khau-viewer-moi-2026','confirm_password':'Mat-khau-viewer-moi-2026'})
        self.assertEqual(200,status,data)
        self.cookie, self.csrf = headers['set-cookie'].split(';',1)[0], data['csrf']

    def test_cookie_session_is_opaque_hashed_and_logout_revokes(self):
        status, headers, data = self.request("POST", "/api/login", {"username": "admin", "password": "Mat-khau-admin-2026"}, auth=False, csrf=False)
        self.assertEqual(200, status)
        cookie = headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertNotIn("admin", cookie)
        token = cookie.split(";", 1)[0].split("=", 1)[1]
        conn = core.connect(self.db)
        try:
            hashes = [r[0] for r in conn.execute("SELECT token_hash FROM sessions")]
        finally:
            conn.close()
        self.assertNotIn(token, hashes)
        self.assertEqual(200, self.request("POST", "/api/logout", {})[0])
        self.assertEqual(401, self.request("GET", "/api/dashboard")[0])

    def test_csrf_missing_or_wrong_and_cross_site_origin_block_mutation(self):
        for kwargs in ({"csrf": False}, {"headers": {"HTTP_X_CSRF_TOKEN": "invalid"}},
                       {"headers": {"HTTP_ORIGIN": "https://evil.example"}},
                       {"headers": {"HTTP_SEC_FETCH_SITE": "cross-site"}}):
            status, _, _ = self.request("POST", "/api/branches", {"name": "Không được ghi"}, **kwargs)
            self.assertEqual(403, status)
        self.assertEqual(0, self.request("GET", "/api/branches")[2]["total"])

    def test_unknown_host_and_unauthenticated_api_rejected(self):
        self.assertEqual(400, self.request("GET", "/api/session", headers={"HTTP_HOST": "attacker.example"})[0])
        for path in ("/api/athletes", "/api/export", "/api/audit", "/api/evidence/missing"):
            self.assertEqual(401, self.request("GET", path, auth=False)[0])

    def test_setup_is_local_only_and_cannot_replace_existing_admin(self):
        status, _, _ = self.request("POST", "/api/setup", {"username": "attacker", "password": "Mat-khau-khac-2026"}, remote="203.0.113.2")
        self.assertEqual(403, status)
        self.assertEqual(409, self.request("POST", "/api/setup", {"username": "second", "password": "Mat-khau-khac-2026"})[0])
        with patch.dict("os.environ", {"TKD_ALLOW_SETUP": "0"}):
            self.assertEqual(403, self.request("POST", "/api/setup", {"username": "second", "password": "Mat-khau-khac-2026"})[0])

    def test_secure_cookie_enabled_explicitly_for_https_deployment(self):
        with patch.dict("os.environ", {"TKD_SECURE_COOKIE": "1"}):
            secure_app = server.Application(self.db)
        old = self.app
        self.app = secure_app
        try:
            status, headers, _ = self.request("POST", "/api/login", {"username": "admin", "password": "Mat-khau-admin-2026"}, auth=False)
            self.assertEqual(200, status)
            self.assertIn("; Secure", headers["set-cookie"])
        finally:
            self.app = old

    def test_viewer_cannot_export_sources_users_or_upload(self):
        athlete, result = self.create_record()
        self.viewer_login(athlete["id"])
        for path in ("/api/export", "/api/users", "/api/audit", "/api/integrations", f"/api/source/athletes/{athlete['id']}"):
            self.assertEqual(403, self.request("GET", path)[0], path)
        self.assertEqual(403, self.request("POST", f"/api/evidence?achievement_id={result['id']}", raw=PNG, headers={"HTTP_X_FILENAME": "image.png"})[0])

    def test_evidence_requires_own_verified_record_and_public_file_permission(self):
        athlete, result = self.create_record()
        status, _, upload = self.request("POST", f"/api/evidence?achievement_id={result['id']}", raw=PNG, headers={"HTTP_X_FILENAME": "proof.png"})
        self.assertEqual(200, status, upload)
        evidence_id = upload["id"]
        result = self.request("GET", f"/api/achievements/{result['id']}")[2]
        status, _, verified = self.request("POST", f"/api/achievements/{result['id']}/verify", {"version": result["version"],
            "evidence_checked": True, "duplicate_checked": True, "note": "Đã đối chiếu fixture"})
        self.assertEqual(200, status, verified)
        self.viewer_login(athlete["id"])
        self.assertEqual(403, self.request("GET", f"/api/evidence/{evidence_id}")[0])
        viewer_cookie, viewer_csrf = self.cookie, self.csrf
        self.cookie, self.csrf = self.admin_cookie, self.admin_csrf
        self.assertEqual(200, self.request("PATCH", f"/api/evidence/{evidence_id}", {"publication_allowed": True})[0])
        self.cookie, self.csrf = viewer_cookie, viewer_csrf
        status, headers, image = self.request("GET", f"/api/evidence/{evidence_id}")
        self.assertEqual(200, status)
        self.assertEqual(PNG, image)
        self.assertIn("attachment;", headers["content-disposition"])
        self.assertEqual("nosniff", headers["x-content-type-options"])

    def test_evidence_rejects_script_or_path_escape(self):
        _, result = self.create_record()
        status, _, _ = self.request("POST", f"/api/evidence?achievement_id={result['id']}",
            raw=b"<script>alert(1)</script>", headers={"HTTP_X_FILENAME": "proof.pdf"})
        self.assertEqual(422, status)
        self.assertEqual(404, self.request("GET", "/static/../data/portal.sqlite3")[0])
        self.assertNotEqual(200, self.request("GET", "/api/evidence/../../data/portal.sqlite3")[0])

    def test_import_preview_cancel_does_not_write_and_token_cannot_be_reused(self):
        status, _, preview = self.request("POST", "/api/import/preview", raw=workbook_bytes(), headers={"HTTP_X_FILENAME": "fixture.xlsx"})
        self.assertEqual(200, status, preview)
        self.assertEqual([], preview["errors"])
        self.assertEqual(0, self.request("GET", "/api/athletes")[2]["total"])
        self.assertEqual(200, self.request("POST", "/api/import/cancel", {"token": preview["token"]})[0])
        self.assertEqual(409, self.request("POST", "/api/import/commit", {"token": preview["token"]})[0])
        self.assertEqual(0, self.request("GET", "/api/athletes")[2]["total"])

    def test_import_preview_token_bound_to_admin_that_created_it(self):
        status, _, preview = self.request("POST", "/api/import/preview", raw=workbook_bytes(), headers={"HTTP_X_FILENAME": "fixture.xlsx"})
        self.assertEqual(200, status)
        self.assertEqual(200, self.request("POST", "/api/users", {"username": "admin2", "password": "Mat-khau-admin2-2026", "role": "admin"})[0])
        status, headers, login = self.request("POST", "/api/login", {"username": "admin2", "password": "Mat-khau-admin2-2026"}, auth=False)
        self.assertEqual(200, status)
        self.cookie, self.csrf = headers["set-cookie"].split(";", 1)[0], login["csrf"]
        self.assertEqual(409, self.request("POST", "/api/import/commit", {"token": preview["token"]})[0])

    def test_import_http_commits_revalidated_staged_bytes_only(self):
        status, _, preview = self.request("POST", "/api/import/preview", raw=workbook_bytes(), headers={"HTTP_X_FILENAME": "fixture.xlsx"})
        self.assertEqual(200, status)
        status, _, result = self.request("POST", "/api/import/commit", {"token": preview["token"], "rows": [{"verification_status": "verified"}]})
        self.assertEqual(200, status, result)
        dashboard = self.request("GET", "/api/dashboard")[2]
        self.assertEqual(0, dashboard["verified"])
        self.assertEqual(1, dashboard["pending"])
        self.assertEqual(1, self.request("GET", "/api/athletes")[2]["total"])

    def test_staff_tournament_catalog_exposes_only_selection_metadata_and_allows_new_result(self):
        athlete, _ = self.create_record()
        status, _, new_tournament = self.request("POST", "/api/tournaments", {
            "tournament_name": "Giải mới chưa có người tham gia", "year": 2025, "competition_level": "CLB",
            "notes": "Nội dung quản trị riêng", "source_url": "https://example.org/private-source"})
        self.assertEqual(200, status, new_tournament)
        new_id = new_tournament["tournament"]["id"]
        self.assertEqual(200, self.request("POST", "/api/users", {"username": "catalogcoach",
            "password": "Mat-khau-coach-2026", "role": "coach", "athlete_ids": [athlete["id"]]})[0])
        status, headers, login = self.request("POST", "/api/login", {"username": "catalogcoach", "password": "Mat-khau-coach-2026"}, auth=False)
        self.assertEqual(200, status)
        self.cookie, self.csrf = headers["set-cookie"].split(";", 1)[0], login["csrf"]
        status, _, catalog = self.request("GET", "/api/tournament-catalog")
        self.assertEqual(200, status, catalog)
        self.assertEqual(2, len(catalog["items"]))
        self.assertIn(new_id, [r["id"] for r in catalog["items"]])
        allowed = {"id", "tournament_name", "year", "competition_level", "status"}
        self.assertTrue(all(set(r).issubset(allowed) for r in catalog["items"]))
        self.assertEqual(1, self.request("GET", "/api/tournaments")[2]["total"])
        self.assertEqual(403, self.request("GET", f"/api/tournaments/{new_id}")[0])
        status, _, result = self.request("POST", "/api/achievements", {"tournament_id": new_id,
            "event_name": "Kết quả mới do coach nhập", "discipline": "Quyền", "participation_type": "Cá nhân",
            "medal_type": "HCB", "athlete_ids": [athlete["id"]]})
        self.assertEqual(200, status, result)
        self.assertEqual("pending", result["verification_status"])
        self.assertEqual(2, self.request("GET", "/api/tournaments")[2]["total"])
        self.assertEqual(401, self.request("GET", "/api/tournament-catalog", auth=False)[0])
        self.cookie, self.csrf = self.admin_cookie, self.admin_csrf
        self.viewer_login(athlete["id"])
        self.assertEqual(403, self.request("GET", "/api/tournament-catalog")[0])

    def test_mixed_roster_coach_reads_own_history_but_not_raw_source_evidence_or_mutations(self):
        athlete, result = self.create_record()
        status, _, other = self.request("POST", "/api/athletes", {"full_name": "Đồng đội khác phạm vi",
            "official_code": "TKD-HTTP-002", "identity_verification_status": "verified"})
        self.assertEqual(200, status, other)
        status, _, result = self.request("PATCH", f"/api/achievements/{result['id']}", {"version": result["version"],
            "participation_type": "Đôi", "athlete_ids": [athlete["id"], other["athlete"]["id"]],
            "source_original_text": "Tên đồng đội và văn bản nội bộ", "evidence_url": "https://example.org/private-evidence"})
        self.assertEqual(200, status, result)
        status, _, evidence = self.request("POST", f"/api/evidence?achievement_id={result['id']}", raw=PNG, headers={"HTTP_X_FILENAME": "private-proof.png"})
        self.assertEqual(200, status, evidence)
        result = self.request("GET", f"/api/achievements/{result['id']}")[2]
        status, _, result = self.request("POST", f"/api/achievements/{result['id']}/verify", {"version": result["version"],
            "evidence_checked": True, "duplicate_checked": True, "note": "Đã đối chiếu cả hai thành viên"})
        self.assertEqual(200, status, result)
        self.assertEqual(200, self.request("POST", "/api/users", {"username": "mixedcoach",
            "password": "Mat-khau-coach-2026", "role": "coach", "can_verify": True, "athlete_ids": [athlete["id"]]})[0])
        status, headers, login = self.request("POST", "/api/login", {"username": "mixedcoach", "password": "Mat-khau-coach-2026"}, auth=False)
        self.assertEqual(200, status)
        self.cookie, self.csrf = headers["set-cookie"].split(";", 1)[0], login["csrf"]
        status, _, detail = self.request("GET", f"/api/achievements/{result['id']}")
        self.assertEqual(200, status, detail)
        self.assertEqual([athlete["id"]], [a["id"] for a in detail["athletes"]])
        self.assertFalse(detail.get("source_original_text"))
        self.assertFalse(detail.get("evidence_url"))
        self.assertEqual([], detail.get("evidence_files", []))
        self.assertEqual(1, self.request("GET", f"/api/athletes/{athlete['id']}")[2]["medals"]["HCV"])
        self.assertEqual(403, self.request("GET", f"/api/evidence/{evidence['id']}")[0])
        self.assertEqual(403, self.request("GET", f"/api/source/achievements/{result['id']}")[0])
        self.assertEqual(403, self.request("PATCH", f"/api/achievements/{result['id']}", {"version": result["version"], "event_name": "Sửa cả đội"})[0])
        self.assertEqual(403, self.request("POST", f"/api/achievements/{result['id']}/verify", {"version": result["version"],
            "evidence_checked": True, "duplicate_checked": True, "note": "Thiếu phạm vi cả đội"})[0])


if __name__ == "__main__":
    unittest.main()
