"""Verify real MSI commands on a disposable GitHub-hosted Windows runner."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from updater_app import _install_msi
from version import APP_VERSION

REPOSITORY = 'chzzk-dev/CHZZK-Auto-Category'


def baseline_release():
    result = subprocess.run(['gh', 'api', f'repos/{REPOSITORY}/releases?per_page=100'],
                            capture_output=True, text=True, encoding='utf-8', check=True)
    candidates = []
    current = tuple(map(int, APP_VERSION.split('.')))
    for release in json.loads(result.stdout):
        version = release['tag_name'].removeprefix('v')
        if release['draft'] or release['prerelease'] or not re.fullmatch(r'\d+\.\d+\.\d+', version):
            continue
        key = tuple(map(int, version.split('.')))
        asset = next((a for a in release['assets'] if a['name'] == f'ChzzkAutoCategory-{version}.msi'), None)
        eligible = key < current or (key == current and os.environ.get('REBUILD_RELEASE') == 'true')
        if eligible and asset and str(asset.get('digest', '')).startswith('sha256:'):
            candidates.append((key, version, release['tag_name'], asset['digest'].split(':', 1)[1]))
    if not candidates:
        raise RuntimeError('No previous stable MSI with a GitHub checksum is available for upgrade verification.')
    return max(candidates)[1:]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def installed_version():
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'Software\CHZZK Dev\AutoCategory',
                        0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        return winreg.QueryValueEx(key, 'Version')[0]


def installed_products():
    import winreg
    products = set()
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
            r'Software\Microsoft\Windows\CurrentVersion\Uninstall',
            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as uninstall:
        for index in range(winreg.QueryInfoKey(uninstall)[0]):
            name = winreg.EnumKey(uninstall, index)
            with winreg.OpenKey(uninstall, name) as product:
                try:
                    if winreg.QueryValueEx(product, 'DisplayName')[0] == 'CHZZK Auto Category':
                        products.add(name)
                except FileNotFoundError:
                    continue
    return products


def malformed_property_result(package, target):
    """Check MSI's property parser without any interactive error/help window."""
    msi = ctypes.WinDLL('msi', use_last_error=True)
    msi.MsiSetInternalUI.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)]
    msi.MsiSetInternalUI.restype = ctypes.c_uint
    msi.MsiInstallProductW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    msi.MsiInstallProductW.restype = ctypes.c_uint
    previous = msi.MsiSetInternalUI(2, None)  # INSTALLUILEVEL_NONE
    try:
        properties = subprocess.list2cmdline(['INSTALLFOLDER=' + str(target)])
        return msi.MsiInstallProductW(str(package), properties)
    finally:
        msi.MsiSetInternalUI(previous, None)


def main():
    if os.name != 'nt' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Run this integration check only on the disposable Windows CI runner.')
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError('The Windows MSI verification runner must be elevated.')
    base_version, base_tag, base_hash = baseline_release()
    print('Upgrade verification baseline:', base_version, flush=True)
    logs = ROOT / 'build/msi-smoke'
    logs.mkdir(parents=True, exist_ok=True)
    current = ROOT / 'dist-installer' / f'ChzzkAutoCategory-{APP_VERSION}.msi'
    payload = ROOT / 'dist/ChzzkAutoCategory'
    msiexec = str(Path(os.environ['SystemRoot']) / 'System32/msiexec.exe')
    target = Path(os.environ['ProgramFiles']) / 'CHZZK MSI test & 한글'
    if target.exists():
        raise RuntimeError('The test destination already exists; refusing to use it.')
    installed_package = None
    with tempfile.TemporaryDirectory(prefix='chzzk-msi-') as temporary:
        directory = Path(temporary) / '다운로드 & test'
        directory.mkdir()
        baseline = directory / f'ChzzkAutoCategory-{base_version}.msi'
        subprocess.run(['gh', 'release', 'download', base_tag, '--repo', REPOSITORY,
                        '--pattern', baseline.name, '--dir', str(directory)], check=True, timeout=120)
        if digest(baseline) != base_hash:
            raise RuntimeError('The baseline MSI does not match its GitHub checksum.')
        profile = Path(temporary) / 'profile'
        config = profile / 'ChzzkAutoCategory/config.json'
        config.parent.mkdir(parents=True)
        saved = json.dumps({'setup_completed': True, 'pending_sound': False, 'autostart': False,
                            'rules': [{'process': 'Test.exe', 'category_id': 'test', 'category_name': 'Test'}]}).encode()
        config.write_bytes(saved)
        original_local = os.environ.get('LOCALAPPDATA')
        os.environ['LOCALAPPDATA'] = str(profile)
        try:
            legacy = malformed_property_result(baseline, target)
            print('Legacy whole-property quoting MSI parser result:', legacy, flush=True)
            if legacy in (0, 3010, 1641):
                installed_package = baseline
            if legacy not in (87, 1639):
                raise RuntimeError('The MSI property parser did not reject the legacy invalid argument.')

            _install_msi(baseline, target, logs / 'baseline-install.log')
            installed_package = baseline
            if installed_version() != base_version or not (target / 'ChzzkAutoCategory.exe').is_file():
                raise RuntimeError('The baseline was not installed at the specified Unicode/space path.')
            if config.read_bytes() != saved:
                raise RuntimeError('Installing the baseline changed user settings.')
            print('Fixed command installed the baseline successfully.', flush=True)
            baseline_products = installed_products()
            if len(baseline_products) != 1:
                raise RuntimeError('The baseline must have exactly one registered product.')

            _install_msi(current, target, logs / 'upgrade-install.log')
            installed_package = current
            if installed_version() != APP_VERSION:
                raise RuntimeError('Windows Installer did not register the upgraded version.')
            for executable in ('ChzzkAutoCategory.exe', 'ChzzkAutoUpdater.exe'):
                if digest(target / executable) != digest(payload / executable):
                    raise RuntimeError('The installed executable does not match the new build: ' + executable)
            if config.read_bytes() != saved:
                raise RuntimeError('Upgrading changed user settings.')
            products = installed_products()
            if len(products) != 1 or products == baseline_products:
                raise RuntimeError('The old product registration was not replaced exactly once.')
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
