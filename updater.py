import ctypes
import json
import os
from pathlib import Path
import re
from release_versions import SemVer
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
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from version import (
    APP_VERSION,
    CHECKSUM_ASSET_NAME,
    GITHUB_LATEST_API,
    UPDATER_EXE_NAME,
)


from theme import UPDATE_STYLE
from app_icons import set_button_icon


def _version_tuple(value):
    return SemVer(value)


def is_newer_version(candidate, current=APP_VERSION):
    try:
        return SemVer(candidate) > SemVer(current)
    except ValueError:
        return False


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


def fetch_latest_release(allow_prerelease=False):
    try:
        with _github_request(GITHUB_LATEST_API.replace('/latest', '?per_page=100') if allow_prerelease else GITHUB_LATEST_API) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except Exception as exc:
        if getattr(exc, 'code', None) == 404:
            return None
        raise

    if isinstance(payload, list):
        candidates = []
        for item in payload:
            if not isinstance(item, dict) or item.get('draft') or (item.get('prerelease') and not allow_prerelease):
                continue
            try:
                candidates.append((SemVer(item.get('tag_name')), item))
            except ValueError:
                continue
        payload = max(candidates, key=lambda x: x[0])[1] if candidates else None
    if not isinstance(payload, dict) or payload.get('draft') or (payload.get('prerelease') and not allow_prerelease):
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
        'release_tag': str(payload.get('tag_name') or ''),
        'prerelease': bool(payload.get('prerelease')),
        'release_tag_version': tag_version,
        'html_url': str(payload.get('html_url') or ''),
        'package_name': package_name,
        'package_url': str(package.get('browser_download_url') or ''),
        'package_size': int(package.get('size') or 0),
        'checksum_url': str(checksums.get('browser_download_url') or '') if checksums else '',
        'release_notes': str(payload.get('body') or '').strip(),
        'published_at': str(payload.get('published_at') or ''),
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
        f"--release-tag={release.get('release_tag') or 'v' + version}",
        *(['--allow-prerelease'] if release.get('prerelease') else []),
    ]

    # Keep the helper and restarted app in the original user's session. Windows
    # Installer requests elevation itself when applying the per-machine MSI.
    subprocess.Popen([str(target), *args], cwd=str(target.parent))



class UpdateCheckWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, parent=None, allow_prerelease=False):
        super().__init__(parent)
        self.allow_prerelease = bool(allow_prerelease)

    def run(self):
        try:
            release = fetch_latest_release(self.allow_prerelease)
            if release and is_newer_version(release.get('version')):
                self.completed.emit(release)
            else:
                self.completed.emit(None)
        except Exception as exc:
            self.failed.emit(str(exc))


class AutoUpdateWindow(QMainWindow):
    deferred = Signal(object)

    def __init__(self, release, parent=None):
        super().__init__(parent)
        self.release = dict(release or {})
        self.owner = parent
        self.dot_count = 0
        self.status_base = '업데이트 프로그램 준비 중'
        self.started = False
        self.setWindowTitle('업데이트')
        self.resize(600, 460)
        self.setMinimumSize(520, 400)
        self.setStyleSheet(UPDATE_STYLE)

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        shell = QFrame()
        shell.setObjectName('updateShell')
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)
        heading = QLabel('업데이트')
        heading.setObjectName('updateHeading')
        layout.addWidget(heading)
        divider = QFrame()
        divider.setObjectName('updateDivider')
        layout.addWidget(divider)

        version = str(self.release.get('version') or '?')
        self.status_label = QLabel(f'{version} 버전이 출시되었습니다.')
        self.status_label.setObjectName('updateVersion')
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.version_label = QLabel(f'현재 버전 {APP_VERSION}  →  새 버전 {version}')
        self.version_label.setObjectName('updateCaption')
        layout.addWidget(self.version_label)

        self.notes = QTextBrowser()
        self.notes.setObjectName('releaseNotes')
        self.notes.setReadOnly(True)
        self.notes.setOpenLinks(False)
        self.notes.setMarkdown(self.release.get('release_notes') or '이번 버전의 변경 내용이 제공되지 않았습니다.')
        layout.addWidget(self.notes, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.detail_label = QLabel('업데이트하는 동안 프로그램이 종료됩니다.')
        self.detail_label.setObjectName('updateNotice')
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)
        footer = QHBoxLayout()
        footer.addStretch()
        self.close_button = QPushButton('나중에')
        self.close_button.clicked.connect(self.close)
        footer.addWidget(self.close_button)
        self.update_button = QPushButton('앱 업데이트하기')
        self.update_button.setObjectName('primary')
        self.update_button.clicked.connect(self.start_updater)
        footer.addWidget(self.update_button)
        layout.addLayout(footer)
        outer.addWidget(shell)
        self.setCentralWidget(root)
        self.anim = QTimer(self)
        self.anim.setInterval(330)
        self.anim.timeout.connect(self.animate_status)

    def animate_status(self):
        if self.started:
            self.dot_count = (self.dot_count + 1) % 4
            self.status_label.setText(self.status_base + ('.' * self.dot_count))

    def start_updater(self):
        if self.started:
            return
        self.started = True
        self.close_button.setEnabled(False)
        self.update_button.setEnabled(False)
        self.update_button.setText('준비 중…')
        self.status_label.setText(self.status_base)
        self.progress.show()
        self.progress.setValue(10)
        self.anim.start()
        try:
            launch_external_updater(self.release)
        except Exception as exc:
            self.started = False
            self.anim.stop()
            self.status_label.setText('업데이트 프로그램 실행 실패')
            self.detail_label.setText(str(exc))
            self.detail_label.setObjectName('updateError')
            self.detail_label.style().unpolish(self.detail_label)
            self.detail_label.style().polish(self.detail_label)
            self.progress.setValue(0)
            self.close_button.setText('닫기')
            self.close_button.setEnabled(True)
            self.update_button.setText('다시 시도')
            self.update_button.setEnabled(True)
            return
        self.progress.setValue(100)
        self.status_base = '업데이트 프로그램으로 전환 중'
        self.status_label.setText(self.status_base)
        self.detail_label.setText('업데이트 창이 열립니다. 설치가 끝나면 프로그램을 다시 실행합니다.')
        QTimer.singleShot(600, self._quit_owner)

    def closeEvent(self, event):
        if self.started:
            event.ignore()
            return
        self.deferred.emit(dict(self.release))
        super().closeEvent(event)

    def _quit_owner(self):
        if self.owner is not None and hasattr(self.owner, 'quit_app'):
            self.owner.quit_app()
        else:
            QApplication.instance().quit()
