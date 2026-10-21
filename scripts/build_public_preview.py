"""Build a synthetic login demo. Never export real student records to static hosting."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]


def sample_profile():
    athlete = {'id':'sample-athlete-1','full_name':'Võ sinh mẫu 01','official_code':'MAU-TKD-001',
               'is_sample':True,'branch_name':None,'status':None}
    results = []
    for n,year,kind,medal in [(1,2025,'Cá nhân','HCV'),(2,2025,'Cá nhân','HCB'),(3,2025,'Đồng đội','HCV'),(4,2026,'Cá nhân','HCĐ')]:
        results.append({'id':f'sample-result-{n}','tournament_id':f'sample-tournament-{year}',
            'tournament_name':f'Giải kiểm thử Taekwondo Kids {year}','year':year,
            'event_name':'Quyền minh họa','discipline':'Quyền','participation_type':kind,'medal_type':medal,
            'athletes':[athlete],'verification_status':'sample','is_sample':True,'evidence_files':[]})
    results.sort(key=lambda r:(-r['year'],r['id']))
    return {'athlete':athlete,'achievements':results,'medals':{'HCV':2,'HCB':1,'HCĐ':1},
            'tournament_count':2,'achievement_count':4,'is_sample':True}


def build(output,base='/',*,sample=False,database=None):
    if not re.fullmatch(r'/(?:[A-Za-z0-9_-]+/)*',base): raise ValueError('base-path phải có dạng / hoặc /ten-repo/.')
    if database and not sample:
        raise ValueError('Đã đóng xuất hồ sơ thật ra website tĩnh. Dữ liệu thật chỉ phục vụ qua backend có đăng nhập.')
    output=output.resolve()
    if output == ROOT: raise ValueError('Không xuất đè vào mã nguồn.')
    output.mkdir(parents=True,exist_ok=True); static=output/'static'; static.mkdir(exist_ok=True)
    # Exact retired exports only; never delete a database or upload.
    for relative in ('public-data.json','static/public.js','static/preview-data.js','static/sample-profile.js','static/demo-auth.js'):
        target=output/relative
        if target.is_file(): target.unlink()
    for name in ('logo.png','public.css','contributions.js','student.css','student.js'):
        shutil.copy2(ROOT/'static'/name,static/name)
    client=(static/'student.js').read_text(encoding='utf-8').replace('href="/',f'href="{base}')
    (static/'student.js').write_text(client,encoding='utf-8')
    student=(ROOT/'static'/'student.html').read_text(encoding='utf-8')
    if sample:
        (static/'sample-profile.js').write_text('/* Synthetic fixture, never real data. */\nwindow.TKDSampleProfile='+json.dumps(sample_profile(),ensure_ascii=False,separators=(',',':'))+';\n',encoding='utf-8')
        shutil.copy2(ROOT/'static'/'demo-auth.js',static/'demo-auth.js')
        student=student.replace('<body>','<body data-preview="sample">')
        student=student.replace('<script src="/static/student.js"','<script src="/static/sample-profile.js" defer></script>\n  <script src="/static/demo-auth.js" defer></script>\n  <script src="/static/student.js"')
    else:
        student=student.replace('<body>','<body data-static-preview="1">')
    student=student.replace('href="/',f'href="{base}').replace('src="/static/',f'src="{base}static/')
    student=student.replace(f'<a href="{base}admin/">Admin / HLV</a>','<span>Hồ sơ cần đăng nhập</span>')
    for name in ('public.css','student.css','student.js','contributions.js','sample-profile.js','demo-auth.js','logo.png'):
        if (static/name).is_file():
            version=hashlib.sha256((static/name).read_bytes()).hexdigest()[:12]
            student=student.replace(f'static/{name}"',f'static/{name}?v={version}"')
    for name in ('index.html','dang-nhap.html'):
        (output/name).write_text(student,encoding='utf-8')
    (output/'.nojekyll').touch()
    (output/'.gitignore').write_text('.env\n.env.*\n*.db\n*.sqlite*\n*.log\n',encoding='utf-8')
    (output/'README.md').write_text('''# Taekwondo Kids · Đăng nhập hồ sơ

Trang chủ yêu cầu đăng nhập. Đã bỏ tra cứu công khai và public-data.json.
GitHub Pages chỉ là mô phỏng trên thiết bị, không bảo vệ dữ liệu thật.
Chỉ có hồ sơ tổng hợp Võ sinh mẫu 01; không chứa database, Excel nội bộ hoặc tài khoản thật.
Mã mẫu: MAU-TKD-001. Mật khẩu ban đầu: TKD-Mau!2026.
Lần đầu phải đổi mật khẩu thử trước khi mở hồ sơ. Không dùng mật khẩu thật.
Bổ sung thành tích mẫu chỉ lưu trên trình duyệt, chưa gửi tới CLB.
Dữ liệu thật cần backend có xác thực, phân quyền phía server và HTTPS.
Không xuất hồ sơ thật vào tệp tĩnh, kể cả khi đã có trang đăng nhập.
''',encoding='utf-8')
    return {'mode':'sample' if sample else 'disabled','profiles':1 if sample else 0,'database_read':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(); mode.add_argument('--sample',action='store_true'); mode.add_argument('--db',type=Path)
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--base-path',default='/')
    args=parser.parse_args()
    print(json.dumps(build(args.output,args.base_path,sample=args.sample,database=args.db)))
