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
from main import Window, apply_light_theme
from storage import normalize_config
from app_icons import validate_icons


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
        checks = []
        for width, height in ((1200, 820), (1440, 960)):
            w.resize(width, height)
            for i in range(6):
                w.nav.setCurrentRow(i)
                app.processEvents()
                page = w.pages.currentWidget()
                assert page.width() > 0 and page.height() > 0
                assert w.page_title.geometry().intersects(w.toggle_button.geometry()) is False
                assert w.grab().save(str(destination / f'page-{i}-{width}.png'))
                checks.append({'page': i, 'width': width, 'height': height, 'title': w.page_title.text()})
        w.tray_popup.show()
        app.processEvents()
        assert w.tray_popup.grab().save(str(destination / 'tray.png'))
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
    print(f'Qt scale {os.environ.get("QT_SCALE_FACTOR", "1")}: 12 page/size renders, icons, popup and restore passed')


if __name__ == '__main__':
    main()
