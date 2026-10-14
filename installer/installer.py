import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QPoint, QPropertyAnimation, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor
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
    QScrollArea,
    QSizeGrip,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from ui_components import information as show_info, warning as show_warning, error as show_error


PRODUCT_NAME = 'CHZZK Auto Category'
EXE_NAME = 'ChzzkAutoCategory.exe'
UPDATER_EXE_NAME = 'ChzzkAutoUpdater.exe'
UNINSTALLER_EXE_NAME = 'ChzzkAutoUninstall.exe'
GITHUB_REPO = 'chzzk-dev/CHZZK-Auto-Category'
GITHUB_LATEST_API = f'https://api.github.com/repos/{GITHUB_REPO}/releases/latest'
CHECKSUM_ASSET_NAME = 'SHA256SUMS.txt'
INSTALL_DIR = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'CHZZK Auto Category'
CONFIG_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ChzzkAutoCategory'
AUTOSTART_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
STARTUP_APPROVED_KEY = r'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run'
AUTOSTART_VALUE = 'ChzzkAutoCategory'
UNINSTALL_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\CHZZK Auto Category'

APP_STYLE = '''
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
QFrame#titlebar, QFrame#titlebarButtonWrap {
    background: transparent;
    border: none;
}
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
QFrame#heroCard, QFrame#panelCard, QFrame#actionCard {
    background: #151922;
    border: 1px solid #232936;
    border-radius: 20px;
}
QLabel#logo {
    background: #25d39c;
    color: #041711;
    border-radius: 22px;
    font-size: 22px;
    font-weight: 900;
}
QLabel#title { font-size: 28px; font-weight: 900; color: #fbfdff; }
QLabel#subtitle, QLabel#miniLabel { color: #95a0b3; font-size: 12px; }
QLabel#status { font-size: 34px; font-weight: 900; color: #fbfdff; }
QLabel#detail { color: #a9b4c6; font-size: 13px; }
QLabel#version {
    color: #dce8f8;
    background: #171c26;
    border: 1px solid #2b3341;
    border-radius: 16px;
    padding: 10px 14px;
    font-weight: 700;
}
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
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #1bcf95, stop:1 #5ee8bb);
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
QPushButton#primary { background: #25d39c; color: #071911; border: none; }
QPushButton#primary:hover { background: #33e1aa; }
QPushButton:disabled { color: #718095; background: #131720; border-color: #222836; }
QSizeGrip { width: 18px; height: 18px; margin: 0 2px 2px 0; }
QScrollArea#contentScroll {
    background: transparent;
    border: none;
}
QWidget#scrollContent { background: transparent; }
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px 0 2px 0;
}
QScrollBar::handle:vertical {
    background: #313948;
    min-height: 42px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover { background: #465165; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
'''




def _is_admin():
    if os.name != 'nt':
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _relaunch_as_admin():
    if os.name != 'nt' or _is_admin():
        return False

    args = list(sys.argv[1:])
    if '--elevated' not in args:
        args.append('--elevated')

    if getattr(sys, 'frozen', False):
        executable = sys.executable
        params = subprocess.list2cmdline(args)
    else:
        executable = sys.executable
        params = subprocess.list2cmdline([str(Path(__file__).resolve()), *args])

    result = ctypes.windll.shell32.ShellExecuteW(None, 'runas', executable, params, None, 1)
    if int(result) <= 32:
        raise OSError('C:\\Program Files 설치를 위한 관리자 권한 요청이 취소되었습니다.')
    return True


def _request(url, timeout=15):
    req = urllib.request.Request(
        url,
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'CHZZK-Auto-Category-Setup/4.11.0',
            'X-GitHub-Api-Version': '2022-11-28',
        },
    )
    return urllib.request.urlopen(req, timeout=timeout)


def _read_json_url(url, timeout=15):
    with _request(url, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def _asset(release, name):
    assets = release.get('assets') if isinstance(release, dict) else []
    for item in assets if isinstance(assets, list) else []:
        if isinstance(item, dict) and item.get('name') == name:
            return item
    return None


def _latest_release_info():
    try:
        release = _read_json_url(GITHUB_LATEST_API)
    except Exception as exc:
        if getattr(exc, 'code', None) == 404:
            raise RuntimeError('GitHub Releases에 아직 배포된 버전이 없습니다.') from None
        raise RuntimeError('GitHub Release 정보를 불러오지 못했습니다.') from exc

    if not isinstance(release, dict) or release.get('draft') or release.get('prerelease'):
        raise RuntimeError('설치할 수 있는 정식 GitHub Release가 없습니다.')

    version = str(release.get('tag_name') or '').strip().lstrip('vV')
    if not version:
        raise RuntimeError('GitHub Release 버전을 확인할 수 없습니다.')

    package_name = f'ChzzkAutoCategory-{version}.zip'
    package = _asset(release, package_name)
    if not package:
        candidates = [
            item for item in (release.get('assets') or [])
            if isinstance(item, dict)
            and str(item.get('name') or '').startswith('ChzzkAutoCategory-')
            and str(item.get('name') or '').endswith('.zip')
        ]
        package = candidates[0] if candidates else None

    if not package or not package.get('browser_download_url'):
        raise RuntimeError(f'GitHub Release에서 {package_name} 패키지를 찾지 못했습니다.')

    checksum = _asset(release, CHECKSUM_ASSET_NAME)
    return {
        'version': version,
        'package_url': str(package.get('browser_download_url')),
        'package_size': int(package.get('size') or 0),
        'package_name': str(package.get('name') or package_name),
        'checksum_url': str(checksum.get('browser_download_url') or '') if checksum else '',
    }


def _expected_hash(url, filename):
    if not url:
        return ''
    try:
        with _request(url) as response:
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


def _safe_extract(archive, destination):
    destination = destination.resolve()
    for info in archive.infolist():
        target = (destination / info.filename).resolve()
        try:
            target.relative_to(destination)
        except ValueError:
            raise RuntimeError('업데이트 파일 안에 허용되지 않은 경로가 있습니다.')
    archive.extractall(destination)


def _payload_root(staging):
    exe = staging / EXE_NAME
    if exe.exists():
        return staging
    children = [p for p in staging.iterdir() if p.name not in ('__MACOSX',)]
    if len(children) == 1 and children[0].is_dir() and (children[0] / EXE_NAME).exists():
        return children[0]
    for candidate in staging.rglob(EXE_NAME):
        return candidate.parent
    raise RuntimeError(f'패키지에서 {EXE_NAME}를 찾지 못했습니다.')


def _stop_running_app():
    if os.name != 'nt':
        return
    subprocess.run(
        ['taskkill', '/IM', EXE_NAME, '/F'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        check=False,
    )
    time.sleep(0.8)


def _force_remove(path, attempts=8, delay=0.55):
    """설치 폴더를 남김없이 제거합니다. 잠긴/읽기 전용 파일은 잠시 기다린 뒤 재시도합니다."""
    path = Path(path)
    if not path.exists():
        return

    def make_writable(func, target, _exc):
        try:
            os.chmod(target, stat.S_IWRITE)
        except OSError:
            pass
        try:
            func(target)
        except OSError:
            pass

    last_error = None
    for attempt in range(max(1, int(attempts))):
        try:
            shutil.rmtree(path, onerror=make_writable)
            if not path.exists():
                return
        except OSError as exc:
            last_error = exc
        time.sleep(delay * (attempt + 1))

    if path.exists():
        message = f'기존 설치 폴더를 삭제하지 못했습니다: {path}'
        if last_error:
            message += f'\n{last_error}'
        raise RuntimeError(message)


def _validate_payload(payload):
    exe = Path(payload) / EXE_NAME
    updater = Path(payload) / UPDATER_EXE_NAME
    uninstaller = Path(payload) / UNINSTALLER_EXE_NAME
    internal = Path(payload) / '_internal'
    if not exe.is_file():
        raise RuntimeError(f'새 패키지에서 {EXE_NAME}를 찾지 못했습니다.')
    if not updater.is_file():
        raise RuntimeError(f'새 패키지에서 {UPDATER_EXE_NAME}를 찾지 못했습니다.')
    if not uninstaller.is_file():
        raise RuntimeError(f'새 패키지에서 {UNINSTALLER_EXE_NAME}를 찾지 못했습니다.')
    if not internal.is_dir():
        raise RuntimeError('새 패키지의 _internal 폴더가 없습니다.')


def _install_clean(payload):
    """기존 설치 폴더를 완전히 삭제하고 새 패키지만 복사합니다."""
    payload = Path(payload)
    _validate_payload(payload)
    INSTALL_DIR.parent.mkdir(parents=True, exist_ok=True)

    # 과거 업데이트가 남긴 임시/백업 폴더도 함께 제거합니다.
    for stale in (
        INSTALL_DIR,
        INSTALL_DIR.with_name(INSTALL_DIR.name + '.old'),
        INSTALL_DIR.with_name(INSTALL_DIR.name + '.new'),
    ):
        _force_remove(stale)

    incoming = INSTALL_DIR.with_name(INSTALL_DIR.name + '.new')
    try:
        shutil.copytree(payload, incoming)
        _validate_payload(incoming)
        incoming.replace(INSTALL_DIR)
    except Exception:
        _force_remove(incoming)
        _force_remove(INSTALL_DIR)
        raise


def _register_autostart(exe_path):
    if os.name != 'nt':
        return
    import winreg
    command = f'"{Path(exe_path).resolve()}" --background --autostart'
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, AUTOSTART_VALUE, 0, winreg.REG_SZ, command)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(
            key, AUTOSTART_VALUE, 0, winreg.REG_BINARY,
            bytes((0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00)),
        )


def _mark_config_defaults():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = CONFIG_DIR / 'config.json'
    data = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}
    data.setdefault('autostart', True)
    data.setdefault('auto_update', True)
    data.setdefault('auto_start_change', True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def _register_uninstall_entry(exe_path, version):
    if os.name != 'nt':
        return
    import winreg
    exe = Path(exe_path).resolve()
    uninstall = exe.parent / UNINSTALLER_EXE_NAME
    if not uninstall.is_file():
        raise RuntimeError(f'{UNINSTALLER_EXE_NAME}를 찾지 못했습니다.')
    with winreg.CreateKeyEx(
        winreg.HKEY_LOCAL_MACHINE,
        UNINSTALL_KEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        values = {
            'DisplayName': PRODUCT_NAME,
            'DisplayVersion': str(version or ''),
            'Publisher': 'CHZZK Dev',
            'DisplayIcon': f'{exe},0',
            'InstallLocation': str(exe.parent),
            'UninstallString': f'"{uninstall}"',
            'URLInfoAbout': f'https://github.com/{GITHUB_REPO}',
        }
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.SetValueEx(key, 'NoModify', 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, 'NoRepair', 0, winreg.REG_DWORD, 1)


def _create_start_menu_shortcut(exe_path):
    if os.name != 'nt':
        return
    # Keep one stable all-users shortcut path across clean installs and updates.
    # Existing Start pins then continue pointing to the same .lnk instead of a transient file.
    start_menu = Path(os.environ.get('PROGRAMDATA', r'C:\ProgramData')) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs'
    start_menu.mkdir(parents=True, exist_ok=True)
    shortcut = start_menu / f'{PRODUCT_NAME}.lnk'
    exe = Path(exe_path).resolve()
    script = (
        "$w=New-Object -ComObject WScript.Shell;"
        f"$s=$w.CreateShortcut('{str(shortcut).replace("'", "''")}');"
        f"$s.TargetPath='{str(exe).replace("'", "''")}';"
        f"$s.WorkingDirectory='{str(INSTALL_DIR).replace("'", "''")}';"
        f"$s.IconLocation='{str(exe).replace("'", "''")},0';"
        "$s.Save()"
    )
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        check=False,
    )
    if result.returncode != 0 or not shortcut.exists():
        raise RuntimeError('시작 메뉴 바로가기를 만들지 못했습니다.')

    old_shortcut = Path(os.environ.get('APPDATA', str(Path.home()))) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / f'{PRODUCT_NAME}.lnk'
    if old_shortcut != shortcut:
        try:
            old_shortcut.unlink(missing_ok=True)
        except OSError:
            pass


class InstallWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    detail = Signal(str)
    version = Signal(str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def run(self):
        temp_root = Path(tempfile.mkdtemp(prefix='chzzk-auto-setup-'))
        try:
            self.progress.emit(2)
            self.status.emit('GitHub 패치 확인 중')
            self.detail.emit('최신 GitHub Release를 확인하고 있습니다.')
            info = _latest_release_info()
            version = info['version']
            self.version.emit(version)

            package = temp_root / info['package_name']
            expected_hash = _expected_hash(info.get('checksum_url', ''), info['package_name'])

            # 먼저 새 패키지를 완전히 내려받고 검증합니다.
            # 다운로드 실패 때문에 정상 설치본까지 지워지는 상황을 방지합니다.
            self.progress.emit(5)
            self.status.emit('새 파일 다운로드 중')
            self.detail.emit('새 버전 전체 패키지를 임시 폴더에 내려받고 있습니다.')
            req = urllib.request.Request(
                info['package_url'],
                headers={'User-Agent': 'CHZZK-Auto-Category-Setup/4.11.0'},
            )
            digest = hashlib.sha256()
            with urllib.request.urlopen(req, timeout=30) as response, package.open('wb') as out:
                total = int(response.headers.get('Content-Length') or info.get('package_size') or 0)
                received = 0
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                    if total > 0:
                        pct = 5 + int(min(1.0, received / total) * 48)
                        self.progress.emit(pct)
                        self.detail.emit(f'{received / 1024 / 1024:.1f} MB / {total / 1024 / 1024:.1f} MB')

            self.progress.emit(56)
            self.status.emit('파일 확인 중')
            self.detail.emit('SHA-256과 패키지 구성을 확인하고 있습니다.')
            if expected_hash and digest.hexdigest().lower() != expected_hash:
                raise RuntimeError('다운로드 파일의 SHA-256 값이 일치하지 않습니다.')

            staging = temp_root / 'staging'
            staging.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(package, 'r') as archive:
                _safe_extract(archive, staging)
            payload = _payload_root(staging)
            _validate_payload(payload)

            self.progress.emit(66)
            self.status.emit('앱 종료 중')
            self.detail.emit('실행 중인 CHZZK Auto Category를 종료하고 파일 잠금을 해제합니다.')
            _stop_running_app()

            self.progress.emit(72)
            self.status.emit('기존 파일 삭제 중')
            self.detail.emit(r'C:\Program Files\CHZZK Auto Category의 기존 프로그램 파일을 완전히 삭제합니다.')
            # config.json은 LOCALAPPDATA에 있으므로 게임 규칙/설정은 삭제되지 않습니다.
            for stale in (
                INSTALL_DIR,
                INSTALL_DIR.with_name(INSTALL_DIR.name + '.old'),
                INSTALL_DIR.with_name(INSTALL_DIR.name + '.new'),
            ):
                _force_remove(stale)

            self.progress.emit(82)
            self.status.emit('새 파일 설치 중')
            self.detail.emit('검증이 끝난 새 버전 파일만 깨끗한 설치 폴더에 복사합니다.')
            _install_clean(payload)

            self.progress.emit(94)
            self.status.emit('Windows 설정 중')
            self.detail.emit('시작 프로그램과 시작 메뉴 바로가기를 다시 연결하고 있습니다.')
            exe = INSTALL_DIR / EXE_NAME
            if not exe.exists():
                raise RuntimeError('설치는 완료됐지만 실행 파일을 찾을 수 없습니다.')

            _register_autostart(exe)
            _register_uninstall_entry(exe, version)
            _mark_config_defaults()
            try:
                _create_start_menu_shortcut(exe)
            except Exception:
                pass

            self.progress.emit(100)
            self.status.emit('클린 업데이트 완료')
            self.detail.emit('기존 프로그램 파일을 제거하고 새 버전을 전체 설치했습니다. 사용자 설정은 유지됩니다.')
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
        self.caption.setStyleSheet('font-size: 13px; font-weight: 700; color: #dfe6f0;')
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


class InstallerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'{PRODUCT_NAME} Setup')
        self.resize(1200, 820)
        self.setMinimumSize(1200, 820)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(APP_STYLE)
        self.exe_path = ''
        self.dot_count = 0
        self.status_base = '설치 준비 중'
        self._intro_anim = None
        self._progress_anim = None
        self._pulse_anim = None
        self._shadow = None

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 18, 18, 18)

        shell = QFrame()
        shell.setObjectName('shell')
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(18, 16, 18, 14)
        shell_layout.setSpacing(14)

        self.titlebar = _FramelessTitleBar(self, 'CHZZK Auto Category Setup')
        shell_layout.addWidget(self.titlebar)

        content_scroll = QScrollArea()
        content_scroll.setObjectName('contentScroll')
        content_scroll.setWidgetResizable(True)
        content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        content_scroll.setFrameShape(QFrame.Shape.NoFrame)

        content_widget = QWidget()
        content_widget.setObjectName('scrollContent')
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(14)
        content_scroll.setWidget(content_widget)
        shell_layout.addWidget(content_scroll, 1)

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
        title = QLabel('CHZZK Auto Category')
        title.setObjectName('title')
        subtitle = QLabel('Windows 설치 프로그램 · 최신 GitHub Release 자동 설치')
        subtitle.setObjectName('subtitle')
        brand.addWidget(title)
        brand.addWidget(subtitle)
        header_layout.addLayout(brand, 1)

        self.version_label = QLabel('버전 확인 중')
        self.version_label.setObjectName('version')
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.version_label.setMinimumSize(112, 66)
        self.version_label.setMaximumWidth(150)
        header_layout.addWidget(self.version_label, 0, Qt.AlignmentFlag.AlignVCenter)
        header_card.setMinimumHeight(112)
        content_layout.addWidget(header_card)

        progress_card = QFrame()
        progress_card.setObjectName('panelCard')
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(24, 20, 24, 20)
        progress_layout.setSpacing(10)

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self.activity_dot = QLabel('●')
        self.activity_dot.setStyleSheet('color: #25d39c; font-size: 15px;')
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

        self.detail_label = QLabel('최신 버전을 확인하고 필요한 설치 파일을 준비하고 있습니다.')
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
        self.phase_label = QLabel('설치 준비')
        self.phase_label.setObjectName('miniLabel')
        self.percent = QLabel('0%')
        self.percent.setObjectName('miniValue')
        progress_meta.addWidget(self.phase_label)
        progress_meta.addStretch()
        progress_meta.addWidget(self.percent)
        progress_layout.addLayout(progress_meta)
        progress_card.setMinimumHeight(178)
        content_layout.addWidget(progress_card)

        lower = QHBoxLayout()
        lower.setSpacing(14)

        info_card = QFrame()
        info_card.setObjectName('panelCard')
        info_card.setMinimumHeight(250)
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(20, 18, 20, 18)
        info_layout.setSpacing(9)
        info_title = QLabel('설치 정보')
        info_title.setStyleSheet('font-size: 16px; font-weight: 800; color: #f4f7fb;')
        info_layout.addWidget(info_title)

        def _meta_row(label_text, value_text='-'):
            row = QHBoxLayout()
            row.setSpacing(12)
            label = QLabel(label_text)
            label.setObjectName('miniLabel')
            label.setMinimumWidth(105)
            value = QLabel(value_text)
            value.setObjectName('miniValue')
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(label)
            row.addStretch()
            row.addWidget(value)
            return row, value

        row, self.step_value = _meta_row('상태', '대기 중')
        info_layout.addLayout(row)
        row, self.source_value = _meta_row('소스', 'GitHub Release')
        info_layout.addLayout(row)
        row, self.autostart_value = _meta_row('Windows 자동 실행', '사용')
        info_layout.addLayout(row)
        row, self.shortcut_value = _meta_row('시작 메뉴 바로가기', '생성')
        info_layout.addLayout(row)
        row, self.settings_value = _meta_row('사용자 설정', '기존 설정 유지')
        info_layout.addLayout(row)

        install_label = QLabel('설치 위치')
        install_label.setObjectName('miniLabel')
        info_layout.addWidget(install_label)
        self.install_path_value = QLabel(str(INSTALL_DIR))
        self.install_path_value.setObjectName('miniValue')
        self.install_path_value.setWordWrap(True)
        self.install_path_value.setMinimumHeight(36)
        self.install_path_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info_layout.addWidget(self.install_path_value)
        info_layout.addStretch()
        lower.addWidget(info_card, 1)

        actions = QFrame()
        actions.setObjectName('actionCard')
        actions.setMinimumHeight(250)
        actions.setMinimumWidth(280)
        actions.setMaximumWidth(310)
        actions_layout = QVBoxLayout(actions)
        actions_layout.setContentsMargins(20, 18, 20, 18)
        actions_layout.setSpacing(12)
        actions_title = QLabel('설치 후 동작')
        actions_title.setStyleSheet('font-size: 16px; font-weight: 800; color: #f4f7fb;')
        actions_layout.addWidget(actions_title)
        actions_help = QLabel('설치가 끝나면 프로그램이 자동으로 열립니다. 처음 사용하는 경우 채널과 확장 연결을 안내하며, 설정 완료 후에는 메인 화면으로 바로 이동합니다.')
        actions_help.setObjectName('miniLabel')
        actions_help.setWordWrap(True)
        actions_layout.addWidget(actions_help)
        actions_layout.addStretch()

        self.launch_button = QPushButton('설정 / 프로그램 열기')
        self.launch_button.setObjectName('primary')
        self.launch_button.setEnabled(False)
        self.launch_button.clicked.connect(self.launch_app)
        actions_layout.addWidget(self.launch_button)

        self.close_button = QPushButton('닫기')
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.close)
        actions_layout.addWidget(self.close_button)
        lower.addWidget(actions, 0)
        content_layout.addLayout(lower)
        content_layout.addStretch(1)

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
        shadow.setColor(QColor(0, 0, 0, 180))
        shell.setGraphicsEffect(shadow)
        self._shadow = shadow

        self.anim = QTimer(self)
        self.anim.setInterval(340)
        self.anim.timeout.connect(self.animate_status)
        self.anim.start()

        self.worker = InstallWorker(self)
        self.worker.progress.connect(self.set_progress)
        self.worker.status.connect(self.set_status)
        self.worker.detail.connect(self.detail_label.setText)
        self.worker.version.connect(lambda value: self.version_label.setText(f'버전 {value}'))
        self.worker.finished_ok.connect(self.install_done)
        self.worker.finished.connect(self.open_after_install)
        self.worker.failed.connect(self.install_failed)
        QTimer.singleShot(20, self._start_intro_animation)
        QTimer.singleShot(550, self.worker.start)

    def _start_intro_animation(self):
        self.setWindowOpacity(0.0)
        self._intro_anim = QPropertyAnimation(self, b'windowOpacity', self)
        self._intro_anim.setDuration(260)
        self._intro_anim.setStartValue(0.0)
        self._intro_anim.setEndValue(1.0)
        self._intro_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._intro_anim.start()

    def closeEvent(self, event):
        if self.worker.isRunning():
            show_info(self, '설치 진행 중', '설치가 끝난 뒤 창을 닫아 주세요.')
            event.ignore()
            return
        super().closeEvent(event)

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

    def set_status(self, text):
        self.status_base = str(text)
        self.dot_count = 0
        self.status_label.setText(self.status_base)
        self.phase_label.setText(self.status_base)
        self.step_value.setText(self.status_base)

    def animate_status(self):
        if not self.worker.isRunning():
            return
        self.dot_count = (self.dot_count + 1) % 4
        self.status_label.setText(self.status_base + ('.' * self.dot_count))

    def install_done(self, exe_path):
        self.exe_path = exe_path
        self.anim.stop()
        self.status_base = '설치 완료'
        self.status_label.setText('설치 완료 ✓')
        self.detail_label.setText('설치가 완료되었습니다. 처음 실행하면 설정 안내가 열립니다. 기존 설정과 게임 규칙은 유지됩니다.')
        self.progress.setValue(100)
        self.percent.setText('100%')
        self.phase_label.setText('완료')
        self.step_value.setText('완료')
        if self._pulse_anim:
            self._pulse_anim.stop()
            self.activity_dot.setStyleSheet('color: #59e6b9; font-size: 15px;')
        self.launch_button.setEnabled(True)
        self.close_button.setEnabled(True)

    def install_failed(self, error):
        self.anim.stop()
        self.status_label.setText('설치 실패')
        self.detail_label.setText(str(error))
        self.progress.setValue(0)
        self.percent.setText('오류')
        self.phase_label.setText('오류')
        self.step_value.setText('오류')
        if self._pulse_anim:
            self._pulse_anim.stop()
            self.activity_dot.setStyleSheet('color: #ff6d83; font-size: 15px;')
        self.close_button.setEnabled(True)

    def open_after_install(self):
        if self.exe_path:
            self.launch_app()

    def launch_app(self):
        if not self.exe_path:
            return
        try:
            subprocess.Popen([self.exe_path, '--after-install'], cwd=str(Path(self.exe_path).parent))
            self.close()
        except OSError as exc:
            show_warning(self, '실행 실패', str(exc))


def main():
    try:
        if _relaunch_as_admin():
            return 0
    except Exception as exc:
        app = QApplication(sys.argv)
        show_error(None, '관리자 권한 필요', str(exc))
        return 1

    app = QApplication(sys.argv)
    window = InstallerWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
