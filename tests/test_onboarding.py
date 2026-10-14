import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QDialog
from onboarding import FirstRunSetup, needs_setup
from storage import normalize_config, load_config
from installer.installer import _mark_config_defaults, InstallerWindow
from build_protected import dependencies
import main as application


class SetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'LOCALAPPDATA': self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.bridge_patch = patch('onboarding.LocalExtensionBridge')
        self.bridge_factory = self.bridge_patch.start()
        self.bridge = self.bridge_factory.return_value
        self.bridge.connected = False
        self.addCleanup(self.bridge_patch.stop)
        self.wizard = FirstRunSetup(normalize_config({}))
        self.addCleanup(self.wizard.cleanup)
        self.addCleanup(self.wizard.deleteLater)

    def final_page(self):
        self.wizard.channel.setText('https://chzzk.naver.com/' + 'a'*32)
        self.wizard.advance()
        self.wizard.advance()
        self.assertEqual(self.wizard.pages.currentIndex(), 2)

    def test_invalid_channel_stays_on_first_page(self):
        self.wizard.channel.setText('invalid')
        self.wizard.advance()
        self.assertEqual(self.wizard.pages.currentIndex(), 0)
        self.assertTrue(self.wizard.error.text())
        self.bridge.start.assert_not_called()

    def test_cancel_never_marks_setup_complete_or_changes_config(self):
        before = copy.deepcopy(self.wizard.config)
        self.final_page()
        self.wizard.reject()
        self.assertTrue(needs_setup(load_config()))
        self.assertEqual(self.wizard.config, before)
        self.bridge.stop.assert_called_once()

    def test_disconnected_requires_explicit_skip_then_saves_once(self):
        self.final_page()
        self.wizard.advance()
        self.assertIsNone(self.wizard.result_config)
        self.wizard.allow_unconnected.setChecked(True)
        self.wizard.autostart.setChecked(False)
        self.wizard.auto_change.setChecked(False)
        self.wizard.advance()
        saved = load_config()
        self.assertEqual(self.wizard.result(), QDialog.DialogCode.Accepted)
        self.assertFalse(needs_setup(saved))
        self.assertEqual(saved['channel'], 'a'*32)
        self.assertFalse(saved['autostart'])
        self.assertFalse(saved['auto_start_change'])

    def test_connected_completes_without_skip_and_keeps_rules(self):
        self.wizard.config['rules'] = [{'process': 'a.exe', 'category_id': 'a', 'category_name': 'A'}]
        self.final_page()
        self.bridge.connected = True
        self.wizard.advance()
        self.assertFalse(needs_setup(load_config()))
        self.assertEqual(load_config()['rules'], self.wizard.config['rules'])

    def test_save_failure_does_not_complete_setup(self):
        self.final_page()
        self.bridge.connected = True
        with patch('onboarding.save_config', side_effect=OSError('disk full')):
            self.wizard.advance()
        self.assertIsNone(self.wizard.result_config)
        self.assertTrue(needs_setup(load_config()))
        self.assertIn('disk full', self.wizard.error.text())

    def test_installer_preserves_completed_flag_and_user_choices(self):
        directory = Path(self.temp.name)
        values = {'setup_completed': True, 'autostart': False, 'auto_update': False, 'auto_start_change': False}
        (directory/'config.json').write_text(json.dumps(values))
        with patch('installer.installer.CONFIG_DIR', directory):
            _mark_config_defaults()
        self.assertEqual(json.loads((directory/'config.json').read_text()), values)

    def test_install_launches_foreground_entry(self):
        host = Mock(exe_path=str(Path(self.temp.name)/'App.exe'))
        with patch('installer.installer.subprocess.Popen') as popen:
            InstallerWindow.launch_app(host)
        self.assertEqual(popen.call_args.args[0], [host.exe_path, '--after-install'])
        host.close.assert_called_once()

    def test_setup_module_included_in_protected_build(self):
        self.assertIn('onboarding', dependencies('main')[0])

    def test_completed_setup_is_not_reopened_and_new_setup_shows_main(self):
        for completed in (True, False):
            with self.subTest(completed=completed), patch('main.QApplication', return_value=self.app), \
                    patch.object(QApplication, 'exec', return_value=0), \
                    patch('main.QLockFile'), patch('main.load_config', return_value=normalize_config({
                        'channel': 'a'*32, 'setup_completed': completed, 'start_hidden': True})), \
                    patch('main.FirstRunSetup') as setup, patch('main.Window') as window, \
                    patch('main.set_windows_autostart'), patch('main.ensure_start_menu_shortcut'), \
                    patch('main.QSystemTrayIcon.isSystemTrayAvailable', return_value=True), \
                    patch('main.sys.argv', ['app', '--background']):
                setup.return_value.exec.return_value = QDialog.DialogCode.Accepted
                setup.return_value.result_config = normalize_config({'channel': 'a'*32, 'setup_completed': True})
                self.assertEqual(application.main(), 0)
                if completed:
                    setup.assert_not_called()
                    window.return_value.hide.assert_called_once()
                else:
                    setup.assert_called_once()
                    window.return_value.show.assert_called_once()

    def test_cancelled_setup_does_not_start_main_window(self):
        with patch('main.QApplication', return_value=self.app), patch('main.QLockFile'), \
                patch('main.load_config', return_value=normalize_config({})), \
                patch('main.FirstRunSetup') as setup, patch('main.Window') as window:
            setup.return_value.exec.return_value = QDialog.DialogCode.Rejected
            self.assertEqual(application.main(), 0)
            window.assert_not_called()


if __name__ == '__main__':
    unittest.main()
