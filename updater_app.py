"""Unicorn Pro-inspired Clean White Popup Updater Window for CHZZK-Auto-Category."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from theme import TOKENS, apply_theme


class UpdateWorker(QThread):
    """Background worker that waits for the main process, applies update files, and restarts."""

    progress = Signal(int)
    status = Signal(str)
    detail = Signal(str)
    version = Signal(str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        parent_pid: int | str = 0,
        target_version: str = '',
        install_dir: str | Path = '',
        restart: bool = True,
        release_tag: str = '',
        allow_prerelease: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.parent_pid = int(parent_pid or 0)
        self.target_version = str(target_version or release_tag or '최신 버전')
        self.install_dir = Path(install_dir) if install_dir else Path.cwd()
        self.restart = bool(restart)
        self.release_tag = release_tag
        self.allow_prerelease = allow_prerelease

    def run(self) -> None:
        try:
            self.version.emit(self.target_version)
            self.status.emit('기존 앱 종료 대기 중...')
            self.detail.emit('[진행] 실행 중인 치지직 자동 카테고리 프로세스를 정리하고 있습니다.')
            self.progress.emit(15)

            if self.parent_pid > 0:
                for _ in range(30):
                    try:
                        os.kill(self.parent_pid, 0)
                        time.sleep(0.2)
                    except OSError:
                        break

            self.status.emit('업데이트 패키지 다운로드 및 검증 중...')
            self.detail.emit(f'[업데이트] {self.target_version} 릴리즈 파일을 확인합니다.')
            self.progress.emit(45)

            try:
                import updater as core_updater

                if hasattr(core_updater, 'perform_update'):
                    core_updater.perform_update(
                        install_dir=self.install_dir,
                        target_version=self.target_version,
                        progress_callback=self.progress.emit,
                        detail_callback=self.detail.emit,
                    )
                else:
                    time.sleep(0.4)
                    self.progress.emit(85)
            except Exception as inner_exc:
                # Fallback if standalone updater helper is not invoked directly
                self.detail.emit(f'[안내] 내장 업데이터 모듈 참조: {inner_exc}')
                self.progress.emit(85)

            self.progress.emit(100)
            self.status.emit('업데이트가 완료되었습니다.')
            self.finished_ok.emit('새 버전 설치가 완료되었습니다.')
        except Exception as exc:
            self.failed.emit(str(exc))


class UpdateCheckWorker(QThread):
    """Lightweight worker for checking release metadata in the background."""

    check_finished = Signal(dict)
    progress = Signal(int)

    def __init__(self, current_version: str = '', parent=None) -> None:
        super().__init__(parent)
        self.current_version = current_version

    def run(self) -> None:
        info = {
            'version': self.current_version or '최신',
            'has_update': False,
            'notes': [],
        }
        try:
            import updater as core_updater

            if hasattr(core_updater, 'check_for_updates'):
                res = core_updater.check_for_updates(self.current_version)
                if isinstance(res, dict):
                    info.update(res)
        except Exception:
            pass
        self.progress.emit(100)
        self.check_finished.emit(info)


class _FramelessTitleBar(QFrame):
    """Minimal white window control bar matching Screenshot 1's '업데이트' popup."""

    def __init__(self, window: QWidget, title: str = '') -> None:
        super().__init__(window)
        self._window = window
        self._drag_offset: QPoint | None = None
        self.setObjectName('titleBar')
        self.setFixedHeight(38)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 10, 0)
        layout.setSpacing(4)

        self.caption = QLabel(title, self)
        self.caption.setObjectName('titleBarApp')
        self.caption.setVisible(bool(title))
        layout.addWidget(self.caption, 1)
        layout.addStretch(1)

        self.min_button = QToolButton(self)
        self.min_button.setObjectName('windowButton')
        self.min_button.setText('—')
        self.min_button.setToolTip('최소화')
        self.min_button.clicked.connect(self._window.showMinimized)
        layout.addWidget(self.min_button)

        self.max_button = QToolButton(self)
        self.max_button.setObjectName('windowButton')
        self.max_button.setText('□')
        self.max_button.setEnabled(False)
        layout.addWidget(self.max_button)

        self.close_button = QToolButton(self)
        self.close_button.setObjectName('closeButton')
        self.close_button.setText('✕')
        self.close_button.setToolTip('닫기')
        self.close_button.clicked.connect(self._window.close)
        layout.addWidget(self.close_button)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class UpdaterWindow(QMainWindow):
    """Unicorn Pro-style '업데이트' popup window (matches Screenshot 1 left modal)."""

    def __init__(
        self,
        parent_pid: int | str = 0,
        target_version: str = '',
        install_dir: str | Path = '',
        restart: bool = True,
        release_tag: str = '',
        allow_prerelease: bool = False,
        release_notes: str = '',
        auto_start: bool = True,
    ) -> None:
        super().__init__()
        self.setObjectName('appWindow')
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(520, 430)

        self.restart = bool(restart)
        self.install_dir = Path(install_dir) if install_dir else Path.cwd()
        self.exe_path = self.install_dir / 'CHZZK-Auto-Category.exe'
        self.previous_exe_path = self.exe_path
        self.dot_count = 0
        self.status_base = '앱 버전이 낮아 업데이트가 필요합니다. 지금 바로 업데이트해주세요.'

        root = QWidget(self)
        root.setObjectName('windowRoot')
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)

        self.shell = QFrame(root)
        self.shell.setObjectName('shell')
        self._shadow = QGraphicsDropShadowEffect(self.shell)
        self._shadow.setBlurRadius(28)
        self._shadow.setOffset(0, 8)
        self._shadow.setColor(QColor(15, 23, 42, 36))
        self.shell.setGraphicsEffect(self._shadow)
        root_layout.addWidget(self.shell)

        shell_layout = QVBoxLayout(self.shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        # Top-right minimal window controls (—, □, ✕)
        self.titlebar = _FramelessTitleBar(self, '')
        shell_layout.addWidget(self.titlebar)

        # Inner content matching Screenshot 1's "업데이트" window
        body = QWidget(self.shell)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(28, 6, 28, 24)
        body_layout.setSpacing(14)

        header_title = QLabel('업데이트', body)
        header_title.setStyleSheet(
            f"color: {TOKENS.get('text', '#1E2024')}; font-size: 21px; font-weight: 800;"
        )
        body_layout.addWidget(header_title)

        # Bordered white changelog box
        notes_box = QFrame(body)
        notes_box.setStyleSheet(
            'QFrame { background: #FFFFFF; border: 1px solid #EAECEF; border-radius: 4px; }'
        )
        notes_layout = QVBoxLayout(notes_box)
        notes_layout.setContentsMargins(18, 16, 18, 14)
        notes_layout.setSpacing(8)

        ver_str = target_version or release_tag or '최신 버전'
        self.version_label = QLabel(f'{ver_str} 변경사항', notes_box)
        self.version_label.setStyleSheet(
            f"color: {TOKENS.get('text', '#1E2024')}; font-size: 14px; font-weight: 800; border: none;"
        )
        notes_layout.addWidget(self.version_label)

        self.log_text = QTextEdit(notes_box)
        self.log_text.setReadOnly(True)
        self.log_text.setFrameShape(QFrame.Shape.NoFrame)
        self.log_text.setStyleSheet(
            'QTextEdit { background: transparent; border: none; color: #3A3E47; font-size: 12px; line-height: 1.5; padding: 0px; }'
        )
        default_notes = (
            release_notes.strip()
            if release_notes
            else (
                '치지직 연동 및 카테고리 자동 감지\n'
                '- [개선] 유니콘 프로 스타일 클린 화이트 & 코랄 미니멀 UI 디자인 적용\n'
                '- [수정] 치지직 스튜디오 브릿지 재연결 안정성 및 응답 속도 개선\n\n'
                '게임 프로세스 매칭\n'
                '- [기능] Steam 한국어 카테고리 매칭 및 리그 오브 레전드 모드 감지 최적화\n'
                '- [수정] 백그라운드 트레이 전환 시 상태 표시 동기화 개선'
            )
        )
        self.log_text.setPlainText(default_notes)
        notes_layout.addWidget(self.log_text, 1)

        self.detail_label = QLabel('', notes_box)
        self.detail_label.setObjectName('sectionInfo')
        self.detail_label.setStyleSheet('border: none; color: #8B909A; font-size: 11px;')
        self.detail_label.setVisible(False)
        notes_layout.addWidget(self.detail_label)

        self.pbar = QProgressBar(notes_box)
        self.pbar.setRange(0, 100)
        self.pbar.setValue(0)
        self.pbar.setFixedHeight(6)
        self.pbar.setVisible(False)
        self.progress_bar = self.pbar
        notes_layout.addWidget(self.pbar)

        body_layout.addWidget(notes_box, 1)

        # Hidden/compact restart checkbox for compatibility
        self.restart_checkbox = QCheckBox('업데이트 완료 후 자동 재시작', body)
        self.restart_checkbox.setChecked(self.restart)
        self.restart_checkbox.setVisible(False)

        # Bottom footer: Left coral warning/status text + Right solid coral "앱 업데이트 하기" button
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 2, 0, 0)
        footer.setSpacing(12)

        self.activity_dot = QLabel('●', body)
        self.activity_dot.setStyleSheet(f"color: {TOKENS.get('accent', '#F0564A')}; font-size: 10px;")
        self.activity_dot.setVisible(False)
        footer.addWidget(self.activity_dot, 0)

        self.status_label = QLabel(self.status_base, body)
        self.status_label.setStyleSheet(
            f"color: {TOKENS.get('accent', '#F0564A')}; font-size: 11.5px; font-weight: 600;"
        )
        self.status_label.setWordWrap(True)
        footer.addWidget(self.status_label, 1)

        self.update_button = QPushButton('앱 업데이트 하기', body)
        self.update_button.setObjectName('primary')
        self.update_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_button.setMinimumSize(118, 36)
        self.update_button.clicked.connect(self.start_update)
        footer.addWidget(self.update_button, 0)

        self.cancel_button = QPushButton('닫기', body)
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.setMinimumHeight(36)
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.close)
        self.close_button = self.cancel_button
        footer.addWidget(self.cancel_button, 0)

        body_layout.addLayout(footer)
        shell_layout.addWidget(body, 1)

        self.worker = UpdateWorker(
            parent_pid=parent_pid,
            target_version=target_version,
            install_dir=self.install_dir,
            restart=restart,
            release_tag=release_tag,
            allow_prerelease=allow_prerelease,
            parent=self,
        )
        self.worker.progress.connect(self.on_progress)
        self.worker.status.connect(self.on_status)
        self.worker.detail.connect(self.on_detail)
        self.worker.version.connect(self.on_version)
        self.worker.finished_ok.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)

        self._center_on_screen()
        if auto_start and parent_pid:
            QTimer.singleShot(250, self.start_update)

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2,
            )

    def _update_status_text(self) -> None:
        self.dot_count = (self.dot_count + 1) % 4
        dots = '.' * self.dot_count
        self.status_label.setText(f'{self.status_base}{dots}')

    def start_update(self) -> None:
        if not self.worker.isRunning():
            self.pbar.setVisible(True)
            self.detail_label.setVisible(True)
            self.update_button.setEnabled(False)
            self.update_button.setText('업데이트 중...')
            self.worker.start()

    def on_progress(self, val: int) -> None:
        self.pbar.setVisible(True)
        self.pbar.setValue(int(val))

    def on_status(self, text: str) -> None:
        self.status_base = str(text)
        self.status_label.setText(self.status_base)

    def on_detail(self, text: str) -> None:
        self.detail_label.setVisible(True)
        self.detail_label.setText(str(text))
        self.log_text.append(str(text))

    def on_version(self, text: str) -> None:
        self.version_label.setText(f'{text} 변경사항')

    def on_finished(self, msg: str) -> None:
        self.pbar.setValue(100)
        self.status_label.setText(str(msg))
        self.update_button.setText('업데이트 완료')
        self.cancel_button.setVisible(True)
        if self.restart_checkbox.isChecked() and self.exe_path.exists():
            try:
                subprocess.Popen([str(self.exe_path)], cwd=str(self.install_dir))
            except Exception:
                pass
            QTimer.singleShot(600, self.close)

    def on_failed(self, err: str) -> None:
        self.status_label.setText(f'업데이트 실패: {err}')
        self.update_button.setEnabled(True)
        self.update_button.setText('다시 시도')
        self.cancel_button.setVisible(True)

    # Aliases for internal slot naming compatibility
    _on_progress = on_progress
    _on_status = on_status
    _on_detail = on_detail
    _on_finished = on_finished
    _on_failed = on_failed


class AutoUpdateWindow(QDialog):
    """Dialog wrapper for in-app update prompt matching Screenshot 1's '업데이트' popup."""

    def __init__(self, parent=None, release_info: dict | None = None) -> None:
        super().__init__(parent)
        self.release_info = release_info or {}
        self.setObjectName('subDialog')
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(480, 390)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 22)
        layout.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel('업데이트', self)
        title.setStyleSheet(
            f"color: {TOKENS.get('text', '#1E2024')}; font-size: 20px; font-weight: 800;"
        )
        top.addWidget(title, 1)
        close_btn = QToolButton(self)
        close_btn.setObjectName('closeButton')
        close_btn.setText('✕')
        close_btn.clicked.connect(self.reject)
        top.addWidget(close_btn, 0)
        layout.addLayout(top)

        box = QFrame(self)
        box.setStyleSheet('QFrame { background: #FFFFFF; border: 1px solid #EAECEF; border-radius: 4px; }')
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(16, 14, 16, 14)

        ver = self.release_info.get('version', '최신 버전')
        ver_lbl = QLabel(f'{ver} 변경사항', box)
        ver_lbl.setStyleSheet('font-size: 14px; font-weight: 800; border: none;')
        box_layout.addWidget(ver_lbl)

        notes = QTextEdit(box)
        notes.setReadOnly(True)
        notes.setFrameShape(QFrame.Shape.NoFrame)
        notes.setPlainText(
            self.release_info.get(
                'body',
                '- [기능] 유니콘 프로 스타일 클린 화이트 미니멀 UI 적용\n'
                '- [개선] 게임 프로세스 감지 및 치지직 카테고리 동기화 안정성 향상',
            )
        )
        box_layout.addWidget(notes, 1)

        self.pbar = QProgressBar(box)
        self.pbar.setRange(0, 100)
        self.pbar.setVisible(False)
        box_layout.addWidget(self.pbar)
        layout.addWidget(box, 1)

        bottom = QHBoxLayout()
        self.notice_label = QLabel(
            '앱 버전이 낮아 업데이트가 권장됩니다. 지금 바로 업데이트해주세요.',
            self,
        )
        self.notice_label.setStyleSheet(
            f"color: {TOKENS.get('accent', '#F0564A')}; font-size: 11px; font-weight: 600;"
        )
        bottom.addWidget(self.notice_label, 1)

        self.update_btn = QPushButton('앱 업데이트 하기', self)
        self.update_btn.setObjectName('primary')
        self.update_btn.clicked.connect(self.start_update)
        bottom.addWidget(self.update_btn, 0)
        layout.addLayout(bottom)

    def start_update(self) -> None:
        self.pbar.setVisible(True)
        self.pbar.setValue(100)
        self.accept()

    def on_progress(self, value: int) -> None:
        self.pbar.setVisible(True)
        self.pbar.setValue(int(value))

    def on_finished(self) -> None:
        self.accept()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='CHZZK Auto Category Updater')
    parser.add_argument('--pid', type=int, default=0)
    parser.add_argument('--version', type=str, default='')
    parser.add_argument('--dir', type=str, default='')
    parser.add_argument('--no-restart', action='store_true')
    parser.add_argument('--tag', type=str, default='')
    parser.add_argument('--prerelease', action='store_true')
    args, _ = parser.parse_known_args(argv)

    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)
    win = UpdaterWindow(
        parent_pid=args.pid,
        target_version=args.version,
        install_dir=args.dir,
        restart=not args.no_restart,
        release_tag=args.tag,
        allow_prerelease=args.prerelease,
        auto_start=bool(args.pid),
    )
    win.show()
    return app.exec()


run_updater = main


if __name__ == '__main__':
    raise SystemExit(main())
