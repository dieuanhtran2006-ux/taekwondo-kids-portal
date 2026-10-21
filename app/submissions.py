"""Untrusted parent contributions. Receiving a claim never verifies an achievement."""
from __future__ import annotations

from datetime import date
import hashlib
import json
import uuid
from urllib.parse import urlparse

from .core import AppError, Service, MEDALS, DISCIPLINES, PARTICIPATION_TYPES, audit, new_id, now, url_valid
from .public_portal import PublicPortal


TEXT_LIMITS = {'athlete_name': 120, 'athlete_code': 80, 'public_athlete_id': 80,
               'tournament_name': 240, 'event_name': 300, 'evidence_url': 2000,
               'notes': 2000, 'contact': 160}
REQUIRED = {'athlete_name', 'tournament_name', 'event_name'}
CHOICES = {'discipline': DISCIPLINES, 'participation_type': PARTICIPATION_TYPES,
           'medal_type': MEDALS + ['Chưa xác định']}
ALLOWED = set(TEXT_LIMITS) | set(CHOICES) | {'year', 'consent_to_review', 'client_request_id', 'website'}


def validate_submission(payload):
    if not isinstance(payload, dict) or set(payload) - ALLOWED:
        raise AppError(422, 'Đề nghị có trường dữ liệu không được hỗ trợ.')
    if payload.get('website'):
        raise AppError(422, 'Không thể tiếp nhận đề nghị này.')
    if payload.get('consent_to_review') is not True:
        raise AppError(422, 'Cần đồng ý gửi thông tin cho CLB đối chiếu.')
    try:
        request_id = str(uuid.UUID(payload.get('client_request_id', '')))
    except (ValueError, TypeError, AttributeError):
        raise AppError(422, 'Mã gửi không hợp lệ. Hãy mở lại biểu mẫu.')
    result = {}
    for key, limit in TEXT_LIMITS.items():
        value = payload.get(key, '')
        if not isinstance(value, str) or len(value.strip()) > limit:
            raise AppError(422, f'Trường {key} không hợp lệ hoặc quá dài.')
        result[key] = value.strip()
        if key in REQUIRED and not result[key]:
            raise AppError(422, 'Cần họ tên võ sinh, tên giải và nội dung thi đấu.')
    year = payload.get('year')
    if isinstance(year, bool) or not isinstance(year, int) or not 1900 <= year <= date.today().year + 1:
        raise AppError(422, 'Năm thi đấu không hợp lệ.')
    result['year'] = year
    for key, choices in CHOICES.items():
        value = payload.get(key, 'Chưa xác định')
        if value not in choices:
            raise AppError(422, 'Nội dung, hình thức hoặc huy chương chưa hợp lệ.')
        result[key] = value
    proof = urlparse(result['evidence_url'])
    if not url_valid(result['evidence_url']) or proof.password:
        raise AppError(422, 'Minh chứng phải là liên kết http hoặc https hợp lệ.')
    result['consent_to_review'] = True
    return request_id, result


def receive(conn, payload):
    request_id, data = validate_submission(payload)
    serialized = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    digest = hashlib.sha256(serialized.encode()).hexdigest()
    existing = conn.execute('SELECT id,payload_hash FROM achievement_submissions WHERE client_request_id=?', (request_id,)).fetchone()
    if existing:
        if existing['payload_hash'] != digest:
            raise AppError(409, 'Mã gửi này đã được dùng cho nội dung khác. Hãy mở đề nghị mới.')
        return {'receipt_id': existing['id'], 'status': 'received', 'duplicate': True}
    # A public reference is only a claim; it never establishes guardianship or an identity match.
    if data['public_athlete_id']:
        PublicPortal(conn).profile(data['public_athlete_id'])
    id = new_id()
    conn.execute('INSERT INTO achievement_submissions(id,client_request_id,payload_hash,payload_json,created_at) VALUES(?,?,?,?,?)',
                 (id, request_id, digest, serialized, now()))
    audit(conn, 'public-submission', 'received', 'achievement_submissions', id, None, {'status': 'pending'})
    return {'receipt_id': id, 'status': 'received', 'duplicate': False}


class SubmissionReview:
    def __init__(self, conn, user):
        self.conn, self.user = conn, user
        self.service = Service(conn, user)
        self.service.require_admin()

    def _raw(self, id):
        row = self.conn.execute('SELECT * FROM achievement_submissions WHERE id=?', (id,)).fetchone()
        if not row:
            raise AppError(404, 'Không tìm thấy đề nghị bổ sung.')
        return dict(row)

    @staticmethod
    def _dto(row):
        row = dict(row)
        row['data'] = json.loads(row.pop('payload_json'))
        row.pop('payload_hash', None)
        row.pop('client_request_id', None)
        return row

    def detail(self, id):
        return self._dto(self._raw(id))

    def list(self, query):
        try:
            page = max(1, int(query.get('page', 1)))
            limit = max(1, min(100, int(query.get('limit', 20))))
        except (ValueError, TypeError):
            raise AppError(422, 'Trang danh sách không hợp lệ.')
        status = query.get('status', '')
        if status and status not in ('pending', 'reviewing', 'converted', 'rejected'):
            raise AppError(422, 'Trạng thái đề nghị không hợp lệ.')
        q = str(query.get('q', '')).strip()
        if len(q) > 100:
            raise AppError(422, 'Từ khóa tối đa 100 ký tự.')
        where = '1=1'; values = []
        if status:
            where += ' AND status=?'; values.append(status)
        if q:
            # Literal search, not a SQL wildcard. Claims are never searched through athlete records.
            where += ' AND INSTR(LOWER(payload_json),LOWER(?))>0'; values.append(q)
        total = self.conn.execute(f'SELECT COUNT(*) FROM achievement_submissions WHERE {where}', values).fetchone()[0]
        pages = max(1, (total + limit - 1) // limit); page = min(page, pages)
        rows = self.conn.execute(f'SELECT * FROM achievement_submissions WHERE {where} ORDER BY created_at DESC,id LIMIT ? OFFSET ?', values + [limit, (page - 1) * limit])
        return {'items': [self._dto(r) for r in rows], 'page': page, 'pages': pages, 'total': total}

    def _check(self, id, payload):
        before = self._raw(id)
        if payload.get('version') != before['version']:
            raise AppError(409, 'Đề nghị đã thay đổi. Hãy tải lại trước khi xử lý.')
        if before['status'] in ('converted', 'rejected'):
            raise AppError(409, 'Đề nghị đã được xử lý; không thể tiếp nhận lần nữa.')
        return before

    def _save(self, before, status, note, target=None):
        if not isinstance(note, str) or not 1 <= len(note.strip()) <= 2000:
            raise AppError(422, 'Cần ghi căn cứ xử lý, tối đa 2.000 ký tự.')
        changed = self.conn.execute('UPDATE achievement_submissions SET status=?,resolution_notes=?,reviewed_by=?,reviewed_at=?,linked_achievement_id=?,version=version+1 WHERE id=? AND version=?',
            (status, note.strip(), self.user['id'], now(), target, before['id'], before['version'])).rowcount
        if changed != 1:
            raise AppError(409, 'Đề nghị đã thay đổi. Hãy tải lại.')
        # Keep the submitted text immutable; audit only the review decision.
        old = {k: before[k] for k in ('status', 'linked_achievement_id', 'version')}
        audit(self.conn, self.user['id'], 'review', 'achievement_submissions', before['id'], old,
              {'status': status, 'linked_achievement_id': target, 'note': note.strip()})
        return self.detail(before['id'])

    def update(self, id, payload):
        before = self._check(id, payload)
        if set(payload) - {'version', 'status', 'resolution_notes'}:
            raise AppError(422, 'Không được sửa nguyên văn đề nghị.')
        status = payload.get('status')
        if status not in ('pending', 'reviewing', 'rejected'):
            raise AppError(422, 'Chỉ có thể chờ xử lý, đối chiếu hoặc từ chối tại đây.')
        return self._save(before, status, payload.get('resolution_notes'))

    def convert(self, id, payload):
        before = self._check(id, payload)
        if payload.get('duplicate_checked') is not True or payload.get('identity_checked') is not True:
            raise AppError(422, 'Cần đối chiếu người nhận và kiểm tra trùng trước khi tiếp nhận.')
        note = payload.get('resolution_notes')
        if not isinstance(note, str) or not 1 <= len(note.strip()) <= 2000:
            raise AppError(422, 'Cần ghi căn cứ xử lý, tối đa 2.000 ký tự.')
        if payload.get('action') == 'link':
            target = self.service.achievement_scope(payload.get('achievement_id'), True)
            if target['archived']:
                raise AppError(422, 'Không thể liên kết kết quả đã lưu trữ.')
            # This only records the reviewed relationship, without altering any result or roster.
            achievement_id = target['id']
        elif payload.get('action') == 'create':
            data = payload.get('achievement')
            if not isinstance(data, dict):
                raise AppError(422, 'Cần chọn giải đấu, nội dung và người nhận để tạo kết quả.')
            claim = json.loads(before['payload_json'])
            source = {k: v for k, v in claim.items() if k not in ('contact', 'consent_to_review')}
            created = self.service.create('achievements', {**data,
                'source_row': 'Đề nghị bổ sung ' + id,
                'source_original_text': json.dumps(source, ensure_ascii=False, indent=2),
                'review_notes': note.strip(), 'publication_allowed': False,
                'evidence_publication_allowed': False})
            achievement_id = created['id']
            # Structured JSON can mention both the chosen medal and source text.
            # Check the original descriptive span separately so multiple JSON fields
            # cannot hide a contradiction from the source-text detector.
            from .importer import _medal_conflict, _multiple_medals_in_source
            description = claim['event_name'] + '\n' + claim['notes']
            conflict = (claim['medal_type'] in MEDALS and claim['medal_type'] != data.get('medal_type'))
            conflict = conflict or _medal_conflict(description, data.get('medal_type')) or _multiple_medals_in_source(description)
            if conflict and not created['source_conflict']:
                self.conn.execute('UPDATE achievements SET source_conflict=1 WHERE id=?', (achievement_id,))
                audit(self.conn, self.user['id'], 'claim_medal_conflict', 'achievements', achievement_id,
                      {'source_conflict': 0}, {'source_conflict': 1, 'submission_id': id})
        else:
            raise AppError(422, 'Chọn tạo kết quả chờ xác minh hoặc liên kết kết quả hiện có.')
        return self._save(before, 'converted', note, achievement_id)
