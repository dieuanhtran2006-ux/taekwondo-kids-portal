"""Recorded sessions only: no schedule, inferred absence, or invented training history."""
from datetime import date, time
from .core import AppError, Service, audit, new_id, now

STATUSES = {'present':'Có mặt','excused_absent':'Vắng có phép','unexcused_absent':'Vắng không phép'}
FIELDS = {'athlete_id','session_date','start_time','class_name','branch_id','status','note'}


class Attendance:
    def __init__(self, conn, user):
        self.conn, self.user = conn, user
        self.service = Service(conn, user)

    def listing(self, query, athlete_id=None):
        if athlete_id:
            self.service.scope_athlete(athlete_id)
        else:
            self.service.require_staff()
        scope, params = self.service.athlete_scope_sql('a')
        where = ['r.archived=0',scope]
        target = athlete_id or query.get('athlete_id')
        if target:
            self.service.scope_athlete(target)
            where.append('r.athlete_id=?');params.append(target)
        if query.get('status'):
            if query['status'] not in STATUSES: raise AppError(422,'Trạng thái điểm danh không hợp lệ.')
            where.append('r.status=?');params.append(query['status'])
        for key,operator in [('from_date','>='),('to_date','<=')]:
            if query.get(key):
                try: date.fromisoformat(query[key])
                except (ValueError,TypeError): raise AppError(422,'Ngày lọc không hợp lệ.')
                where.append('r.session_date'+operator+'?');params.append(query[key])
        condition=' AND '.join(where)
        source=' FROM attendance_records r JOIN athletes a ON a.id=r.athlete_id WHERE '+condition
        totals={key:0 for key in STATUSES}
        for row in self.conn.execute('SELECT r.status,COUNT(*) n'+source+' GROUP BY r.status',params): totals[row['status']]=row['n']
        total=sum(totals.values())
        try: limit=max(1,min(100,int(query.get('limit',30))));page=max(1,int(query.get('page',1)))
        except (TypeError,ValueError): raise AppError(422,'Phân trang không hợp lệ.')
        pages=max(1,(total+limit-1)//limit);page=min(page,pages)
        fields='r.id,r.athlete_id,a.full_name,a.official_code,r.session_date,r.start_time,r.class_name,r.branch_name_snapshot,r.status,r.note,r.version'
        if self.service.staff: fields+=',r.branch_id'
        rows=self.conn.execute('SELECT '+fields+source+' ORDER BY r.session_date DESC,r.start_time DESC,r.id LIMIT ? OFFSET ?',params+[limit,(page-1)*limit])
        return {'items':[dict(r) for r in rows],'summary':totals,'total':total,'page':page,'pages':pages}

    def detail(self, id):
        self.service.require_staff()
        row=self.conn.execute('SELECT * FROM attendance_records WHERE id=? AND archived=0',(id,)).fetchone()
        if not row: raise AppError(404,'Không tìm thấy bản ghi điểm danh.')
        self.service.scope_athlete(row['athlete_id'])
        return dict(row)

    def validate(self, payload, before=None):
        if set(payload)-FIELDS-{'version'}: raise AppError(422,'Trường điểm danh không được hỗ trợ.')
        data={**(before or {}),**payload}
        athlete=self.service.scope_athlete(data.get('athlete_id'))
        if athlete['archived']: raise AppError(422,'Hồ sơ đã lưu trữ; không thể nhập điểm danh mới.')
        if before and data['athlete_id']!=before['athlete_id']: raise AppError(422,'Không thể đổi võ sinh của bản ghi; hãy lưu trữ bản sai và nhập lại.')
        try:
            day=date.fromisoformat(data['session_date'])
            if day.isoformat()!=data['session_date']: raise ValueError()
            start=time.fromisoformat(data['start_time'])
            if start.strftime('%H:%M')!=data['start_time']: raise ValueError()
        except (KeyError,TypeError,ValueError): raise AppError(422,'Cần ngày học YYYY-MM-DD và giờ bắt đầu HH:MM hợp lệ.')
        if day>date.today(): raise AppError(422,'Chưa thể ghi nhận điểm danh cho buổi học trong tương lai.')
        if data.get('status') not in STATUSES: raise AppError(422,'Cần chọn trạng thái điểm danh.')
        for field,limit,required in [('class_name',120,True),('note',1000,False)]:
            value=data.get(field,'')
            if not isinstance(value,str) or len(value.strip())>limit or (required and not value.strip()): raise AppError(422,'Tên lớp hoặc ghi chú chưa hợp lệ.')
            data[field]=value.strip()
        branch_id=data.get('branch_id') or None
        if branch_id:
            branch=self.conn.execute('SELECT name FROM branches WHERE id=? AND archived=0',(branch_id,)).fetchone()
            if not branch: raise AppError(422,'Cơ sở không tồn tại hoặc đã lưu trữ.')
            if not self.service.admin and branch_id!=athlete['current_branch_id'] and not self.conn.execute('SELECT 1 FROM user_branches WHERE user_id=? AND branch_id=?',(self.user['id'],branch_id)).fetchone():
                raise AppError(403,'Cơ sở nằm ngoài phạm vi được cấp quyền.')
            # Preserve the name at the recorded time on subsequent status/note corrections.
            data['branch_name_snapshot']=before['branch_name_snapshot'] if before and before['branch_id']==branch_id else branch['name']
        else: data['branch_name_snapshot']=None
        data['branch_id']=branch_id
        return {k:data.get(k) for k in FIELDS|{'branch_name_snapshot'}}

    def save(self, payload, id=None):
        self.service.require_staff()
        before=self.detail(id) if id else None
        if before and (type(payload.get('version')) is not int or payload['version']!=before['version']):
            raise AppError(409,'Điểm danh đã thay đổi. Hãy tải lại trước khi sửa.')
        data=self.validate(payload,before)
        stamp=now()
        if before:
            fields=list(data)
            changed=self.conn.execute('UPDATE attendance_records SET '+','.join(k+'=?' for k in fields)+',updated_by=?,updated_at=?,version=version+1 WHERE id=? AND version=?',[data[k] for k in fields]+[self.user['id'],stamp,id,before['version']]).rowcount
            if changed!=1: raise AppError(409,'Điểm danh đã thay đổi. Hãy tải lại.')
        else:
            id=new_id(); data.update(id=id,created_by=self.user['id'],updated_by=self.user['id'],created_at=stamp,updated_at=stamp)
            fields=list(data)
            self.conn.execute('INSERT INTO attendance_records('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',[data[k] for k in fields])
        result=self.detail(id)
        audit(self.conn,self.user['id'],'update' if before else 'create','attendance_records',id,before,result)
        return result

    def archive(self,id,payload):
        before=self.detail(id)
        if type(payload.get('version')) is not int or payload['version']!=before['version']: raise AppError(409,'Điểm danh đã thay đổi. Hãy tải lại.')
        self.conn.execute('UPDATE attendance_records SET archived=1,version=version+1,updated_by=?,updated_at=? WHERE id=? AND version=?',(self.user['id'],now(),id,before['version']))
        audit(self.conn,self.user['id'],'archive','attendance_records',id,before,{'archived':1})
        return {'ok':True}
