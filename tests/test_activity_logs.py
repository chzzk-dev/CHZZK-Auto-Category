import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from diagnostics import activity_parts
from main import Window, apply_light_theme
from storage import normalize_config
from worker import Worker


class MatchingLogTests(unittest.TestCase):
    def test_repeated_search_cycles_keep_states_but_only_one_main_result(self):
        with tempfile.TemporaryDirectory() as directory, patch('worker.discord_cache_file', return_value=Path(directory)/'discord.json'):
            worker = Worker({'steam_lookup_enabled': False})
        events = []
        worker.event.connect(events.append)
        game = {'id': 'game', 'name': 'Smilemo'}
        worker.pipeline.snapshot(['Smilemo.exe'])
        for _ in range(20):
            for stage in ('분석 중', '검색 중', '검증 중', '확인 필요'):
                worker.observe_matching(game, 'Smilemo.exe', stage)
        main = [e for e in events if e['kind'] == 'log' and not e.get('detail')]
        self.assertEqual(len(main), 1)
        self.assertIn('카테고리 확인 필요', main[0]['text'])
        self.assertEqual(len([e for e in events if e['kind'] == 'pipeline_state']), 80)
        self.assertGreater(len([e for e in events if e.get('detail')]), 60)
        worker.observe_matching(game, 'Smilemo.exe', '연결 완료', category_id='verified', category_name='스마일모')
        self.assertIn('스마일모', events[-1]['text'])
        self.assertFalse(events[-1].get('detail', False))

    def test_exit_and_relaunch_allow_a_new_summary(self):
        with tempfile.TemporaryDirectory() as directory, patch('worker.discord_cache_file', return_value=Path(directory)/'discord.json'):
            worker = Worker({'steam_lookup_enabled': False})
        events = []
        worker.event.connect(events.append)
        game = {'id': 'game', 'name': 'Smilemo'}
        worker.pipeline.snapshot(['Smilemo.exe'])
        worker.observe_matching(game, 'Smilemo.exe', '확인 필요')
        with patch('worker.process_names', return_value=[]):
            worker.refresh_processes(force=True)
        with patch('worker.process_names', return_value=['Smilemo.exe']):
            worker.refresh_processes(force=True)
        worker.observe_matching(game, 'Smilemo.exe', '분석 중')
        worker.observe_matching(game, 'Smilemo.exe', '확인 필요')
        self.assertEqual(len([e for e in events if e['kind'] == 'log' and not e.get('detail')]), 2)


class ActivityLogUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        apply_light_theme(cls.app)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        environment = patch.dict(os.environ, {'LOCALAPPDATA': self.temp.name})
        environment.start()
        self.addCleanup(environment.stop)
        self.window = Window(normalize_config({'autostart': False, 'auto_start_change': False,
                                              'auto_update': False}), preview=True)
        self.addCleanup(self.window.deleteLater)

    def test_connection_poll_is_quiet_but_change_and_recovery_remain_visible(self):
        w = self.window
        connected = {'kind': 'checked', 'text': '연결 성공 · 프랫폴', 'category_name': '프랫폴'}
        for _ in range(20):
            w.on_event(connected)
        self.assertEqual(len(w.log_entries), 1)
        w.on_event({'kind': 'error', 'operation': 'check', 'text': '치지직 연결 실패'})
        w.on_event(connected)
        w.on_event(dict(connected, text='연결 성공 · 스마일모', category_name='스마일모'))
        self.assertEqual(len(w.log_entries), 4)
        self.assertTrue(w.connection_verified)
        self.assertEqual(w.last_category, '스마일모')

    def test_details_are_preserved_without_polluting_main_or_dashboard(self):
        w = self.window
        w.append_log('[자동 매칭] Smilemo · 카테고리 확인 필요')
        for _ in range(3):
            w.on_event({'kind': 'log', 'text': '[카테고리 검색] Smilemo.exe · 분석 중', 'detail': True})
            w.append_log('[자동 매칭] Smilemo · 카테고리 확인 필요')
        self.assertEqual(len(w.recent_activity), 1)
        self.assertNotIn('분석 중', w.log.toPlainText())
        self.assertEqual(w.log.toPlainText().count('카테고리 확인 필요'), 1)
        self.assertNotIn('[자동 매칭]', w.log.toPlainText())
        w.log_details.setChecked(True)
        self.assertIn('분석 중', w.log.toPlainText())
        w.log_filter.setCurrentText('카테고리 검색')
        self.assertNotIn('카테고리 확인 필요', w.log.toPlainText())
        w.log_details.setChecked(False)
        w.log_filter.setCurrentText('전체')
        for _ in range(1050):
            w.append_log('[카테고리 검색] 반복 중간 과정', detail=True)
        self.assertEqual(len(w.log_detail_entries), 1000)
        self.assertEqual(len(w.log_entries), 1)
        self.assertIn('카테고리 확인 필요', w.log.toPlainText())

    def test_clear_survives_filter_changes_and_html_is_escaped(self):
        w = self.window
        w.append_log('[오류] <b>literal</b> api_key=do-not-display')
        self.assertIn('<b>literal</b>', w.log.toPlainText())
        self.assertNotIn('do-not-display', w.log.toPlainText())
        w.copy_logs()
        copied = self.app.clipboard().text()
        self.assertIn('[오류] <b>literal</b>', copied)
        self.assertEqual(len(copied.splitlines()), 1)
        self.assertNotIn('do-not-display', copied)
        self.assertEqual(activity_parts('[자동 매칭] 연결 완료'), ('자동 매칭', '연결 완료'))
        w.clear_logs()
        w.log_details.setChecked(True)
        w.log_filter.setCurrentText('오류')
        self.assertNotIn('literal', w.log.toPlainText())
        self.assertEqual(len(w.log_entries), 0)
        self.assertEqual(len(w.log_detail_entries), 0)
        self.assertEqual(len(w.recent_activity), 0)

    def test_new_log_does_not_jump_when_reading_earlier_rows(self):
        w = self.window
        w.resize(1200, 820)
        w.nav.setCurrentRow(5)
        w.show()
        for i in range(45):
            w.append_log(f'[게임 감지] Game{i}.exe 실행 감지')
        self.app.processEvents()
        from PySide6.QtGui import QTextTable
        table = next(frame for frame in w.log.document().rootFrame().childFrames() if isinstance(frame, QTextTable))
        self.assertEqual(table.cellAt(1, 0).firstCursorPosition().block().layout().lineCount(), 1)
        bar = w.log.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        bar.setValue(0)
        w.append_log('[게임 감지] New.exe 실행 감지')
        self.app.processEvents()
        self.assertEqual(bar.value(), 0)
        w.hide()


if __name__ == '__main__':
    unittest.main()
