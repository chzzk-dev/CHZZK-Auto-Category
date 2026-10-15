from pathlib import Path
import ast
import json
import tempfile
import unittest
from unittest.mock import patch

from build_protected import staged_source
from scripts.release_notes import insert_entry, make_notes, generate, validate_tag
import release


class ReleaseHistoryTests(unittest.TestCase):
    def test_repeated_record_keeps_one_version_and_preserves_old_history(self):
        original = '# 변경 기록\n\n## 미배포\n\n- 다음 변경\n\n## [1.0.0] — old\n\n- 이전 내역\n'
        notes = '## [2.0.0](https://example.test) — new\n\n- 변경 사항\n'
        first = insert_entry(original, '2.0.0', notes)
        second = insert_entry(first, '2.0.0', notes)
        self.assertEqual(first, second)
        self.assertEqual(second.count('## [2.0.0]'), 1)
        self.assertIn('- 이전 내역', second)
        self.assertNotIn('- 다음 변경', second)

    def test_next_version_pending_notes_survive_publication_race(self):
        original = '# 기록\n\n## 미배포\n\n- 아직 배포하지 않은 다음 버전 기능\n'
        result = insert_entry(original, '2.0.0', '## [2.0.0] — published\n', consume_pending=False)
        self.assertIn('- 아직 배포하지 않은 다음 버전 기능', result)

    def test_notes_include_curated_changes_commits_and_kst_date(self):
        with tempfile.TemporaryDirectory() as directory:
            notes = make_notes(Path(directory), '4.11.4', 'v4.11.4', '# 기록\n\n## 미배포\n\n- MSI 수정\n',
                               date='2026-10-14', commits=[('a'*40, 'Fix [UI] <loader>')])
            self.assertIn('2026-10-14 (KST)', notes)
            self.assertIn('- MSI 수정', notes)
            self.assertIn('Fix \\[UI\\] &lt;loader&gt;', notes)
            self.assertIn('ChzzkAutoCategory-4.11.4.msi', notes)

    def test_tag_validation_prevents_version_mismatch_and_path_injection(self):
        self.assertEqual(validate_tag('4.11.4', '4.11.4'), '4.11.4')
        self.assertEqual(validate_tag('4.11.4', 'v4.11.4'), 'v4.11.4')
        for tag in ('v4.11.3', '../release', 'v4.11.4;rm', '4.11.4-beta'):
            with self.assertRaises(ValueError): validate_tag('4.11.4', tag)

    def test_generate_does_not_mark_repository_changelog_as_published(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = '# 기록\n\n## 미배포\n\n- 변경\n'
            (root/'CHANGELOG.md').write_text(current)
            notes, full = generate(root, '4.11.4', 'v4.11.4')
            self.assertEqual((root/'CHANGELOG.md').read_text(), current)
            self.assertIn('## [4.11.4]', notes.read_text())
            self.assertIn('## [4.11.4]', full.read_text())

    def test_bare_tag_release_metadata_points_to_actual_asset_url(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installer = root/'dist-installer'/f'ChzzkAutoCategory-{release.APP_VERSION}.msi'
            installer.parent.mkdir()
            installer.write_bytes(bytes.fromhex('D0CF11E0A1B11AE1') + b'fixture')
            with patch.object(release, 'ROOT', root), patch.object(release, 'WEB_DOWNLOADS', root/'website/downloads'):
                _, _, metadata = release.create_release(tag=release.APP_VERSION)
            info = json.loads(metadata.read_text())
            self.assertIn('/download/'+release.APP_VERSION+'/', info['packageUrl'])


class CredentialStagingTests(unittest.TestCase):
    def test_steam_secret_uses_exact_actions_name_and_only_changes_staging(self):
        source = "APP_STEAM_WEB_API_KEY = ''\nOTHER_SETTING = True\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'storage.py'
            path.write_text(source)
            value = "synthetic-'quote'-secret"
            staged = staged_source('storage', path, {'STEAM_WEB_API': value})
            namespace = {}
            exec(compile(staged, '<staging>', 'exec'), namespace)
            self.assertEqual(namespace['APP_STEAM_WEB_API_KEY'], value)
            self.assertTrue(namespace['OTHER_SETTING'])
            self.assertEqual(path.read_text(), source)
            self.assertEqual(staged_source('storage', path, {}), source)
            self.assertEqual(staged_source('worker', path, {'STEAM_WEB_API': value}), source)

    def test_credentials_are_injected_into_staging_without_changing_public_source(self):
        source = "import os\nAPP_CLIENT_ID = os.environ.get('CHZZK_CLIENT_ID', '')\nAPP_CLIENT_SECRET = os.environ.get('CHZZK_CLIENT_SECRET', '')\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'chzzk_open.py';path.write_text(source)
            value = "test-secret-with-'quote'"
            staged = staged_source('chzzk_open', path, {'CHZZK_CLIENT_ID': 'test-client-id', 'CHZZK_CLIENT_SECRET': value})
            self.assertEqual(path.read_text(), source)
            tree = ast.parse(staged)
            assignments = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)}
            self.assertEqual(assignments['APP_CLIENT_ID'], 'test-client-id')
            self.assertEqual(assignments['APP_CLIENT_SECRET'], value)
            self.assertEqual(staged_source('chzzk_open', path, {}), source)


if __name__ == '__main__':
    unittest.main()
