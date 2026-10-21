import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('preview_builder',ROOT/'scripts'/'build_public_preview.py')
builder=importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)


class PreviewBuildTest(unittest.TestCase):
    def test_sample_does_not_open_database_and_is_always_labeled(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(builder.sqlite3,'connect',side_effect=AssertionError('real DB must not be read')):
            root=Path(temp)
            report=builder.build(root,'/taekwondo-kids-preview/',sample=True,database=Path('private.sqlite3'))
            data=json.loads((root/'public-data.json').read_text(encoding='utf-8'))
            page=(root/'index.html').read_text(encoding='utf-8')
            self.assertEqual(3,report['profiles']); self.assertFalse(report['database_read'])
            self.assertIn('data-preview="sample"',page); self.assertIn('chưa gửi tới CLB',page)
            self.assertIn('/taekwondo-kids-preview/static/preview-data.js',page)
            for profile in data['profiles']:
                self.assertTrue(profile['athlete']['is_sample']); self.assertTrue(profile['athlete']['official_code'].startswith('MAU-'))
                self.assertEqual({'id','full_name','official_code','is_sample'},set(profile['athlete']))
            self.assertTrue(all(r['verification_status']=='sample' for r in data['achievements']))
            for field in ('date_of_birth','birth_year','legacy_','contact','source_original_text','review_notes'):
                self.assertNotIn(field,json.dumps(data))

    def test_team_has_one_result_and_three_profile_credits(self):
        data=builder.sample_snapshot(); result=next(r for r in data['achievements'] if r['participation_type']=='Đồng đội')
        self.assertEqual(3,len(result['athletes']))
        self.assertEqual(1,sum(r['id']==result['id'] for r in data['achievements']))
        self.assertEqual(3,sum(any(r['id']==result['id'] for r in p['achievements']) for p in data['profiles']))
        self.assertEqual(4,data['summary']['achievement_count']); self.assertEqual(6,data['summary']['athlete_medal_credits'])

    def test_without_explicit_sample_or_database_build_is_empty_and_not_demo(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); builder.build(root)
            self.assertEqual([],json.loads((root/'public-data.json').read_text(encoding='utf-8'))['profiles'])
            self.assertNotIn('data-preview="sample"',(root/'index.html').read_text(encoding='utf-8'))

    def test_invalid_base_path_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError): builder.build(Path(temp),'/evil\'script/')
