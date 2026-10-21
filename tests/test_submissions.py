"""Actual WSGI paths for private, unverified parent contributions."""
import json
from pathlib import Path
import sys
import uuid
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from app import core
import test_http_security as http_security


class SubmissionTest(TestCase):
    setUp = http_security.HttpSecurityTest.setUp
    tearDown = http_security.HttpSecurityTest.tearDown
    request = http_security.HttpSecurityTest.request

    def claim(self, **overrides):
        return {'client_request_id':str(uuid.uuid4()),'athlete_name':'Võ sinh đề nghị thử',
            'athlete_code':'MA-DO-NGUOI-GUI-KHAI','public_athlete_id':'',
            'tournament_name':'Giải do phụ huynh cung cấp','year':2025,
            'event_name':'Quyền theo lời khai','discipline':'Quyền','participation_type':'Cá nhân',
            'medal_type':'HCV','evidence_url':'https://example.org/private-proof',
            'contact':'PRIVATE_CONTACT','notes':'PRIVATE_CLAIM','consent_to_review':True,'website':'',**overrides}

    def submit(self, data=None, **kwargs):
        return self.request('POST','/api/public/submissions',data or self.claim(),auth=False,csrf=False,**kwargs)

    def rows(self, sql, args=()):
        conn=core.connect(self.db)
        try: return [dict(r) for r in conn.execute(sql,args)]
        finally: conn.close()

    def records(self):
        _,_,a=self.request('POST','/api/athletes',{'full_name':'Võ sinh đã nhận diện','official_code':'TKD-CLAIM-001','identity_verification_status':'verified'})
        _,_,t=self.request('POST','/api/tournaments',{'tournament_name':'Giải đã đối chiếu','year':2025})
        return a['athlete'],t['tournament']

    def conversion(self, athlete, tournament, **overrides):
        return {'version':1,'action':'create','identity_checked':True,'duplicate_checked':True,
            'resolution_notes':'Đã đối chiếu người nhận; tạo nháp để xét minh chứng.',
            'achievement':{'tournament_id':tournament['id'],'event_name':'Quyền đã đối chiếu',
                'competition_year':2025,'discipline':'Quyền','participation_type':'Cá nhân',
                'medal_type':'HCV','athlete_ids':[athlete['id']],
                'evidence_url':'https://example.org/checked','publication_allowed':True,
                'verification_status':'verified','public_search_allowed':True},**overrides}

    def test_receive_durable_pending_does_not_create_athlete_or_medal(self):
        status,_,receipt=self.submit()
        self.assertEqual(200,status,receipt)
        self.assertEqual({'receipt_id','status','duplicate'},set(receipt))
        self.app=server.Application(self.db)
        status,_,record=self.request('GET','/api/submissions/'+receipt['receipt_id'])
        self.assertEqual(200,status); self.assertEqual('pending',record['status'])
        self.assertEqual('PRIVATE_CONTACT',record['data']['contact'])
        for table in ('achievements','athletes','athlete_achievements','verification_queue'):
            self.assertEqual(0,self.rows(f'SELECT COUNT(*) n FROM {table}')[0]['n'])
        self.assertEqual(0,self.request('GET','/api/public/summary',auth=False)[2]['achievement_count'])

    def test_retry_is_idempotent_and_different_payload_with_same_key_conflicts(self):
        claim=self.claim(); first=self.submit(claim)[2]
        second=self.submit(claim)[2]
        self.assertEqual(first['receipt_id'],second['receipt_id']); self.assertTrue(second['duplicate'])
        self.assertEqual(409,self.submit({**claim,'event_name':'Nội dung khác'})[0])
        self.assertEqual(1,len(self.rows('SELECT * FROM achievement_submissions')))

    def test_same_names_or_codes_are_untrusted_and_never_auto_linked(self):
        athlete,_=self.records()
        _,_,receipt=self.submit(self.claim(athlete_name=athlete['full_name'],athlete_code=athlete['official_code']))
        record=self.request('GET','/api/submissions/'+receipt['receipt_id'])[2]
        self.assertEqual('',record['data']['public_athlete_id'])
        self.assertIsNone(record['linked_achievement_id'])
        self.assertEqual(0,len(self.rows('SELECT * FROM athlete_achievements')))

    def test_private_or_nonexistent_reference_has_same_not_found(self):
        athlete,_=self.records()
        private=self.submit(self.claim(public_athlete_id=athlete['id']))
        missing=self.submit(self.claim(public_athlete_id='not-a-public-id'))
        self.assertEqual(404,private[0]); self.assertEqual(private[2],missing[2])
        self.assertEqual(0,len(self.rows('SELECT * FROM achievement_submissions')))

    def test_incomplete_claim_can_wait_for_review_without_medal_inference(self):
        status,_,r=self.submit(self.claim(medal_type='Chưa xác định',discipline='Chưa xác định',participation_type='Chưa xác định',evidence_url=''))
        self.assertEqual(200,status,r)
        data=self.request('GET','/api/submissions/'+r['receipt_id'])[2]['data']
        self.assertEqual('Chưa xác định',data['medal_type'])

    def test_bad_input_cannot_change_verification_and_body_limit_applies(self):
        for data in (self.claim(verification_status='verified'),self.claim(year=True),
                     self.claim(evidence_url='javascript:alert(1)'),self.claim(evidence_url='https://:secret@example.org'),self.claim(consent_to_review='true'),
                     self.claim(website='spam')):
            self.assertEqual(422,self.submit(data,remote=str(uuid.uuid4()))[0])
        self.assertEqual(413,self.submit(self.claim(notes='x'*17000))[0])
        self.assertEqual(422,self.request('POST','/api/public/submissions',raw=b'{}',auth=False,csrf=False)[0])
        self.assertEqual(0,len(self.rows('SELECT * FROM achievement_submissions')))

    def test_cross_site_and_public_listing_are_denied(self):
        self.assertEqual(403,self.submit(headers={'HTTP_ORIGIN':'https://evil.example'})[0])
        self.assertEqual(403,self.submit(headers={'HTTP_SEC_FETCH_SITE':'cross-site'})[0])
        self.assertEqual(405,self.request('GET','/api/public/submissions',auth=False)[0])
        _,_,r=self.submit()
        for path in ('/api/submissions','/api/submissions/'+r['receipt_id'], '/api/submissions/'+r['receipt_id']+'/convert'):
            self.assertEqual(401,self.request('GET',path,auth=False)[0])

    def test_rate_limit_is_separate_from_search_and_expires(self):
        for _ in range(5): self.assertEqual(200,self.submit()[0])
        self.assertEqual(429,self.submit()[0])
        self.assertEqual(200,self.request('GET','/api/public/summary',auth=False)[0])
        with patch('server.time.monotonic',return_value=10**12): self.assertEqual(200,self.submit()[0])

    def test_coach_cannot_read_or_review_parent_contact(self):
        _,_,r=self.submit()
        self.request('POST','/api/users',{'username':'coach-claims','password':'Coach-mat-khau-2026','role':'coach','can_verify':True})
        _,headers,login=self.request('POST','/api/login',{'username':'coach-claims','password':'Coach-mat-khau-2026'},auth=False,csrf=False)
        self.cookie=headers['set-cookie'].split(';')[0]; self.csrf=login['csrf']
        for method,path,payload in [('GET','/api/submissions',None),('GET','/api/submissions/'+r['receipt_id'],None),('PATCH','/api/submissions/'+r['receipt_id'],{'version':1,'status':'rejected','resolution_notes':'x'})]:
            self.assertEqual(403,self.request(method,path,payload)[0])

    def test_admin_conversion_creates_only_pending_private_result_and_preserves_source(self):
        athlete,tournament=self.records(); _,_,receipt=self.submit()
        status,_,r=self.request('POST','/api/submissions/'+receipt['receipt_id']+'/convert',self.conversion(athlete,tournament))
        self.assertEqual(200,status,r); self.assertEqual('converted',r['status'])
        result=self.request('GET','/api/achievements/'+r['linked_achievement_id'])[2]
        self.assertEqual('pending',result['verification_status'])
        self.assertEqual(0,result['publication_allowed']); self.assertEqual(0,result['public_search_allowed'])
        self.assertIn('PRIVATE_CLAIM',result['source_original_text'])
        self.assertNotIn('PRIVATE_CONTACT',result['source_original_text'])
        self.assertEqual([athlete['id']],[a['id'] for a in result['athletes']])
        self.assertEqual('pending',result['athletes'][0]['link_status'])
        self.assertEqual(0,self.request('GET','/api/public/summary',auth=False)[2]['achievement_count'])
        self.assertEqual(409,self.request('POST','/api/submissions/'+receipt['receipt_id']+'/convert',self.conversion(athlete,tournament))[0])
        self.assertEqual(1,len(self.rows('SELECT * FROM achievements')))

    def test_conversion_requires_manual_checks_and_rolls_back_invalid_links(self):
        athlete,tournament=self.records(); _,_,r=self.submit(); url='/api/submissions/'+r['receipt_id']+'/convert'
        self.assertEqual(422,self.request('POST',url,self.conversion(athlete,tournament,identity_checked=False))[0])
        data=self.conversion(athlete,tournament); data['achievement']['athlete_ids']=['unknown']
        self.assertEqual(404,self.request('POST',url,data)[0])
        self.assertEqual(0,len(self.rows('SELECT * FROM achievements')))
        self.assertEqual('pending',self.request('GET','/api/submissions/'+r['receipt_id'])[2]['status'])

    def test_link_existing_result_does_not_mutate_roster_or_status(self):
        athlete,tournament=self.records()
        _,_,result=self.request('POST','/api/achievements',self.conversion(athlete,tournament)['achievement'])
        _,_,receipt=self.submit(); url='/api/submissions/'+receipt['receipt_id']+'/convert'
        status,_,r=self.request('POST',url,{'version':1,'action':'link','achievement_id':result['id'],
            'identity_checked':True,'duplicate_checked':True,'resolution_notes':'Đã kiểm tra đây là kết quả hiện có.'})
        self.assertEqual(200,status,r)
        self.assertEqual(result,self.request('GET','/api/achievements/'+result['id'])[2])
        self.assertEqual(1,len(self.rows('SELECT * FROM achievements')))

    def test_review_has_csrf_immutable_claims_versions_and_audit(self):
        _,_,receipt=self.submit(); url='/api/submissions/'+receipt['receipt_id']
        payload={'version':1,'status':'reviewing','resolution_notes':'Cần đối chiếu minh chứng.'}
        self.assertEqual(403,self.request('PATCH',url,payload,csrf=False)[0])
        self.assertEqual(422,self.request('PATCH',url,{**payload,'data':{'athlete_name':'Sửa lời khai'}})[0])
        status,_,r=self.request('PATCH',url,payload)
        self.assertEqual(200,status,r); self.assertEqual(2,r['version'])
        self.assertEqual(409,self.request('PATCH',url,payload)[0])
        self.assertEqual(200,self.request('PATCH',url,{'version':2,'status':'rejected','resolution_notes':'Nguồn không đối chiếu được.'})[0])
        self.assertEqual(409,self.request('PATCH',url,{'version':3,'status':'pending','resolution_notes':'mở lại'})[0])
        self.assertEqual(3,len(self.rows('SELECT * FROM audit_logs WHERE entity_type=?',('achievement_submissions',))))

    def test_list_filter_pagination_and_literal_search(self):
        self.submit(self.claim(athlete_name='Tên một')); self.submit(self.claim(athlete_name='Tên hai'))
        data=self.request('GET','/api/submissions?limit=1')[2]
        self.assertEqual(2,data['total']); self.assertEqual(2,data['pages']); self.assertEqual(1,len(data['items']))
        self.assertEqual(0,self.request('GET','/api/submissions?q=%25')[2]['total'])
        self.assertEqual(2,self.request('GET','/api/submissions?status=pending')[2]['total'])
        self.assertEqual(422,self.request('GET','/api/submissions?status=verified')[0])

    def test_emoji_conflict_survives_conversion_and_blocks_verification(self):
        athlete,tournament=self.records(); _,_,r=self.submit(self.claim(notes='HCB 🥈 theo tài liệu gốc'))
        _,_,converted=self.request('POST','/api/submissions/'+r['receipt_id']+'/convert',self.conversion(athlete,tournament))
        result=self.request('GET','/api/achievements/'+converted['linked_achievement_id'])[2]
        self.assertTrue(result['source_conflict'])
        self.assertEqual(422,self.request('POST','/api/achievements/'+result['id']+'/verify',{
            'version':result['version'],'evidence_checked':True,'duplicate_checked':True,'note':'Không được tự chọn huy chương.'})[0])
