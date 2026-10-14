import argparse
import ctypes
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QPoint, QPropertyAnimation, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSizeGrip,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from ui_components import confirm as show_confirm, error as show_error


PRODUCT_NAME = 'CHZZK Auto Category'
APP_EXE_NAME = 'ChzzkAutoCategory.exe'
UPDATER_EXE_NAME = 'ChzzkAutoUpdater.exe'
UNINSTALLER_EXE_NAME = 'ChzzkAutoUninstall.exe'
AUTOSTART_VALUE = 'ChzzkAutoCategory'
AUTOSTART_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
STARTUP_APPROVED_KEYS = (
    r'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run',
    r'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run32',
)
UNINSTALL_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\CHZZK Auto Category'
DEFAULT_INSTALL_DIR = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'CHZZK Auto Category'
CONFIG_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ChzzkAutoCategory'
TEMP_APP_DIR = Path(tempfile.gettempdir()) / 'ChzzkAutoCategory'

STYLE = '''
QWidget {
    font-family: "Pretendard", "SUIT Variable", "Noto Sans KR", "Malgun Gothic";
    color: #eef2f8;
    font-size: 13px;
}
QMainWindow { background: transparent; }
QFrame#shell {
    background: #11141b;
    border: 1px solid #242a36;
    border-radius: 24px;
}
QFrame#titlebar { background: transparent; border: none; }
QToolButton {
    min-width: 34px;
    max-width: 34px;
    min-height: 34px;
    max-height: 34px;
    border-radius: 10px;
    border: 1px solid #2b3340;
    background: #171b23;
    color: #dce3ed;
    font-size: 14px;
}
QToolButton:hover { background: #1d2330; border-color: #3b4556; }
QToolButton#closeButton:hover { background: #432129; border-color: #90465a; color: #fff0f4; }
QFrame#heroCard, QFrame#notice, QFrame#dangerCard, QFrame#actionCard, QFrame#panelCard {
    background: #151922;
    border: 1px solid #232936;
    border-radius: 20px;
}
QLabel#logo {
    background: #ff6a7f;
    color: #290812;
    border-radius: 22px;
    font-size: 22px;
    font-weight: 900;
}
QLabel#title { font-size: 28px; font-weight: 900; color: #fbfdff; }
QLabel#sub { color: #95a0b3; font-size: 13px; }
QLabel#status { font-size: 28px; font-weight: 900; color: #fbfdff; }
QLabel#detail { color: #a9b4c6; font-size: 13px; }
QLabel#miniLabel { color: #8490a4; font-size: 12px; }
QLabel#miniValue { color: #eff4fb; font-size: 14px; font-weight: 700; }
QProgressBar {
    min-height: 16px;
    max-height: 16px;
    border: none;
    border-radius: 8px;
    background: #0d1118;
    color: transparent;
}
QProgressBar::chunk {
    border-radius: 8px;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #ff627b, stop:1 #ff8962);
}
QPushButton {
    min-height: 46px;
    border-radius: 14px;
    padding: 0 18px;
    background: #181d27;
    border: 1px solid #2c3542;
    color: #eef3fb;
    font-weight: 700;
}
QPushButton:hover { background: #202633; border-color: #3c4657; }
QPushButton#danger { background: #ff6d83; color: #19050b; border: none; }
QPushButton#danger:hover { background: #ff8295; }
QPushButton:disabled { color: #718095; background: #131720; border-color: #222836; }
QCheckBox { color: #d7dde8; spacing: 8px; }
QSizeGrip { width: 18px; height: 18px; margin: 0 2px 2px 0; }
'''




def _is_admin():
    if os.name != 'nt':
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _copy_to_temp_and_launch(install_dir):
    if not getattr(sys, 'frozen', False):
        return False
    source = Path(sys.executable).resolve()
    try:
        source.relative_to(TEMP_APP_DIR.resolve())
        return False
    except ValueError:
        pass

    target_dir = TEMP_APP_DIR / 'uninstall' / uuid.uuid4().hex
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / UNINSTALLER_EXE_NAME
    shutil.copy2(source, target)
    subprocess.Popen(
        [str(target), '--temp-run', '--install-dir', str(install_dir)],
        cwd=str(target_dir),
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
    return True


def _relaunch_as_admin(install_dir):
    if os.name != 'nt' or _is_admin():
        return False

    args = ['--temp-run', '--elevated', '--install-dir', str(install_dir)]
    if getattr(sys, 'frozen', False):
        executable = sys.executable
        params = subprocess.list2cmdline(args)
    else:
        executable = sys.executable
        params = subprocess.list2cmdline([str(Path(__file__).resolve()), *args])

    result = ctypes.windll.shell32.ShellExecuteW(None, 'runas', executable, params, None, 1)
    if int(result) <= 32:
        raise OSError('프로그램 제거를 위한 관리자 권한 요청이 취소되었습니다.')
    return True


def _remove_registry_value(root, path, name):
    if os.name != 'nt':
        return
    import winreg
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
    except FileNotFoundError:
        pass


def _delete_registry_tree(root, path):
    if os.name != 'nt':
        return
    import winreg
    try:
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        pass
    except OSError:
        # This key only stores values in this project; recursively handle any future subkeys.
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
                children = []
                index = 0
                while True:
                    try:
                        children.append(winreg.EnumKey(key, index))
                        index += 1
                    except OSError:
                        break
            for child in children:
                _delete_registry_tree(root, path + '\\' + child)
            winreg.DeleteKey(root, path)
        except FileNotFoundError:
            pass


def _remove_windows_registration():
    if os.name != 'nt':
        return
    import winreg

    _remove_registry_value(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, AUTOSTART_VALUE)
    for key_path in STARTUP_APPROVED_KEYS:
        _remove_registry_value(winreg.HKEY_CURRENT_USER, key_path, AUTOSTART_VALUE)

    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        _delete_registry_tree(root, UNINSTALL_KEY)


def _shortcut_candidates():
    program_data = Path(os.environ.get('PROGRAMDATA', r'C:\ProgramData'))
    app_data = Path(os.environ.get('APPDATA', str(Path.home())))
    public = Path(os.environ.get('PUBLIC', r'C:\Users\Public'))
    user_profile = Path(os.environ.get('USERPROFILE', str(Path.home())))
    names = ('CHZZK Auto Category.lnk', 'ChzzkAutoCategory.lnk')
    paths = []
    for name in names:
        paths.extend([
            program_data / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / name,
            app_data / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / name,
            public / 'Desktop' / name,
            user_profile / 'Desktop' / name,
        ])
    paths.extend([
        program_data / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'CHZZK Auto Category',
        app_data / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'CHZZK Auto Category',
    ])
    return paths


def _make_writable(func, target, _exc_info):
    try:
        os.chmod(target, stat.S_IWRITE)
    except OSError:
        pass
    try:
        func(target)
    except OSError:
        pass


def _remove_path(path, attempts=12, delay=0.35):
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        return

    last_error = None
    for attempt in range(max(1, int(attempts))):
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path, onerror=_make_writable)
            else:
                try:
                    os.chmod(path, stat.S_IWRITE)
                except OSError:
                    pass
                path.unlink(missing_ok=True)
            if not path.exists():
                return
        except OSError as exc:
            last_error = exc
        time.sleep(delay * (1 + min(attempt, 4)))

    if path.exists():
        message = f'삭제하지 못했습니다: {path}'
        if last_error:
            message += f'\n{last_error}'
        raise RuntimeError(message)


def _stop_process(image_name):
    if os.name != 'nt':
        return
    subprocess.run(
        ['taskkill.exe', '/IM', image_name, '/T', '/F'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        check=False,
    )


def _stop_running_app():
    _stop_process(APP_EXE_NAME)
    _stop_process(UPDATER_EXE_NAME)
    time.sleep(0.8)


def _remove_shortcuts():
    for path in _shortcut_candidates():
        try:
            _remove_path(path, attempts=3, delay=0.1)
        except Exception:
            pass


def _schedule_temp_cleanup():
    if os.name != 'nt':
        return
    root = str(TEMP_APP_DIR).replace("'", "''")
    pid = os.getpid()
    script = (
        f"$targetPid={pid};"
        "while (Get-Process -Id $targetPid -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 500 };"
        f"Remove-Item -LiteralPath '{root}' -Recurse -Force -ErrorAction SilentlyContinue"
    )
    subprocess.Popen(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )


class RemoveWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    detail = Signal(str)
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, install_dir, remove_user_data=True, parent=None):
        super().__init__(parent)
        self.install_dir = Path(install_dir)
        self.remove_user_data = bool(remove_user_data)

    def run(self):
        try:
            self.progress.emit(8)
            self.status.emit('앱 종료 중')
            self.detail.emit('실행 중인 앱과 업데이트 프로세스를 종료하고 있습니다.')
            _stop_running_app()

            self.progress.emit(24)
            self.status.emit('Windows 시작 앱 제거 중')
            self.detail.emit('자동 실행 및 Windows 설치 정보를 제거하고 있습니다.')
            _remove_windows_registration()

            self.progress.emit(38)
            self.status.emit('시작 메뉴 정리 중')
            self.detail.emit('시작 메뉴와 바탕 화면에 남은 바로가기를 제거하고 있습니다.')
            _remove_shortcuts()

            if self.remove_user_data:
                self.progress.emit(54)
                self.status.emit('사용자 데이터 삭제 중')
                self.detail.emit('설정, 게임 규칙, 캐시와 로컬 로그를 삭제하고 있습니다.')
                _remove_path(CONFIG_DIR)

            self.progress.emit(70)
            self.status.emit('프로그램 파일 삭제 중')
            self.detail.emit(str(self.install_dir))
            for target in (
                self.install_dir,
                self.install_dir.with_name(self.install_dir.name + '.old'),
                self.install_dir.with_name(self.install_dir.name + '.new'),
            ):
                _remove_path(target)

            self.progress.emit(92)
            self.status.emit('임시 파일 정리 중')
            self.detail.emit('업데이트/제거 작업의 임시 파일을 예약 정리합니다.')
            _schedule_temp_cleanup()

            self.progress.emit(100)
            self.status.emit('제거 완료')
            self.detail.emit('CHZZK Auto Category의 Windows 앱 구성요소를 모두 제거했습니다.')
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))




class _FramelessTitleBar(QFrame):
    def __init__(self, window, title):
        super().__init__(window)
        self._window = window
        self._drag_offset = QPoint()
        self.setObjectName('titlebar')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        self.caption = QLabel(title)
        self.caption.setStyleSheet('font-size: 13px; font-weight: 700; color: #dfe6f0;')
        layout.addSpacing(6)
        layout.addWidget(self.caption)
        layout.addStretch()

        self.min_button = QToolButton()
        self.min_button.setText('─')
        self.min_button.clicked.connect(window.showMinimized)
        layout.addWidget(self.min_button)

        self.close_button = QToolButton()
        self.close_button.setObjectName('closeButton')
        self.close_button.setText('✕')
        self.close_button.clicked.connect(window.close)
        layout.addWidget(self.close_button)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and not self._window.isMaximized():
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)


class UninstallerWindow(QMainWindow):
    def __init__(self, install_dir):
        super().__init__()
        self.install_dir = Path(install_dir)
        self.worker = None
        self.dot_count = 0
        self.status_base = '제거 준비됨'
        self._shadow = None
        self._intro_anim = None
        self._progress_anim = None
        self._pulse_anim = None
        self.setWindowTitle(f'{PRODUCT_NAME} 제거')
        self.resize(1200, 820)
        self.setMinimumSize(1200, 820)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(STYLE)

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 18, 18, 18)

        shell = QFrame()
        shell.setObjectName('shell')
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(14)

        self.titlebar = _FramelessTitleBar(self, f'{PRODUCT_NAME} 제거')
        layout.addWidget(self.titlebar)

        hero = QFrame()
        hero.setObjectName('heroCard')
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(24, 24, 24, 24)
        hero_layout.setSpacing(18)

        logo = QLabel('C')
        logo.setObjectName('logo')
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(44, 44)
        hero_layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(6)
        title = QLabel('CHZZK Auto Category 제거')
        title.setObjectName('title')
        subtitle = QLabel('앱, 등록 정보, 바로가기와 자동 실행 설정을 깔끔하게 제거합니다.')
        subtitle.setObjectName('sub')
        info.addWidget(title)
        info.addWidget(subtitle)
        info.addSpacing(10)

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self.activity_dot = QLabel('●')
        self.activity_dot.setStyleSheet('color: #ff6d83; font-size: 16px;')
        self.activity_dot.setFixedWidth(18)
        status_row.addWidget(self.activity_dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self.status = QLabel(self.status_base)
        self.status.setObjectName('status')
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(42)
        status_row.addWidget(self.status, 1)
        info.addLayout(status_row)

        dot_effect = QGraphicsOpacityEffect(self.activity_dot)
        self.activity_dot.setGraphicsEffect(dot_effect)
        self._pulse_anim = QPropertyAnimation(dot_effect, b'opacity', self)
        self._pulse_anim.setDuration(1300)
        self._pulse_anim.setStartValue(0.3)
        self._pulse_anim.setKeyValueAt(0.5, 1.0)
        self._pulse_anim.setEndValue(0.3)
        self._pulse_anim.setLoopCount(-1)
        self._pulse_anim.start()

        self.detail = QLabel('완전히 제거를 누르면 관리자 권한으로 제거를 시작합니다.')
        self.detail.setObjectName('detail')
        self.detail.setWordWrap(True)
        info.addWidget(self.detail)

        hero_layout.addLayout(info, 1)

        meta = QVBoxLayout()
        meta.setSpacing(8)
        install_badge = QLabel('설치 위치')
        install_badge.setObjectName('miniLabel')
        meta.addWidget(install_badge, alignment=Qt.AlignmentFlag.AlignRight)
        install_state = QLabel('Windows 앱')
        install_state.setObjectName('version')
        install_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        install_state.setMinimumSize(112, 62)
        meta.addWidget(install_state)
        meta.addStretch()
        hero_layout.addLayout(meta)
        layout.addWidget(hero)

        install_card = QFrame()
        install_card.setObjectName('panelCard')
        install_layout = QVBoxLayout(install_card)
        install_layout.setContentsMargins(20, 14, 20, 14)
        install_layout.setSpacing(6)
        install_title = QLabel('설치 위치')
        install_title.setObjectName('miniLabel')
        self.install_badge_value = QLabel(str(self.install_dir))
        self.install_badge_value.setObjectName('miniValue')
        self.install_badge_value.setWordWrap(True)
        self.install_badge_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        install_layout.addWidget(install_title)
        install_layout.addWidget(self.install_badge_value)
        layout.addWidget(install_card)

        mid = QHBoxLayout()
        mid.setSpacing(14)

        notice = QFrame()
        notice.setObjectName('notice')
        notice_layout = QVBoxLayout(notice)
        notice_layout.setContentsMargins(20, 18, 20, 18)
        notice_layout.setSpacing(10)
        notice_title = QLabel('제거 대상')
        notice_title.setStyleSheet('font-size: 16px; font-weight: 800; color: #f4f7fb;')
        notice_layout.addWidget(notice_title)
        notice_text = QLabel(
            '• C:\\Program Files\\CHZZK Auto Category\n'
            '• Windows 로그인 자동 실행 등록\n'
            '• 시작 메뉴 / 바탕 화면 바로가기\n'
            '• Windows 설치 앱 등록 정보\n'
            '• 업데이트 및 제거 임시 파일'
        )
        notice_text.setWordWrap(True)
        notice_text.setObjectName('detail')
        notice_layout.addWidget(notice_text)
        mid.addWidget(notice, 1)

        side = QVBoxLayout()
        side.setSpacing(14)
        action_card = QFrame()
        action_card.setObjectName('actionCard')
        action_card.setMinimumWidth(320)
        action_layout = QVBoxLayout(action_card)
        action_layout.setContentsMargins(20, 18, 20, 18)
        action_title = QLabel('추가 제거')
        action_title.setStyleSheet('font-size: 16px; font-weight: 800; color: #f4f7fb;')
        action_layout.addWidget(action_title)
        self.remove_data = QCheckBox('사용자 설정, 게임 규칙, 캐시와 로그도 함께 삭제')
        self.remove_data.setChecked(True)
        action_layout.addWidget(self.remove_data)
        action_layout.addStretch()
        side.addWidget(action_card)

        danger = QFrame()
        danger.setObjectName('dangerCard')
        danger_layout = QVBoxLayout(danger)
        danger_layout.setContentsMargins(20, 18, 20, 18)
        danger_title = QLabel('주의')
        danger_title.setStyleSheet('font-size: 16px; font-weight: 800; color: #f4f7fb;')
        danger_layout.addWidget(danger_title)
        danger_text = QLabel('제거가 완료되면 앱 실행 파일, Windows 등록 정보, 바로가기가 삭제되며 사용자 데이터 삭제 옵션을 켠 경우 되돌릴 수 없습니다.')
        danger_text.setObjectName('detail')
        danger_text.setWordWrap(True)
        danger_layout.addWidget(danger_text)
        side.addWidget(danger)
        mid.addLayout(side, 1)
        layout.addLayout(mid)

        progress_card = QFrame()
        progress_card.setObjectName('panelCard')
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(20, 18, 20, 18)
        progress_layout.setSpacing(10)
        progress_title = QLabel('진행 상황')
        progress_title.setStyleSheet('font-size: 16px; font-weight: 800; color: #f4f7fb;')
        progress_layout.addWidget(progress_title)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.hide()
        progress_layout.addWidget(self.progress)
        self.progress_meta = QLabel('대기 중')
        self.progress_meta.setObjectName('miniLabel')
        progress_layout.addWidget(self.progress_meta, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(progress_card)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton('취소')
        self.remove_button = QPushButton('완전히 제거')
        self.remove_button.setObjectName('danger')
        self.cancel_button.clicked.connect(self.close)
        self.remove_button.clicked.connect(self.start_remove)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.remove_button)
        layout.addLayout(buttons)

        grip_row = QHBoxLayout()
        grip_row.addStretch()
        grip_row.addWidget(QSizeGrip(shell), 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        layout.addLayout(grip_row)

        outer.addWidget(shell)
        self.setCentralWidget(root)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 14)
        shadow.setColor(QColor(0, 0, 0, 180))
        shell.setGraphicsEffect(shadow)
        self._shadow = shadow

        self.timer = QTimer(self)
        self.timer.setInterval(450)
        self.timer.timeout.connect(self.animate_status)
        QTimer.singleShot(20, self._start_intro_animation)

    def _start_intro_animation(self):
        self.setWindowOpacity(0.0)
        self._intro_anim = QPropertyAnimation(self, b'windowOpacity', self)
        self._intro_anim.setDuration(260)
        self._intro_anim.setStartValue(0.0)
        self._intro_anim.setEndValue(1.0)
        self._intro_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._intro_anim.start()

    def animate_status(self):
        if not self.worker or not self.worker.isRunning():
            return
        self.dot_count = (self.dot_count + 1) % 4
        self.status.setText(self.status_base + '.' * self.dot_count)

    def start_remove(self):
        if not show_confirm(
            self,
            '완전 제거 확인',
            'CHZZK Auto Category를 제거하시겠습니까?\n\n체크된 경우 사용자 설정과 게임 규칙도 함께 삭제되며 되돌릴 수 없습니다.',
            confirm_text='완전히 제거',
            cancel_text='취소',
            danger=True,
        ):
            return

        self.remove_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.remove_data.setEnabled(False)
        self.progress.show()
        self.worker = RemoveWorker(self.install_dir, self.remove_data.isChecked(), self)
        self.worker.progress.connect(self.on_progress)
        self.worker.status.connect(self.on_status)
        self.worker.detail.connect(self.detail.setText)
        self.worker.finished_ok.connect(self.on_done)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()
        self.timer.start()

    def on_progress(self, value):
        value = int(value)
        if self._progress_anim and self._progress_anim.state() == QAbstractAnimation.State.Running:
            self._progress_anim.stop()
        self._progress_anim = QPropertyAnimation(self.progress, b'value', self)
        self._progress_anim.setDuration(300)
        self._progress_anim.setStartValue(self.progress.value())
        self._progress_anim.setEndValue(value)
        self._progress_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._progress_anim.start()
        self.progress_meta.setText(f'{value}%')

    def on_status(self, text):
        self.status_base = str(text)
        self.dot_count = 0
        self.status.setText(self.status_base)
        self.progress_meta.setText(self.status_base)

    def on_done(self):
        self.timer.stop()
        if self._pulse_anim:
            self._pulse_anim.stop()
        self.activity_dot.setStyleSheet('color: #25d39c; font-size: 16px;')
        self.status.setText('제거 완료 ✓')
        self.detail.setText('Windows 앱 구성요소가 제거되었습니다. 이 창을 닫아 주세요.')
        self.progress_meta.setText('완료')
        self.cancel_button.setText('닫기')
        self.cancel_button.setEnabled(True)
        self.remove_button.hide()

    def on_failed(self, message):
        self.timer.stop()
        if self._pulse_anim:
            self._pulse_anim.stop()
        self.activity_dot.setStyleSheet('color: #ff6d83; font-size: 16px;')
        self.status.setText('제거 실패')
        self.detail.setText(message)
        self.progress_meta.setText('오류')
        self.cancel_button.setEnabled(True)
        self.remove_button.setEnabled(True)
        self.remove_data.setEnabled(True)
        show_error(self, '제거 실패', message)



def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--install-dir', default=str(DEFAULT_INSTALL_DIR))
    parser.add_argument('--temp-run', action='store_true')
    parser.add_argument('--elevated', action='store_true')
    args, _unknown = parser.parse_known_args()
    install_dir = Path(args.install_dir)

    if not args.temp_run and _copy_to_temp_and_launch(install_dir):
        return 0

    if os.name == 'nt' and not _is_admin():
        try:
            if _relaunch_as_admin(install_dir):
                return 0
        except Exception as exc:
            app = QApplication(sys.argv)
            show_error(None, '관리자 권한 필요', str(exc))
            return 1

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    window = UninstallerWindow(install_dir)
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
