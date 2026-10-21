"""Build public assets. --sample never opens a real database or imports a workbook."""
from __future__ import annotations
import argparse
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def counts(results):
    return {'medals': {m: sum(r['medal_type'] == m for r in results) for m in ('HCV','HCB','HCĐ')},
            'tournament_count': len({r['tournament_id'] for r in results}), 'achievement_count': len(results)}


def empty_snapshot():
    return {'format_version': 1, 'mode': 'published', 'published_at': datetime.now(timezone.utc).isoformat(),
            'summary': {'athletes': 0, **counts([]), 'athlete_medal_credits': 0}, 'profiles': [], 'achievements': []}


def sample_snapshot():
    snapshot = empty_snapshot(); snapshot['mode'] = 'sample'
    snapshot['notice'] = 'Dữ liệu kiểm thử tổng hợp, không phải hồ sơ hoặc thành tích thật của CLB.'
    athletes = [{'id': f'sample-athlete-{n}', 'full_name': f'Võ sinh mẫu {n:02}',
                 'official_code': f'MAU-TKD-{n:03}', 'is_sample': True} for n in range(1,4)]
    specs = [(1,2025,'Quyền cá nhân minh họa','Cá nhân','HCV',athletes[:1]),
             (2,2025,'Đối kháng minh họa','Cá nhân','HCB',athletes[:1]),
             (3,2025,'Quyền đồng đội minh họa','Đồng đội','HCV',athletes),
             (4,2026,'Quyền cá nhân minh họa','Cá nhân','HCĐ',athletes[:1])]
    results = [{'id': f'sample-result-{n}', 'tournament_id': f'sample-tournament-{year}',
                'tournament_name': f'Giải kiểm thử Taekwondo Kids {year}', 'year': year,
                'event_name': event, 'discipline': 'Đối kháng' if n == 2 else 'Quyền',
                'participation_type': kind, 'medal_type': medal, 'athletes': members,
                'age_category': None, 'weight_category': None, 'belt_category': None,
                'verification_status': 'sample', 'is_sample': True, 'evidence_files': []}
               for n,year,event,kind,medal,members in specs]
    results.sort(key=lambda r: (-r['year'],r['id']))
    snapshot['achievements'] = results
    for athlete in athletes:
        own = [r for r in results if athlete in r['athletes']]
        snapshot['profiles'].append({'athlete':athlete,'achievements':own,**counts(own),'is_sample':True})
    snapshot['summary'] = {'athletes':len(athletes),**counts(results),
        'athlete_medal_credits':sum(len(r['athletes']) for r in results),'is_sample':True}
    return snapshot


def published_snapshot(database):
    from app.public_portal import PublicPortal, PROFILE_WHERE
    snapshot = empty_snapshot()
    if not database or not database.is_file(): return snapshot
    conn = sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True); conn.row_factory=sqlite3.Row
    try:
        conn.execute('BEGIN')
        needed={'athletes':{'public_profile_allowed'},'achievements':{'public_search_allowed','public_evidence_allowed'},'evidence_files':{'public_access_allowed'}}
        if not all(fields <= {r['name'] for r in conn.execute(f'PRAGMA table_info({table})')} for table,fields in needed.items()): return snapshot
        portal=PublicPortal(conn); snapshot['summary']=portal.summary()
        ids=[r[0] for r in conn.execute(f'SELECT a.id FROM athletes a WHERE {PROFILE_WHERE} ORDER BY a.id')]
        snapshot['profiles']=[portal.profile(id) for id in ids]; snapshot['achievements']=portal.results()
        for result in snapshot['achievements']: result['evidence_files']=[]
        return snapshot
    finally: conn.close()


def build(output,base='/',*,sample=False,database=None):
    if not re.fullmatch(r'/(?:[A-Za-z0-9_-]+/)*',base): raise ValueError('base-path phải có dạng / hoặc /ten-repo/.')
    snapshot=sample_snapshot() if sample else published_snapshot(database)
    output.mkdir(parents=True,exist_ok=True); static=output/'static'; static.mkdir(exist_ok=True)
    (output/'public-data.json').write_text(json.dumps(snapshot,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    for name in ('logo.png','public.css','preview-data.js','contributions.js'): shutil.copy2(ROOT/'static'/name,static/name)
    page=(ROOT/'static'/'public.html').read_text(encoding='utf-8')
    page=page.replace('<body>','<body data-static-preview="1"'+(' data-preview="sample"' if sample else '')+'>')
    page=page.replace('<script src="/static/contributions.js"','<script src="/static/preview-data.js" defer></script>\n  <script src="/static/contributions.js"')
    banner='BẢN KIỂM THỬ · Chỉ sử dụng hồ sơ mẫu · Đề nghị mẫu chỉ lưu trên thiết bị, chưa gửi tới CLB' if sample else 'BẢN XEM THỬ · Chỉ hiển thị thông tin được phép công bố'
    page=page.replace('<main id="noi-dung"',f'<div class="preview-banner" role="note">{banner}</div>\n  <main id="noi-dung"')
    page=page.replace('<a href="/admin/">Đăng nhập quản trị <span aria-hidden="true">↗</span></a>','<span>'+('Dữ liệu kiểm thử · Không phải hồ sơ thật' if sample else 'Bản xem thử · Chưa kết nối tiếp nhận online')+'</span>')
    if sample:
        page=page.replace('Xác minh bởi CLB','Dữ liệu kiểm thử').replace('Chỉ hiển thị thông tin được phép công bố.','Bản mẫu để thử tra cứu và bổ sung thành tích.')
    page=page.replace('href="/favicon.ico"','href="/static/logo.png"').replace('href="/',f'href="{base}').replace('src="/static/',f'src="{base}static/')
    (output/'index.html').write_text(page,encoding='utf-8')
    client=(ROOT/'static'/'public.js').read_text(encoding='utf-8')
    start=client.index('  async function api(path) {'); end=client.index('\n  function landing(',start)
    adapter="""  let snapshotPromise;
  async function api(path) {
    if (!snapshotPromise) snapshotPromise = fetch('BASEpublic-data.json', {credentials:'omit', cache:'no-store'})
      .then(response => { if (!response.ok) throw new Error('Chưa thể tải bản xem thử.'); return response.json(); })
      .catch(error => { snapshotPromise = null; throw new Error('Chưa thể kết nối sổ thành tích. Hãy tải lại trang.'); });
    return window.TKDPreviewData.read(await snapshotPromise, path);
  }
""".replace('BASE',base)
    client=client[:start]+adapter+client[end:]
    client=client.replace('href="/ho-so/','href="/#/ho-so/')
    client=client.replace("if (location.pathname.startsWith('/ho-so/')) {","if (location.hash.startsWith('#/ho-so/')) {")
    client=client.replace("decodeURIComponent(location.pathname.split('/')[2] || '')","decodeURIComponent(location.hash.slice('#/ho-so/'.length).split(/[?#]/)[0] || '')")
    client=client.replace('location.origin + location.pathname','location.origin + location.pathname + location.hash')
    client=client.replace("history.pushState({}, '', '/?'","history.pushState({}, '', '"+base+"?'")
    client=client.replace('href="/',f'href="{base}')
    client=client.replace("  window.addEventListener('popstate', start);","  window.addEventListener('popstate', start);\n  window.addEventListener('hashchange', () => { if (location.hash.startsWith('#/ho-so/') || state.profile) start(); });")
    (static/'public.js').write_text(client,encoding='utf-8')
    # Pages/browser caches may otherwise mix new HTML with old JavaScript/CSS.
    for name in ('public.css','public.js','contributions.js','preview-data.js','logo.png'):
        version=hashlib.sha256((static/name).read_bytes()).hexdigest()[:12]
        page=page.replace(f'static/{name}"',f'static/{name}?v={version}"')
    (output/'index.html').write_text(page,encoding='utf-8')
    (output/'.nojekyll').touch()
    (output/'.gitignore').write_text('.env\n.env.*\n*.db\n*.sqlite*\n*.log\n',encoding='utf-8')
    (output/'README.md').write_text('''# Taekwondo Kids · Bản xem thử

Bản GitHub Pages được dựng từ mã nguồn MVP riêng tư. Không chứa database, Excel nội bộ, tài khoản hoặc minh chứng tải lên.

- Hồ sơ `Võ sinh mẫu 01`, `02`, `03`, mã `MAU-TKD-001` đến `003` là dữ liệu tổng hợp để kiểm thử.
- Bốn kết quả để thử tìm kiếm, lịch sử, bộ lọc và đồng đội; không phải thành tích thật hoặc kết quả CLB đã xác minh.
- Một kết quả đồng đội hiển thị ở ba hồ sơ nhưng chỉ có một bản ghi huy chương mẫu.
- Bổ sung thành tích: nhập → kiểm tra → lưu đề nghị mẫu trên trình duyệt. Tải lại vẫn còn trên cùng trình duyệt; dùng nút Xóa dữ liệu thử để xóa.
- Đề nghị mẫu chưa gửi tới CLB, không cộng vào huy chương, không đồng bộ sang thiết bị khác hoặc trang quản trị.
- Khi chạy toàn bộ backend Python, biểu mẫu gửi vào hàng chờ riêng cho quản trị viên xử lý. GitHub Pages chưa chạy backend đó.

Không đưa thông tin thật của trẻ em hoặc liên hệ cá nhân vào dữ liệu thử. Không sao chép database hoặc tài liệu nội bộ vào repository công khai.
''',encoding='utf-8')
    if not sample:
        (output/'README.md').write_text('''# Taekwondo Kids · Snapshot công khai

Chỉ gồm dữ liệu đã được quyền công bố qua lớp PublicPortal. Không có backend ghi dữ liệu hoặc tự đồng bộ. Biểu mẫu bổ sung chưa kết nối và không gửi đề nghị. Không có database, dữ liệu Excel nội bộ, contact hoặc minh chứng tải lên trong gói xuất.
''',encoding='utf-8')
    return {'mode':snapshot['mode'],'profiles':len(snapshot['profiles']),'achievements':len(snapshot['achievements']),'database_read':bool(database and not sample)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(); mode.add_argument('--sample',action='store_true'); mode.add_argument('--db',type=Path)
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--base-path',default='/')
    args=parser.parse_args()
    print(json.dumps(build(args.output,args.base_path,sample=args.sample,database=args.db)))
