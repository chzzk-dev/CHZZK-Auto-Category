import ctypes
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from version import (
    APP_VERSION,
    CHECKSUM_ASSET_NAME,
    GITHUB_LATEST_API,
    UPDATER_EXE_NAME,
)


UPDATE_STYLE = '''
QWidget {
    font-family: "Pretendard", "SUIT Variable", "Noto Sans KR", "Malgun Gothic";
    color: #e9fff5;
    font-size: 13px;
}
QMainWindow { background: #06110d; }
QFrame#shell {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #071a13, stop:0.58 #0a241a, stop:1 #0b3022);
    border: 1px solid #1f684c;
    border-radius: 20px;
}
QLabel#logo {
    background: #18d39b;
    color: #032218;
    border-radius: 19px;
    font-size: 20px;
    font-weight: 900;
}
QLabel#title { font-size: 17px; font-weight: 800; color: #f3fff9; }
QLabel#sub { color: #83ae9a; }
QLabel#status { font-size: 22px; font-weight: 900; color: #edfff6; }
QLabel#detail { color: #8eb8a5; }
QLabel#version {
    color: #8ce2bd;
    background: rgba(15, 67, 48, 0.65);
    border: 1px solid #286f54;
    border-radius: 10px;
    padding: 6px 10px;
}
QProgressBar {
    min-height: 15px;
    max-height: 15px;
    border: none;
    border-radius: 7px;
    background: #102b21;
    color: transparent;
}
QProgressBar::chunk {
    border-radius: 7px;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #0fb981, stop:0.55 #19d49b, stop:1 #3cf0bd);
}
QPushButton {
    min-height: 40px;
    border-radius: 11px;
    padding: 0 18px;
    background: #103629;
    border: 1px solid #2a7256;
    color: #e4fff2;
    font-weight: 700;
}
QPushButton:hover { background: #154936; border-color: #3a9b75; }
'''


def _version_tuple(value):
    text = str(value or '').strip().lstrip('vV')
    parts = []
    for chunk in re.split(r'[^0-9]+', text):
        if chunk:
            parts.append(int(chunk))
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def is_newer_version(candidate, current=APP_VERSION):
    return _version_tuple(candidate) > _version_tuple(current)


def _github_request(url, timeout=12):
    request = urllib.request.Request(
        url,
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': f'CHZZK-Auto-Category/{APP_VERSION}',
            'X-GitHub-Api-Version': '2022-11-28',
        },
    )
    return urllib.request.urlopen(request, timeout=timeout)


def fetch_latest_release():
    try:
        with _github_request(GITHUB_LATEST_API) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except Exception as exc:
        if getattr(exc, 'code', None) == 404:
            return None
        raise

    if not isinstance(payload, dict) or payload.get('draft') or payload.get('prerelease'):
        return None

    tag_version = str(payload.get('tag_name') or payload.get('name') or '').strip().lstrip('vV')
    assets = payload.get('assets') if isinstance(payload.get('assets'), list) else []

    # The checker, helper, and download page use the same versioned MSI name.
    if not re.fullmatch(r'\d+\.\d+\.\d+', tag_version):
        return None
    version = tag_version
    expected_name = f'ChzzkAutoCategory-{version}.msi'
    package = next((item for item in assets if isinstance(item, dict)
                    and item.get('name') == expected_name
                    and item.get('browser_download_url')), None)
    if package is None:
        return None

    package_name = str(package.get('name') or f'ChzzkAutoCategory-{version}.msi')
    checksums = next((item for item in assets if isinstance(item, dict) and item.get('name') == CHECKSUM_ASSET_NAME), None)

    return {
        'version': version,
        'release_tag_version': tag_version,
        'html_url': str(payload.get('html_url') or ''),
        'package_name': package_name,
        'package_url': str(package.get('browser_download_url') or ''),
        'package_size': int(package.get('size') or 0),
        'checksum_url': str(checksums.get('browser_download_url') or '') if checksums else '',
    }


def _installed_updater_path():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent / UPDATER_EXE_NAME
    return Path(__file__).resolve().parent / 'dist-updater' / UPDATER_EXE_NAME


def _temp_updater_path(version):
    root = Path(tempfile.gettempdir()) / 'ChzzkAutoCategory' / 'updater' / f'{version}-{os.getpid()}'
    root.mkdir(parents=True, exist_ok=True)
    return root / UPDATER_EXE_NAME


def launch_external_updater(release):
    source = _installed_updater_path()
    if not source.is_file():
        raise RuntimeError(
            f'{UPDATER_EXE_NAME}를 찾지 못했습니다.\n'
            'MSI 설치 파일로 복구하거나 다시 설치해 주세요.'
        )

    version = str(release.get('version') or '').strip()
    if not version:
        raise RuntimeError('업데이트 버전을 확인할 수 없습니다.')

    target = _temp_updater_path(version)
    shutil.copy2(source, target)

    install_dir = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    args = [
        f'--parent-pid={os.getpid()}',
        f'--target-version={version}',
        f'--install-dir={install_dir}',
        '--restart',
    ]

    # Keep the helper and restarted app in the original user's session. Windows
    # Installer requests elevation itself when applying the per-machine MSI.
    subprocess.Popen([str(target), *args], cwd=str(target.parent))



class UpdateCheckWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            release = fetch_latest_release()
            if release and is_newer_version(release.get('version')):
                self.completed.emit(release)
            else:
                self.completed.emit(None)
        except Exception as exc:
            self.failed.emit(str(exc))


class AutoUpdateWindow(QMainWindow):
    def __init__(self, release, parent=None):
        super().__init__(parent)
        self.release = dict(release or {})
        self.owner = parent
        self.dot_count = 0
        self.status_base = '업데이트 프로그램 준비 중'
        self.started = False
        self.setWindowTitle('CHZZK Auto Category Update')
        self.setFixedSize(610, 330)
        self.setStyleSheet(UPDATE_STYLE)

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 18, 18, 18)

        shell = QFrame()
        shell.setObjectName('shell')
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.setSpacing(15)

        header = QHBoxLayout()
        logo = QLabel('C')
        logo.setObjectName('logo')
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(38, 38)
        header.addWidget(logo)

        brand = QVBoxLayout()
        title = QLabel('CHZZK Auto Category')
        title.setObjectName('title')
        sub = QLabel('External Update Handoff')
        sub.setObjectName('sub')
        brand.addWidget(title)
        brand.addWidget(sub)
        header.addLayout(brand)
        header.addStretch()

        version = str(self.release.get('version') or '?')
        version_label = QLabel(f'{APP_VERSION}  →  {version}')
        version_label.setObjectName('version')
        header.addWidget(version_label)
        layout.addLayout(header)

        layout.addSpacing(8)
        self.status_label = QLabel(self.status_base)
        self.status_label.setObjectName('status')
        layout.addWidget(self.status_label)

        self.detail_label = QLabel(
            '별도 업데이트 프로그램을 임시 폴더에서 실행합니다.\n'
            '현재 앱이 종료된 뒤 Windows Installer로 새 MSI를 설치합니다.'
        )
        self.detail_label.setObjectName('detail')
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(10)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        layout.addStretch()
        self.close_button = QPushButton('취소')
        self.close_button.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self.close_button)
        layout.addLayout(row)

        outer.addWidget(shell)
        self.setCentralWidget(root)

        self.anim = QTimer(self)
        self.anim.setInterval(330)
        self.anim.timeout.connect(self.animate_status)
        self.anim.start()
        QTimer.singleShot(450, self.start_updater)

    def animate_status(self):
        if not self.started:
            self.dot_count = (self.dot_count + 1) % 4
            self.status_label.setText(self.status_base + ('.' * self.dot_count))

    def start_updater(self):
        if self.started:
            return
        self.started = True
        self.close_button.setEnabled(False)
        try:
            launch_external_updater(self.release)
        except Exception as exc:
            self.started = False
            self.anim.stop()
            self.status_label.setText('업데이트 프로그램 실행 실패')
            self.detail_label.setText(str(exc))
            self.progress.setValue(0)
            self.close_button.setText('닫기')
            self.close_button.setEnabled(True)
            return

        self.progress.setValue(100)
        self.status_label.setText('업데이트 프로그램으로 전환 중')
        self.detail_label.setText('업데이트 창이 열립니다. 현재 앱은 파일 잠금을 풀기 위해 종료됩니다.')
        QTimer.singleShot(600, self._quit_owner)

    def _quit_owner(self):
        if self.owner is not None and hasattr(self.owner, 'quit_app'):
            self.owner.quit_app()
        else:
            QApplication.instance().quit()
