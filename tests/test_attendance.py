"""Server-level privacy, recording, corrections, and attendance history."""
import unittest
from app import core
import server
import test_http_security as http


class AttendanceTest(unittest.TestCase):
    setUp=http.HttpSecurityTest.setUp
    tearDown=http.HttpSecurityTest.tearDown
    request=http.HttpSecurityTest.request
    viewer_login=http.HttpSecurityTest.viewer_login

    def athlete(self,code='ATT-001',**extra):
        status,_,data=self.request('POST','/api/athletes',{'full_name':'Tên kiểm thử điểm danh','official_code':code,'identity_verification_status':'verified','date_of_birth':'2015-02-03',**extra})
        self.assertEqual(200,status,data);return data['athlete']

    def record(self,athlete,**extra):
        return self.request('POST','/api/attendance',{'athlete_id':athlete['id'],'session_date':'2025-10-01','start_time':'17:30','class_name':'Lớp kiểm thử','status':'present','note':'Ghi chú cho gia đình',**extra})

    def test_saved_records_survive_restart_and_only_recorded_sessions_are_counted(self):
        a=self.athlete();self.assertEqual(0,self.request('GET','/api/attendance')[2]['total'])
        for day,status in [('01','present'),('02','excused_absent'),('03','unexcused_absent')]:
            self.assertEqual(200,self.record(a,session_date='2025-10-'+day,status=status)[0])
        self.app=server.Application(self.db)
        status,_,data=self.request('GET','/api/athletes/'+a['id']+'/attendance?limit=2')
        self.assertEqual(200,status);self.assertEqual(3,data['total']);self.assertEqual(2,len(data['items']))
        self.assertEqual({'present':1,'excused_absent':1,'unexcused_absent':1},data['summary'])
        self.assertEqual(1,self.request('GET','/api/attendance?status=present')[2]['total'])
        self.assertEqual(2,self.request('GET','/api/attendance?from_date=2025-10-02')[2]['total'])

    def test_duplicate_session_rejected_but_multiple_classes_allowed(self):
        a=self.athlete();self.assertEqual(200,self.record(a)[0]);self.assertEqual(422,self.record(a)[0])
        self.assertEqual(200,self.record(a,class_name='Lớp khác')[0])
        self.assertEqual(2,self.request('GET','/api/attendance')[2]['total'])

    def test_correction_requires_version_and_archive_retains_audit(self):
        a=self.athlete();r=self.record(a)[2]
        self.assertEqual(403,self.request('PATCH','/api/attendance/'+r['id'],{'version':1,'status':'excused_absent'},csrf=False)[0])
        status,_,changed=self.request('PATCH','/api/attendance/'+r['id'],{'version':1,'status':'excused_absent'})
        self.assertEqual(200,status,changed);self.assertEqual(2,changed['version'])
        self.assertEqual(409,self.request('PATCH','/api/attendance/'+r['id'],{'version':1,'status':'present'})[0])
        self.assertEqual(409,self.request('DELETE','/api/attendance/'+r['id'],{'version':1})[0])
        self.assertEqual(200,self.request('DELETE','/api/attendance/'+r['id'],{'version':2})[0])
        self.assertEqual(0,self.request('GET','/api/attendance')[2]['total'])
        conn=core.connect(self.db)
        try:
            self.assertEqual(1,conn.execute('SELECT archived FROM attendance_records').fetchone()[0])
            self.assertEqual(3,conn.execute("SELECT COUNT(*) FROM audit_logs WHERE entity_type='attendance_records'").fetchone()[0])
        finally:conn.close()

    def test_student_reads_only_own_full_profile_and_cannot_edit(self):
        own=self.athlete(status='Đang tập');other=self.athlete('ATT-002')
        r=self.record(own)[2];self.record(other)
        self.viewer_login(own['id'])
        status,_,data=self.request('GET','/api/student/athletes/'+own['id'])
        self.assertEqual(200,status,data);self.assertEqual('Đang tập',data['athlete']['status'])
        self.assertEqual('2015-02-03',data['athlete']['date_of_birth'])
        self.assertEqual(1,data['attendance']['summary']['present'])
        self.assertNotIn('created_by',data['attendance']['items'][0])
        self.assertEqual(403,self.request('GET','/api/athletes/'+other['id']+'/attendance')[0])
        for method,path,payload in [('GET','/api/attendance',None),('GET','/api/attendance/'+r['id'],None),('PATCH','/api/attendance/'+r['id'],{'version':1,'status':'present'}),('DELETE','/api/attendance/'+r['id'],{'version':1})]:
            self.assertEqual(403,self.request(method,path,payload)[0])
        self.assertEqual(403,self.record(own)[0])

    def test_coach_can_record_only_assigned_athletes_and_update_training_status(self):
        own=self.athlete();other=self.athlete('ATT-002');other_record=self.record(other)[2]
        self.request('POST','/api/users',{'username':'coach-att','password':'Coach-Test!2026','role':'coach','athlete_ids':[own['id']]})
        _,headers,session=self.request('POST','/api/login',{'username':'coach-att','password':'Coach-Test!2026'},auth=False,csrf=False)
        self.cookie=headers['set-cookie'].split(';')[0];self.csrf=session['csrf']
        self.assertEqual(200,self.record(own)[0]);self.assertEqual(403,self.record(other)[0])
        self.assertEqual(403,self.request('PATCH','/api/attendance/'+other_record['id'],{'version':1,'status':'present'})[0])
        self.assertEqual([own['id']],[r['athlete_id'] for r in self.request('GET','/api/attendance')[2]['items']])
        self.assertEqual(200,self.request('PATCH','/api/athletes/'+own['id'],{'version':own['version'],'status':'Tạm nghỉ'})[0])

    def test_branch_transfer_preserves_recorded_branch_and_history(self):
        _,_,b1=self.request('POST','/api/branches',{'name':'Cơ sở cũ'})
        _,_,b2=self.request('POST','/api/branches',{'name':'Cơ sở mới'})
        a=self.athlete(current_branch_id=b1['id']);r=self.record(a,branch_id=b1['id'])[2]
        self.request('PATCH','/api/athletes/'+a['id'],{'version':a['version'],'current_branch_id':b2['id']})
        self.request('PATCH','/api/branches/'+b1['id'],{'version':b1['version'],'name':'Tên cơ sở đã đổi'})
        status,_,data=self.request('PATCH','/api/attendance/'+r['id'],{'version':r['version'],'note':'Đã sửa ghi chú'})
        self.assertEqual(200,status,data);self.assertEqual('Cơ sở cũ',data['branch_name_snapshot'])
        self.assertEqual(1,self.request('GET','/api/athletes/'+a['id']+'/attendance')[2]['total'])

    def test_invalid_dates_statuses_future_and_identity_changes_rejected(self):
        a=self.athlete();other=self.athlete('ATT-002')
        for extra in ({'session_date':'2025-02-30'},{'session_date':'2099-01-01'},{'start_time':'25:90'},{'status':'unknown'},{'class_name':''},{'note':'x'*1001},{'branch_id':'unknown'}):
            self.assertEqual(422,self.record(a,**extra)[0])
        r=self.record(a)[2]
        self.assertEqual(422,self.request('PATCH','/api/attendance/'+r['id'],{'version':1,'athlete_id':other['id']})[0])
        for path in ('/api/attendance','/api/athletes/'+a['id']+'/attendance','/api/student/athletes/'+a['id']):
            self.assertEqual(401,self.request('GET',path,auth=False)[0])
