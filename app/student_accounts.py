"""Issue a scoped account and expose only the signed-in athlete's allowed records."""
import secrets
from .core import AppError, Service, create_user, audit, safe_user


def issue_account(conn, user, athlete_id, payload):
    svc=Service(conn,user); svc.require_admin()
    athlete=svc.scope_athlete(athlete_id)
    if payload.get('version')!=athlete['version']:
        raise AppError(409,'Hồ sơ đã thay đổi. Hãy tải lại trước khi cấp tài khoản.')
    code=athlete.get('official_code')
    if athlete['archived'] or athlete['identity_verification_status']!='verified' or not code or code.upper().startswith('TAM-'):
        raise AppError(422,'Cần nhận diện võ sinh và mã chính thức trước khi cấp tài khoản.')
    if conn.execute('SELECT 1 FROM users WHERE login_athlete_id=? OR username=?',(athlete_id,code)).fetchone():
        raise AppError(409,'Hồ sơ/mã này đã có tài khoản. Quản trị viên có thể đặt lại mật khẩu trong Tài khoản & quyền.')
    password=payload.get('password') or secrets.token_urlsafe(18)
    if not isinstance(password,str) or password.casefold()==code.casefold():
        raise AppError(422,'Mật khẩu tạm phải khác mã võ sinh.')
    account=create_user(conn,{'username':code,'password':password,'role':'viewer','athlete_ids':[athlete_id]})
    conn.execute('UPDATE users SET login_athlete_id=? WHERE id=?',(athlete_id,account['id']))
    account=safe_user(conn.execute('SELECT * FROM users WHERE id=?',(account['id'],)).fetchone())
    audit(conn,user['id'],'issue_student_account','users',account['id'],None,account)
    return {'account':account,'initial_password':password}


def student_profile(conn,user,athlete_id):
    if user['role']!='viewer': raise AppError(403,'Đây là trang hồ sơ dành cho tài khoản võ sinh.')
    profile=Service(conn,user).profile(athlete_id)
    athlete=profile['athlete']
    return {'athlete':{k:athlete.get(k) for k in ('id','full_name','official_code','branch_name','status')},
            'achievements':[student_result(r) for r in profile['achievements']],'medals':profile['medals'],
            'tournament_count':profile['tournament_count'],'achievement_count':len(profile['achievements'])}


def student_result(result):
    allowed={'id','tournament_id','tournament_name','year','event_name','discipline','participation_type',
             'medal_type','age_category','weight_category','belt_category','athletes','evidence_files','evidence_url','verification_status'}
    return {key:value for key,value in result.items() if key in allowed}
