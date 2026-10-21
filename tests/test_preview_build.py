import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('preview_builder',ROOT/'scripts'/'build_public_preview.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class PreviewBuildTest(unittest.TestCase):
    def test_sample_is_single_synthetic_profile_and_never_reads_database(self):
        with tempfile.TemporaryDirectory() as temp,patch('sqlite3.connect',side_effect=AssertionError('No real DB')):
            root=Path(temp)
            report=builder.build(root,'/taekwondo-kids-preview/',sample=True,database=Path('private.sqlite3'))
            self.assertEqual(1,report['profiles']);self.assertFalse(report['database_read'])
            page=(root/'index.html').read_text(encoding='utf-8')
            self.assertIn('data-preview="sample"',page);self.assertIn('/taekwondo-kids-preview/static/student.js?v=',page)
            self.assertNotIn('Tra cứu công khai',page);self.assertNotIn('public-data.json',page)
            self.assertEqual(page,(root/'dang-nhap.html').read_text(encoding='utf-8'))
            data=(root/'static/sample-profile.js').read_text(encoding='utf-8')
            self.assertIn('Võ sinh mẫu 01',data);self.assertNotIn('MAU-TKD-002',data)
            self.assertNotIn('source_original_text',data);self.assertNotIn('contact',data)
            self.assertIn('không bảo vệ dữ liệu thật',(root/'README.md').read_text(encoding='utf-8'))

    def test_removes_old_export_and_search_assets_when_rebuilding(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'static').mkdir()
            for path in ('public-data.json','static/public.js','static/preview-data.js'):
                (root/path).write_text('OLD_DATA')
            builder.build(root,sample=True)
            for path in ('public-data.json','static/public.js','static/preview-data.js'):
                self.assertFalse((root/path).exists())
            builder.build(root)
            self.assertFalse((root/'static/sample-profile.js').exists())
            self.assertFalse((root/'static/demo-auth.js').exists())
            self.assertIn('data-static-preview="1"',(root/'index.html').read_text(encoding='utf-8'))

    def test_real_database_export_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,'Đã đóng'):
                builder.build(Path(temp),database=Path('private.sqlite3'))

    def test_invalid_base_path_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):builder.build(Path(temp),'/evil\'script/')
