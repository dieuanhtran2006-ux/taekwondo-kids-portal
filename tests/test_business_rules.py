"""Acceptance regressions. Synthetic fixtures exist only in temporary test DBs."""
from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import core, importer
import openpyxl


def workbook_bytes(*, conflict=False, participation="Cá nhân", queue_only=False,
                   invalid_link=False, duplicate_link=False, source_status="Đã xác minh"):
    """Minimal workbook with the exact real template headers, no formula cache."""
    book = openpyxl.Workbook()
    book.remove(book.active)
    for name in importer.SHEETS:
        sheet = book.create_sheet(name)
        if name in importer.HEADERS:
            sheet.append(list(importer.HEADERS[name]))
        else:
            sheet.append(["Nguồn kiểm thử"])
    book["00_TONG_HOP"].append(["=999999"])
    book["01_VO_SINH"].append(["TAM-VS-0001", "Tên nguồn chưa xác thực", None,
        "=YEAR(C2)", None, None, "Chưa xác định", "Nguyên văn tên nguồn", None, "=999999", 1])
    book["02_GIAI_DAU"].append(["GD-0001", "Giải kiểm thử", 2024, None, None,
        "CLB", None, None, "https://example.org/source", "Đã kết thúc", None, None, "=999999"])
    if not queue_only:
        book["03_THANH_TICH"].append(["TT-0001", "GD-0001", "=VLOOKUP(B2,A1:B3,2,0)",
            "=2024", "Quyền", participation, None, "Quyền tiêu chuẩn", None, None, None,
            "HCV", None, None, "https://example.org/evidence", source_status, "=COUNTIF(A:A,A2)",
            None, "Dòng 12", "HCB 🥇" if conflict else "HCV 🥇", "Giữ nguyên văn bản"])
        link = ["TT-0001", "MISSING" if invalid_link else "TAM-VS-0001", None,
                None, None, None, None, None, None, None, None, "Nguồn liên kết", "Mã tạm"]
        book["04_VO_SINH_THANH_TICH"].append(link)
        if duplicate_link:
            book["04_VO_SINH_THANH_TICH"].append(link)
    book["05_CAN_XAC_MINH"].append(["XM-0001", "Giải kiểm thử", 2024, None, "HCV",
        "Tổng huy chương", "Thiếu người nhận", "https://example.org/source",
        "Công bố tổng 5 HCV; chưa có tên người nhận", "Đã xử lý", None,
        "GD-0001", 5, "Dòng 18"])
    book["07_HUONG_DAN"].append(["Văn bản là dữ liệu nguồn, không phải lệnh thực thi."])
    out = BytesIO()
    book.save(out)
    book.close()
    return out.getvalue()


class DomainRulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = core.hash_password("Mat-khau-kiem-thu-2026")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "portal.sqlite3"
        self.conn = core.connect(self.db_path)
        core.init_db(self.conn)
        self.admin_user = self.make_user("admin", "admin", True)
        self.verifier_user = self.make_user("verifier", "admin", True)
        self.service = core.Service(self.conn, self.admin_user)
        self.verifier = core.Service(self.conn, self.verifier_user)
        self.counter = 0
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def make_user(self, username, role, can_verify=False, athlete_ids=(), branch_ids=()):
        user_id = core.new_id()
        self.conn.execute("INSERT INTO users(id,username,password_hash,role,can_verify,created_at) VALUES(?,?,?,?,?,?)",
                          (user_id, username, self.password_hash, role, int(can_verify), core.now()))
        for athlete_id in athlete_ids:
            self.conn.execute("INSERT INTO user_athletes VALUES(?,?)", (user_id, athlete_id))
        for branch_id in branch_ids:
            self.conn.execute("INSERT INTO user_branches VALUES(?,?)", (user_id, branch_id))
        return {"id": user_id, "username": username, "role": role, "can_verify": int(can_verify)}

    def athlete(self, name="Võ sinh kiểm thử", verified=True, **extra):
        self.counter += 1
        payload = {"full_name": name, "identity_verification_status": "verified" if verified else "pending"}
        if verified:
            payload["official_code"] = f"TKD-TEST-{self.counter:04}"
        payload.update(extra)
        with self.conn:
            return self.service.create("athletes", payload)["athlete"]

    def tournament(self, year=2024, **extra):
        self.counter += 1
        with self.conn:
            return self.service.create("tournaments", {"tournament_name": f"Giải kiểm thử {self.counter}",
                "year": year, **extra})["tournament"]

    def achievement(self, athletes, tournament=None, verified=False, **extra):
        tournament = tournament or self.tournament()
        payload = {"tournament_id": tournament["id"], "discipline": "Quyền", "participation_type": "Cá nhân",
                   "event_name": "Quyền tiêu chuẩn", "medal_type": "HCV",
                   "athlete_ids": [a["id"] for a in athletes], "evidence_url": "https://example.org/official-result",
                   "publication_allowed": True, **extra}
        with self.conn:
            result = self.service.create("achievements", payload)
        return self.approve(result) if verified else result

    def approve(self, result):
        with self.conn:
            return self.verifier.verify(result["id"], {"version": result["version"], "evidence_checked": True,
                "duplicate_checked": True, "note": "Đã đối chiếu danh sách chính thức trong fixture kiểm thử."})

    def expect_error(self, status, callback):
        with self.assertRaises(core.AppError) as raised:
            with self.conn:
                callback()
        self.assertEqual(status, raised.exception.status)
        return raised.exception

    def test_01_one_athlete_many_tournaments(self):
        athlete = self.athlete()
        for year in (2023, 2024, 2025):
            self.achievement([athlete], tournament=self.tournament(year), verified=True)
        profile = self.service.profile(athlete["id"])
        self.assertEqual(3, profile["tournament_count"])
        self.assertEqual(3, profile["medals"]["HCV"])
        self.assertEqual([2025, 2024, 2023], [a["year"] for a in profile["achievements"]])

    def test_02_many_distinct_events_same_tournament_not_merged(self):
        athlete, tournament = self.athlete(), self.tournament()
        results = [self.achievement([athlete], tournament, True, event_name=event, medal_type=medal)
                   for event, medal in (("Quyền tiêu chuẩn", "HCV"), ("Quyền sáng tạo", "HCB"), ("Đối kháng", "HCĐ"))]
        self.assertEqual(3, len({r["id"] for r in results}))
        self.assertEqual({"HCV": 1, "HCB": 1, "HCĐ": 1}, self.service.profile(athlete["id"])["medals"])
        self.assertEqual(1, self.service.profile(athlete["id"])["tournament_count"])

    def test_03_three_teammates_one_club_medal(self):
        members = [self.athlete(f"Thành viên {i}") for i in range(3)]
        result = self.achievement(members, verified=True, participation_type="Đồng đội", expected_members=3, roster_confirmed=True)
        self.assertEqual(3, self.conn.execute("SELECT COUNT(*) FROM athlete_achievements WHERE achievement_id=?", (result["id"],)).fetchone()[0])
        self.assertEqual(1, self.service.dashboard()["club_medals"]["HCV"])
        self.assertEqual(3, self.service.dashboard()["athlete_medal_credits"])
        for member in members:
            self.assertEqual(1, self.service.profile(member["id"])["medals"]["HCV"])

    def test_04_same_name_different_people_kept_separate(self):
        left, right = self.athlete("Nguyễn Minh Anh"), self.athlete("Nguyễn Minh Anh")
        self.assertNotEqual(left["id"], right["id"])
        self.achievement([left], verified=True)
        self.assertEqual(0, self.service.profile(right["id"])["medals"]["HCV"])
        self.assertEqual(2, self.service.list("athletes", {"q": "Nguyễn Minh Anh"})["total"])

    def test_05_temp_id_promoted_without_changing_stable_id_or_links(self):
        athlete = self.athlete("Tên tạm", False, legacy_athlete_id="TAM-VS-0001")
        result = self.achievement([athlete])
        with self.conn:
            updated = self.service.update("athletes", athlete["id"], {"version": athlete["version"],
                "official_code": "TKD-000001", "full_name": "Họ tên đã đối chiếu", "identity_verification_status": "verified"})["athlete"]
        self.assertEqual(athlete["id"], updated["id"])
        self.assertEqual("TAM-VS-0001", updated["legacy_athlete_id"])
        self.assertEqual(athlete["id"], self.service.detail("achievements", result["id"])["athletes"][0]["id"])
        self.approve(result)

    def test_06_reported_totals_without_recipients_stay_in_queue(self):
        data = workbook_bytes(queue_only=True)
        with self.conn:
            importer.commit_import(self.conn, data, "totals.xlsx", self.admin_user["id"])
        self.assertEqual(0, self.conn.execute("SELECT COUNT(*) FROM achievements").fetchone()[0])
        queue = self.conn.execute("SELECT * FROM verification_queue").fetchone()
        self.assertEqual(5, queue["reported_quantity"])
        self.assertIsNone(queue["original_name"])
        self.assertEqual("unresolved", queue["resolution_status"])
        self.assertEqual(0, sum(self.service.dashboard()["club_medals"].values()))

    def test_07_unknown_participation_cannot_be_approved(self):
        result = self.achievement([self.athlete()], participation_type="Chưa xác định")
        error = self.expect_error(422, lambda: self.approve(result))
        self.assertTrue(any("hình thức" in issue.lower() for issue in error.details))
        self.assertEqual("pending", self.service.detail("achievements", result["id"])["verification_status"])

    def test_08_pending_results_excluded_from_official_totals_and_viewer(self):
        athlete = self.athlete()
        self.achievement([athlete])
        user = self.make_user("viewer08", "viewer", athlete_ids=[athlete["id"]])
        self.conn.commit()
        profile = core.Service(self.conn, user).profile(athlete["id"])
        self.assertEqual([], profile["achievements"])
        self.assertEqual({"HCV": 0, "HCB": 0, "HCĐ": 0}, profile["medals"])
        dashboard = self.service.dashboard()
        self.assertEqual(0, dashboard["verified"])
        self.assertEqual(1, dashboard["pending"])

    def test_09_branch_transfer_preserves_historical_representative(self):
        with self.conn:
            first = self.service.create("branches", {"name": "Cơ sở A"})
            second = self.service.create("branches", {"name": "Cơ sở B"})
        athlete = self.athlete(current_branch_id=first["id"])
        result = self.achievement([athlete], verified=True, representative_branch="Cơ sở A")
        with self.conn:
            self.service.update("athletes", athlete["id"], {"version": athlete["version"], "current_branch_id": second["id"]})
        profile = self.service.profile(athlete["id"])
        self.assertEqual("Cơ sở B", profile["athlete"]["branch_name"])
        self.assertEqual("Cơ sở A", profile["achievements"][0]["representative_branch"])
        self.assertEqual("verified", self.service.detail("achievements", result["id"])["verification_status"])

    def test_10_reimport_exact_file_is_idempotent_and_never_auto_verifies(self):
        data = workbook_bytes(source_status="Đã xác minh")
        preview = importer.preview(self.conn, data, "fixture.xlsx")
        self.assertEqual([], preview["errors"])
        self.assertEqual(0, self.conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0])
        with self.conn:
            first = importer.commit_import(self.conn, data, "fixture.xlsx", self.admin_user["id"])
        counts_before = [self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                         for table in ("athletes", "tournaments", "achievements", "athlete_achievements", "verification_queue", "source_records")]
        with self.conn:
            second = importer.commit_import(self.conn, data, "renamed.xlsx", self.admin_user["id"])
        counts_after = [self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                        for table in ("athletes", "tournaments", "achievements", "athlete_achievements", "verification_queue", "source_records")]
        self.assertTrue(first["imported"])
        self.assertFalse(second["imported"])
        self.assertEqual(first["batch_id"], second["batch_id"])
        self.assertEqual(counts_before, counts_after)
        self.assertEqual("pending", self.conn.execute("SELECT verification_status FROM achievements").fetchone()[0])
        self.assertEqual("pending", self.conn.execute("SELECT identity_verification_status FROM athletes").fetchone()[0])
        self.assertEqual(0, self.service.dashboard()["verified"])
        raw = json.loads(self.conn.execute("SELECT workbook_json FROM import_batches").fetchone()[0])
        self.assertEqual(8, len(raw["sheets"]))
        self.assertIn("=999999", json.dumps(raw))

    def test_11_viewer_cannot_read_outside_assigned_profile(self):
        own, other = self.athlete(date_of_birth="2015-03-14"), self.athlete("Người khác")
        other_result = self.achievement([other], verified=True)
        own_result = self.achievement([own], verified=True)
        viewer = core.Service(self.conn, self.make_user("viewer11", "viewer", athlete_ids=[own["id"]]))
        self.conn.commit()
        self.expect_error(403, lambda: viewer.profile(other["id"]))
        self.expect_error(403, lambda: viewer.detail("achievements", other_result["id"]))
        self.expect_error(403, lambda: viewer.dashboard())
        self.expect_error(403, lambda: viewer.create("achievements", {}))
        profile = viewer.profile(own["id"])
        self.assertNotIn("date_of_birth", profile["athlete"])
        self.assertNotIn("source_original_text", profile["achievements"][0])
        self.assertNotIn("evidence_url", profile["achievements"][0])
        self.assertEqual([own["id"]], [a["id"] for a in viewer.list("athletes")["items"]])
        self.assertEqual(own_result["id"], profile["achievements"][0]["id"])

    def test_12_medal_emoji_word_conflict_preserved_and_blocks_approval(self):
        data = workbook_bytes(conflict=True)
        preview = importer.preview(self.conn, data, "conflict.xlsx")
        self.assertTrue(any(w["code"] == "SOURCE_CONFLICT" for w in preview["warnings"]))
        with self.conn:
            importer.commit_import(self.conn, data, "conflict.xlsx", self.admin_user["id"])
        athlete = dict(self.conn.execute("SELECT * FROM athletes").fetchone())
        with self.conn:
            self.service.update("athletes", athlete["id"], {"version": athlete["version"],
                "identity_verification_status": "verified", "official_code": "TKD-CONFLICT-01"})
        result = dict(self.conn.execute("SELECT * FROM achievements").fetchone())
        self.assertEqual("HCB 🥇", result["source_original_text"])
        self.assertEqual(1, result["source_conflict"])
        self.assertEqual("pending", result["verification_status"])
        error = self.expect_error(422, lambda: self.approve(result))
        self.assertTrue(any("mâu thuẫn" in issue.lower() for issue in error.details))

    def test_13_dashboard_counts_club_medals_separately_from_athlete_credits(self):
        members = [self.athlete(f"Võ sinh {i}") for i in range(3)]
        tournament = self.tournament()
        self.achievement(members, tournament, True, participation_type="Đồng đội", expected_members=3, roster_confirmed=True)
        self.achievement([members[0]], tournament, True, medal_type="HCB", event_name="Đối kháng")
        self.achievement([members[1]], tournament, False, medal_type="HCĐ")
        report = self.service.dashboard()
        self.assertEqual({"HCV": 1, "HCB": 1, "HCĐ": 0}, report["club_medals"])
        self.assertEqual(2, report["verified"])
        self.assertEqual(4, report["athlete_medal_credits"])
        self.assertEqual(1, report["pending"])
        self.assertEqual(2, report["years"][0]["verified"])

    def test_duplicate_pair_and_legacy_codes_rejected(self):
        athlete = self.athlete(legacy_athlete_id="TAM-DUP-1")
        result = self.achievement([athlete])
        with self.assertRaises(sqlite3.IntegrityError):
            with self.conn:
                self.conn.execute("INSERT INTO athlete_achievements(achievement_id,athlete_id) VALUES(?,?)", (result["id"], athlete["id"]))
        with self.assertRaises(sqlite3.IntegrityError):
            with self.conn:
                self.service.create("athletes", {"full_name": "Người khác", "legacy_athlete_id": "TAM-DUP-1"})
        self.assertEqual(1, self.service.list("athletes")["total"])

    def test_foreign_keys_and_invalid_import_rollback(self):
        invalid = workbook_bytes(invalid_link=True)
        self.assertTrue(any(w["code"] == "INVALID_FK" for w in importer.preview(self.conn, invalid, "bad.xlsx")["errors"]))
        with self.assertRaises(ValueError):
            with self.conn:
                importer.commit_import(self.conn, invalid, "bad.xlsx", self.admin_user["id"])
        self.assertEqual(0, self.conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0])
        athlete = self.athlete()
        with self.assertRaises(sqlite3.IntegrityError):
            with self.conn:
                self.conn.execute("INSERT INTO athlete_achievements VALUES(?,?,?,?)", ("MISSING", athlete["id"], "pending", None))

    def test_duplicate_import_links_block_preview(self):
        preview = importer.preview(self.conn, workbook_bytes(duplicate_link=True), "double-link.xlsx")
        self.assertTrue(any(e["code"] == "DUPLICATE_LINK" for e in preview["errors"]))

    def test_coach_has_scope_and_cannot_self_grant_verification(self):
        own, other = self.athlete(), self.athlete("Ngoài phạm vi")
        result = self.achievement([own])
        coach = core.Service(self.conn, self.make_user("coach", "coach", athlete_ids=[own["id"]]))
        self.conn.commit()
        self.assertEqual(own["id"], coach.profile(own["id"])["athlete"]["id"])
        self.expect_error(403, lambda: coach.scope_athlete(other["id"]))
        self.expect_error(403, lambda: coach.verify(result["id"], {"version": result["version"], "evidence_checked": True,
            "duplicate_checked": True, "note": "Không có quyền xác minh"}))
        self.expect_error(403, lambda: coach.update("athletes", own["id"], {"version": own["version"], "identity_verification_status": "verified"}))

    def test_stale_update_fails_instead_of_overwriting(self):
        athlete = self.athlete()
        with self.conn:
            self.service.update("athletes", athlete["id"], {"version": athlete["version"], "notes": "Bản mới"})
        self.expect_error(409, lambda: self.service.update("athletes", athlete["id"], {"version": athlete["version"], "notes": "Bản cũ"}))
        self.assertEqual("Bản mới", self.service.profile(athlete["id"])["athlete"]["notes"])

    def test_editing_verified_result_resets_approval_and_preserves_audit(self):
        result = self.achievement([self.athlete()], verified=True)
        with self.conn:
            result = self.service.update("achievements", result["id"], {"version": result["version"], "event_name": "Nội dung cần đối chiếu lại"})
        self.assertEqual("pending", result["verification_status"])
        self.assertEqual(0, self.service.dashboard()["verified"])
        self.assertEqual("pending", self.conn.execute("SELECT link_status FROM athlete_achievements").fetchone()[0])
        actions = [r[0] for r in self.conn.execute("SELECT action FROM audit_logs WHERE entity_id=? ORDER BY id", (result["id"],))]
        self.assertEqual(["create", "verify", "update"], actions)

    def test_incomplete_team_missing_evidence_and_year_mismatch_block_approval(self):
        members = [self.athlete(f"Thành viên thiếu {i}") for i in range(2)]
        result = self.achievement(members, participation_type="Đồng đội", expected_members=3,
                                  roster_confirmed=False, evidence_url=None, competition_year=2025)
        error = self.expect_error(422, lambda: self.approve(result))
        reasons = " ".join(error.details)
        self.assertIn("thành viên", reasons)
        self.assertIn("minh chứng", reasons)
        self.assertIn("Năm", reasons)

    def test_unpublished_result_is_not_visible_to_viewer(self):
        athlete = self.athlete()
        result = self.achievement([athlete], verified=True, publication_allowed=False)
        viewer = core.Service(self.conn, self.make_user("privateviewer", "viewer", athlete_ids=[athlete["id"]]))
        self.conn.commit()
        self.assertEqual([], viewer.profile(athlete["id"])["achievements"])
        self.expect_error(403, lambda: viewer.detail("achievements", result["id"]))

    def test_verified_record_with_pending_viewer_link_not_visible(self):
        athlete = self.athlete()
        result = self.achievement([athlete], verified=True)
        with self.conn:
            self.conn.execute("UPDATE athlete_achievements SET link_status='pending' WHERE achievement_id=?", (result["id"],))
        viewer = core.Service(self.conn, self.make_user("pendinglink", "viewer", athlete_ids=[athlete["id"]]))
        self.conn.commit()
        self.assertEqual([], viewer.profile(athlete["id"])["achievements"])
        self.expect_error(403, lambda: viewer.detail("achievements", result["id"]))

    def test_persistence_after_connection_reopened(self):
        athlete = self.athlete()
        self.achievement([athlete], verified=True)
        self.conn.close()
        self.conn = core.connect(self.db_path)
        self.service = core.Service(self.conn, self.admin_user)
        self.assertEqual(1, self.service.profile(athlete["id"])["medals"]["HCV"])

    def test_dashboard_and_tournament_aggregate_beyond_first_1000_rows(self):
        athlete, tournament = self.athlete(), self.tournament()
        with self.conn:
            self.conn.executemany("INSERT INTO achievements(id,tournament_id,event_name,discipline,participation_type,medal_type,verification_status,publication_allowed) VALUES(?,?,?,?,?,?,?,?)",
                [(f"large-{i}", tournament["id"], f"Nội dung {i}", "Quyền", "Cá nhân", "HCV", "verified", 1) for i in range(1001)])
            self.conn.executemany("INSERT INTO athlete_achievements(achievement_id,athlete_id,link_status) VALUES(?,?,?)",
                [(f"large-{i}", athlete["id"], "verified") for i in range(1001)])
        self.assertEqual(1001, self.service.dashboard()["verified"])
        self.assertEqual(1001, self.service.dashboard()["club_medals"]["HCV"])
        self.assertEqual(1001, self.service.dashboard()["athlete_medal_credits"])
        self.assertEqual(1001, self.service.detail("tournaments", tournament["id"])["club_medals"]["HCV"])

    def test_reports_group_official_medals_and_drafts_in_all_dimensions(self):
        members = [self.athlete(f"Võ sinh báo cáo {i}") for i in range(3)]
        tournament = self.tournament(2024)
        self.achievement(members, tournament, True, participation_type="Đồng đội", expected_members=3,
                         roster_confirmed=True, representative_branch="Cơ sở lịch sử", discipline="Quyền")
        self.achievement([members[0]], tournament, False, medal_type="HCB", discipline="Đối kháng")
        report = self.service.reports({"year": 2024})
        self.assertEqual({"year", "tournament", "representative_branch", "discipline", "athlete"}, set(report))
        self.assertEqual(1, report["year"][0]["HCV"])
        self.assertEqual(0, report["year"][0]["HCB"])
        self.assertEqual(1, report["year"][0]["pending"])
        self.assertEqual(3, report["year"][0]["athlete_medal_credits"])
        self.assertEqual(3, len(report["athlete"]))
        self.assertTrue(all(r["HCV"] == 1 and r["athlete_medal_credits"] == 1 for r in report["athlete"]))
        self.assertTrue(all(not rows for rows in self.service.reports({"year": 2025}).values()))

    def test_coach_mixed_scope_team_cannot_leak_teammate_identity(self):
        own, other = self.athlete(), self.athlete("Đồng đội ngoài phạm vi")
        result = self.achievement([own, other], verified=True, participation_type="Đôi",
            source_original_text="Văn bản nội bộ có tên đồng đội ngoài phạm vi", legacy_achievement_id="PRIVATE-LEGACY",
            review_notes="Ghi chú riêng của người duyệt")
        coach = core.Service(self.conn, self.make_user("mixedcoach", "coach", True, athlete_ids=[own["id"]]))
        viewer = core.Service(self.conn, self.make_user("mixedviewer", "viewer", athlete_ids=[own["id"]]))
        self.conn.commit()
        detail = coach.detail("achievements", result["id"])
        self.assertEqual([own["id"]], [a["id"] for a in detail["athletes"]])
        self.assertEqual(1, coach.list("achievements")["total"])
        self.assertEqual(1, coach.profile(own["id"])["medals"]["HCV"])
        self.assertEqual([result["id"]], [a["id"] for a in coach.profile(own["id"])["achievements"]])
        report = coach.dashboard()
        self.assertEqual(1, report["club_medals"]["HCV"])
        self.assertEqual(1, report["athlete_medal_credits"])
        self.assertEqual(1, len(coach.reports()["athlete"]))
        for key in ("source_original_text", "source_records", "source_row", "review_notes", "legacy_achievement_id", "evidence_url"):
            self.assertFalse(detail.get(key), f"Thông tin ngoài phạm vi chưa được che: {key}")
        self.assertEqual([], detail.get("evidence_files", []))
        self.assertEqual(0, coach.list("achievements", {"q": "Văn bản nội bộ"})["total"])
        self.assertEqual(0, coach.list("achievements", {"q": "PRIVATE-LEGACY"})["total"])
        self.expect_error(403, lambda: coach.update("achievements", result["id"], {"version": result["version"], "event_name": "Sửa ngoài phạm vi"}))
        self.expect_error(403, lambda: coach.verify(result["id"], {"version": result["version"], "evidence_checked": True,
            "duplicate_checked": True, "note": "Không đủ phạm vi cả đội"}))
        self.assertEqual([own["id"]], [a["id"] for a in viewer.detail("achievements", result["id"])["athletes"]])

    def test_viewer_search_cannot_probe_hidden_source_or_legacy_code(self):
        athlete = self.athlete()
        result = self.achievement([athlete], verified=True, event_name="Quyền công khai",
            source_original_text="PrivateNeedle938 Nội dung nội bộ", legacy_achievement_id="SECRET-LEGACY-919")
        viewer = core.Service(self.conn, self.make_user("searchviewer", "viewer", athlete_ids=[athlete["id"]]))
        self.conn.commit()
        self.assertEqual(1, self.service.list("achievements", {"q": "PrivateNeedle938"})["total"])
        self.assertEqual(0, viewer.list("achievements", {"q": "PrivateNeedle938"})["total"])
        self.assertEqual(0, viewer.list("achievements", {"q": "SECRET-LEGACY-919"})["total"])
        self.assertEqual([result["id"]], [r["id"] for r in viewer.list("achievements", {"q": "Quyền công khai"})["items"]])

    def test_coach_can_update_notes_status_on_verified_athlete_without_changing_identity(self):
        athlete = self.athlete()
        result = self.achievement([athlete], verified=True)
        coach = core.Service(self.conn, self.make_user("editcoach", "coach", athlete_ids=[athlete["id"]]))
        self.conn.commit()
        with self.conn:
            updated = coach.update("athletes", athlete["id"], {"version": athlete["version"],
                "notes": "Cần trao đổi với quản trị về minh chứng", "status": "Tạm nghỉ"})["athlete"]
        self.assertEqual("Tạm nghỉ", updated["status"])
        self.assertEqual("Cần trao đổi với quản trị về minh chứng", updated["notes"])
        self.assertEqual("verified", updated["identity_verification_status"])
        self.assertEqual(athlete["official_code"], updated["official_code"])
        self.assertEqual(athlete["full_name"], updated["full_name"])
        self.assertEqual("verified", self.service.detail("achievements", result["id"])["verification_status"])
        self.expect_error(403, lambda: coach.update("athletes", athlete["id"], {"version": updated["version"], "full_name": "Tên tự đổi"}))

    def test_queue_cannot_be_resolved_by_link_to_pending_or_other_tournament(self):
        athlete, tournament = self.athlete(), self.tournament()
        pending = self.achievement([athlete], tournament)
        with self.conn:
            queue = self.service.create("queue", {"tournament_id": tournament["id"], "issue_type": "Thiếu người nhận",
                "reported_quantity": 5, "source_original_text": "Tổng 5 HCV"})
        self.expect_error(422, lambda: self.service.update("queue", queue["id"], {"version": queue["version"],
            "resolution_status": "resolved", "resolution_notes": "Chưa đối chiếu", "linked_achievement_id": pending["id"]}))
        wrong = self.achievement([athlete], verified=True)
        self.expect_error(422, lambda: self.service.update("queue", queue["id"], {"version": queue["version"],
            "resolution_status": "resolved", "resolution_notes": "Khác giải", "linked_achievement_id": wrong["id"]}))
        approved = self.approve(pending)
        with self.conn:
            resolved = self.service.update("queue", queue["id"], {"version": queue["version"],
                "resolution_status": "resolved", "resolution_notes": "Đã đối chiếu và liên kết đúng kết quả", "linked_achievement_id": approved["id"]})
        self.assertEqual("resolved", resolved["resolution_status"])
        self.assertEqual(2, self.conn.execute("SELECT COUNT(*) FROM achievements").fetchone()[0])

    def test_manual_entry_medal_conflict_also_blocks_approval_until_reviewed(self):
        result = self.achievement([self.athlete()], source_original_text="HCB 🥇")
        self.assertEqual(1, result["source_conflict"])
        self.expect_error(422, lambda: self.approve(result))
        with self.conn:
            result = self.service.update("achievements", result["id"], {"version": result["version"],
                "conflict_resolution": "Đã đối chiếu văn bản chính thức: HCV; giữ nguyên trích dẫn gốc."})
        approved = self.approve(result)
        self.assertEqual("verified", approved["verification_status"])
        self.assertEqual("HCB 🥇", approved["source_original_text"])

    def test_new_queue_item_cannot_skip_resolution_workflow(self):
        self.expect_error(422, lambda: self.service.create("queue", {
            "issue_type": "Thiếu người nhận", "reported_quantity": 7,
            "resolution_status": "resolved", "resolution_notes": "Không có liên kết đối chiếu"}))
        self.assertEqual(0, self.conn.execute("SELECT COUNT(*) FROM verification_queue").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
