"""Anonymous read model: explicit consent, current verification and a small field allowlist."""
from __future__ import annotations

import unicodedata
from .core import AppError, MEDALS, achievement_blockers


def search_key(value):
    value = unicodedata.normalize('NFKD', str(value or '').casefold().replace('đ', 'd'))
    return ' '.join(''.join(c for c in value if not unicodedata.combining(c)).split())


PROFILE_WHERE = "a.public_profile_allowed=1 AND a.identity_verification_status='verified' AND a.archived=0 AND a.official_code IS NOT NULL AND TRIM(a.official_code)!='' AND UPPER(a.official_code) NOT LIKE 'TAM-%'"


class PublicPortal:
    def __init__(self, conn):
        self.conn = conn
        self.conn.create_function('tkd_search', 1, search_key, deterministic=True)
        self._results = None

    @staticmethod
    def _athlete(row):
        return {key: row[key] for key in ('id', 'full_name', 'official_code')}

    def results(self):
        if self._results is not None: return self._results
        self._results = []
        candidates = self.conn.execute("""SELECT ac.*,t.tournament_name,t.year FROM achievements ac
            JOIN tournaments t ON t.id=ac.tournament_id
            WHERE ac.archived=0 AND t.archived=0 AND ac.verification_status='verified'
              AND ac.publication_allowed=1 AND ac.public_search_allowed=1
            ORDER BY t.year DESC, t.tournament_name, ac.event_name, ac.id""").fetchall()
        for row in candidates:
            if achievement_blockers(self.conn, row): continue
            if self.conn.execute("SELECT 1 FROM athlete_achievements WHERE achievement_id=? AND link_status!='verified'", (row['id'],)).fetchone(): continue
            members = self.conn.execute(f"""SELECT a.id,a.full_name,a.official_code FROM athletes a
                JOIN athlete_achievements aa ON aa.athlete_id=a.id
                WHERE aa.achievement_id=? AND aa.link_status='verified' AND {PROFILE_WHERE}
                ORDER BY tkd_search(a.full_name),a.official_code""", (row['id'],)).fetchall()
            if not members: continue
            result = {key: row[key] for key in ('id', 'tournament_id', 'tournament_name', 'year',
                'event_name', 'discipline', 'participation_type', 'medal_type', 'age_category', 'weight_category', 'belt_category')}
            result['athletes'] = [self._athlete(member) for member in members]
            result['verification_status'] = 'verified'
            if row['public_evidence_allowed'] and row['evidence_publication_allowed'] and row['evidence_url']:
                result['evidence_url'] = row['evidence_url']
            result['evidence_files'] = [dict(f) for f in self.conn.execute("""SELECT id,mime_type FROM evidence_files
                WHERE achievement_id=? AND publication_allowed=1 AND public_access_allowed=1 ORDER BY id""", (row['id'],))]
            self._results.append(result)
        return self._results

    @staticmethod
    def _counts(results):
        return {'medals': {medal: sum(r['medal_type'] == medal for r in results) for medal in MEDALS},
                'tournament_count': len({r['tournament_id'] for r in results}), 'achievement_count': len(results)}

    def summary(self):
        results = self.results()
        return {'athletes': self.conn.execute(f'SELECT COUNT(*) FROM athletes a WHERE {PROFILE_WHERE}').fetchone()[0],
                **self._counts(results), 'athlete_medal_credits': sum(len(r['athletes']) for r in results)}

    def search(self, query):
        q = str(query.get('q', '')).strip()
        if len(q) > 100: raise AppError(422, 'Từ khóa tối đa 100 ký tự.')
        try:
            page = max(1, int(query.get('page', 1)))
            limit = max(1, min(24, int(query.get('limit', 12))))
        except (ValueError, TypeError): raise AppError(422, 'Trang tìm kiếm không hợp lệ.')
        key = search_key(q)
        if len(key) < 2:
            return {'items': [], 'total': 0, 'page': 1, 'pages': 1, 'query_required': True}
        where = PROFILE_WHERE + " AND INSTR(tkd_search(a.full_name || ' ' || a.official_code),?)>0"
        total = self.conn.execute(f'SELECT COUNT(*) FROM athletes a WHERE {where}', (key,)).fetchone()[0]
        pages = max(1, (total + limit - 1) // limit); page = min(page, pages)
        rows = self.conn.execute(f"""SELECT a.id,a.full_name,a.official_code FROM athletes a WHERE {where}
            ORDER BY tkd_search(a.full_name),a.official_code LIMIT ? OFFSET ?""", (key, limit, (page - 1) * limit)).fetchall()
        results = self.results()
        items = []
        for row in rows:
            own = [r for r in results if any(m['id'] == row['id'] for m in r['athletes'])]
            items.append({**self._athlete(row), **self._counts(own)})
        return {'items': items, 'total': total, 'page': page, 'pages': pages, 'query_required': False}

    def profile(self, id):
        row = self.conn.execute(f'SELECT a.id,a.full_name,a.official_code FROM athletes a WHERE a.id=? AND {PROFILE_WHERE}', (id,)).fetchone()
        if not row: raise AppError(404, 'Hồ sơ chưa được công bố hoặc không tồn tại.')
        results = [r for r in self.results() if any(m['id'] == id for m in r['athletes'])]
        return {'athlete': self._athlete(row), 'achievements': results, **self._counts(results)}

    def achievement(self, id):
        for result in self.results():
            if result['id'] == id: return result
        raise AppError(404, 'Thành tích chưa được công bố hoặc không tồn tại.')

    def evidence(self, id):
        row = self.conn.execute('SELECT * FROM evidence_files WHERE id=? AND publication_allowed=1 AND public_access_allowed=1', (id,)).fetchone()
        if not row: raise AppError(404, 'Minh chứng chưa được công bố hoặc không tồn tại.')
        self.achievement(row['achievement_id'])
        return row
