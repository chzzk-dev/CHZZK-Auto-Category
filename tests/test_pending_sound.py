import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from main import Window, play_pending_alert
from PySide6.QtWidgets import QApplication
from storage import load_config, normalize_config


def pending(process, reason='category-not-found'):
    return {'process': process, 'reason': reason, 'games': ['Test game']}


class PendingSoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def host(self, **config):
        return SimpleNamespace(auto_pending=[], config=normalize_config(config), preview=False,
                               persist=Mock(), refresh_table=Mock(), refresh_pending_page=Mock(),
                               tray_popup=None)

    def send(self, host, rows):
        Window.on_event(host, {'kind': 'auto_pending', 'data': rows})

    def test_existing_users_default_to_sound_and_can_disable_it(self):
        self.assertTrue(normalize_config({})['pending_sound'])
        self.assertFalse(normalize_config({'pending_sound': False})['pending_sound'])

    def test_settings_checkbox_persists_across_restarts(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOCALAPPDATA': directory}), \
                patch('main.set_windows_autostart'):
            window = Window(normalize_config({'auto_start_change': False, 'auto_update': False}), preview=True)
            self.addCleanup(window.deleteLater)
            self.assertTrue(window.pending_sound.isChecked())
            window.pending_sound.setChecked(False)
            window.save_options()
            saved = load_config()
            self.assertFalse(saved['pending_sound'])
            reopened = Window(saved, preview=True)
            self.addCleanup(reopened.deleteLater)
            self.assertFalse(reopened.pending_sound.isChecked())

    def test_new_batch_plays_once_and_updates_pending_ui(self):
        host = self.host()
        rows = [pending('a.exe'), pending('b.exe')]
        with patch('main.play_pending_alert') as sound:
            self.send(host, rows)
        sound.assert_called_once_with()
        self.assertEqual(host.auto_pending, rows)
        self.assertEqual(host.config['auto_pending'], rows)
        host.persist.assert_called_once_with()
        host.refresh_pending_page.assert_called_once_with()

    def test_reorder_case_reason_and_candidate_changes_do_not_repeat(self):
        host = self.host()
        with patch('main.play_pending_alert') as sound:
            self.send(host, [pending('a.exe'), pending('b.exe')])
            self.send(host, [pending('B.EXE', 'category-ambiguous'), pending('A.EXE')])
            host.auto_pending[0]['games'] = ['Updated candidate']
            self.send(host, list(host.auto_pending))
        sound.assert_called_once_with()

    def test_new_game_alerts_even_when_older_game_is_still_waiting(self):
        host = self.host()
        with patch('main.play_pending_alert') as sound:
            self.send(host, [pending('a.exe')])
            self.send(host, [pending('a.exe'), pending('b.exe')])
        self.assertEqual(sound.call_count, 2)

    def test_clearing_is_silent_and_returning_game_alerts_again(self):
        host = self.host()
        with patch('main.play_pending_alert') as sound:
            self.send(host, [pending('a.exe')])
            self.send(host, [])
            self.assertEqual(sound.call_count, 1)
            self.send(host, [pending('a.exe')])
        self.assertEqual(sound.call_count, 2)

    def test_league_lobby_match_transitions_do_not_repeat(self):
        host = self.host()
        with patch('main.play_pending_alert') as sound:
            for process in ('LeagueClient.exe', 'League of Legends.exe', 'LeagueClient.exe'):
                self.send(host, [pending(process)])
        sound.assert_called_once_with()

    def test_disabled_sound_keeps_pending_updates_working(self):
        host = self.host(pending_sound=False, notify=True)
        with patch('main.play_pending_alert') as sound:
            self.send(host, [pending('a.exe')])
        sound.assert_not_called()
        self.assertEqual(len(host.auto_pending), 1)
        host.refresh_pending_page.assert_called_once_with()

    def test_preview_and_empty_process_do_not_play_sound(self):
        host = self.host()
        host.preview = True
        with patch('main.play_pending_alert') as sound:
            self.send(host, [pending('a.exe')])
            host.preview = False
            self.send(host, [pending('')])
        sound.assert_not_called()

    def test_category_change_notification_setting_does_not_mute_pending_sound(self):
        host = self.host(notify=False)
        with patch('main.play_pending_alert') as sound:
            self.send(host, [pending('a.exe')])
        sound.assert_called_once_with()

    def test_windows_playback_is_asynchronous(self):
        native = SimpleNamespace(SND_ALIAS=0x10000, SND_ASYNC=1, PlaySound=Mock())
        with patch('main.sys.platform', 'win32'), patch.dict(sys.modules, {'winsound': native}), \
                patch('main.QApplication.beep') as fallback:
            play_pending_alert()
        native.PlaySound.assert_called_once_with('SystemExclamation', 0x10001)
        fallback.assert_not_called()

    def test_native_audio_failure_falls_back_without_breaking_ui(self):
        native = SimpleNamespace(SND_ALIAS=0x10000, SND_ASYNC=1,
                                 PlaySound=Mock(side_effect=RuntimeError('audio unavailable')))
        with patch('main.sys.platform', 'win32'), patch.dict(sys.modules, {'winsound': native}), \
                patch('main.QApplication.beep') as fallback:
            play_pending_alert()
        fallback.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
