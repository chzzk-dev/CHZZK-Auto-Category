import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from updater import AutoUpdateWindow, fetch_latest_release
from updater_app import UpdaterWindow


class UpdateUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def release(self):
        return {'version': '4.12.12', 'release_tag': 'v4.12.12',
                'release_notes': '### 변경 사항\n\n- 트레이 상태 표시 개선\n- UI 개선'}

    def prompt(self):
        window = AutoUpdateWindow(self.release())
        self.addCleanup(window.deleteLater)
        return window

    def progress_window(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        window = UpdaterWindow(0, '4.12.12', temp.name, restart=False, auto_start=False)
        self.addCleanup(window.deleteLater)
        return window, Path(temp.name)

    def test_release_metadata_preserves_notes_without_requesting_another_resource(self):
        payload = {'tag_name': 'v4.12.12', 'body': '**실제 변경 내용**',
                   'published_at': '2026-10-23T00:00:00Z', 'assets': [
                       {'name': 'ChzzkAutoCategory-4.12.12.msi',
                        'browser_download_url': 'https://example.test/app.msi', 'size': 10}]}
        with patch('updater._github_request', return_value=io.BytesIO(json.dumps(payload).encode())) as request:
            result = fetch_latest_release()
        self.assertEqual(result['release_notes'], payload['body'])
        self.assertEqual(result['published_at'], payload['published_at'])
        request.assert_called_once()

    def test_release_notes_are_visible_and_opening_never_launches_the_installer(self):
        window = self.prompt()
        self.assertIn('트레이 상태 표시 개선', window.notes.toPlainText())
        with patch('updater.launch_external_updater') as launch:
            window.show()
            QTest.qWait(600)
            launch.assert_not_called()
        self.assertTrue(window.update_button.isEnabled())
        self.assertFalse(window.started)
        window.hide()

    def test_click_starts_one_handoff_and_failure_allows_retry(self):
        window = self.prompt()
        with patch('updater.launch_external_updater', side_effect=RuntimeError('실행 파일이 없습니다.')) as launch:
            window.update_button.click()
            self.assertIn('실패', window.status_label.text())
            self.assertIn('실행 파일이 없습니다', window.detail_label.text())
            self.assertTrue(window.update_button.isEnabled())
            self.assertFalse(window.started)
            launch.assert_called_once()
        with patch('updater.launch_external_updater') as launch, patch.object(window, '_quit_owner'):
            window.update_button.click()
            window.start_updater()
            launch.assert_called_once()
            self.assertTrue(window.started)
            self.assertFalse(window.update_button.isEnabled())
        window.anim.stop()

    def test_later_preserves_release_and_missing_notes_have_an_honest_empty_state(self):
        window = AutoUpdateWindow({'version': '4.12.12'})
        self.addCleanup(window.deleteLater)
        deferred = []
        window.deferred.connect(deferred.append)
        self.assertIn('변경 내용이 제공되지 않았습니다', window.notes.toPlainText())
        window.show()
        window.close_button.click()
        self.assertEqual(deferred, [{'version': '4.12.12'}])

    def test_compact_windows_keep_notes_scrollable_and_actions_inside_at_minimum_size(self):
        prompt = self.prompt()
        prompt.notes.setMarkdown('\n\n'.join(f'- 변경 사항 {i}' for i in range(100)))
        prompt.resize(prompt.minimumSize())
        prompt.show()
        self.app.processEvents()
        self.assertGreater(prompt.notes.verticalScrollBar().maximum(), 0)
        for button in (prompt.update_button, prompt.close_button):
            self.assertTrue(button.parentWidget().rect().contains(button.geometry()))
        self.assertLess(prompt.width(), 700)
        prompt.hide()
        progress, _ = self.progress_window()
        progress.resize(progress.minimumSize())
        progress.show()
        self.app.processEvents()
        for button in (progress.launch_button, progress.close_button):
            self.assertTrue(button.parentWidget().rect().contains(button.geometry()))
        self.assertLess(progress.width(), 700)
        progress.hide()

    def test_finished_and_failed_downloads_stop_old_progress_animation(self):
        window, directory = self.progress_window()
        window.set_progress(75)
        window.update_done(str(directory/'new.exe'))
        QTest.qWait(320)
        self.assertEqual(window.progress.value(), 100)
        self.assertTrue(window.launch_button.isEnabled())
        self.assertTrue(window.close_button.isEnabled())
        window.set_progress(80)
        old = directory/'ChzzkAutoCategory.exe'
        old.write_bytes(b'previous')
        window.update_failed('설치 취소')
        QTest.qWait(320)
        self.assertEqual(window.progress.value(), 0)
        self.assertIn('실패', window.status_label.text())
        self.assertEqual(window.exe_path, str(old))
        self.assertTrue(window.launch_button.isEnabled())

    def test_reboot_required_disables_launch_without_automatic_reboot(self):
        window, _ = self.progress_window()
        window.worker.reboot_required = True
        window.update_done('new.exe')
        self.assertFalse(window.launch_button.isEnabled())
        self.assertTrue(window.close_button.isEnabled())
        self.assertIn('다시 시작', window.detail_label.text())


if __name__ == '__main__':
    unittest.main()
