"""Offline adapter tests: network calls are mocked, never use credentials."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.google_adapter import GoogleAdapterError, GoogleSheetsAdapter, integration_status, plan_changes


class GoogleAdapterTest(unittest.TestCase):
    def test_unconfigured_status_never_claims_connected(self):
        with patch.dict("os.environ", {}, clear=True):
            status = integration_status()
        self.assertFalse(status["configured"])
        self.assertFalse(status["connected"])
        self.assertFalse(status["sync_enabled"])

    def test_identical_snapshots_no_changes(self):
        rows = [{"id": "a", "name": "An", "version": 1}]
        plan = plan_changes(rows, rows, rows)
        self.assertEqual([], plan["changes"])
        self.assertEqual([], plan["conflicts"])
        self.assertEqual(1, plan["unchanged"])

    def test_concurrent_changes_require_review(self):
        base = [{"id": "a", "name": "An", "version": 1}]
        local = [{"id": "a", "name": "An local", "version": 2}]
        remote = [{"id": "a", "name": "An remote", "version": 2}]
        self.assertEqual("both_changed", plan_changes(local, remote, base)["conflicts"][0]["reason"])
        self.assertEqual("missing_baseline", plan_changes(local, remote)["conflicts"][0]["reason"])

    def test_one_side_changed_has_direction_and_original_snapshot(self):
        base = [{"id": "a", "version": 1}]
        newer = [{"id": "a", "version": 2}]
        local_plan = plan_changes(newer, base, base)
        remote_plan = plan_changes(base, newer, base)
        self.assertEqual("local_to_remote", local_plan["changes"][0]["direction"])
        self.assertEqual("remote_to_local", remote_plan["changes"][0]["direction"])
        self.assertEqual(base[0], local_plan["changes"][0]["before"])

    def test_deletion_and_duplicate_ids_never_auto_apply(self):
        rows = [{"id": "a", "version": 1}]
        self.assertEqual("deletion_requires_review", plan_changes(rows, [], rows)["conflicts"][0]["reason"])
        with self.assertRaises(GoogleAdapterError):
            plan_changes(rows + rows, rows)

    def test_apply_rejects_unauthorized_or_unconfirmed(self):
        adapter = GoogleSheetsAdapter("sheet", "private-test-token", True)
        plan = plan_changes([], [])
        for user, confirmed in (({"role": "coach"}, True), ({"role": "admin"}, False)):
            with self.assertRaises(GoogleAdapterError) as raised:
                adapter.apply(plan, user=user, source_range="Athletes!A1:B2", confirmed=confirmed)
            self.assertEqual(403, raised.exception.status)

    def test_apply_rechecks_remote_hash_and_stages_without_overwriting(self):
        base = [{"id": "a", "version": 1}]
        local = [{"id": "a", "version": 2}]
        adapter = GoogleSheetsAdapter("sheet", "private-test-token", True)
        plan = plan_changes(local, base, base)
        with patch.object(adapter, "read_table", return_value=[{"id": "a", "version": 3}]):
            with self.assertRaises(GoogleAdapterError) as raised:
                adapter.apply(plan, user={"id": "admin", "role": "admin"}, source_range="Athletes!A:B", confirmed=True)
            self.assertEqual(409, raised.exception.status)
        with patch.object(adapter, "read_table", return_value=base), patch.object(adapter, "_request", return_value={"updates": {"updatedRange": "_TKD_SYNC_INBOX!A2:H2"}}) as request:
            result = adapter.apply(plan, user={"id": "admin", "role": "admin"}, source_range="Athletes!A:B", confirmed=True)
        self.assertEqual(1, result["staged"])
        self.assertFalse(result["applied"])
        self.assertFalse(result["source_overwritten"])
        self.assertIn(":append?", request.call_args.args[1])
        self.assertIn("valueInputOption=RAW", request.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
