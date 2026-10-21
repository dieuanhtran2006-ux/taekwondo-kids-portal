"""Anonymous access must never inherit the permissions of a signed-in viewer/admin."""
import json
from unittest.mock import patch
import unittest

from app import core
import test_http_security as http_security

PNG = http_security.PNG


class PublicPortalTest(unittest.TestCase):
    setUp = http_security.HttpSecurityTest.setUp
    tearDown = http_security.HttpSecurityTest.tearDown
    request = http_security.HttpSecurityTest.request

    def make_profile(self, name='Trần Đức Minh', code='TKD-PUBLIC-001'):
        status, _, data = self.request('POST', '/api/athletes', {'full_name': name,
            'official_code': code, 'identity_verification_status': 'verified',
            'date_of_birth': '2015-02-03', 'notes': 'PRIVATE_PROFILE_NOTE', 'legacy_athlete_id': 'PRIVATE_LEGACY_' + code})
        self.assertEqual(200, status, data)
        return data['athlete']

    def make_result(self, members, **extra):
        status, _, tournament = self.request('POST', '/api/tournaments', {'tournament_name': 'Giải kiểm thử công bố', 'year': 2024, 'source_url': 'https://example.org/PRIVATE_SOURCE'})
        self.assertEqual(200, status, tournament)
        status, _, result = self.request('POST', '/api/achievements', {'tournament_id': tournament['tournament']['id'],
            'event_name': 'Quyền tiêu chuẩn', 'discipline': 'Quyền', 'participation_type': 'Cá nhân', 'medal_type': 'HCV',
            'athlete_ids': [a['id'] for a in members], 'evidence_url': 'https://example.org/PRIVATE_PROOF',
            'publication_allowed': True, 'evidence_publication_allowed': True,
            'source_original_text': 'PRIVATE_SOURCE_TEXT', 'review_notes': 'PRIVATE_REVIEW', **extra})
        self.assertEqual(200, status, result)
        return self.verify(result)

    def verify(self, result):
        result = self.request('GET', '/api/achievements/' + result['id'])[2]
        status, _, result = self.request('POST', '/api/achievements/' + result['id'] + '/verify', {'version': result['version'],
            'evidence_checked': True, 'duplicate_checked': True, 'note': 'PRIVATE_VERIFICATION_NOTE'})
        self.assertEqual(200, status, result)
        return result

    def publish(self, entity, id, **flags):
        current = self.request('GET', '/api/' + entity + '/' + id)[2]
        record = current['athlete'] if entity == 'athletes' else current
        return self.request('PATCH', '/api/publication/' + entity + '/' + id, {'version': record['version'], **flags})

    def publish_pair(self):
        athlete = self.make_profile()
        result = self.make_result([athlete])
        self.assertEqual(200, self.publish('athletes', athlete['id'], public_profile_allowed=True)[0])
        self.assertEqual(200, self.publish('achievements', result['id'], public_search_allowed=True)[0])
        return athlete, result

    def public(self, path):
        return self.request('GET', '/api/public/' + path, auth=False, csrf=False)

    def test_home_is_public_admin_is_separate_and_internal_apis_stay_locked(self):
        status, _, page = self.request('GET', '/', auth=False)
        self.assertEqual(200, status)
        self.assertIn(b'/static/public.js', page)
        self.assertNotIn(b'/static/app.js', page)
        self.assertIn(b'/static/app.js', self.request('GET', '/admin/', auth=False)[2])
        self.assertEqual(200, self.request('GET', '/ho-so/unknown', auth=False)[0])
        for path in ('/api/athletes', '/api/dashboard', '/api/audit', '/api/export', '/api/source/athletes/missing', '/api/evidence/missing'):
            self.assertEqual(401, self.request('GET', path, auth=False)[0], path)
        self.assertEqual(404, self.request('GET', '/static/../data/portal.sqlite3', auth=False)[0])

    def test_existing_verified_viewer_permissions_never_auto_publish(self):
        athlete = self.make_profile(); result = self.make_result([athlete])
        self.assertEqual(0, self.public('summary')[2]['achievement_count'])
        self.assertEqual(0, self.public('athletes?q=Minh')[2]['total'])
        self.assertEqual(404, self.public('athletes/' + athlete['id'])[0])
        self.assertEqual(404, self.public('achievements/' + result['id'])[0])

    def test_guest_search_handles_vietnamese_and_returns_only_allowlisted_fields(self):
        athlete, result = self.publish_pair()
        for query in ('tran%20duc', 'TR%E1%BA%A6N', 'TKD-PUBLIC-001'):
            status, _, data = self.public('athletes?q=' + query)
            self.assertEqual(200, status, data); self.assertEqual(1, data['total'])
            self.assertEqual(athlete['id'], data['items'][0]['id'])
        profile = self.public('athletes/' + athlete['id'])[2]
        self.assertEqual({'id', 'full_name', 'official_code'}, set(profile['athlete']))
        self.assertEqual(1, profile['medals']['HCV'])
        content = json.dumps(profile)
        for private in ('date_of_birth', 'birth_year', 'PRIVATE_', 'legacy_', 'source_', 'review_', 'verified_by', 'current_branch_id', 'version', 'public_search_allowed'):
            self.assertNotIn(private, content)
        # Logging into admin does not broaden an anonymous endpoint's response.
        self.assertEqual(profile, self.request('GET', '/api/public/athletes/' + athlete['id'])[2])

    def test_empty_or_wildcard_query_cannot_list_the_roster(self):
        self.publish_pair()
        for query in ('', 'q=A', 'q=%25%25', 'q=__', 'q=%27%20OR%201%3D1'):
            data = self.public('athletes?' + query)[2]
            self.assertEqual(0, data['total'])
        self.assertTrue(self.public('athletes')[2]['query_required'])
        self.assertEqual(422, self.public('athletes?q=' + 'a' * 101)[0])
        self.assertEqual(422, self.public('athletes?q=Minh&page=no')[0])

    def test_duplicate_names_and_pagination_keep_separate_official_codes(self):
        for index in range(3):
            a = self.make_profile('Tên Trùng', f'TKD-DUP-{index}')
            self.assertEqual(200, self.publish('athletes', a['id'], public_profile_allowed=True)[0])
        first = self.public('athletes?q=ten%20trung&limit=2')[2]
        second = self.public('athletes?q=ten%20trung&limit=2&page=2')[2]
        self.assertEqual(3, first['total']); self.assertEqual(2, first['pages'])
        self.assertEqual(3, len({a['id'] for a in first['items'] + second['items']}))
        self.assertEqual(0, first['items'][0]['achievement_count'])

    def test_team_medal_is_counted_once_and_unpublished_teammate_is_redacted(self):
        members = [self.make_profile('Thành viên ' + str(i), f'TKD-TEAM-{i}') for i in range(3)]
        result = self.make_result(members, participation_type='Đồng đội', expected_members=3, roster_confirmed=True)
        for a in members[:2]: self.assertEqual(200, self.publish('athletes', a['id'], public_profile_allowed=True)[0])
        self.assertEqual(200, self.publish('achievements', result['id'], public_search_allowed=True)[0])
        summary = self.public('summary')[2]
        self.assertEqual(1, summary['medals']['HCV']); self.assertEqual(2, summary['athlete_medal_credits'])
        self.assertEqual(3, self.request('GET', '/api/dashboard')[2]['athlete_medal_credits'])
        public_result = self.public('achievements/' + result['id'])[2]
        self.assertEqual(2, len(public_result['athletes']))
        self.assertNotIn(members[2]['full_name'], json.dumps(public_result, ensure_ascii=False))
        self.assertEqual(404, self.public('athletes/' + members[2]['id'])[0])

    def test_unverified_identity_cannot_be_published(self):
        status, _, data = self.request('POST', '/api/athletes', {'full_name': 'Tên tạm', 'legacy_athlete_id': 'TAM-VS-0001'})
        self.assertEqual(200, status)
        self.assertEqual(422, self.publish('athletes', data['athlete']['id'], public_profile_allowed=True)[0])

    def test_only_admin_can_change_public_permissions_and_stale_versions_conflict(self):
        athlete, result = self.publish_pair()
        current = self.request('GET', '/api/athletes/' + athlete['id'])[2]['athlete']
        status, _, coach = self.request('POST', '/api/users', {'username': 'coach', 'password': 'Mat-khau-coach-2026', 'role': 'coach', 'athlete_ids': [athlete['id']]})
        self.assertEqual(200, status)
        status, headers, login = self.request('POST', '/api/login', {'username': 'coach', 'password': 'Mat-khau-coach-2026'}, auth=False)
        self.cookie, self.csrf = headers['set-cookie'].split(';', 1)[0], login['csrf']
        self.assertEqual(403, self.request('PATCH', '/api/publication/athletes/' + athlete['id'], {'version': current['version'], 'public_profile_allowed': False})[0])
        self.cookie, self.csrf = self.admin_cookie, self.admin_csrf
        self.assertEqual(409, self.request('PATCH', '/api/publication/athletes/' + athlete['id'], {'version': current['version'] - 1, 'public_profile_allowed': False})[0])
        self.assertEqual(422, self.publish('athletes', athlete['id'], public_profile_allowed='false')[0])

    def test_revocation_is_immediate_and_does_not_undo_verification(self):
        athlete, result = self.publish_pair()
        self.assertEqual(200, self.publish('achievements', result['id'], public_search_allowed=False)[0])
        self.assertEqual(404, self.public('achievements/' + result['id'])[0])
        self.assertEqual('verified', self.request('GET', '/api/achievements/' + result['id'])[2]['verification_status'])
        self.assertEqual(200, self.publish('athletes', athlete['id'], public_profile_allowed=False)[0])
        self.assertEqual(404, self.public('athletes/' + athlete['id'])[0])
        logs = self.request('GET', '/api/audit')[2]
        self.assertIn('public_visibility', json.dumps(logs))

    def test_editing_result_or_identity_requires_fresh_publication(self):
        athlete, result = self.publish_pair()
        current = self.request('GET', '/api/achievements/' + result['id'])[2]
        status, _, changed = self.request('PATCH', '/api/achievements/' + result['id'], {'version': current['version'], 'event_name': 'Quyền mới'})
        self.assertEqual(200, status); self.assertEqual(0, changed['public_search_allowed'])
        self.verify(changed)
        self.assertEqual(404, self.public('achievements/' + result['id'])[0])
        current = self.request('GET', '/api/athletes/' + athlete['id'])[2]['athlete']
        self.assertEqual(200, self.request('PATCH', '/api/athletes/' + athlete['id'], {'version': current['version'], 'full_name': 'Tên đã đối chiếu mới'})[0])
        self.assertEqual(404, self.public('athletes/' + athlete['id'])[0])

    def test_current_eligibility_is_rechecked_for_every_public_request(self):
        athlete, result = self.publish_pair()
        conn = core.connect(self.db)
        try:
            with conn: conn.execute("UPDATE athlete_achievements SET link_status='pending' WHERE achievement_id=?", (result['id'],))
        finally: conn.close()
        self.assertEqual(404, self.public('achievements/' + result['id'])[0])
        self.assertEqual(0, self.public('summary')[2]['achievement_count'])

    def test_file_and_url_evidence_have_separate_explicit_guest_permissions(self):
        athlete, result = self.publish_pair()
        self.assertNotIn('evidence_url', self.public('achievements/' + result['id'])[2])
        self.assertEqual(200, self.publish('achievements', result['id'], public_search_allowed=True, public_evidence_allowed=True)[0])
        self.assertIn('evidence_url', self.public('achievements/' + result['id'])[2])
        status, _, upload = self.request('POST', '/api/evidence?achievement_id=' + result['id'], raw=PNG, headers={'HTTP_X_FILENAME': 'PRIVATE_FILENAME.png'})
        self.assertEqual(200, status, upload)
        self.verify(result)
        self.assertEqual(200, self.publish('achievements', result['id'], public_search_allowed=True)[0])
        file_id = upload['id']
        self.assertEqual(200, self.request('PATCH', '/api/evidence/' + file_id, {'publication_allowed': True})[0])
        self.assertEqual(404, self.public('evidence/' + file_id)[0])
        self.assertEqual(200, self.request('PATCH', '/api/evidence/' + file_id, {'public_access_allowed': True})[0])
        status, headers, content = self.public('evidence/' + file_id)
        self.assertEqual(200, status); self.assertEqual(PNG, content)
        self.assertIn('attachment;', headers['content-disposition'])
        self.assertNotIn('PRIVATE_FILENAME', json.dumps(self.public('achievements/' + result['id'])[2]))
        self.assertEqual(200, self.publish('achievements', result['id'], public_search_allowed=False)[0])
        self.assertEqual(404, self.public('evidence/' + file_id)[0])

    def test_read_only_guest_endpoints_and_rate_limit(self):
        self.assertEqual(405, self.request('POST', '/api/public/athletes', {'full_name': 'Không được ghi'}, auth=False)[0])
        for index in range(60): self.assertEqual(200, self.public('summary')[0])
        self.assertEqual(429, self.public('summary')[0])
        with patch('server.time.monotonic', return_value=10**12): self.assertEqual(200, self.public('summary')[0])

    def test_migration_preserves_data_and_defaults_existing_records_to_private(self):
        athlete = self.make_profile(); result = self.make_result([athlete])
        conn = core.connect(self.db)
        try:
            conn.execute('DROP INDEX idx_athlete_public'); conn.execute('DROP INDEX idx_achievement_public')
            for table, columns in {'athletes': ('public_profile_allowed',), 'achievements': ('public_search_allowed', 'public_evidence_allowed'), 'evidence_files': ('public_access_allowed',)}.items():
                for column in columns: conn.execute(f'ALTER TABLE {table} DROP COLUMN {column}')
            conn.commit()
            core.init_db(conn); core.init_db(conn)
            self.assertEqual(0, conn.execute('SELECT public_profile_allowed FROM athletes WHERE id=?', (athlete['id'],)).fetchone()[0])
            self.assertEqual('verified', conn.execute('SELECT verification_status FROM achievements WHERE id=?', (result['id'],)).fetchone()[0])
        finally: conn.close()
        self.assertEqual(0, self.public('summary')[2]['achievement_count'])


if __name__ == '__main__': unittest.main()
