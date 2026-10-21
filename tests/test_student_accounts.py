"""First-login password gate, account issuance and server-side child isolation."""
import json
import sqlite3
from pathlib import Path
import tempfile
from unittest import TestCase
from app import core
import server
import test_http_security as http_security

TEMP_PASSWORD='Temp-Student!2026'
NEW_PASSWORD='Mat-khau-rieng!2026'


class StudentAccountsTest(TestCase):
    setUp=http_security.HttpSecurityTest.setUp
    tearDown=http_security.HttpSecurityTest.tearDown
    request=http_security.HttpSecurityTest.request

    def athlete(self,code='TKD-LOGIN-001',name='Tên trùng kiểm thử'):
        status,_,data=self.request('POST','/api/athletes',{'full_name':name,'official_code':code,'identity_verification_status':'verified'})
        self.assertEqual(200,status,data);return data['athlete']

    def issue(self,athlete,password=TEMP_PASSWORD):
        return self.request('POST','/api/athletes/'+athlete['id']+'/account',{'version':athlete['version'],'password':password})

    def login(self,username,password=TEMP_PASSWORD):
        status,headers,data=self.request('POST','/api/student/login',{'username':username,'password':password},auth=False,csrf=False)
        if status==200:self.cookie=headers['set-cookie'].split(';')[0];self.csrf=data['csrf']
        return status,headers,data

    def change(self,old=TEMP_PASSWORD,new=NEW_PASSWORD,**extra):
        status,headers,data=self.request('POST','/api/password',{'current_password':old,'password':new,'confirm_password':new,**extra})
        if status==200:self.cookie=headers['set-cookie'].split(';')[0];self.csrf=data['csrf']
        return status,headers,data

    def test_issue_uses_official_code_one_bound_profile_and_no_plaintext_audit(self):
        athlete=self.athlete();status,_,issued=self.issue(athlete)
        self.assertEqual(200,status,issued);account=issued['account']
        self.assertEqual(athlete['official_code'],account['username']);self.assertEqual('viewer',account['role'])
        self.assertEqual(1,account['must_change_password']);self.assertEqual(athlete['id'],account['login_athlete_id'])
        self.assertNotIn('password_hash',account);self.assertEqual(TEMP_PASSWORD,issued['initial_password'])
        conn=core.connect(self.db)
        try:
            row=conn.execute('SELECT password_hash FROM users WHERE id=?',(account['id'],)).fetchone()
            self.assertNotEqual(TEMP_PASSWORD,row[0]);self.assertTrue(core.verify_password(TEMP_PASSWORD,row[0]))
            logs=' '.join(r[0] or '' for r in conn.execute('SELECT after_json FROM audit_logs'))
            self.assertNotIn(TEMP_PASSWORD,logs)
            self.assertEqual([athlete['id']],[r[0] for r in conn.execute('SELECT athlete_id FROM user_athletes WHERE user_id=?',(account['id'],))])
        finally:conn.close()
        self.assertEqual(409,self.issue(athlete)[0])

    def test_first_login_blocks_private_apis_until_change_and_rotates_session(self):
        a=self.athlete();self.issue(a);status,_,s=self.login(a['official_code'].lower())
        self.assertEqual(200,status,s);self.assertTrue(s['user']['must_change_password']);self.assertEqual([],s['user']['athlete_ids'])
        for path in ('/api/student/athletes/'+a['id'],'/api/athletes/'+a['id'],'/api/achievements','/api/evidence/unknown','/api/catalogs'):
            status,_,error=self.request('GET',path);self.assertEqual(403,status,error);self.assertEqual('PASSWORD_CHANGE_REQUIRED',error['details']['code'])
        old_cookie=self.cookie;old_csrf=self.csrf
        status,_,changed=self.change();self.assertEqual(200,status,changed)
        self.assertFalse(changed['user']['must_change_password']);self.assertEqual([a['id']],changed['user']['athlete_ids'])
        self.assertNotEqual(old_cookie,self.cookie);self.assertNotEqual(old_csrf,self.csrf)
        self.assertEqual(200,self.request('GET','/api/student/athletes/'+a['id'])[0])
        new_cookie,new_csrf=self.cookie,self.csrf;self.cookie,self.csrf=old_cookie,old_csrf
        self.assertEqual(401,self.request('GET','/api/student/athletes/'+a['id'])[0]);self.cookie,self.csrf=new_cookie,new_csrf
        self.assertEqual(401,self.login(a['official_code'],TEMP_PASSWORD)[0]);self.assertEqual(200,self.login(a['official_code'],NEW_PASSWORD)[0])

    def test_first_change_cannot_be_skipped_with_wrong_same_short_or_mismatched_password(self):
        a=self.athlete();self.issue(a);self.login(a['official_code'])
        for kwargs in ({'old':'wrong'},{'new':TEMP_PASSWORD},{'new':'short'},{'new':a['official_code']},{'confirm_password':'khac'},{'new':'x'*257}):
            self.assertEqual(422,self.change(**kwargs)[0])
        self.assertTrue(self.request('GET','/api/session')[2]['user']['must_change_password'])
        self.assertEqual(403,self.request('POST','/api/password',{'current_password':TEMP_PASSWORD,'password':NEW_PASSWORD,'confirm_password':NEW_PASSWORD},csrf=False)[0])
        self.assertEqual(200,self.change()[0])

    def test_same_name_other_child_and_staff_apis_remain_forbidden(self):
        own=self.athlete();other=self.athlete('TKD-LOGIN-002');self.issue(own);self.login(own['official_code']);self.change()
        self.assertEqual(403,self.request('GET','/api/student/athletes/'+other['id'])[0])
        self.assertEqual(403,self.request('GET','/api/athletes/'+other['id'])[0])
        for path in ('/api/users','/api/export','/api/audit','/api/submissions'):
            self.assertEqual(403,self.request('GET',path)[0])
        listing=self.request('GET','/api/athletes')[2]
        self.assertEqual([own['id']],[r['id'] for r in listing['items']])

    def test_private_verified_result_needs_no_public_search_consent(self):
        a=self.athlete();_,_,t=self.request('POST','/api/tournaments',{'tournament_name':'Giải riêng tư','year':2025})
        _,_,r=self.request('POST','/api/achievements',{'tournament_id':t['tournament']['id'],'event_name':'Quyền','discipline':'Quyền','participation_type':'Cá nhân','medal_type':'HCV','athlete_ids':[a['id']],'publication_allowed':True,'evidence_url':'https://example.org/private','source_original_text':'PRIVATE_SOURCE','team_name':'PRIVATE_TEAM_TEXT'})
        status,_,r=self.request('POST','/api/achievements/'+r['id']+'/verify',{'version':r['version'],'evidence_checked':True,'duplicate_checked':True,'note':'Căn cứ kiểm thử'})
        self.assertEqual(200,status,r);self.issue(a);self.login(a['official_code']);self.change()
        status,_,profile=self.request('GET','/api/student/athletes/'+a['id']);self.assertEqual(200,status,profile)
        self.assertEqual(1,profile['medals']['HCV']);self.assertEqual(1,profile['achievement_count'])
        for text in ('date_of_birth','legacy_','source_original_text','PRIVATE_SOURCE','PRIVATE_TEAM_TEXT'):
            self.assertNotIn(text,json.dumps(profile))
        self.assertEqual(404,self.request('GET','/api/public/athletes/'+a['id'],auth=False)[0])

    def test_admin_reset_revokes_sessions_and_requires_change_again(self):
        a=self.athlete();_,_,issued=self.issue(a);self.login(a['official_code']);self.change()
        student_cookie,student_csrf=self.cookie,self.csrf;self.cookie,self.csrf=self.admin_cookie,self.admin_csrf
        account=next(u for u in self.request('GET','/api/users')[2]['items'] if u['id']==issued['account']['id'])
        status,_,updated=self.request('PATCH','/api/users/'+account['id'],{'version':account['version'],'password':'Reset-Student!2026'})
        self.assertEqual(200,status,updated);self.assertTrue(updated['must_change_password'])
        self.cookie,self.csrf=student_cookie,student_csrf
        self.assertEqual(401,self.request('GET','/api/student/athletes/'+a['id'])[0])
        self.assertEqual(200,self.login(a['official_code'],'Reset-Student!2026')[0])
        self.assertEqual(403,self.request('GET','/api/student/athletes/'+a['id'])[0])

    def test_admin_cannot_accidentally_expand_bound_scope(self):
        a=self.athlete();other=self.athlete('TKD-LOGIN-002');_,_,issued=self.issue(a);u=issued['account']
        for patch in ({'athlete_ids':[a['id'],other['id']]},{'role':'admin'},{'athlete_ids':[]}):
            self.assertEqual(422,self.request('PATCH','/api/users/'+u['id'],{'version':u['version'],**patch})[0])

    def test_issue_requires_admin_valid_identity_and_current_version(self):
        a=self.athlete();self.assertEqual(409,self.request('POST','/api/athletes/'+a['id']+'/account',{'version':0})[0])
        self.assertEqual(403,self.request('POST','/api/athletes/'+a['id']+'/account',{'version':a['version']},csrf=False)[0])
        _,_,draft=self.request('POST','/api/athletes',{'full_name':'Tên tạm','legacy_athlete_id':'TAM-VS-01'})
        self.assertEqual(422,self.issue(draft['athlete'])[0])
        self.request('POST','/api/users',{'username':'coach-student','password':TEMP_PASSWORD,'role':'coach'})
        status,h,s=self.request('POST','/api/login',{'username':'coach-student','password':TEMP_PASSWORD},auth=False,csrf=False)
        self.assertEqual(200,status);self.cookie=h['set-cookie'].split(';')[0];self.csrf=s['csrf']
        self.assertEqual(403,self.issue(a)[0])

    def test_default_viewer_cannot_opt_out_of_first_change_and_student_login_rejects_admin(self):
        a=self.athlete();status,_,u=self.request('POST','/api/users',{'username':'legacy-viewer','password':TEMP_PASSWORD,'role':'viewer','athlete_ids':[a['id']],'must_change_password':False})
        self.assertEqual(200,status,u);self.assertTrue(u['must_change_password'])
        self.assertEqual(401,self.login('admin','Mat-khau-admin-2026')[0])
        self.assertEqual(404,self.request('GET','/static/demo-auth.js',auth=False)[0])

    def test_login_attempts_shared_across_alias_and_case(self):
        a=self.athlete();self.issue(a)
        for i in range(8):
            path='/api/login' if i%2 else '/api/student/login'
            self.assertEqual(401,self.request('POST',path,{'username':a['official_code'].lower() if i%2 else a['official_code'],'password':'incorrect'},auth=False,csrf=False)[0])
        self.assertEqual(429,self.login(a['official_code'])[0])

    def test_pending_session_can_logout_and_page_has_no_default_real_credentials(self):
        a=self.athlete();self.issue(a);self.login(a['official_code'])
        self.assertEqual(200,self.request('POST','/api/logout',{})[0])
        status,_,page=self.request('GET','/dang-nhap',auth=False)
        self.assertEqual(200,status);self.assertIn(b'/static/student.js',page);self.assertNotIn(b'TKD-Mau!2026',page)

    def test_migration_forces_legacy_viewers_only_once_and_preserves_password(self):
        with tempfile.TemporaryDirectory() as temp:
            db=Path(temp)/'old.sqlite3';conn=sqlite3.connect(db)
            conn.execute('CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT UNIQUE,password_hash TEXT,role TEXT,can_verify INTEGER DEFAULT 0,active INTEGER DEFAULT 1,version INTEGER DEFAULT 1,created_at TEXT)')
            encoded=core.hash_password(TEMP_PASSWORD)
            conn.execute('INSERT INTO users(id,username,password_hash,role) VALUES(?,?,?,?)',('old-viewer','legacy',encoded,'viewer'));conn.commit();conn.close()
            conn=core.connect(db)
            try:
                core.init_db(conn);row=conn.execute('SELECT * FROM users').fetchone()
                self.assertEqual(1,row['must_change_password']);self.assertEqual(encoded,row['password_hash'])
                conn.execute('UPDATE users SET must_change_password=0');conn.commit();core.init_db(conn)
                self.assertEqual(0,conn.execute('SELECT must_change_password FROM users').fetchone()[0])
            finally:conn.close()
