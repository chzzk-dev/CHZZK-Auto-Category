from datetime import date, timedelta
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.request

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QToolButton
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from main import Window, apply_light_theme
from storage import normalize_config


class DashboardFocusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        apply_light_theme(cls.app)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        environment = patch.dict(os.environ, {'LOCALAPPDATA': temporary.name})
        environment.start()
        self.addCleanup(environment.stop)
        self.window = Window(normalize_config({'autostart': False, 'auto_start_change': False,
                                              'auto_update': False, 'update_notify': False}), preview=True)
        self.addCleanup(self.window.deleteLater)

    def test_dashboard_hides_secondary_navigation_and_footer_without_losing_other_pages(self):
        w = self.window
        w.show()
        self.app.processEvents()
        self.assertFalse(w.navigation_sidebar.isVisible())
        self.assertFalse(w.page_title.isVisible())
        self.assertTrue(w.icon_rail.isVisible())
        self.assertEqual(len(w.dashboard_metric_cards), 4)
        self.assertEqual([w.dashboard_period.itemData(i) for i in range(3)], [1, 7, 30])
        w.rail_buttons[1][0].click()
        self.app.processEvents()
        self.assertTrue(w.navigation_sidebar.isVisible())
        self.assertTrue(w.page_title.isVisible())
        self.assertFalse(w.findChild(QFrame, 'sidebarStatus').isVisible())
        self.assertFalse(w.findChild(QPushButton, 'sidebarTrayButton').isVisible())
        w.rail_buttons[0][0].click()
        self.assertEqual(w.pages.currentIndex(), 0)
        self.assertFalse(w.navigation_sidebar.isVisible())
        w.hide()

    def test_hero_switch_uses_existing_enable_command_and_tracks_confirmed_state(self):
        w = self.window
        w.config['channel'] = 'a' * 32
        with patch.object(w.worker, 'submit') as submit:
            w.dashboard_toggle.click()
            submit.assert_called_once_with('enable', True)
        w.on_event({'kind': 'enabled', 'value': True})
        w.connection_verified = True
        w.refresh_dashboard()
        self.assertTrue(w.dashboard_toggle.isChecked())
        self.assertEqual(w.dashboard_ring.state, 'running')
        with patch.object(w.worker, 'submit') as submit:
            w.dashboard_toggle.click()
            submit.assert_called_once_with('enable', False)
        w.on_event({'kind': 'enabled', 'value': False})
        self.assertFalse(w.dashboard_toggle.isChecked())
        self.assertEqual(w.dashboard_ring.state, 'paused')

    def test_period_selector_changes_real_daily_totals_without_recording_extra_events(self):
        w = self.window
        today = date.today()
        w.activity_stats.days = {
            today.isoformat(): {'detected': 1},
            (today - timedelta(days=6)).isoformat(): {'detected': 2},
            (today - timedelta(days=29)).isoformat(): {'detected': 4}}
        for period, expected in ((1, '1'), (7, '3'), (30, '7')):
            w.dashboard_period.setCurrentIndex(w.dashboard_period.findData(period))
            w.refresh_dashboard_statistics()
            self.assertEqual(w.dashboard_metrics['detected'].text(), expected)

    def test_calendar_opens_period_menu_and_mouse_selection_changes_the_period(self):
        w = self.window
        w.show()
        self.app.processEvents()
        self.addCleanup(w.dashboard_period.hidePopup)
        w.findChild(QToolButton, 'dashboardCalendar').click()
        self.app.processEvents()
        view = w.dashboard_period.view()
        self.assertTrue(view.isVisible())
        target = view.visualRect(view.model().index(2, 0)).center()
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=target)
        self.assertEqual(w.dashboard_period.currentData(), 30)
        w.dashboard_period.hidePopup()
        w.hide()

    def test_authenticated_extension_info_updates_about_update_and_dashboard_and_expires(self):
        w = self.window
        bridge = w.bridge
        bridge.port = 0
        bridge.start()
        self.addCleanup(bridge.stop)
        extension_id = bridge.extension_id
        version = json.loads((Path(__file__).resolve().parent.parent / 'extension/manifest.json').read_text())['version']
        payload = {'type': 'extension_info', 'extensionId': extension_id, 'version': version,
                   'protocolVersion': 1, 'browser': 'Edge', 'connected': True, 'sessionId': 'ui-test', 'sequence': 1}
        request = urllib.request.Request(f'http://127.0.0.1:{bridge.server.server_address[1]}/extension/info',
            data=json.dumps(payload).encode(), headers={'Origin': 'chrome-extension://' + extension_id,
                'X-Extension-Id': extension_id, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=3) as response:
            self.assertEqual(response.status, 200)
        w.refresh_connection_page()
        for note in (w.about_extension_label, w.update_extension_label, w.dashboard_extension):
            self.assertIn(version, note.text())
            self.assertIn('Edge', note.text())
        bridge.connected_at = time.monotonic() - 41
        w.refresh_connection_page()
        for note in (w.about_extension_label, w.update_extension_label, w.dashboard_extension):
            self.assertNotIn(version, note.text())

    def test_update_results_stay_inline_across_navigation_and_connection_refresh(self):
        w = self.window
        with patch('main.show_info') as info, patch('main.show_warning') as warning:
            w.manual_update_check = True
            w.on_update_check_completed(None)
            w.nav.setCurrentRow(4)
            w.setting_tabs.setCurrentIndex(1)
            w.refresh_connection_page()
            self.assertIn('최신 버전', w.update_page_status.text())
            self.assertIn('최신 버전', w.dashboard_update_status.text())
            w.manual_update_check = True
            w.on_update_check_failed('네트워크 연결을 확인해 주세요.')
            w.refresh_update_page()
            w.refresh_connection_page()
            self.assertIn('확인하지 못했습니다', w.update_page_status.text())
            self.assertIn('네트워크', w.update_page_detail.text())
            info.assert_not_called()
            warning.assert_not_called()
        self.assertFalse(any('버전 정책' in note.text() for note in w.findChildren(QLabel)))

    def test_available_update_is_reopened_from_dashboard_without_a_second_check(self):
        w = self.window
        release = {'version': '9.0.0', 'release_tag': 'v9.0.0'}
        with patch.object(w, 'open_update_window') as open_window:
            w.on_update_check_completed(release)
            w.refresh_connection_page()
            self.assertIn('9.0.0', w.update_page_status.text())
            self.assertFalse(w.install_update_button.isHidden())
            with patch.object(w, 'check_for_updates_manual') as check:
                w.dashboard_update_button.click()
                check.assert_not_called()
            self.assertEqual(open_window.call_args.args[0], release)

    def test_update_check_disables_duplicate_actions_and_allows_retry_after_failure(self):
        w = self.window
        w.preview = False
        with patch('main.sys.platform', 'win32'), patch('main.sys.frozen', True, create=True), patch('main.UpdateCheckWorker') as checker:
            w.check_for_updates_manual()
            self.assertFalse(w.update_check_button.isEnabled())
            self.assertFalse(w.dashboard_update_button.isEnabled())
            checker.return_value.start.assert_called_once()
            w.on_update_check_failed('일시적인 연결 오류')
            w.clear_update_check_worker()
            self.assertTrue(w.update_check_button.isEnabled())
            w.check_for_updates_manual()
            self.assertEqual(checker.return_value.start.call_count, 2)
        w.update_check_worker = None
        w.preview = True

    def test_help_about_and_settings_rail_controls_open_their_real_destinations(self):
        w = self.window
        w.rail_about_button.click()
        self.assertEqual(w.pages.currentIndex(), 4)
        self.assertEqual(w.setting_tabs.currentIndex(), 2)
        self.assertTrue(w.rail_about_button.property('active'))
        w.rail_buttons[4][0].click()
        self.assertEqual(w.setting_tabs.currentIndex(), 0)
        observed = []
        def open_connections():
            dialog = self.app.activeModalWidget()
            if dialog is None:
                return
            observed.append(dialog.windowTitle())
            target = next((button for button in dialog.findChildren(QPushButton) if button.text() == '연결 관리'), None)
            if target:
                target.click()
            else:
                dialog.reject()
        QTimer.singleShot(0, open_connections)
        w.rail_help_button.click()
        self.assertEqual(observed, ['사용 안내'])
        self.assertEqual(w.pages.currentIndex(), 3)

    def test_only_actual_category_changes_increment_the_change_card(self):
        w = self.window
        for changed in (False, True, False):
            w.on_event({'kind': 'applied', 'text': 'Game.exe → 게임', 'category_name': '게임', 'changed': changed})
        self.assertEqual(w.dashboard_metrics['changed'].text(), '1')
