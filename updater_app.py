import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import ntpath
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QPoint, QPropertyAnimation, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
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
from ui_components import information as show_info, warning as show_warning


PRODUCT_NAME = 'CHZZK Auto Category'
APP_EXE_NAME = 'ChzzkAutoCategory.exe'
UPDATER_EXE_NAME = 'ChzzkAutoUpdater.exe'
GITHUB_REPO = 'chzzk-dev/CHZZK-Auto-Category'
GITHUB_LATEST_API = f'https://api.github.com/repos/{GITHUB_REPO}/releases/latest'
CHECKSUM_ASSET_NAME = 'SHA256SUMS.txt'
AUTOSTART_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
STARTUP_APPROVED_KEY = r'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run'
AUTOSTART_VALUE = 'ChzzkAutoCategory'
CONFIG_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ChzzkAutoCategory'

STYLE = '''
QWidget {
    font-family: "Pretendard", "SUIT Variable", "Noto Sans KR", "Malgun Gothic";
    color: #17313c;
    font-size: 13px;
}
QMainWindow { background: transparent; }
QFrame#shell {
    background: #f6fafb;
    border: 1px solid #d3e5e4;
    border-radius: 24px;
}
QFrame#titlebar {
    background: transparent;
    border: none;
}
QFrame#titlebarButtonWrap {
    background: transparent;
    border: none;
}
QToolButton {
    min-width: 34px;
    max-width: 34px;
    min-height: 34px;
    max-height: 34px;
    border-radius: 10px;
    border: 1px solid #dce6e9;
    background: #ffffff;
    color: #27434e;
    font-size: 14px;
}
QToolButton:hover { background: #edf8f3; border-color: #b6d9cd; }
QToolButton#closeButton:hover { background: #fae5eb; border-color: #e9cbd4; color: #a83a55; }
QFrame#heroCard, QFrame#panelCard, QFrame#actionCard {
    background: #ffffff;
    border: 1px solid #e0e9ed;
    border-radius: 20px;
}
QLabel#logo {
    background: #49edbb;
    color: #10392e;
    border-radius: 22px;
    font-size: 22px;
    font-weight: 900;
}
QLabel#title { font-size: 28px; font-weight: 900; color: #132c37; }
QLabel#sub { color: #607782; font-size: 13px; }
QLabel#status { font-size: 28px; font-weight: 900; color: #132c37; }
QLabel#detail { color: #607782; font-size: 13px; }
QLabel#version {
    color: #7252b6;
    background: #ece8fa;
    border: 1px solid #e1daf1;
    border-radius: 16px;
    padding: 10px 14px;
    font-weight: 700;
}
QLabel#miniLabel { color: #607782; font-size: 12px; }
QLabel#miniValue { color: #27434e; font-size: 14px; font-weight: 700; }
QProgressBar {
    min-height: 16px;
    max-height: 16px;
    border: none;
    border-radius: 8px;
    background: #e9f1ef;
    color: transparent;
}
QProgressBar::chunk {
    border-radius: 8px;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #24ca94, stop:1 #72efca);
}
QPushButton {
    min-height: 46px;
    border-radius: 14px;
    padding: 0 18px;
    background: #f5f9fa;
    border: 1px solid #dce6e9;
    color: #27434e;
    font-weight: 700;
}
QPushButton:hover { background: #edf8f3; border-color: #b6d9cd; }
QPushButton#primary { background: #49edbb; color: #10392e; border: none; }
QPushButton#primary:hover { background: #66f1c7; }
QPushButton:disabled { color: #92a5ac; background: #eff4f5; border-color: #e0e8eb; }
QPushButton#primary:disabled { color: #92a5ac; background: #eff4f5; border: 1px solid #e0e8eb; }
QSizeGrip { width: 18px; height: 18px; margin: 0 2px 2px 0; }
'''




def _request(url, timeout=30):
    req = urllib.request.Request(
        url,
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'CHZZK-Auto-Updater/1.0',
            'X-GitHub-Api-Version': '2022-11-28',
        },
    )
    return urllib.request.urlopen(req, timeout=timeout)


def _asset(release, name):
    assets = release.get('assets') if isinstance(release, dict) else []
    for item in assets if isinstance(assets, list) else []:
        if isinstance(item, dict) and item.get('name') == name:
            return item
    return None


def _latest_release(target_version=''):
    with _request(GITHUB_LATEST_API, timeout=15) as response:
        release = json.loads(response.read().decode('utf-8'))

    if not isinstance(release, dict) or release.get('draft') or release.get('prerelease'):
        raise RuntimeError('사용할 수 있는 정식 GitHub Release가 없습니다.')

    version = str(release.get('tag_name') or '').strip().lstrip('vV')
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise RuntimeError('GitHub Release 버전은 숫자 3자리 형식이어야 합니다. 예: 4.11.1')
    if target_version and version != str(target_version).strip().lstrip('vV'):
        raise RuntimeError(f'업데이트 대상 버전이 변경되었습니다. 요청 {target_version}, 현재 {version}')

    package_name = f'ChzzkAutoCategory-{version}.msi'
    package = _asset(release, package_name)
    checksum = _asset(release, CHECKSUM_ASSET_NAME)
    if not package or not package.get('browser_download_url'):
        raise RuntimeError(f'GitHub Release에서 {package_name}을 찾지 못했습니다.')

    return {
        'version': version,
        'package_name': package_name,
        'package_url': str(package.get('browser_download_url') or ''),
        'package_size': int(package.get('size') or 0),
        'checksum_url': str(checksum.get('browser_download_url') or '') if checksum else '',
    }


def _expected_hash(url, filename):
    if not url:
        return ''
    try:
        with _request(url, timeout=15) as response:
            text = response.read().decode('utf-8', errors='replace')
    except Exception:
        return ''

    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1].lstrip('*') == filename:
            digest = parts[0].lower()
            if re.fullmatch(r'[0-9a-f]{64}', digest):
                return digest
    return ''


def _pid_running(pid):
    if not pid or pid <= 0:
        return False
    if os.name != 'nt':
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    SYNCHRONIZE = 0x00100000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, int(pid))
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return int(code.value) == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _wait_parent_exit(pid, timeout=18):
    deadline = time.monotonic() + max(1, int(timeout))
    while time.monotonic() < deadline:
        if not _pid_running(pid):
            return True
        time.sleep(0.25)
    return not _pid_running(pid)


def _force_stop_pid(pid):
    if os.name != 'nt' or not pid or pid <= 0:
        return
    subprocess.run(
        ['taskkill', '/PID', str(int(pid)), '/T', '/F'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        check=False,
    )
    _wait_parent_exit(pid, timeout=8)


def _cleanup_user_startup():
    """Remove only this user's app startup entries; never delete their settings."""
    if os.name != 'nt':
        return
    import winreg
    for key_path in (AUTOSTART_KEY, STARTUP_APPROVED_KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, AUTOSTART_VALUE)
        except FileNotFoundError:
            pass
    shortcut = Path(os.environ.get('APPDATA', str(Path.home()))) / 'Microsoft/Windows/Start Menu/Programs' / f'{PRODUCT_NAME}.lnk'
    shortcut.unlink(missing_ok=True)


def _msi_install_command(package, install_dir, log_path):
    msiexec = ntpath.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'msiexec.exe')
    folder = str(install_dir)
    if not folder or any(character in folder for character in ('"', '\r', '\n', '\x00')):
        raise ValueError('MSI 설치 경로의 형식이 올바르지 않습니다.')
    # msiexec parses properties itself: quote the value, not the entire NAME=value.
    command = subprocess.list2cmdline([
        msiexec, '/i', str(package), '/passive', '/norestart', '/L*v', str(log_path),
    ])
    return command + ' INSTALLFOLDER="' + folder + '"'


def _install_msi(package, install_dir, log_path):
    """Return True when Windows Installer requires a reboot; preserve its log."""
    if os.name != 'nt':
        raise RuntimeError('MSI 업데이트는 Windows에서만 실행할 수 있습니다.')
    result = subprocess.run(_msi_install_command(package, install_dir, log_path),
                            shell=False, check=False)
    code = result.returncode
    if code in (0, 3010, 1641):
        return code != 0
    if code == 1602:
        raise RuntimeError('MSI 설치 또는 관리자 권한 요청이 취소되었습니다.')
    if code == 1618:
        raise RuntimeError('다른 Windows 설치 작업이 진행 중입니다. 완료된 뒤 다시 시도해 주세요.')
    if code == 1639:
        raise RuntimeError(f'MSI 명령 형식 오류 (코드 1639). MSI 설치 파일을 직접 실행해 주세요. 로그: {log_path}')
    raise RuntimeError(f'MSI 설치 실패 (코드 {code}). 로그: {log_path}')


def _launch_app(exe_path):
    exe_path = Path(exe_path)
    if not exe_path.is_file():
        return
    subprocess.Popen(
        [str(exe_path), '--background', '--post-update'],
        cwd=str(exe_path.parent),
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )


class UpdateWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    detail = Signal(str)
    version = Signal(str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, parent_pid, target_version, install_dir, restart=True, parent=None):
        super().__init__(parent)
        self.parent_pid = int(parent_pid or 0)
        self.target_version = str(target_version or '').strip()
        self.install_dir = Path(install_dir)
        self.restart = bool(restart)
        self.reboot_required = False

    def run(self):
        temp_root = Path(tempfile.mkdtemp(prefix='chzzk-auto-update-'))
        try:
            self.progress.emit(2)
            self.status.emit('앱 종료 대기 중')
            self.detail.emit('현재 CHZZK Auto Category가 파일 잠금을 해제할 때까지 기다립니다.')
            if self.parent_pid and not _wait_parent_exit(self.parent_pid, timeout=18):
                self.detail.emit('앱이 아직 실행 중이어서 종료 요청을 보냅니다.')
                _force_stop_pid(self.parent_pid)
            if self.parent_pid and _pid_running(self.parent_pid):
                raise RuntimeError('기존 앱 프로세스를 종료하지 못했습니다.')

            self.progress.emit(8)
            self.status.emit('GitHub 패치 확인 중')
            self.detail.emit('최신 GitHub Release 패키지를 확인하고 있습니다.')
            info = _latest_release(self.target_version)
            self.version.emit(info['version'])

            package = temp_root / info['package_name']
            expected = _expected_hash(info.get('checksum_url', ''), info['package_name'])
            if not expected:
                raise RuntimeError('MSI의 SHA-256 검증 정보를 가져오지 못했습니다. 설치를 중단합니다.')

            self.progress.emit(12)
            self.status.emit('새 파일 다운로드 중')
            self.detail.emit('새 버전 전체 패키지를 임시 폴더로 내려받고 있습니다.')
            digest = hashlib.sha256()
            with _request(info['package_url'], timeout=30) as response, package.open('wb') as stream:
                total = int(response.headers.get('Content-Length') or info.get('package_size') or 0)
                received = 0
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    stream.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                    if total:
                        pct = 12 + int(min(1.0, received / total) * 43)
                        self.progress.emit(pct)
                        self.detail.emit(f'{received / 1024 / 1024:.1f} MB / {total / 1024 / 1024:.1f} MB')

            self.progress.emit(58)
            self.status.emit('파일 확인 중')
            self.detail.emit('다운로드한 MSI의 SHA-256을 확인하고 있습니다.')
            if digest.hexdigest().lower() != expected:
                raise RuntimeError('다운로드한 업데이트 패키지의 SHA-256 값이 일치하지 않습니다.')

            self.progress.emit(70)
            self.status.emit('MSI 설치 중')
            self.detail.emit('Windows Installer에서 새 버전을 설치합니다. 관리자 권한 요청을 확인해 주세요.')
            logs = CONFIG_DIR / 'logs'
            logs.mkdir(parents=True, exist_ok=True)
            log_path = logs / f'msi-update-{info["version"]}-{int(time.time())}.log'
            self.reboot_required = _install_msi(package, self.install_dir, log_path)
            exe = self.install_dir / APP_EXE_NAME
            if not self.reboot_required and not exe.is_file():
                raise RuntimeError(f'MSI 설치 후 실행 파일을 찾을 수 없습니다. 로그: {log_path}')
            self.progress.emit(100)
            self.status.emit('업데이트 완료')
            self.detail.emit('Windows Installer가 새 버전 설치를 완료했습니다.')
            self.finished_ok.emit(str(exe))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)




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
        self.caption.setStyleSheet('font-size: 13px; font-weight: 700; color: #607782;')
        layout.addSpacing(6)
        layout.addWidget(self.caption)
        layout.addStretch()

        button_wrap = QFrame()
        button_wrap.setObjectName('titlebarButtonWrap')
        button_layout = QHBoxLayout(button_wrap)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(6)

        self.min_button = QToolButton()
        self.min_button.setText('─')
        self.min_button.clicked.connect(window.showMinimized)
        button_layout.addWidget(self.min_button)

        self.close_button = QToolButton()
        self.close_button.setObjectName('closeButton')
        self.close_button.setText('✕')
        self.close_button.clicked.connect(window.close)
        button_layout.addWidget(self.close_button)

        layout.addWidget(button_wrap)

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


class UpdaterWindow(QMainWindow):
    def __init__(self, parent_pid, target_version, install_dir, restart=True):
        super().__init__()
        self.restart = bool(restart)
        self.exe_path = ''
        self.dot_count = 0
        self.status_base = '업데이트 준비 중'
        self._shadow = None
        self._intro_anim = None
        self._progress_anim = None
        self._pulse_anim = None
        self.setWindowTitle('CHZZK Auto Updater')
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
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(18, 16, 18, 14)
        shell_layout.setSpacing(14)

        self.titlebar = _FramelessTitleBar(self, 'CHZZK Auto Updater')
        shell_layout.addWidget(self.titlebar)

        # Header card: brand + target version only. Keep progress content out of
        # this row so long Korean status strings can never collide with the badge.
        header_card = QFrame()
        header_card.setObjectName('heroCard')
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(24, 20, 24, 20)
        header_layout.setSpacing(18)

        logo = QLabel('C')
        logo.setObjectName('logo')
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(44, 44)
        header_layout.addWidget(logo, 0, Qt.AlignmentFlag.AlignVCenter)

        brand = QVBoxLayout()
        brand.setSpacing(4)
        title = QLabel('CHZZK Auto Updater')
        title.setObjectName('title')
        sub = QLabel('Windows Installer · MSI 업데이트')
        sub.setObjectName('sub')
        brand.addWidget(title)
        brand.addWidget(sub)
        header_layout.addLayout(brand, 1)

        self.version_label = QLabel(f'버전 {target_version or "latest"}')
        self.version_label.setObjectName('version')
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.version_label.setMinimumSize(112, 66)
        self.version_label.setMaximumWidth(150)
        header_layout.addWidget(self.version_label, 0, Qt.AlignmentFlag.AlignVCenter)
        shell_layout.addWidget(header_card)

        # Dedicated progress card with enough vertical space for status/detail/bar.
        progress_card = QFrame()
        progress_card.setObjectName('panelCard')
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(24, 20, 24, 20)
        progress_layout.setSpacing(10)

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self.activity_dot = QLabel('●')
        self.activity_dot.setStyleSheet('color: #17916a; font-size: 15px;')
        self.activity_dot.setFixedWidth(18)
        status_row.addWidget(self.activity_dot, 0, Qt.AlignmentFlag.AlignTop)

        self.status_label = QLabel(self.status_base)
        self.status_label.setObjectName('status')
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(42)
        status_row.addWidget(self.status_label, 1)
        progress_layout.addLayout(status_row)

        dot_effect = QGraphicsOpacityEffect(self.activity_dot)
        self.activity_dot.setGraphicsEffect(dot_effect)
        self._pulse_anim = QPropertyAnimation(dot_effect, b'opacity', self)
        self._pulse_anim.setDuration(1200)
        self._pulse_anim.setStartValue(0.35)
        self._pulse_anim.setKeyValueAt(0.5, 1.0)
        self._pulse_anim.setEndValue(0.35)
        self._pulse_anim.setLoopCount(-1)
        self._pulse_anim.start()

        self.detail_label = QLabel('GitHub 릴리즈를 확인하고 업데이트를 준비하고 있습니다.')
        self.detail_label.setObjectName('detail')
        self.detail_label.setWordWrap(True)
        self.detail_label.setMinimumHeight(24)
        progress_layout.addWidget(self.detail_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        progress_layout.addWidget(self.progress)

        progress_meta = QHBoxLayout()
        self.phase_label = QLabel('업데이트 준비')
        self.phase_label.setObjectName('miniLabel')
        self.percent = QLabel('0%')
        self.percent.setObjectName('miniValue')
        progress_meta.addWidget(self.phase_label)
        progress_meta.addStretch()
        progress_meta.addWidget(self.percent)
        progress_layout.addLayout(progress_meta)
        shell_layout.addWidget(progress_card)

        lower = QHBoxLayout()
        lower.setSpacing(14)

        panel = QFrame()
        panel.setObjectName('panelCard')
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(20, 18, 20, 18)
        panel_layout.setSpacing(9)
        panel_title = QLabel('현재 작업')
        panel_title.setStyleSheet('font-size: 16px; font-weight: 800; color: #132c37;')
        panel_layout.addWidget(panel_title)

        def _meta_row(label_text, value_text='-'):
            row = QHBoxLayout()
            row.setSpacing(12)
            label = QLabel(label_text)
            label.setObjectName('miniLabel')
            label.setMinimumWidth(98)
            value = QLabel(value_text)
            value.setObjectName('miniValue')
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(label)
            row.addStretch()
            row.addWidget(value)
            return row, value

        row, self.step_value = _meta_row('상태', '대기 중')
        panel_layout.addLayout(row)
        row, self.source_value = _meta_row('소스', 'GitHub Release')
        panel_layout.addLayout(row)
        row, self.restart_value = _meta_row('업데이트 후 실행', '예' if self.restart else '아니오')
        panel_layout.addLayout(row)

        install_label = QLabel('설치 위치')
        install_label.setObjectName('miniLabel')
        panel_layout.addWidget(install_label)
        self.install_value = QLabel(str(install_dir))
        self.install_value.setObjectName('miniValue')
        self.install_value.setWordWrap(True)
        self.install_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        panel_layout.addWidget(self.install_value)
        panel_layout.addStretch()
        lower.addWidget(panel, 1)

        actions = QFrame()
        actions.setObjectName('actionCard')
        actions.setMinimumWidth(280)
        actions.setMaximumWidth(310)
        actions_layout = QVBoxLayout(actions)
        actions_layout.setContentsMargins(20, 18, 20, 18)
        actions_layout.setSpacing(12)
        actions_title = QLabel('빠른 동작')
        actions_title.setStyleSheet('font-size: 16px; font-weight: 800; color: #132c37;')
        actions_layout.addWidget(actions_title)
        actions_help = QLabel('업데이트가 완료되면 새 버전을 바로 실행하거나 창만 닫을 수 있습니다.')
        actions_help.setObjectName('miniLabel')
        actions_help.setWordWrap(True)
        actions_layout.addWidget(actions_help)
        actions_layout.addStretch()

        self.launch_button = QPushButton('백그라운드로 실행')
        self.launch_button.setObjectName('primary')
        self.launch_button.setEnabled(False)
        self.launch_button.clicked.connect(self.launch_app)
        actions_layout.addWidget(self.launch_button)

        self.close_button = QPushButton('닫기')
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.close)
        actions_layout.addWidget(self.close_button)
        lower.addWidget(actions, 0)

        shell_layout.addLayout(lower, 1)

        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 0, 0)
        grip_row.addStretch()
        grip_row.addWidget(QSizeGrip(shell), 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        shell_layout.addLayout(grip_row)

        outer.addWidget(shell)
        self.setCentralWidget(root)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 14)
        shadow.setColor(QColor(16, 57, 46, 55))
        shell.setGraphicsEffect(shadow)
        self._shadow = shadow

        self.anim = QTimer(self)
        self.anim.setInterval(330)
        self.anim.timeout.connect(self.animate_status)
        self.anim.start()

        self.worker = UpdateWorker(parent_pid, target_version, install_dir, restart, self)
        self.worker.progress.connect(self.set_progress)
        self.worker.status.connect(self.set_status)
        self.worker.detail.connect(self.detail_label.setText)
        self.worker.version.connect(lambda value: self.version_label.setText(f'버전 {value}'))
        self.worker.finished_ok.connect(self.update_done)
        self.worker.failed.connect(self.update_failed)
        QTimer.singleShot(20, self._start_intro_animation)
        QTimer.singleShot(450, self.worker.start)

    def _start_intro_animation(self):
        self.setWindowOpacity(0.0)
        self._intro_anim = QPropertyAnimation(self, b'windowOpacity', self)
        self._intro_anim.setDuration(260)
        self._intro_anim.setStartValue(0.0)
        self._intro_anim.setEndValue(1.0)
        self._intro_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._intro_anim.start()

    def set_progress(self, value):
        value = int(value)
        if self._progress_anim and self._progress_anim.state() == QAbstractAnimation.State.Running:
            self._progress_anim.stop()
        self._progress_anim = QPropertyAnimation(self.progress, b'value', self)
        self._progress_anim.setDuration(280)
        self._progress_anim.setStartValue(self.progress.value())
        self._progress_anim.setEndValue(value)
        self._progress_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._progress_anim.start()
        self.percent.setText(f'{value}%')

    def set_status(self, value):
        self.status_base = str(value)
        self.dot_count = 0
        self.status_label.setText(self.status_base)
        self.phase_label.setText(self.status_base)
        self.step_value.setText(self.status_base)

    def animate_status(self):
        if not self.worker.isRunning():
            return
        self.dot_count = (self.dot_count + 1) % 4
        self.status_label.setText(self.status_base + ('.' * self.dot_count))

    def update_done(self, exe_path):
        self.exe_path = exe_path
        self.anim.stop()
        self.progress.setValue(100)
        self.percent.setText('100%')
        self.status_label.setText('업데이트 완료 ✓')
        self.phase_label.setText('완료')
        self.step_value.setText('완료')
        self.detail_label.setText('Windows Installer가 새 버전 설치를 완료했습니다.')
        if self._pulse_anim:
            self._pulse_anim.stop()
            self.activity_dot.setStyleSheet('color: #59e6b9; font-size: 15px;')
        self.launch_button.setEnabled(not self.worker.reboot_required)
        self.close_button.setEnabled(True)
        if self.worker.reboot_required:
            self.detail_label.setText('설치를 마치려면 Windows를 다시 시작해 주세요. 자동으로 재부팅하지 않습니다.')
            return
        if self.restart:
            QTimer.singleShot(1000, self.launch_app)

    def update_failed(self, error):
        self.anim.stop()
        self.status_label.setText('업데이트 실패')
        self.phase_label.setText('오류')
        self.step_value.setText('오류')
        self.detail_label.setText(str(error))
        self.progress.setValue(0)
        self.percent.setText('오류')
        if self._pulse_anim:
            self._pulse_anim.stop()
            self.activity_dot.setStyleSheet('color: #ff6d83; font-size: 15px;')
        self.close_button.setEnabled(True)

    def launch_app(self):
        if not self.exe_path:
            return
        try:
            _launch_app(self.exe_path)
            self.close()
        except Exception as exc:
            show_warning(self, '실행 실패', str(exc))

    def closeEvent(self, event):
        if self.worker.isRunning():
            show_info(self, '업데이트 진행 중', '업데이트가 끝난 뒤 창을 닫아 주세요.')
            event.ignore()
            return
        super().closeEvent(event)


def main():
    if '--cleanup-user' in sys.argv:
        _cleanup_user_startup()
        return 0
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--parent-pid', type=int, default=0)
    parser.add_argument('--target-version', default='')
    parser.add_argument('--install-dir', default='')
    parser.add_argument('--restart', action='store_true')
    args, _unknown = parser.parse_known_args()

    default_dir = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'CHZZK Auto Category'
    install_dir = Path(args.install_dir).resolve() if args.install_dir else default_dir

    app = QApplication(sys.argv)
    window = UpdaterWindow(args.parent_pid, args.target_version, install_dir, args.restart)
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
