import os
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from core import Rule
from main import Window
from storage import normalize_config
from worker import Worker


class TrayStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        environment = patch.dict(os.environ, {'LOCALAPPDATA': self.temp.name})
        environment.start()
        self.addCleanup(environment.stop)
        self.window = Window(normalize_config({'autostart': False, 'auto_start_change': False,
                                              'auto_update': False}), preview=True)
        self.addCleanup(self.window.deleteLater)
        self.window.enabled = True
        self.window.last_applied_text = 'VALORANT-Win64-Shipping.exe → 발로란트'
        self.state = {'key': 'valorant', 'process': 'VALORANT-Win64-Shipping.exe',
                      'game_name': 'VALORANT', 'localized_name': '발로란트',
                      'stage': '적용 완료', 'running': True}

    def test_open_popup_and_tooltip_clear_when_snapshot_reports_exit(self):
        w = self.window
        w.on_event({'kind': 'pipeline_state', 'data': self.state})
        w.show_tray_popup()
        self.app.processEvents()
        self.assertEqual(w.tray_popup.last_line.text(), '현재 게임 · 발로란트')
        w.on_event({'kind': 'detected_games', 'data': []})
        self.assertEqual(w.tray_popup.last_line.text(), '현재 게임 · 없음')
        self.assertIn('실행 중인 게임이 없습니다', w.tray_popup.status_text.text())
        self.assertNotIn('발로란트', w.tray.toolTip())
        self.assertEqual(w.last_applied_text, 'VALORANT-Win64-Shipping.exe → 발로란트')
        self.assertIn('실행 중인 게임이 없습니다', w.dashboard_game.text())
        w.tray_popup.hide()

    def test_pipeline_exit_and_removal_refresh_visible_popup_without_status_event(self):
        w = self.window
        w.tray_popup.show()
        for event in ({'kind': 'pipeline_state', 'data': dict(self.state, running=False)},
                      {'kind': 'pipeline_remove', 'key': 'valorant'}):
            with self.subTest(kind=event['kind']):
                w.on_event({'kind': 'pipeline_state', 'data': self.state})
                w.on_event(event)
                self.assertEqual(w.tray_popup.last_line.text(), '현재 게임 · 없음')
                self.assertNotIn('발로란트', w.tray.toolTip())
        w.tray_popup.hide()

    def test_hidden_popup_reopens_with_current_game_and_pause_clears_old_status(self):
        w = self.window
        w.on_event({'kind': 'pipeline_state', 'data': self.state})
        w.on_event({'kind': 'detected_games', 'data': []})
        w.on_event({'kind': 'status', 'text': '감지 중 · 여러 게임은 대표 게임을 선택해 주세요'})
        w.tray_popup.refresh()
        self.assertEqual(w.tray_popup.last_line.text(), '현재 게임 · 없음')
        self.assertNotIn('여러 게임', w.tray_popup.status_text.text())
        w.on_event({'kind': 'pipeline_state', 'data': self.state})
        w.tray_popup.refresh()
        self.assertEqual(w.tray_popup.last_line.text(), '현재 게임 · 발로란트')
        w.on_event({'kind': 'enabled', 'value': False})
        w.tray_popup.refresh()
        self.assertIn('일시정지', w.tray_popup.status_text.text())
        self.assertIn('일시정지', w.tray.toolTip())

    def test_active_game_keeps_broadcast_wait_and_validation_errors_visible(self):
        w = self.window
        w.on_event({'kind': 'pipeline_state', 'data': self.state})
        for text in ('방송 시작 대기 · 발로란트', '카테고리 검증 대기 · 발로란트', '카테고리 변경 실패'):
            with self.subTest(text=text):
                w.on_event({'kind': 'status', 'text': text})
                w.tray_popup.refresh()
                self.assertEqual(w.tray_popup.status_text.text(), text)
        w.on_event({'kind': 'detected_games', 'data': []})
        w.on_event({'kind': 'status', 'text': '게임 감지 오류'})
        w.tray_popup.refresh()
        self.assertEqual(w.tray_popup.status_text.text(), '게임 감지 오류')
        self.assertEqual(w.tray_popup.last_line.text(), '현재 게임 · 없음')


class WorkerIdleStatusTests(unittest.TestCase):
    def test_saved_rules_do_not_imply_running_games(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch('worker.discord_cache_file', return_value=Path(directory)/'discord.json'):
            worker = Worker({'steam_lookup_enabled': False})
            self.addCleanup(worker.steam.close)
            self.addCleanup(worker.chzzk_open.close)
            worker.startup_talk_attempted = True
            worker.mapper.entries = {'unmapped.exe': [{'id': 'unmapped', 'name': 'Unmapped'}]}
            worker.config['auto_rules'] = [asdict(Rule('First.exe', 'first', 'First')),
                                           asdict(Rule('Second.exe', 'second', 'Second'))]
            cases = (([], '실행 중인 게임이 없습니다'),
                     (['Unmapped.exe'], '게임 카테고리 연결을 기다립니다'),
                     (['First.exe', 'Second.exe'], '여러 게임'))
            for processes, expected in cases:
                with self.subTest(processes=processes), \
                        patch('worker.process_names', return_value=processes), \
                        patch.object(worker, 'maybe_sync_auto'):
                    worker.scan()
                    self.assertIn(expected, worker.last_status)


if __name__ == '__main__':
    unittest.main()
