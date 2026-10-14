import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QTableView
from main import Window, apply_light_theme
from core import Rule
from storage import normalize_config, load_config
from app_icons import validate_icons
from theme import TOKENS


class ModernUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        apply_light_theme(cls.app)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'LOCALAPPDATA': self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.window = Window(normalize_config({'autostart': False, 'auto_start_change': False,
                                              'auto_update': False}), preview=True)
        self.addCleanup(self.window.deleteLater)

    def test_six_pages_default_dashboard_and_reused_widgets(self):
        w = self.window
        self.assertEqual(w.nav.count(), 6)
        self.assertEqual(w.pages.count(), 6)
        self.assertEqual(w.pages.currentIndex(), 0)
        identities = [id(w.pages.widget(i)) for i in range(6)]
        for _ in range(2):
            for i in range(6):
                w.nav.setCurrentRow(i)
                self.app.processEvents()
                self.assertEqual(w.pages.currentIndex(), i)
        self.assertEqual([id(w.pages.widget(i)) for i in range(6)], identities)
        self.assertEqual(w.minimumWidth(), 1200)
        self.assertEqual(w.minimumHeight(), 820)
        self.assertEqual(TOKENS['background'], '#F3F1EB')

    def test_all_offline_icons_render(self):
        self.assertTrue(validate_icons())
        for i in range(6):
            self.assertFalse(self.window.nav.item(i).icon().isNull())

    def test_model_table_filters_and_priority_selection(self):
        w = self.window
        w.rules = [Rule('Manual.exe', 'manual', '수동 게임', game_name='Manual')]
        w.auto_rules = [Rule('Auto.exe', 'auto', '자동 게임', game_name='Auto')]
        w.refresh_table()
        self.assertIsInstance(w.table, QTableView)
        self.assertEqual(w.game_model.rowCount(), 2)
        w.game_filter.setCurrentText('수동 연결')
        self.assertEqual(w.game_model.rowCount(), 1)
        w.select_rule_location('manual', 0)
        self.assertEqual(w.selected_rule_location(), {'kind': 'manual', 'index': 0})
        w.game_filter.setCurrentText('전체')
        w.rule_filter.setText('auto')
        self.assertEqual(w.game_model.rowCount(), 1)
        self.assertEqual(w.game_model.rows[0]['game'], 'Auto')

    def test_large_table_uses_model_and_retains_selection(self):
        w = self.window
        w.rules = [Rule(f'Game{i}.exe', str(i), f'Game {i}') for i in range(3000)]
        w.refresh_table()
        self.assertEqual(w.game_model.rowCount(), 3000)
        w.select_rule_location('manual', 2500)
        w.refresh_table()
        self.assertEqual(w.selected_rule_location()['index'], 2500)

    def test_pending_items_are_a_game_filter_not_an_apply_queue(self):
        w = self.window
        w.on_event({'kind': 'auto_pending', 'data': [{'process': 'Unresolved.exe', 'games': ['Unknown'], 'reason': 'category-not-found'}]})
        w.game_filter.setCurrentText('미확정')
        self.assertEqual(w.game_model.rowCount(), 1)
        self.assertEqual(w.game_model.rows[0]['state'], '확인 필요')
        self.assertEqual(w.rules, [])
        self.assertEqual(w.auto_rules, [])

    def test_state_and_game_exit_drive_real_dashboard_fields(self):
        w = self.window
        w.on_event({'kind': 'pipeline_state', 'data': {'key': 'mc', 'process': 'Minecraft.exe',
                    'game_name': 'Minecraft', 'stage': '검색 중', 'running': True, 'representative': True}})
        self.assertEqual(w.dashboard_game.text(), 'Minecraft')
        self.assertIn('검색 중', w.dashboard_game_meta.text())
        w.on_event({'kind': 'detected_games', 'data': []})
        self.assertEqual(w.dashboard_game.text(), '현재 실행 중인 게임이 없습니다.')
        self.assertEqual(w.dashboard_values['extension'][1].text(), '버전: 확인할 수 없음')

    def test_mandatory_matching_and_hour_settings_persist(self):
        w = self.window
        self.assertTrue(w.auto_aggressive.isChecked())
        self.assertFalse(w.auto_aggressive.isEnabled())
        self.assertGreaterEqual(min(w.update_check_interval.itemData(i) for i in range(w.update_check_interval.count())), 60)
        w.update_check_interval.setCurrentIndex(w.update_check_interval.findData(1440))
        w.category_sync.setCurrentIndex(w.category_sync.findData(3))
        w.allow_prerelease.setChecked(True)
        with patch('main.set_windows_autostart'):
            w.save_options()
        c = load_config()
        self.assertEqual(c['update_check_minutes'], 1440)
        self.assertEqual(c['category_sync_hours'], 3)
        self.assertTrue(c['allow_prerelease'])
        self.assertTrue(c['auto_aggressive'])

    def test_recent_activities_bounded_and_sensitive_data_redacted(self):
        from diagnostics import redact
        w = self.window
        for i in range(10):
            w.append_log(f'[게임 감지] Game{i}.exe')
        self.assertEqual(len(w.recent_activity), 5)
        self.assertNotIn('Game0.exe', w.dashboard_activity.text())
        self.assertNotIn('topsecret', redact('Client-Secret=topsecret token info'))
        w.log_filter.setCurrentText('업데이트')
        w.append_log('[업데이트] 확인 완료')
        self.assertIn('업데이트', w.log.toPlainText())
        self.assertNotIn('Game', w.log.toPlainText())

    def test_tray_navigation_restoration_maps_old_shortcuts(self):
        w = self.window
        with patch.object(w, 'show_main'):
            for old, new in ((2, 3), (4, 5), (5, 4), (6, 4), (3, 1)):
                w.open_page_from_tray(old)
                self.assertEqual(w.pages.currentIndex(), new)

    def test_manual_update_check_is_independent_of_disabled_auto_schedule(self):
        w = self.window
        w.preview = False
        w.config['auto_update'] = False
        with patch('main.sys.platform', 'win32'), patch('main.sys.frozen', True, create=True), \
                patch('main.UpdateCheckWorker') as checker:
            w.check_for_updates_manual()
        checker.return_value.start.assert_called_once()
        self.assertGreater(w.config['update_last_checked_at'], 0)

    def test_authorization_cookie_and_json_secrets_are_redacted(self):
        from diagnostics import redact
        for value in ('Authorization: Bearer private', 'Cookie: session=private',
                      "{'Client-Secret': 'private'}", 'access_token=private'):
            self.assertNotIn('private', redact(value))

    def test_keyboard_navigation_switches_existing_pages(self):
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt
        w = self.window
        w.show()
        w.nav.setCurrentRow(0)
        w.nav.setFocus()
        self.app.processEvents()
        QTest.keyClick(w.nav, Qt.Key.Key_Down)
        self.assertEqual(w.pages.currentIndex(), 1)
        QTest.keyClick(w.nav, Qt.Key.Key_Down)
        self.assertEqual(w.pages.currentIndex(), 2)
        w.hide()


if __name__ == '__main__':
    unittest.main()
