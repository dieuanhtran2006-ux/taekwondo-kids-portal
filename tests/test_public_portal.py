"""No record, aggregate, or proof may be fetched anonymously, even if legacy flags are on."""
import unittest
from app import core
import test_http_security as http_security


class LoginOnlyTest(unittest.TestCase):
    setUp=http_security.HttpSecurityTest.setUp
    tearDown=http_security.HttpSecurityTest.tearDown
    request=http_security.HttpSecurityTest.request
    create_record=http_security.HttpSecurityTest.create_record
    viewer_login=http_security.HttpSecurityTest.viewer_login

    def test_all_retired_routes_require_login_for_every_method(self):
        for method in ('GET','POST','PATCH','DELETE'):
            for path in ('summary','athletes?q=Minh','athletes/known','achievements/known','evidence/known','submissions'):
                status,_,data=self.request(method,'/api/public/'+path,auth=False,csrf=False)
                self.assertEqual(401,status,data)
                self.assertEqual({'error'},set(data))

    def test_legacy_public_flags_do_not_bypass_authentication(self):
        athlete,result=self.create_record()
        conn=core.connect(self.db)
        with conn:
            conn.execute('UPDATE athletes SET public_profile_allowed=1 WHERE id=?',(athlete['id'],))
            conn.execute('UPDATE achievements SET public_search_allowed=1,public_evidence_allowed=1 WHERE id=?',(result['id'],))
        conn.close()
        for path in ('summary','athletes?q=HTTP','athletes/'+athlete['id'],'achievements/'+result['id']):
            status,headers,data=self.request('GET','/api/public/'+path,auth=False)
            self.assertEqual(401,status);self.assertIn('no-store',headers['cache-control'])
            self.assertNotIn(athlete['full_name'],str(data))
        self.assertEqual(401,self.request('GET','/api/athletes/'+athlete['id'],auth=False)[0])

    def test_logged_in_accounts_cannot_reopen_anonymous_lookup(self):
        self.assertEqual(410,self.request('GET','/api/public/athletes?q=abc')[0])
        self.assertEqual(410,self.request('PATCH','/api/publication/athletes/any',{'version':1,'public_profile_allowed':True})[0])

    def test_root_and_old_profile_urls_show_login_without_record_data(self):
        athlete,_=self.create_record()
        for path in ('/','/tra-cuu','/ho-so/'+athlete['id'],'/dang-nhap.html'):
            status,_,page=self.request('GET',path,auth=False)
            self.assertEqual(200,status);text=page.decode()
            self.assertIn('id="student-main"',text);self.assertIn('static/student.js',text)
            self.assertNotIn('static/public.js',text);self.assertNotIn(athlete['full_name'],text)
            self.assertNotIn('Tra cứu công khai',text)
        for path in ('/public-data.json','/static/public.js','/static/demo-auth.js','/static/sample-profile.js','/data/portal.sqlite3'):
            self.assertEqual(404,self.request('GET',path,auth=False)[0])

    def test_private_api_still_checks_child_scope(self):
        athlete,_=self.create_record()
        _,_,other=self.request('POST','/api/athletes',{'full_name':'Võ sinh khác'})
        self.viewer_login(athlete['id'])
        self.assertEqual(200,self.request('GET','/api/student/athletes/'+athlete['id'])[0])
        self.assertEqual(403,self.request('GET','/api/student/athletes/'+other['athlete']['id'])[0])

    def test_migration_is_repeatable_and_does_not_remove_history(self):
        athlete,result=self.create_record();conn=core.connect(self.db)
        try:
            core.init_db(conn);core.init_db(conn)
            self.assertEqual(1,conn.execute('SELECT COUNT(*) FROM athlete_achievements WHERE athlete_id=?',(athlete['id'],)).fetchone()[0])
            self.assertEqual(result['id'],conn.execute('SELECT id FROM achievements').fetchone()[0])
            self.assertEqual(0,conn.execute('SELECT COUNT(*) FROM attendance_records').fetchone()[0])
        finally:conn.close()
