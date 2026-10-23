"""Render the actual Qt app without accounts/network; run per QT_SCALE_FACTOR."""
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from PySide6.QtGui import QFontDatabase
from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from main import Window, apply_light_theme
from storage import normalize_config
from app_icons import validate_icons
from core import Rule


def save_preview(widget, path):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not widget.grab().save(buffer, 'PNG'):
        return False
    buffer.close()
    payload = bytes(data)
    if not payload.endswith(bytes.fromhex('0000000049454e44ae426082')):
        return False
    path.write_bytes(payload)
    return True


def render_update_windows(app, destination):
    from updater import AutoUpdateWindow
    from updater_app import UpdaterWindow
    # Preview fixtures only: the real installer and network are never started.
    prompt = AutoUpdateWindow({'version': '4.12.12', 'release_notes':
        '### 변경 사항\n\n- 업데이트 화면을 새 디자인으로 정리했습니다.\n- 진행 상태와 변경 내역을 확인할 수 있습니다.'})
    prompt.show()
    app.processEvents()
    assert not prompt.started and prompt.update_button.isEnabled()
    assert save_preview(prompt, destination / 'update-prompt.png')
    prompt.hide()
    with tempfile.TemporaryDirectory() as directory:
        progress = UpdaterWindow(0, '4.12.12', directory, restart=False, auto_start=False)
        progress.show()
        progress.set_status('업데이트 다운로드 중')
        progress.set_progress(62)
        progress._progress_anim.setCurrentTime(280)
        app.processEvents()
        assert progress.progress.value() == 62
        assert save_preview(progress, destination / 'update-download.png')
        progress.update_done(str(Path(directory) / 'app.exe'))
        app.processEvents()
        assert progress.progress.value() == 100 and progress.launch_button.isEnabled()
        assert save_preview(progress, destination / 'update-complete.png')
        progress.update_failed('설치를 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.')
        app.processEvents()
        assert progress.close_button.isEnabled()
        for widget in (progress.launch_button, progress.close_button):
            assert widget.parentWidget().rect().contains(widget.geometry())
        assert save_preview(progress, destination / 'update-error.png')
        progress.hide()
        progress.deleteLater()
    prompt.deleteLater()
    app.processEvents()


def render_game_list_states(window, app, destination, width):
    window.nav.setCurrentRow(1)
    window.game_tabs.setCurrentIndex(0)
    original = (window.rules, window.auto_rules, window.auto_pending, window.runtime_games)
    try:
        window.rules, window.auto_rules, window.auto_pending, window.runtime_games = [], [], [], {}
        window.refresh_table()
        app.processEvents()
        bounds = (window.table.geometry(), window.rule_selection_info.geometry())
        columns = [window.table.columnWidth(i) for i in range(window.game_model.columnCount())]
        assert window.table.isVisible() and window.table.horizontalHeader().isVisible()
        assert window.rule_empty.isVisible()
        assert window.table.viewport().rect().contains(window.rule_empty.geometry())
        assert save_preview(window.game_tabs.widget(0), destination / f'games-empty-{width}.png')
        window.rules = [Rule('Minecraft.exe', 'minecraft', '마인크래프트', game_name='Minecraft')]
        window.auto_rules = [Rule('VALORANT-Win64-Shipping.exe', 'valorant', '발로란트', game_name='VALORANT')]
        window.runtime_games = {'valorant': {'process': 'VALORANT-Win64-Shipping.exe', 'running': True, 'stage': '감지됨'}}
        window.refresh_table()
        window.select_rule_location('auto', 0)
        app.processEvents()
        assert not window.rule_empty.isVisible() and window.game_model.rowCount() == 2
        assert bounds == (window.table.geometry(), window.rule_selection_info.geometry())
        assert columns == [window.table.columnWidth(i) for i in range(window.game_model.columnCount())]
        assert save_preview(window.game_tabs.widget(0), destination / f'games-populated-{width}.png')
        window.rule_filter.setText('검색 결과가 없는 게임')
        app.processEvents()
        assert window.rule_empty.isVisible() and 'VALORANT' not in window.rule_selection_info.text()
        assert bounds == (window.table.geometry(), window.rule_selection_info.geometry())
        assert columns == [window.table.columnWidth(i) for i in range(window.game_model.columnCount())]
        assert save_preview(window.game_tabs.widget(0), destination / f'games-filtered-{width}.png')
        window.rule_empty_action.click()
        app.processEvents()
        assert window.game_model.rowCount() == 2 and not window.rule_empty.isVisible()
    finally:
        window.rules, window.auto_rules, window.auto_pending, window.runtime_games = original
        window.rule_filter.clear()
        window.game_filter.setCurrentIndex(0)
        window.refresh_table()


def main():
    app = QApplication([])
    font = os.environ.get('CHZZK_UI_TEST_FONT')
    if font:
        if QFontDatabase.addApplicationFont(font) < 0:
            raise RuntimeError('Preview font could not be loaded')
    apply_light_theme(app)
    destination = ROOT / 'build' / 'ui-previews' / os.environ.get('QT_SCALE_FACTOR', '1')
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        os.environ['LOCALAPPDATA'] = d
        w = Window(normalize_config({'autostart': False, 'auto_update': False,
                                     'auto_start_change': False}), preview=True)
        w.show()
        app.processEvents()
        assert w.pages.count() == w.nav.count() == 6
        assert validate_icons()
        # Explicit preview fixtures exercise populated log layout; these are not live activity.
        w.append_log('[게임 감지] Smilemo 실행 감지')
        w.append_log('[카테고리 검색] Smilemo.exe · 분석 중', detail=True)
        w.append_log('[자동 매칭] Smilemo → 스마일모 · 카테고리 연결 완료')
        w.append_log('[카테고리 변경] 변경 완료 · Smilemo.exe → 스마일모')
        checks = []
        for width, height in ((1200, 820), (1360, 860), (1440, 960)):
            w.resize(width, height)
            for i in range(6):
                w.nav.setCurrentRow(i)
                app.processEvents()
                page = w.pages.currentWidget()
                assert page.width() > 0 and page.height() > 0
                assert w.page_title.geometry().intersects(w.toggle_button.geometry()) is False
                if i == 0:
                    cards = w.dashboard_summary_cards
                    assert max(c.width() for c in cards) - min(c.width() for c in cards) <= 1
                    assert w.dashboard_game_card.height() < 220
                    assert w.dashboard_activity_card.y() > w.dashboard_game_card.geometry().bottom()
                    assert w.dashboard.horizontalScrollBar().maximum() == 0
                if i == 5:
                    assert '시간' in w.log.toPlainText() and '스마일모' in w.log.toPlainText()
                    assert '분석 중' not in w.log.toPlainText()
                    for control in (w.log_filter, w.log_details):
                        assert control.parentWidget().rect().contains(control.geometry())
                assert save_preview(w, destination / f'page-{i}-{width}.png')
                checks.append({'page': i, 'width': width, 'height': height, 'title': w.page_title.text()})
            render_game_list_states(w, app, destination, width)
            w.nav.setCurrentRow(3)
            w.connection_tabs.setCurrentIndex(2)
            app.processEvents()
            assert save_preview(w, destination / f'steam-connection-{width}.png')
            w.connection_tabs.setCurrentIndex(0)
        w.tray_popup.show()
        app.processEvents()
        assert save_preview(w.tray_popup, destination / 'tray.png')
        w.tray_popup.hide()
        w.hide()
        w.show_main()
        app.processEvents()
        assert w.isVisible()
        w.quitting = True
        w.close()
        w.deleteLater()
        app.processEvents()
    (destination / 'checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
    render_update_windows(app, destination)
    print(f'Qt scale {os.environ.get("QT_SCALE_FACTOR", "1")}: 18 page/size renders, dashboard alignment, icons, popup and restore passed')
    print('Update prompt, download, completion and error previews passed without starting the installer')
    print('Empty, populated and filtered game lists retained their table/header/footer geometry at all three sizes')


if __name__ == '__main__':
    main()
