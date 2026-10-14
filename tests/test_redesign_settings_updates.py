import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
from unittest.mock import patch
from storage import normalize_config, load_config, save_config, data_dir
from scheduling import seconds_until_check
from release_versions import SemVer
from updater import is_newer_version, fetch_latest_release
from updater_app import _latest_release


def release(version, beta=False):
    base = 'https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/download/v' + version + '/'
    return {'tag_name': 'v' + version, 'draft': False, 'prerelease': beta, 'assets': [
        {'name': 'ChzzkAutoCategory-' + version + '.msi', 'browser_download_url': base + 'app.msi', 'size': 100},
        {'name': 'SHA256SUMS.txt', 'browser_download_url': base + 'SHA256SUMS.txt'}]}


class SettingsMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'LOCALAPPDATA': self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_default_and_preserved_valid_update_interval(self):
        self.assertEqual(normalize_config({})['update_check_minutes'], 180)
        for minutes in (60, 180, 360, 720, 1440, 240):
            self.assertEqual(normalize_config({'update_check_minutes': minutes})['update_check_minutes'], minutes)
        self.assertEqual(normalize_config({'update_check_minutes': 5})['update_check_minutes'], 60)
        self.assertEqual(normalize_config({'update_check_minutes': 'bad'})['update_check_minutes'], 180)
        self.assertEqual(normalize_config({'category_sync_hours': 0})['category_sync_hours'], 1)
        self.assertEqual(normalize_config({})['category_sync_hours'], 6)
        self.assertEqual(normalize_config({'interval': 5})['interval'], 5)
        self.assertTrue(normalize_config({'auto_aggressive': False})['auto_aggressive'])

    def test_migration_backup_is_exact_and_existing_data_survives(self):
        old = {'channel': 'a'*32, 'rules': [{'process': 'Minecraft.exe', 'category_id': 'Minecraft', 'category_name': '마인크래프트'}],
               'update_check_minutes': 180, 'auto_update': False, 'setup_completed': True, 'extension_id': 'b'*32,
               'unknown_future_option': {'keep': True}}
        original = json.dumps(old, ensure_ascii=False, indent=4).encode()
        path = data_dir() / 'config.json'
        path.write_bytes(original)
        config = load_config()
        self.assertEqual((path.parent/'config.pre-v2.backup.json').read_bytes(), original)
        self.assertEqual(path.read_bytes(), original)
        save_config(config)
        migrated = load_config()
        for field in old:
            self.assertEqual(migrated[field], old[field])
        self.assertEqual(migrated['schema_version'], 2)
        self.assertEqual((path.parent/'config.pre-v2.backup.json').read_bytes(), original)

    def test_invalid_source_is_preserved_on_failure(self):
        path = data_dir() / 'config.json'
        path.write_text('broken JSON')
        with self.assertRaises(ValueError):
            load_config()
        self.assertEqual(path.read_text(), 'broken JSON')

    def test_backup_failure_never_writes_over_original(self):
        path = data_dir()/'config.json'
        original = b'{"channel":"test","rules":[]}'
        path.write_bytes(original)
        with patch('storage.Path.open', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                load_config()
        self.assertEqual(path.read_bytes(), original)

    def test_defaults_do_not_share_mutable_rule_lists(self):
        a, b = normalize_config({}), normalize_config({})
        a['rules'].append({'custom': True})
        self.assertEqual(b['rules'], [])


class UpdatePolicyTests(unittest.TestCase):
    def test_one_three_twentyfour_hours_and_disabled_schedule(self):
        for minutes in (60, 180, 1440):
            c = normalize_config({'update_check_minutes': minutes, 'update_last_checked_at': 1000})
            self.assertEqual(seconds_until_check(c, now=1000), minutes * 60)
            self.assertEqual(seconds_until_check(c, now=1000+minutes*60), 0)
        self.assertIsNone(seconds_until_check(normalize_config({'auto_update': False}), now=1000))
        self.assertEqual(seconds_until_check(normalize_config({'update_last_checked_at': 1000}), now=1000+3600), 7200)

    def test_semver_prerelease_and_build_precedence(self):
        versions = ['1.0.0-alpha', '1.0.0-alpha.1', '1.0.0-alpha.beta', '1.0.0-beta',
                    '1.0.0-beta.2', '1.0.0-beta.11', '1.0.0-rc.1', '1.0.0', '1.0.1', '1.1.0', '2.0.0']
        self.assertEqual(sorted(versions, key=SemVer), versions)
        self.assertEqual(SemVer('1.0.0+build1'), SemVer('1.0.0+build2'))
        self.assertTrue(is_newer_version('4.12.0', '4.11.5'))
        self.assertFalse(is_newer_version('4.12.0-rc.1', '4.12.0'))
        self.assertFalse(is_newer_version('fake', '4.11.5'))

    def test_stable_and_beta_release_selection(self):
        with patch('updater._github_request', return_value=io.BytesIO(json.dumps(release('4.11.3')).encode())):
            self.assertEqual(fetch_latest_release()['version'], '4.11.3')
        with patch('updater._github_request', return_value=io.BytesIO(json.dumps(release('4.12.0', True)).encode())):
            self.assertIsNone(fetch_latest_release())
        with patch('updater._github_request', return_value=io.BytesIO(json.dumps([release('4.11.3'), release('4.12.0', True)]).encode())):
            self.assertEqual(fetch_latest_release(True)['version'], '4.12.0')

    def test_deleted_or_missing_assets_are_not_installable(self):
        error = urllib.error.HTTPError('https://github.com/example', 404, 'gone', {}, None)
        with patch('updater._github_request', side_effect=error):
            self.assertIsNone(fetch_latest_release())
        empty = release('4.12.0')
        empty['assets'] = []
        with patch('updater._github_request', return_value=io.BytesIO(json.dumps(empty).encode())):
            self.assertIsNone(fetch_latest_release())
        with patch('updater_app._request', side_effect=error), self.assertRaises(urllib.error.HTTPError):
            _latest_release('4.12.0', 'v4.12.0')

    def test_helper_revalidates_exact_tag_and_beta_opt_in(self):
        with patch('updater_app._request', return_value=io.BytesIO(json.dumps(release('4.12.0', True)).encode())) as req:
            result = _latest_release('4.12.0', 'v4.12.0', True)
            self.assertEqual(result['version'], '4.12.0')
            self.assertTrue(req.call_args.args[0].endswith('/tags/v4.12.0'))
        with patch('updater_app._request', return_value=io.BytesIO(json.dumps(release('4.12.0', True)).encode())), self.assertRaises(RuntimeError):
            _latest_release('4.12.0', 'v4.12.0', False)

    def test_actual_updater_entrypoint_blocks_a_second_download_instance(self):
        import updater_app
        entered, release_app = threading.Event(), threading.Event()
        def event_loop():
            entered.set()
            release_app.wait(3)
            return 0
        with tempfile.TemporaryDirectory() as folder, patch('updater_app.CONFIG_DIR', Path(folder)), \
                patch('updater_app.sys.argv', ['updater']), patch('updater_app.QApplication') as application, \
                patch('updater_app.UpdaterWindow') as window, patch('updater_app.show_info') as notice:
            application.return_value.exec.side_effect = event_loop
            results = []
            first = threading.Thread(target=lambda: results.append(updater_app.main()))
            first.start()
            self.assertTrue(entered.wait(2))
            try:
                self.assertEqual(updater_app.main(), 0)
                self.assertEqual(window.call_count, 1)
                notice.assert_called_once()
            finally:
                release_app.set()
                first.join(3)
            self.assertFalse(first.is_alive())
            self.assertEqual(results, [0])


if __name__ == '__main__':
    unittest.main()
