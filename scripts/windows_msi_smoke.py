"""Verify real MSI commands on a disposable GitHub-hosted Windows runner."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from updater_app import _install_msi
from version import APP_VERSION

BASE_VERSION = '4.11.4'
BASE_URL = ('https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/download/'
            'v4.11.4/ChzzkAutoCategory-4.11.4.msi')
BASE_HASH = '58f54bd27503df9e686e92f5adda5fd2f600b498c2a335af3819016ca9413351'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def installed_version():
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'Software\CHZZK Dev\AutoCategory',
                        0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        return winreg.QueryValueEx(key, 'Version')[0]


def main():
    if os.name != 'nt' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Run this integration check only on the disposable Windows CI runner.')
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError('The Windows MSI verification runner must be elevated.')
    if tuple(map(int, APP_VERSION.split('.'))) <= tuple(map(int, BASE_VERSION.split('.'))):
        raise RuntimeError('Upgrade verification requires a version newer than the baseline.')
    logs = ROOT / 'build/msi-smoke'
    logs.mkdir(parents=True, exist_ok=True)
    current = ROOT / 'dist-installer' / f'ChzzkAutoCategory-{APP_VERSION}.msi'
    expected_exe = ROOT / 'dist/ChzzkAutoCategory/ChzzkAutoCategory.exe'
    msiexec = str(Path(os.environ['SystemRoot']) / 'System32/msiexec.exe')
    target = Path(os.environ['ProgramFiles']) / 'CHZZK MSI test & 한글'
    if target.exists():
        raise RuntimeError('The test destination already exists; refusing to use it.')
    installed_package = None
    with tempfile.TemporaryDirectory(prefix='chzzk-msi-') as temporary:
        directory = Path(temporary) / '다운로드 & test'
        directory.mkdir()
        baseline = directory / f'ChzzkAutoCategory-{BASE_VERSION}.msi'
        request = urllib.request.Request(BASE_URL, headers={'User-Agent': 'CHZZK-MSI-CI'})
        with urllib.request.urlopen(request, timeout=60) as response, baseline.open('wb') as stream:
            while chunk := response.read(256 * 1024):
                stream.write(chunk)
        if digest(baseline) != BASE_HASH:
            raise RuntimeError('The pinned baseline MSI checksum does not match.')
        profile = Path(temporary) / 'profile'
        config = profile / 'ChzzkAutoCategory/config.json'
        config.parent.mkdir(parents=True)
        saved = json.dumps({'setup_completed': True, 'pending_sound': False, 'autostart': False,
                            'rules': [{'process': 'Test.exe', 'category_id': 'test', 'category_name': 'Test'}]}).encode()
        config.write_bytes(saved)
        original_local = os.environ.get('LOCALAPPDATA')
        os.environ['LOCALAPPDATA'] = str(profile)
        try:
            # Reproduce the old CreateProcess command before applying the fix.
            old_args = [msiexec, '/i', str(baseline), '/passive', '/norestart',
                        'INSTALLFOLDER=' + str(target), '/L*v', str(logs / 'legacy-command.log')]
            legacy = subprocess.run(old_args, shell=False, check=False, timeout=90)
            print('Legacy whole-property quoting exit code:', legacy.returncode, flush=True)
            if legacy.returncode in (0, 3010, 1641):
                installed_package = baseline
            if legacy.returncode != 1639:
                raise RuntimeError('The expected legacy command-line error 1639 was not reproduced.')

            _install_msi(baseline, target, logs / 'baseline-install.log')
            installed_package = baseline
            if installed_version() != BASE_VERSION or not (target / 'ChzzkAutoCategory.exe').is_file():
                raise RuntimeError('The baseline was not installed at the specified Unicode/space path.')
            if config.read_bytes() != saved:
                raise RuntimeError('Installing the baseline changed user settings.')
            print('Fixed command installed the baseline successfully.', flush=True)

            _install_msi(current, target, logs / 'upgrade-install.log')
            installed_package = current
            if installed_version() != APP_VERSION:
                raise RuntimeError('Windows Installer did not register the upgraded version.')
            if digest(target / 'ChzzkAutoCategory.exe') != digest(expected_exe):
                raise RuntimeError('The installed executable does not match the new build.')
            if config.read_bytes() != saved:
                raise RuntimeError('Upgrading changed user settings.')
            print('Actual MSI upgrade passed; new executable and existing settings verified.', flush=True)
        finally:
            try:
                if installed_package is not None:
                    result = subprocess.run([msiexec, '/x', str(installed_package), '/qn', '/norestart',
                                             '/L*v', str(logs / 'uninstall.log')],
                                            shell=False, check=False, timeout=180)
                    if result.returncode not in (0, 3010, 1641):
                        raise RuntimeError('MSI smoke cleanup failed: ' + str(result.returncode))
                    if (target / 'ChzzkAutoCategory.exe').exists() or config.read_bytes() != saved:
                        raise RuntimeError('Uninstall verification failed or user settings were removed.')
                    print('MSI uninstall passed; user settings preserved.', flush=True)
            finally:
                if original_local is None:
                    os.environ.pop('LOCALAPPDATA', None)
                else:
                    os.environ['LOCALAPPDATA'] = original_local
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
