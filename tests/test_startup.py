"""Regression checks for local server startup and readiness reporting."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server import Application

class StartupTest(unittest.TestCase):
    def test_health_is_available_without_login_and_reveals_no_personal_data(self):
        with tempfile.TemporaryDirectory() as directory:
            app=Application(Path(directory)/'portal.sqlite3')
            status=[]
            body=b''.join(app({'REQUEST_METHOD':'GET','PATH_INFO':'/api/health','HTTP_HOST':'localhost','REMOTE_ADDR':'127.0.0.1','wsgi.url_scheme':'http','wsgi.input':io.BytesIO(b'')},lambda code,headers:status.append(code)))
            self.assertEqual(status,['200 OK'])
            self.assertEqual(json.loads(body),{'app':'taekwondo-kids-portal','status':'ok'})

    def test_vietnamese_startup_message_does_not_crash_a_cp1252_console(self):
        code=textwrap.dedent('''
            import sys
            from unittest.mock import patch
            import server
            sys.stdout.reconfigure(encoding='cp1252',errors='strict')
            sys.stderr.reconfigure(encoding='cp1252',errors='strict')
            class FakeHTTPServer:
                def __enter__(self): return self
                def __exit__(self,*args): pass
                def serve_forever(self): raise KeyboardInterrupt
            with patch.object(sys,'argv',['server.py']), patch.object(server,'Application',return_value=object()), patch.object(server,'make_server',return_value=FakeHTTPServer()):
                server.main()
        ''')
        result=subprocess.run([sys.executable,'-X','utf8','-c',code],cwd=ROOT,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr.decode('utf-8',errors='replace'))
        self.assertIn('Tạo tài khoản',result.stdout.decode('utf-8'))

if __name__=='__main__': unittest.main()
