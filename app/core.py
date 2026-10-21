"""Domain services. Every operation is authorized here, independently of the UI."""
from __future__ import annotations
import hashlib
import hmac
import json
import secrets
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

MEDALS = ['HCV', 'HCB', 'HCĐ']
DISCIPLINES = ['Quyền', 'Đối kháng', 'Công phá', 'Biểu diễn', 'Khác', 'Chưa xác định']
PARTICIPATION_TYPES = ['Cá nhân', 'Đôi', 'Đồng đội', 'Chưa xác định']
ENTITY_TABLES = {'athletes':'athletes','tournaments':'tournaments','achievements':'achievements','branches':'branches','queue':'verification_queue','verification_queue':'verification_queue'}

class AppError(Exception):
    def __init__(self, status: int, message: str, details: Any = None):
        super().__init__(message)
        self.status, self.message, self.details = status, message, details

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def new_id() -> str:
    return str(uuid.uuid4())

def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=20000')
    conn.execute('PRAGMA journal_mode=WAL')
    return conn

def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))
    # Existing databases stay private. Viewer permissions never imply guest access.
    with conn:
        user_columns = {row['name'] for row in conn.execute('PRAGMA table_info(users)')}
        if 'must_change_password' not in user_columns:
            conn.execute('ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0 CHECK(must_change_password IN (0,1))')
            conn.execute("UPDATE users SET must_change_password=1 WHERE role='viewer'")
        if 'password_changed_at' not in user_columns:
            conn.execute('ALTER TABLE users ADD COLUMN password_changed_at TEXT')
        if 'login_athlete_id' not in user_columns:
            conn.execute('ALTER TABLE users ADD COLUMN login_athlete_id TEXT REFERENCES athletes(id)')
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_student_account ON users(login_athlete_id)')
        for table, columns in {
            'athletes': ('public_profile_allowed',),
            'achievements': ('public_search_allowed', 'public_evidence_allowed'),
            'evidence_files': ('public_access_allowed',),
        }.items():
            existing = {row['name'] for row in conn.execute(f'PRAGMA table_info({table})')}
            for column in columns:
                if column not in existing:
                    conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0 CHECK({column} IN (0,1))')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_athlete_public ON athletes(public_profile_allowed,identity_verification_status,archived)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_achievement_public ON achievements(public_search_allowed,verification_status,archived)')


def permission_value(value):
    if not isinstance(value, (bool, int)) or value not in (0, 1):
        raise AppError(422, 'Quyền hiển thị phải là true hoặc false.')
    return int(value)


def achievement_blockers(conn, achievement):
    a = dict(achievement); issues = []
    t = conn.execute('SELECT * FROM tournaments WHERE id=? AND archived=0', (a.get('tournament_id'),)).fetchone()
    if not t or not t['tournament_name'] or not t['year']: issues.append('Giải đấu chưa hợp lệ.')
    if t and a.get('competition_year') and int(a['competition_year']) != t['year']: issues.append('Năm thi đấu không khớp năm của giải.')
    if a.get('medal_type') not in MEDALS: issues.append('Chưa xác định loại huy chương.')
    if a.get('discipline') not in DISCIPLINES[:-1] or not a.get('event_name'): issues.append('Nội dung thi đấu chưa đủ rõ.')
    members = conn.execute('SELECT a.*,aa.link_status FROM athletes a JOIN athlete_achievements aa ON aa.athlete_id=a.id WHERE aa.achievement_id=?', (a['id'],)).fetchall()
    if not members: issues.append('Chưa gắn người nhận.')
    if any(m['identity_verification_status'] != 'verified' or not m['official_code'] or m['archived'] for m in members): issues.append('Người nhận chưa được xác thực danh tính/mã chính thức.')
    if a.get('participation_type') not in PARTICIPATION_TYPES[:-1]: issues.append('Chưa xác định hình thức thi đấu.')
    elif a['participation_type'] == 'Cá nhân' and len(members) != 1: issues.append('Cá nhân phải có đúng 1 võ sinh.')
    elif a['participation_type'] == 'Đôi' and len(members) != 2: issues.append('Nội dung đôi phải có đúng 2 võ sinh.')
    elif a['participation_type'] == 'Đồng đội':
        if not a.get('expected_members') or int(a['expected_members']) < 2 or len(members) != int(a['expected_members']) or not a.get('roster_confirmed'):
            issues.append('Đồng đội chưa xác nhận đủ thành viên theo danh sách chính thức.')
    if not a.get('evidence_url') and not conn.execute('SELECT 1 FROM evidence_files WHERE achievement_id=?', (a['id'],)).fetchone():
        issues.append('Thiếu minh chứng đối chiếu.')
    if a.get('source_conflict') and not a.get('conflict_resolution'): issues.append('Mâu thuẫn giữa emoji và chữ huy chương chưa được xử lý.')
    return issues

def hash_password(password: str) -> str:
    if not isinstance(password,str) or not 12 <= len(password) <= 256:
        raise AppError(422, 'Mật khẩu cần từ 12 đến 256 ký tự.')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600_000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'

def verify_password(password: str, encoded: str) -> bool:
    if not isinstance(password,str) or len(password)>256: return False
    try:
        _, rounds, salt, digest = encoded.split('$')
        candidate = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        return hmac.compare_digest(candidate,digest)
    except (ValueError,TypeError,AttributeError):
        return False

def audit(conn, actor, action, entity_type, entity_id, before=None, after=None):
    conn.execute('INSERT INTO audit_logs(actor,action,entity_type,entity_id,before_json,after_json,created_at) VALUES(?,?,?,?,?,?,?)',
        (actor,action,entity_type,entity_id,json.dumps(before,ensure_ascii=False,default=str) if before is not None else None,
         json.dumps(after,ensure_ascii=False,default=str) if after is not None else None,now()))

def safe_user(row):
    result = dict(row)
    result.pop('password_hash',None)
    return result

def create_user(conn,payload):
    role = payload.get('role','viewer')
    if role not in ['admin','coach','viewer']:
        raise AppError(422,'Vai trò không hợp lệ.')
    username = str(payload.get('username','')).strip()
    if not 3 <= len(username) <= 80:
        raise AppError(422,'Tên tài khoản phải từ 3 đến 80 ký tự.')
    if role=='viewer' and str(payload.get('password','')).casefold()==username.casefold():
        raise AppError(422,'Mật khẩu phải khác mã đăng nhập.')
    user_id = new_id()
    conn.execute('INSERT INTO users(id,username,password_hash,role,can_verify,created_at,must_change_password) VALUES(?,?,?,?,?,?,?)',
        (user_id,username,hash_password(payload.get('password','')),role,int(role=='admin' or (role=='coach' and bool(payload.get('can_verify')))),now(),int(role=='viewer')))
    for athlete_id in set(payload.get('athlete_ids',[])):
        conn.execute('INSERT INTO user_athletes VALUES(?,?)',(user_id,athlete_id))
    for branch_id in set(payload.get('branch_ids',[])):
        conn.execute('INSERT INTO user_branches VALUES(?,?)',(user_id,branch_id))
    return safe_user(conn.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone())

def url_valid(value):
    if not value:
        return True
    parsed=urlparse(str(value))
    return parsed.scheme in ('https','http') and bool(parsed.netloc) and not parsed.username

def clean_fields(payload, allowed):
    return {key:(value.strip() or None if isinstance(value,str) else value) for key,value in payload.items() if key in allowed}

FIELDS = {
 'athletes': {'legacy_athlete_id','official_code','full_name','date_of_birth','birth_year','current_branch_id','representative_team','status','identity_verification_status','notes'},
 'tournaments': {'legacy_tournament_id','tournament_name','year','start_date','end_date','competition_level','location','organizer','source_url','status','notes'},
 'achievements': {'legacy_achievement_id','tournament_id','discipline','participation_type','gender_category','event_name','age_category','weight_category','belt_category','medal_type','representative_branch','team_name','evidence_url','source_row','source_original_text','review_notes','competition_year','expected_members','roster_confirmed','publication_allowed','evidence_publication_allowed','conflict_resolution'},
 'branches': {'name','notes'},
 'verification_queue': {'tournament_id','original_name','medal_type','event_description','issue_type','reported_quantity','source_url','source_original_text','source_row','resolution_status','resolution_notes','linked_achievement_id'},
}

class Service:
    def __init__(self,conn: sqlite3.Connection,user: dict):
        self.conn,self.user=conn,user
        if not user:
            raise AppError(401,'Vui lòng đăng nhập.')
        if user.get('must_change_password'):
            raise AppError(403,'Cần đổi mật khẩu lần đầu trước khi mở hồ sơ.',{'code':'PASSWORD_CHANGE_REQUIRED'})

    @property
    def admin(self): return self.user['role']=='admin'
    @property
    def staff(self): return self.user['role'] in ('admin','coach')

    def require_admin(self):
        if not self.admin: raise AppError(403,'Chức năng dành cho quản trị viên.')

    def require_staff(self):
        if not self.staff: raise AppError(403,'Tài khoản chỉ có quyền xem hồ sơ được cấp.')

    def scope_athlete(self,athlete_id):
        row=self.conn.execute('SELECT * FROM athletes WHERE id=?',(athlete_id,)).fetchone()
        if not row: raise AppError(404,'Không tìm thấy hồ sơ.')
        if self.admin: return dict(row)
        explicit=self.conn.execute('SELECT 1 FROM user_athletes WHERE user_id=? AND athlete_id=?',(self.user['id'],athlete_id)).fetchone()
        branch=self.user['role']=='coach' and row['current_branch_id'] and self.conn.execute('SELECT 1 FROM user_branches WHERE user_id=? AND branch_id=?',(self.user['id'],row['current_branch_id'])).fetchone()
        if not (explicit or branch): raise AppError(403,'Hồ sơ nằm ngoài phạm vi được cấp quyền.')
        return dict(row)

    def athlete_scope_sql(self,alias='a'):
        if self.admin: return '1=1',[]
        clause=f'EXISTS(SELECT 1 FROM user_athletes ua WHERE ua.athlete_id={alias}.id AND ua.user_id=?)'
        params=[self.user['id']]
        if self.user['role']=='coach':
            clause+=f' OR EXISTS(SELECT 1 FROM user_branches ub WHERE ub.branch_id={alias}.current_branch_id AND ub.user_id=?)'
            params.append(self.user['id'])
        return '('+clause+')',params

    def achievement_scope(self,achievement_id,write=False):
        row=self.conn.execute('SELECT * FROM achievements WHERE id=?',(achievement_id,)).fetchone()
        if not row: raise AppError(404,'Không tìm thấy thành tích.')
        if self.admin: return dict(row)
        linked=self.conn.execute('SELECT athlete_id FROM athlete_achievements WHERE achievement_id=?',(achievement_id,)).fetchall()
        permitted=0
        for item in linked:
            try: self.scope_athlete(item[0]); permitted+=1
            except AppError: pass
        # A coach may not alter or read private data of a mixed-scope roster.
        if not permitted or (write and self.staff and permitted!=len(linked)):
            raise AppError(403,'Thành tích nằm ngoài phạm vi được cấp quyền.')
        if not self.staff:
            if write or row['verification_status']!='verified' or not row['publication_allowed'] or row['archived']:
                raise AppError(403,'Thành tích chưa được phép hiển thị.')
            verified_link=self.conn.execute("SELECT 1 FROM athlete_achievements aa JOIN user_athletes ua ON ua.athlete_id=aa.athlete_id WHERE aa.achievement_id=? AND aa.link_status='verified' AND ua.user_id=?",(achievement_id,self.user['id'])).fetchone()
            if not verified_link: raise AppError(403,'Liên kết hồ sơ chưa được xác minh.')
        return dict(row)

    def table(self,entity):
        if entity not in ENTITY_TABLES: raise AppError(404,'Không tìm thấy dữ liệu.')
        return ENTITY_TABLES[entity]

    def _raw(self,table,id):
        row=self.conn.execute(f'SELECT * FROM {table} WHERE id=?',(id,)).fetchone()
        if not row: raise AppError(404,'Không tìm thấy bản ghi.')
        return dict(row)

    def _authorize(self,table,id,write=False):
        if table=='athletes':
            if write: self.require_staff()
            return self.scope_athlete(id)
        if table=='achievements':
            if write: self.require_staff()
            return self.achievement_scope(id,write)
        if table in ('verification_queue','branches') and write:
            self.require_admin()
        elif table=='verification_queue': self.require_admin()
        elif table=='tournaments':
            self.require_staff()
            if write: self.require_admin()
            if not self.admin:
                scope,params=self.athlete_scope_sql('scope_a')
                exists=self.conn.execute(f'SELECT 1 FROM achievements ac JOIN athlete_achievements aa ON aa.achievement_id=ac.id JOIN athletes scope_a ON scope_a.id=aa.athlete_id WHERE ac.tournament_id=? AND {scope}',[id]+params).fetchone()
                if not exists: raise AppError(403,'Giải đấu nằm ngoài phạm vi được cấp quyền.')
        elif table=='branches': self.require_staff()
        return self._raw(table,id)

    def blockers(self,achievement):
        return achievement_blockers(self.conn, achievement)

    def _achievement(self,row):
        result=dict(row)
        t=self.conn.execute('SELECT tournament_name,year FROM tournaments WHERE id=?',(result['tournament_id'],)).fetchone()
        result.update(dict(t) if t else {})
        rows=self.conn.execute('SELECT a.id,a.full_name,a.official_code,a.identity_verification_status,aa.link_status FROM athletes a JOIN athlete_achievements aa ON aa.athlete_id=a.id WHERE aa.achievement_id=? ORDER BY a.full_name',(result['id'],)).fetchall()
        mixed_scope=False
        if self.user['role']=='coach':
            permitted_rows=[]
            for x in rows:
                try: self.scope_athlete(x['id']); permitted_rows.append(x)
                except AppError: mixed_scope=True
            rows=permitted_rows
        if not self.staff:
            # Teammates' personal information is not disclosed to viewer accounts.
            rows=[x for x in rows if self.conn.execute('SELECT 1 FROM user_athletes WHERE user_id=? AND athlete_id=?',(self.user['id'],x['id'])).fetchone()]
        result['athletes']=[dict(x) for x in rows]
        result['evidence_files']=[dict(x) for x in self.conn.execute('SELECT id,filename,mime_type,publication_allowed,public_access_allowed FROM evidence_files WHERE achievement_id=?'+('' if self.staff else ' AND publication_allowed=1'),(result['id'],))]
        if self.staff:
            result['blockers']=self.blockers(result)
            result['source_records']=[dict(x) for x in self.conn.execute("SELECT sheet,excel_row,original_json FROM source_records WHERE entity_id=? AND entity_type IN ('achievements','achievement')",(result['id'],))]
            if mixed_scope:
                for key in ['source_original_text','review_notes','evidence_url','conflict_resolution','legacy_achievement_id','source_row']:
                    result[key]=None
                result['source_records']=[]; result['evidence_files']=[]
                result['scope_limited']=True
        else:
            keep={'id','tournament_id','tournament_name','year','discipline','participation_type','gender_category','event_name','age_category','weight_category','belt_category','medal_type','representative_branch','team_name','verification_status','athletes','evidence_files','publication_allowed'}
            if result.get('evidence_publication_allowed'): keep.add('evidence_url')
            result={k:v for k,v in result.items() if k in keep}
        return result

    def detail(self,entity,id):
        table=self.table(entity); row=self._authorize(table,id)
        if table=='achievements': return self._achievement(row)
        if table=='athletes': return self.profile(id)
        if table=='tournaments':
            records=self.list('achievements',{'tournament_id':id,'_all':True})['items']
            athlete_ids={m['id'] for a in records for m in a['athletes']}
            medals={m:sum(a['medal_type']==m and a['verification_status']=='verified' for a in records) for m in MEDALS}
            queue=[dict(x) for x in self.conn.execute('SELECT * FROM verification_queue WHERE tournament_id=? AND archived=0',(id,))] if self.admin else []
            if not self.admin:
                row['source_url']=None; row['notes']=None
            return {'tournament':row,'achievements':records,'queue':queue,'athletes':[self.scope_athlete(a) for a in athlete_ids],'club_medals':medals}
        return row

    def profile(self,athlete_id):
        athlete=self.scope_athlete(athlete_id)
        branch=self.conn.execute('SELECT name FROM branches WHERE id=?',(athlete.get('current_branch_id'),)).fetchone()
        athlete['branch_name']=branch[0] if branch else None
        if not self.staff:
            athlete.pop('date_of_birth',None); athlete.pop('notes',None); athlete.pop('legacy_athlete_id',None)
        rows=self.conn.execute('SELECT ac.* FROM achievements ac JOIN athlete_achievements aa ON aa.achievement_id=ac.id JOIN tournaments t ON t.id=ac.tournament_id WHERE aa.athlete_id=? AND ac.archived=0'+('' if self.staff else " AND ac.verification_status='verified' AND ac.publication_allowed=1 AND aa.link_status='verified'")+ ' ORDER BY t.year DESC,ac.id',(athlete_id,)).fetchall()
        results=[]
        for r in rows:
            try: self.achievement_scope(r['id']); results.append(self._achievement(r))
            except AppError: pass
        official=[a for a in results if a['verification_status']=='verified']
        return {'athlete':athlete,'achievements':results,'medals':{m:sum(a['medal_type']==m for a in official) for m in MEDALS},'tournament_count':len({a['tournament_id'] for a in official})}

    def list(self,entity,filters=None):
        filters=filters or {}; table=self.table(entity)
        if table=='verification_queue': self.require_admin()
        if table=='tournaments': self.require_staff()
        if table=='branches': self.require_staff()
        clause=['a.archived=0']; params=[]
        if table=='athletes':
            scoped,p=self.athlete_scope_sql(); clause.append(scoped); params+=p
            search=['full_name','official_code','legacy_athlete_id']
            if filters.get('status'): clause.append('a.identity_verification_status=?'); params.append(filters['status'])
            if filters.get('branch_id'): clause.append('a.current_branch_id=?'); params.append(filters['branch_id'])
        elif table=='achievements':
            search=['event_name','legacy_achievement_id','source_original_text'] if self.admin else ['event_name']
            if not self.admin:
                # Scope results via service authorization after SQL; all mixed rosters excluded for staff.
                scoped,p=self.athlete_scope_sql('scope_a')
                clause.append(f'EXISTS(SELECT 1 FROM athlete_achievements aa JOIN athletes scope_a ON scope_a.id=aa.athlete_id WHERE aa.achievement_id=a.id AND {scoped})'); params+=p
            for key,column in [('status','verification_status'),('medal','medal_type'),('participation_type','participation_type'),('tournament_id','tournament_id'),('discipline','discipline'),('representative_branch','representative_branch')]:
                if filters.get(key): clause.append(f'a.{column}=?'); params.append(filters[key])
            if filters.get('year'): clause.append('a.tournament_id IN (SELECT id FROM tournaments WHERE year=?)'); params.append(filters['year'])
            if not self.staff: clause.append("a.verification_status='verified' AND a.publication_allowed=1")
        elif table=='tournaments':
            search=['tournament_name','legacy_tournament_id']
            if filters.get('year'): clause.append('a.year=?'); params.append(filters['year'])
            if not self.admin:
                scoped,p=self.athlete_scope_sql('scope_a')
                clause.append(f'EXISTS(SELECT 1 FROM achievements ac JOIN athlete_achievements aa ON aa.achievement_id=ac.id JOIN athletes scope_a ON scope_a.id=aa.athlete_id WHERE ac.tournament_id=a.id AND {scoped})'); params+=p
        elif table=='verification_queue':
            search=['original_name','event_description','source_original_text','issue_type']
            for key,column in [('status','resolution_status'),('issue_type','issue_type')]:
                if filters.get(key): clause.append(f'a.{column}=?'); params.append(filters[key])
        else: search=['name']
        if filters.get('q'):
            clause.append('('+' OR '.join(f'a.{c} LIKE ?' for c in search)+')'); params+=['%'+str(filters['q'])+'%']*len(search)
        rows=[dict(x) for x in self.conn.execute(f'SELECT a.* FROM {table} a WHERE '+ ' AND '.join(clause)+' ORDER BY '+('a.year DESC,a.tournament_name' if table=='tournaments' else 'a.full_name' if table=='athletes' else 'a.rowid DESC'),params)]
        if table=='achievements':
            permitted=[]
            for r in rows:
                try: self.achievement_scope(r['id']); permitted.append(r)
                except AppError: pass
            rows=permitted
        try: page=max(1,int(filters.get('page',1))); limit=max(1,min(1000,int(filters.get('limit',20))))
        except (ValueError,TypeError): raise AppError(422,'Phân trang không hợp lệ.')
        total=len(rows); pages=max(1,(total+limit-1)//limit); page=min(page,pages)
        if filters.get('_all') is not True: rows=rows[(page-1)*limit:page*limit]
        if table=='achievements': rows=[self._achievement(r) for r in rows]
        elif table=='athletes':
            for r in rows:
                branch=self.conn.execute('SELECT name FROM branches WHERE id=?',(r['current_branch_id'],)).fetchone(); r['branch_name']=branch[0] if branch else None
                official=self.conn.execute("SELECT COUNT(*) FROM achievements ac JOIN athlete_achievements aa ON aa.achievement_id=ac.id WHERE aa.athlete_id=? AND ac.archived=0 AND ac.verification_status='verified'"+('' if self.staff else " AND ac.publication_allowed=1 AND aa.link_status='verified'"),(r['id'],)).fetchone()[0]
                r['medal_count']=official
                r['draft_count']=self.conn.execute("SELECT COUNT(*) FROM achievements ac JOIN athlete_achievements aa ON aa.achievement_id=ac.id WHERE aa.athlete_id=? AND ac.archived=0 AND ac.verification_status!='verified'",(r['id'],)).fetchone()[0] if self.staff else 0
                if not self.staff:
                    for k in ['date_of_birth','notes','legacy_athlete_id']: r.pop(k,None)
        elif table=='tournaments':
            for r in rows:
                if self.admin:
                    counts=self.conn.execute("SELECT verification_status,COUNT(*) n FROM achievements WHERE tournament_id=? AND archived=0 GROUP BY verification_status",(r['id'],)).fetchall()
                    r['verified_count']=sum(x['n'] for x in counts if x['verification_status']=='verified'); r['pending_count']=sum(x['n'] for x in counts if x['verification_status']!='verified')
                else:
                    scoped_records=self.list('achievements',{'tournament_id':r['id'],'_all':True})['items']
                    r['verified_count']=sum(x['verification_status']=='verified' for x in scoped_records); r['pending_count']=len(scoped_records)-r['verified_count']
                    r['source_url']=None; r['notes']=None
        return {'items':rows,'total':total,'page':page,'pages':pages}

    def _validate(self,table,data,existing=None):
        combined={**(existing or {}),**data}
        if table=='athletes':
            if not combined.get('full_name'): raise AppError(422,'Cần nhập họ tên võ sinh.')
            if combined.get('identity_verification_status') not in (None,'pending','verified'): raise AppError(422,'Trạng thái danh tính không hợp lệ.')
            if combined.get('identity_verification_status')=='verified':
                if not existing or any(k in data and data[k]!=existing.get(k) for k in ('identity_verification_status','official_code','full_name','date_of_birth','birth_year')):
                    self.require_admin()
                if not combined.get('official_code') or str(combined['official_code']).upper().startswith('TAM-'): raise AppError(422,'Xác thực danh tính cần mã chính thức, không dùng mã tạm.')
            if combined.get('date_of_birth'):
                try: dob=date.fromisoformat(combined['date_of_birth'])
                except (ValueError,TypeError): raise AppError(422,'Ngày sinh không hợp lệ.')
                if dob>date.today(): raise AppError(422,'Ngày sinh không thể ở tương lai.')
                data['birth_year']=dob.year
            elif 'date_of_birth' in data and 'birth_year' not in data: data['birth_year']=None
            if data.get('birth_year') is not None:
                try: year=int(data['birth_year']); assert 1900<=year<=date.today().year
                except (ValueError,TypeError,AssertionError): raise AppError(422,'Năm sinh không hợp lệ.')
                data['birth_year']=year
        if table=='tournaments':
            if not combined.get('tournament_name'): raise AppError(422,'Cần tên giải đấu.')
            try: year=int(combined.get('year',0)); assert 1900<=year<=2200
            except (ValueError,TypeError,AssertionError): raise AppError(422,'Năm giải đấu không hợp lệ.')
            if 'year' in data: data['year']=year
            for key in ['start_date','end_date']:
                if combined.get(key):
                    try: parsed=date.fromisoformat(combined[key]); assert parsed.year==year
                    except (ValueError,TypeError,AssertionError): raise AppError(422,'Ngày thi đấu không khớp năm của giải.')
            if combined.get('start_date') and combined.get('end_date') and combined['end_date']<combined['start_date']: raise AppError(422,'Ngày kết thúc trước ngày bắt đầu.')
        if table=='achievements':
            for key in ['tournament_id','event_name','medal_type','discipline','participation_type']:
                if not combined.get(key): raise AppError(422,f'Thiếu trường bắt buộc: {key}.')
            if combined['medal_type'] not in MEDALS or combined['discipline'] not in DISCIPLINES or combined['participation_type'] not in PARTICIPATION_TYPES:
                raise AppError(422,'Giá trị danh mục không hợp lệ.')
            if combined.get('expected_members') is not None:
                try: count=int(combined['expected_members']); assert 1<=count<=100
                except (ValueError,TypeError,AssertionError): raise AppError(422,'Số thành viên dự kiến không hợp lệ.')
                if 'expected_members' in data: data['expected_members']=count
            for k in ('publication_allowed','roster_confirmed','evidence_publication_allowed'):
                if k in data: data[k]=int(bool(data[k]))
            if not self.admin and (data.get('publication_allowed') or data.get('evidence_publication_allowed')): raise AppError(403,'Chỉ quản trị viên được cấp quyền hiển thị.')
            from app.importer import _medal_conflict
            data['source_conflict']=int(bool((existing or {}).get('source_conflict')) or _medal_conflict(combined.get('source_original_text'),combined.get('medal_type')))
        if table=='verification_queue' and not existing:
            if combined.get('resolution_status') not in (None,'unresolved','reviewing'):
                raise AppError(422,'Mục mới phải bắt đầu ở trạng thái chưa xử lý hoặc đang đối chiếu.')
        if table=='branches' and not combined.get('name'): raise AppError(422,'Cần tên cơ sở.')
        for key in ['evidence_url','source_url']:
            if not url_valid(combined.get(key)): raise AppError(422,'Liên kết phải dùng http hoặc https hợp lệ.')
        return data

    def _links(self,achievement_id,ids):
        if not isinstance(ids,list) or not ids: raise AppError(422,'Cần chọn ít nhất một võ sinh.')
        if len(set(ids))!=len(ids): raise AppError(422,'Trùng cặp võ sinh–thành tích.')
        for id in ids:
            row=self.scope_athlete(id)
            if row['archived']: raise AppError(422,'Võ sinh đã được lưu trữ.')
        self.conn.execute('DELETE FROM athlete_achievements WHERE achievement_id=?',(achievement_id,))
        self.conn.executemany("INSERT INTO athlete_achievements(achievement_id,athlete_id,link_status) VALUES(?,?,'pending')",[(achievement_id,id) for id in ids])

    def create(self,entity,payload):
        self.require_staff(); table=self.table(entity)
        if table!='achievements': self.require_admin()
        data=self._validate(table,clean_fields(payload,FIELDS[table])); id=new_id()
        if table=='achievements': data.update(verification_status='pending',created_by=self.user['id'])
        columns=['id']+list(data)
        self.conn.execute(f'INSERT INTO {table}('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',[id]+list(data.values()))
        if table=='achievements': self._links(id,payload.get('athlete_ids',[]))
        audit(self.conn,self.user['id'],'create',table,id,None,self._raw(table,id))
        return self.detail(entity,id)

    def update(self,entity,id,payload):
        table=self.table(entity); before=self._authorize(table,id,True)
        if table=='athletes' and not self.admin:
            # Coaches propose corrections via review notes, no identity or branch reassignment.
            if set(payload)-{'version','notes','representative_team','status'}: raise AppError(403,'Cập nhật danh tính/cơ sở cần quản trị viên.')
        version=payload.get('version')
        if version!=before['version']: raise AppError(409,'Dữ liệu đã thay đổi. Hãy tải lại trước khi lưu.')
        data=self._validate(table,clean_fields(payload,FIELDS[table]),before)
        if table=='achievements': data.update(verification_status='pending',verified_by=None,verified_at=None,public_search_allowed=0,public_evidence_allowed=0)
        if table=='athletes' and any(k in data and data[k]!=before.get(k) for k in ['full_name','official_code','identity_verification_status','date_of_birth']):
            data['public_profile_allowed']=0
        if table=='verification_queue':
            state=data.get('resolution_status',before['resolution_status'])
            if state not in ('unresolved','reviewing','resolved','dismissed'): raise AppError(422,'Trạng thái xử lý không hợp lệ.')
            if state in ('resolved','dismissed') and not (data.get('resolution_notes') or before.get('resolution_notes')): raise AppError(422,'Cần ghi rõ căn cứ/lý do xử lý.')
            if state=='resolved':
                target=data.get('linked_achievement_id',before.get('linked_achievement_id'))
                linked=self._raw('achievements',target) if target else None
                if not linked or linked['verification_status']!='verified' or linked['tournament_id']!=data.get('tournament_id',before.get('tournament_id')): raise AppError(422,'Chỉ hoàn tất khi liên kết thành tích đã xác minh cùng giải.')
            data.update(reviewed_by=self.user['id'],reviewed_at=now())
        assignments=[f'{k}=?' for k in data]+['version=version+1']
        changed=self.conn.execute(f'UPDATE {table} SET '+','.join(assignments)+' WHERE id=? AND version=?',list(data.values())+[id,version]).rowcount
        if changed!=1: raise AppError(409,'Xung đột chỉnh sửa. Hãy tải lại.')
        if table=='achievements':
            if 'athlete_ids' in payload: self._links(id,payload['athlete_ids'])
            else: self.conn.execute("UPDATE athlete_achievements SET link_status='pending' WHERE achievement_id=?",(id,))
        # Identity changes suspend associated official results until reviewed again.
        if table=='athletes' and any(k in data and data[k]!=before.get(k) for k in ['full_name','official_code','identity_verification_status','date_of_birth']):
            ids=[x[0] for x in self.conn.execute("SELECT ac.id FROM achievements ac JOIN athlete_achievements aa ON aa.achievement_id=ac.id WHERE aa.athlete_id=? AND ac.verification_status='verified'",(id,))]
            for ac_id in ids:
                old=self._raw('achievements',ac_id)
                self.conn.execute("UPDATE achievements SET verification_status='pending',verified_by=NULL,verified_at=NULL,public_search_allowed=0,public_evidence_allowed=0,version=version+1 WHERE id=?",(ac_id,))
                self.conn.execute("UPDATE athlete_achievements SET link_status='pending' WHERE achievement_id=?",(ac_id,))
                audit(self.conn,self.user['id'],'identity_changed','achievements',ac_id,old,self._raw('achievements',ac_id))
        if table=='tournaments' and any(k in data and data[k]!=before.get(k) for k in ['year','tournament_name','source_url']):
            for ac in self.conn.execute("SELECT * FROM achievements WHERE tournament_id=? AND verification_status='verified'",(id,)).fetchall():
                self.conn.execute("UPDATE achievements SET verification_status='pending',verified_by=NULL,verified_at=NULL,public_search_allowed=0,public_evidence_allowed=0,version=version+1 WHERE id=?",(ac['id'],))
                self.conn.execute("UPDATE athlete_achievements SET link_status='pending' WHERE achievement_id=?",(ac['id'],))
                audit(self.conn,self.user['id'],'tournament_changed','achievements',ac['id'],dict(ac),self._raw('achievements',ac['id']))
        audit(self.conn,self.user['id'],'update',table,id,before,self._raw(table,id))
        return self.detail(entity,id)

    def set_publication(self, entity, id, payload):
        self.require_admin()
        if entity not in ('athletes', 'achievements'):
            raise AppError(404, 'Không tìm thấy chức năng công bố.')
        before = self._raw(entity, id)
        if payload.get('version') != before['version']:
            raise AppError(409, 'Dữ liệu đã thay đổi. Hãy tải lại trước khi công bố.')
        keys = ('public_profile_allowed',) if entity == 'athletes' else ('public_search_allowed', 'public_evidence_allowed')
        data = {key: permission_value(payload[key]) for key in keys if key in payload}
        if not data: raise AppError(422, 'Chưa chọn quyền công bố cần cập nhật.')
        if entity == 'achievements' and data.get('public_search_allowed') == 0:
            data['public_evidence_allowed'] = 0
        combined = {**before, **data}
        if entity == 'athletes' and combined['public_profile_allowed']:
            if before['archived'] or before['identity_verification_status'] != 'verified' or not before['official_code'] or before['official_code'].upper().startswith('TAM-'):
                raise AppError(422, 'Cần xác thực danh tính và mã chính thức trước khi cho khách tra cứu.')
        if entity == 'achievements' and (combined['public_search_allowed'] or combined['public_evidence_allowed']):
            issues = self.blockers(before)
            if before['archived'] or before['verification_status'] != 'verified' or not before['publication_allowed']:
                issues.append('Kết quả phải được xác minh và được phép hiển thị.')
            if self.conn.execute("SELECT 1 FROM athlete_achievements WHERE achievement_id=? AND link_status!='verified'", (id,)).fetchone():
                issues.append('Liên kết võ sinh chưa được xác minh đầy đủ.')
            if combined['public_evidence_allowed'] and (not combined['public_search_allowed'] or not before['evidence_publication_allowed']):
                issues.append('Công bố URL minh chứng cần bật công bố kết quả và quyền mở URL cho người xem.')
            if issues: raise AppError(422, 'Chưa đủ điều kiện công bố.', issues)
        if entity == 'achievements' and not combined['public_search_allowed']:
            data['public_evidence_allowed'] = 0
        changed = self.conn.execute(f'UPDATE {entity} SET ' + ','.join(f'{key}=?' for key in data) + ',version=version+1 WHERE id=? AND version=?', [*data.values(), id, before['version']]).rowcount
        if changed != 1: raise AppError(409, 'Xung đột chỉnh sửa. Hãy tải lại.')
        audit(self.conn, self.user['id'], 'public_visibility', entity, id,
              {key: before[key] for key in keys}, {key: self._raw(entity, id)[key] for key in keys})
        return self.detail(entity, id)

    def archive(self,entity,id,payload):
        self.require_admin(); table=self.table(entity); row=self._raw(table,id)
        if payload.get('version')!=row['version']: raise AppError(409,'Dữ liệu đã thay đổi. Hãy tải lại.')
        if table=='tournaments' and self.conn.execute('SELECT 1 FROM achievements WHERE tournament_id=? AND archived=0',(id,)).fetchone(): raise AppError(422,'Giải có thành tích; cần giữ lịch sử và chỉ chỉnh trạng thái giải.')
        if table=='athletes' and self.conn.execute('SELECT 1 FROM athlete_achievements WHERE athlete_id=?',(id,)).fetchone(): raise AppError(422,'Hồ sơ có lịch sử; hãy đổi trạng thái tập luyện.')
        if table=='branches' and self.conn.execute('SELECT 1 FROM athletes WHERE current_branch_id=?',(id,)).fetchone(): raise AppError(422,'Cơ sở còn võ sinh, cần chuyển cơ sở trước.')
        self.conn.execute(f'UPDATE {table} SET archived=1,version=version+1 WHERE id=? AND version=?',(id,row['version']))
        audit(self.conn,self.user['id'],'archive',table,id,row,self._raw(table,id))
        return {'ok':True}

    def verify(self,id,payload):
        self.require_staff()
        if not (self.admin or self.user.get('can_verify')): raise AppError(403,'Tài khoản không có quyền xác minh.')
        before=self.achievement_scope(id,True)
        if before['archived']: raise AppError(422,'Không thể duyệt bản ghi đã lưu trữ.')
        if payload.get('version')!=before['version']: raise AppError(409,'Dữ liệu đã thay đổi. Hãy tải lại.')
        blockers=self.blockers(before)
        if not payload.get('evidence_checked'): blockers.append('Cần xác nhận đã đối chiếu minh chứng.')
        if not payload.get('duplicate_checked'): blockers.append('Cần xác nhận đã kiểm tra trùng/liên kết.')
        if not payload.get('note'): blockers.append('Cần ghi căn cứ xác minh.')
        if blockers: raise AppError(422,'Chưa đủ điều kiện xác minh.',blockers)
        changed=self.conn.execute("UPDATE achievements SET verification_status='verified',verified_by=?,verified_at=?,review_notes=?,version=version+1 WHERE id=? AND version=?",(self.user['id'],now(),payload['note'],id,before['version'])).rowcount
        if changed!=1: raise AppError(409,'Xung đột xác minh. Hãy tải lại.')
        self.conn.execute("UPDATE athlete_achievements SET link_status='verified' WHERE achievement_id=?",(id,))
        audit(self.conn,self.user['id'],'verify','achievements',id,before,self._raw('achievements',id))
        return self._achievement(self._raw('achievements',id))

    def return_achievement(self,id,payload):
        self.require_staff()
        if not (self.admin or self.user.get('can_verify')): raise AppError(403,'Tài khoản không có quyền xác minh.')
        before=self.achievement_scope(id,True)
        if payload.get('version')!=before['version']: raise AppError(409,'Dữ liệu đã thay đổi. Hãy tải lại.')
        if not str(payload.get('note','')).strip(): raise AppError(422,'Cần ghi lý do trả lại.')
        self.conn.execute("UPDATE achievements SET verification_status='returned',verified_by=NULL,verified_at=NULL,public_search_allowed=0,public_evidence_allowed=0,review_notes=?,version=version+1 WHERE id=? AND version=?",(payload['note'],id,before['version']))
        self.conn.execute("UPDATE athlete_achievements SET link_status='pending' WHERE achievement_id=?",(id,))
        audit(self.conn,self.user['id'],'return','achievements',id,before,self._raw('achievements',id))
        return self._achievement(self._raw('achievements',id))

    def dashboard(self,filters=None):
        self.require_staff(); filters=filters or {}
        rows=self.list('achievements',{**filters,'_all':True})['items']
        official=[r for r in rows if r['verification_status']=='verified']
        pending=[r for r in rows if r['verification_status']!='verified']
        scoped,p=self.athlete_scope_sql()
        athletes=self.conn.execute('SELECT COUNT(*),SUM(identity_verification_status=\'verified\') FROM athletes a WHERE archived=0 AND '+scoped,p).fetchone()
        years=sorted({r['year'] for r in rows},reverse=True)
        issue_count={}
        for r in rows:
            for issue in r['blockers']: issue_count[issue]=issue_count.get(issue,0)+1
            if r['verification_status']=='verified' and not r['publication_allowed']:
                issue='Đã xác minh nhưng chưa được cấp quyền hiển thị.'; issue_count[issue]=issue_count.get(issue,0)+1
        return {'athletes':athletes[0],'verified_athletes':athletes[1] or 0,'tournaments':self.list('tournaments',{'limit':1000})['total'],
            'verified':len(official),'pending':len(pending),'queue':self.conn.execute("SELECT COUNT(*) FROM verification_queue WHERE archived=0 AND resolution_status IN ('unresolved','reviewing')").fetchone()[0] if self.admin else 0,
            'club_medals':{m:sum(r['medal_type']==m for r in official) for m in MEDALS},'athlete_medal_credits':sum(len(r['athletes']) for r in official),
            'years':[{'year':year,'verified':sum(r['year']==year for r in official),'pending':sum(r['year']==year for r in pending)} for year in years],
            'recent':sorted(rows,key=lambda r:(r.get('year') or 0,r.get('source_row') or ''),reverse=True)[:5],
            'issues':[{'code':str(i),'message':message,'count':count} for i,(message,count) in enumerate(sorted(issue_count.items(),key=lambda x:-x[1]))]}

    def reports(self,filters=None):
        self.require_staff(); filters=filters or {}
        rows=self.list('achievements',{**filters,'_all':True})['items']
        output={}
        dimensions={'year':lambda a:[str(a.get('year') or 'Chưa xác định')],
            'tournament':lambda a:[a['tournament_name']],
            'representative_branch':lambda a:[a.get('representative_branch') or 'Chưa cập nhật'],
            'discipline':lambda a:[a.get('discipline') or 'Chưa xác định'],
            'athlete':lambda a:[m['full_name']+' · '+(m.get('official_code') or m['id'][:8]) for m in a['athletes']]}
        for dimension,keys in dimensions.items():
            groups={}
            for a in rows:
                for key in keys(a):
                    g=groups.setdefault(key,{'label':key,'verified':0,'pending':0,'HCV':0,'HCB':0,'HCĐ':0,'athlete_medal_credits':0})
                    if a['verification_status']=='verified':
                        g['verified']+=1
                        if a['medal_type'] in MEDALS: g[a['medal_type']]+=1
                        g['athlete_medal_credits']+=1 if dimension=='athlete' else len(a['athletes'])
                    else: g['pending']+=1
            output[dimension]=sorted(groups.values(),key=lambda x:(-x['verified'],-x['pending'],x['label']))
        return output
