import json
import os
from pathlib import Path
import sys
import subprocess
import base64
import copy
import time
from scheduling import bounded_minutes
import ctypes
from ctypes import wintypes


APP_NAME = 'ChzzkAutoCategory'
WEBSTORE_EXTENSION_ID = 'jeefpiogpjbphganmnooglppcdicinoh'
AUTOSTART_VALUE = 'ChzzkAutoCategory'
AUTOSTART_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
STARTUP_APPROVED_KEY = r'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run'
PRODUCT_NAME = 'CHZZK Auto Category'

DEFAULT_CONFIG = {
    'setup_completed': False,
    'channel': '',
    'interval': 5,
    'rules': [],
    'auto_rules': [],
    'auto_pending': [],
    'auto_detect': True,
    'auto_aggressive': True,
    'auto_resolve_shared': False,
    'discord_refresh_hours': 24,
    'notify': True,
    'pending_sound': True,
    'start_hidden': False,
    'autostart': True,
    'auto_update': True,
    'update_check_minutes': 180,
    'update_notify': True,
    'auto_start_change': True,
    'bridge_port': 5000,
    'extension_id': WEBSTORE_EXTENSION_ID,
    'chzzk_open_enabled': True,
    'schema_version': 2,
    'category_sync_hours': 6,
    'update_last_checked_at': 0,
    'allow_prerelease': False,
    'game_aliases': {},
    'excluded_processes': [],
    'preferred_process': '',
    'only_when_live': False,
    'league_mode': 'ask',
    'close_to_tray': True,
    'minimize_to_tray': True,
    'detailed_logs': True,
}


def data_dir():
    path = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def normalize_config(value):
    config = copy.deepcopy(DEFAULT_CONFIG)
    if isinstance(value, dict):
        config.update(value)
    config['setup_completed'] = config.get('setup_completed') is True

    config['interval'] = max(3, min(60, int(config.get('interval', 5))))
    config['discord_refresh_hours'] = max(1, min(168, int(config.get('discord_refresh_hours', 24))))
    config['auto_detect'] = bool(config.get('auto_detect', True))
    config['auto_aggressive'] = True  # Matching is mandatory; manual rules stay first.
    # Name-only detection cannot distinguish games sharing one executable name.
    config['auto_resolve_shared'] = False
    config['notify'] = bool(config.get('notify', True))
    config['pending_sound'] = bool(config.get('pending_sound', True))
    config['start_hidden'] = bool(config.get('start_hidden', False))
    config['autostart'] = bool(config.get('autostart', True))
    config['auto_update'] = bool(config.get('auto_update', True))
    config['update_check_minutes'] = bounded_minutes(config.get('update_check_minutes', 180))
    config['category_sync_hours'] = max(1, min(168, int(config.get('category_sync_hours', 6))))
    config['schema_version'] = 2
    for key in ('allow_prerelease', 'only_when_live', 'close_to_tray', 'minimize_to_tray', 'detailed_logs'):
        config[key] = bool(config.get(key, DEFAULT_CONFIG[key]))
    if not isinstance(config.get('game_aliases'), dict):
        config['game_aliases'] = {}
    config['game_aliases'] = {str(k): [str(a).strip() for a in v if isinstance(a, str) and a.strip()][:32]
                              for k, v in config['game_aliases'].items() if isinstance(v, list)}
    if not isinstance(config.get('excluded_processes'), list):
        config['excluded_processes'] = []
    config['update_notify'] = bool(config.get('update_notify', True))
    config['auto_start_change'] = bool(config.get('auto_start_change', True))
    config['bridge_port'] = max(1024, min(65535, int(config.get('bridge_port', 5000))))
    config['extension_id'] = str(config.get('extension_id') or WEBSTORE_EXTENSION_ID).strip().lower()
    config['chzzk_open_enabled'] = bool(config.get('chzzk_open_enabled', True))
    config.pop('chzzk_client_id', None)
    config.pop('chzzk_client_secret', None)

    for key in ('rules', 'auto_rules', 'auto_pending'):
        if not isinstance(config.get(key), list):
            config[key] = []
    return config


def load_config():
    path = data_dir() / 'config.json'
    if not path.exists():
        return copy.deepcopy(DEFAULT_CONFIG)
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('설정 파일의 형식이 올바르지 않습니다.')
    if not isinstance(value.get('rules', []), list):
        raise ValueError('설정 파일의 형식이 올바르지 않습니다.')
    normalized = normalize_config(value)
    if value.get('schema_version') != 2:
        backup = path.with_name('config.pre-v2.backup.json')
        if not backup.exists():
            # Exact bytes, before any migration writes; failure keeps original intact.
            with backup.open('xb') as stream:
                stream.write(path.read_bytes())
    return normalized


def save_config(config):
    path = data_dir() / 'config.json'
    temp = path.with_suffix('.tmp')
    if path.exists():
        existing = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(existing, dict) and existing.get('schema_version') != 2:
            backup = path.with_name('config.pre-v2.backup.json')
            if not backup.exists():
                with backup.open('xb') as stream:
                    stream.write(path.read_bytes())
    normalized = normalize_config(config)
    temp.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def discord_cache_file():
    return data_dir() / 'discord_detectable.json'

def chzzk_catalog_cache_file():
    return data_dir() / 'chzzk_category_catalog.json'


def _chzzk_secret_file():
    return data_dir() / 'chzzk_open_secret.dat'


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_byte))]


def _blob_from_bytes(data):
    raw = bytes(data or b'')
    buffer = ctypes.create_string_buffer(raw, max(1, len(raw)))
    blob = _DATA_BLOB(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _dpapi_protect(data):
    if sys.platform != 'win32':
        raise RuntimeError('CHZZK Client Secret 보호 저장은 Windows에서만 지원합니다.')
    in_blob, _buffer = _blob_from_bytes(data)
    out_blob = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob), 'CHZZK Auto Category Open API', None, None, None, 0,
        ctypes.byref(out_blob),
    ):
        raise OSError('Windows DPAPI로 CHZZK Client Secret을 보호하지 못했습니다.')
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(data):
    if sys.platform != 'win32':
        return b''
    in_blob, _buffer = _blob_from_bytes(data)
    out_blob = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob),
    ):
        return b''
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def save_chzzk_client_secret(secret):
    value = str(secret or '').strip()
    path = _chzzk_secret_file()
    if not value:
        if path.exists():
            path.unlink()
        return
    if sys.platform == 'win32':
        protected = _dpapi_protect(value.encode('utf-8'))
        path.write_bytes(base64.b64encode(protected))
    else:
        # Source-development fallback only. Packaged Windows builds use DPAPI above.
        path.write_text(value, encoding='utf-8')


def get_chzzk_client_secret():
    env_value = str(os.environ.get('CHZZK_CLIENT_SECRET') or '').strip()
    if env_value:
        return env_value
    path = _chzzk_secret_file()
    if not path.exists():
        return ''
    try:
        if sys.platform == 'win32':
            protected = base64.b64decode(path.read_bytes())
            return _dpapi_unprotect(protected).decode('utf-8')
        return path.read_text(encoding='utf-8').strip()
    except Exception:
        return ''


def installed_executable():
    """Return the packaged Windows executable path, or None while running from source."""
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        return None
    return Path(sys.executable).resolve()


def autostart_command(executable=None):
    exe = Path(executable).resolve() if executable else installed_executable()
    if exe is None:
        return None
    return f'"{exe}" --background --autostart'


def _set_startup_approval(enabled):
    """Keep the Windows Settings/Task Manager Startup toggle in sync.

    Windows stores the command in the Run key and the enabled/disabled state separately
    under StartupApproved.  Recreating the Run value during a clean update can otherwise
    leave the Startup Apps UI in a disabled state.
    """
    import winreg

    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        STARTUP_APPROVED_KEY,
        0,
        winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
    ) as key:
        if enabled:
            winreg.SetValueEx(
                key, AUTOSTART_VALUE, 0, winreg.REG_BINARY,
                bytes((0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00)),
            )
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_VALUE)
            except FileNotFoundError:
                pass


def set_windows_autostart(enabled, executable=None):
    """Register/unregister per-user startup and restore its enabled state.

    The installed app starts with --background --autostart so Windows login never opens
    the main window; only the tray icon, local bridge and automation start normally.
    """
    if sys.platform != 'win32':
        return False

    command = autostart_command(executable)
    if enabled and not command:
        return False

    import winreg

    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        AUTOSTART_KEY,
        0,
        winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
    ) as key:
        if enabled:
            winreg.SetValueEx(key, AUTOSTART_VALUE, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_VALUE)
            except FileNotFoundError:
                pass

    _set_startup_approval(bool(enabled))
    return True


def windows_autostart_enabled():
    if sys.platform != 'win32':
        return False

    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
            value, _ = winreg.QueryValueEx(key, AUTOSTART_VALUE)
    except FileNotFoundError:
        return False

    expected = autostart_command()
    command_ok = bool(value) if not expected else str(value).strip() == expected
    if not command_ok:
        return False

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
            approval, _ = winreg.QueryValueEx(key, AUTOSTART_VALUE)
        if isinstance(approval, (bytes, bytearray)) and approval:
            return approval[0] in (0x02, 0x06)
    except FileNotFoundError:
        pass
    return True


def start_menu_shortcut_path(common=False):
    if sys.platform != 'win32':
        return None
    if common:
        base = Path(os.environ.get('PROGRAMDATA', r'C:\ProgramData'))
    else:
        base = Path(os.environ.get('APPDATA', str(Path.home())))
    return base / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / f'{PRODUCT_NAME}.lnk'


def ensure_start_menu_shortcut(executable=None):
    """Ensure a stable Start-menu shortcut exists.

    Updates keep the shortcut path stable so an existing user Start pin has a stable
    target.  The non-elevated app repairs the per-user shortcut when necessary.
    """
    if sys.platform != 'win32':
        return False
    exe = Path(executable).resolve() if executable else installed_executable()
    if exe is None or not exe.is_file():
        return False

    if (exe.parent / 'msi-install.json').is_file():
        # MSI owns its advertised shortcut and can repair it through Windows.
        return True

    common = start_menu_shortcut_path(common=True)
    if common and common.exists():
        return True

    shortcut = start_menu_shortcut_path(common=False)
    shortcut.parent.mkdir(parents=True, exist_ok=True)
    esc_shortcut = str(shortcut).replace("'", "''")
    esc_exe = str(exe).replace("'", "''")
    esc_work = str(exe.parent).replace("'", "''")
    script = (
        "$w=New-Object -ComObject WScript.Shell;"
        f"$s=$w.CreateShortcut('{esc_shortcut}');"
        f"$s.TargetPath='{esc_exe}';"
        f"$s.WorkingDirectory='{esc_work}';"
        f"$s.IconLocation='{esc_exe},0';"
        "$s.Save()"
    )
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False,
    )
    return result.returncode == 0 and shortcut.exists()
