"""Package the existing protected Windows build into a single MSI."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from version import APP_VERSION

WIX_VERSION = '5.0.2'
NS = 'http://wixtoolset.org/schemas/v4/wxs'
UPGRADE_CODE = '7B7F910F-CE5A-48B5-A8B4-3A7951598B62'
COMPONENT_NAMESPACE = uuid.UUID('1b4d79df-66ae-46dd-8b12-6907492454fc')
LEGACY_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\CHZZK Auto Category'
ET.register_namespace('', NS)


def element(parent, tag, **attrs):
    return ET.SubElement(parent, '{' + NS + '}' + tag, attrs)


def validate_version(version):
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('MSI version must have three numeric parts, e.g. 4.11.1.')
    if any(n > limit for n, limit in zip(map(int, version.split('.')), (255, 255, 65535))):
        raise ValueError('MSI version exceeds Windows Installer limits.')
    return version


def stable_id(prefix, relative):
    return prefix + hashlib.sha256(relative.casefold().encode('utf-8')).hexdigest()[:32]


def write_source(payload, output, version=APP_VERSION, embedded_ui=None, completion_actions=None):
    validate_version(version)
    payload = Path(payload).resolve()
    for required in ('ChzzkAutoCategory.exe', 'ChzzkAutoUpdater.exe', 'msi-install.json'):
        if not (payload / required).is_file():
            raise ValueError(f'Missing build output: {required}')
    if not (payload / '_internal').is_dir():
        raise ValueError('Missing PyInstaller _internal directory.')

    root = ET.Element('{' + NS + '}Wix')
    package = element(root, 'Package', Name='CHZZK Auto Category', Manufacturer='CHZZK Dev',
                      Version=version, UpgradeCode=UPGRADE_CODE, Language='1042',
                      Codepage='949', Scope='perMachine', InstallerVersion='500')
    element(package, 'SummaryInformation', Codepage='949', Description='CHZZK Auto Category installer')
    element(package, 'MajorUpgrade', Schedule='afterInstallInitialize',
            DowngradeErrorMessage='더 최신 버전이 설치되어 있습니다. 먼저 해당 버전을 제거해 주세요.')
    element(package, 'MediaTemplate', EmbedCab='yes', CompressionLevel='high')
    element(package, 'Property', Id='MsiLogging', Value='voicewarmupx')
    element(package, 'Property', Id='REBOOT', Value='ReallySuppress')
    element(package, 'Property', Id='ARPURLINFOABOUT', Value='https://github.com/chzzk-dev/CHZZK-Auto-Category')
    element(package, 'SetProperty', Id='ARPINSTALLLOCATION', Value='[INSTALLFOLDER]', After='CostFinalize')
    element(package, 'Icon', Id='AppIcon.ico', SourceFile=str(ROOT / 'chzzk_auto_category.ico'))
    element(package, 'Property', Id='ARPPRODUCTICON', Value='AppIcon.ico')
    # Advertised shortcuts require a PE icon stream with the target's extension.
    element(package, 'Icon', Id='ShortcutIcon.exe', SourceFile=str(payload / 'ChzzkAutoCategory.exe'))

    # Refuse to layer MSI ownership over the legacy installer's destructive uninstaller.
    legacy_properties = []
    for hive in ('HKLM', 'HKCU'):
        for bitness in ('always64', 'always32'):
            prop_id = 'LEGACY_' + hive + ('64' if bitness == 'always64' else '32')
            legacy_properties.append(prop_id)
            prop = element(package, 'Property', Id=prop_id)
            element(prop, 'RegistrySearch', Id='Search' + prop_id, Root=hive, Key=LEGACY_KEY,
                    Name='UninstallString', Type='raw', Bitness=bitness)
    element(package, 'Launch', Condition='Installed OR NOT (' + ' OR '.join(legacy_properties) + ')',
            Message='기존 EXE 설치본을 먼저 제거해 주세요. 제거 창에서 사용자 설정 삭제 체크를 해제하면 설정을 유지할 수 있습니다. 그 다음 이 MSI를 다시 실행해 주세요.')
    prop = element(package, 'Property', Id='INSTALLFOLDER', Secure='yes')
    element(prop, 'RegistrySearch', Id='PreviousMsiFolder', Root='HKLM',
            Key=r'Software\CHZZK Dev\AutoCategory', Name='InstallDir', Type='raw', Bitness='always64')

    program_files = element(package, 'StandardDirectory', Id='ProgramFiles64Folder')
    install = element(program_files, 'Directory', Id='INSTALLFOLDER', Name='CHZZK Auto Category')
    directories = {'.': install}
    components = []
    paths_seen = set()
    files = sorted((p for p in payload.rglob('*') if p.is_file()), key=lambda p: p.relative_to(payload).as_posix().casefold())
    for source in files:
        relative = source.relative_to(payload)
        rel = relative.as_posix()
        if source.is_symlink() or any(p.is_symlink() for p in source.parents if p != payload.parent):
            raise ValueError(f'Symlink in build output: {rel}')
        if rel.casefold() in paths_seen:
            raise ValueError(f'Case-insensitive duplicate path: {rel}')
        paths_seen.add(rel.casefold())
        if source.name in ('ChzzkAutoUninstall.exe', 'ChzzkAutoCategory-Setup.exe'):
            raise ValueError(f'Legacy installer in payload: {rel}. Run build_release.bat again.')
        parent = install
        for index, part in enumerate(relative.parts[:-1], 1):
            key = '/'.join(relative.parts[:index])
            if key not in directories:
                directories[key] = element(parent, 'Directory', Id=stable_id('D', key), Name=part)
            parent = directories[key]
        component_id = stable_id('C', rel)
        component = element(parent, 'Component', Id=component_id, Bitness='always64',
                            Guid=str(uuid.uuid5(COMPONENT_NAMESPACE, rel.casefold())).upper())
        components.append(component_id)
        file_id = {'ChzzkAutoCategory.exe': 'AppExe', 'ChzzkAutoUpdater.exe': 'UpdaterExe'}.get(rel, stable_id('F', rel))
        file = element(component, 'File', Id=file_id, Source=str(source), KeyPath='yes')
        if file_id == 'AppExe':
            element(file, 'Shortcut', Id='StartMenuShortcut', Directory='ProgramMenuFolder',
                    Name='CHZZK Auto Category', WorkingDirectory='INSTALLFOLDER',
                    Advertise='yes', Icon='ShortcutIcon.exe', IconIndex='0')
    element(package, 'StandardDirectory', Id='ProgramMenuFolder')
    registration = element(install, 'Component', Id='InstallRegistration', Guid='A768537E-C225-4A47-BE11-BA8B02F1215B', Bitness='always64')
    element(registration, 'RegistryValue', Root='HKLM', Key=r'Software\CHZZK Dev\AutoCategory',
            Name='InstallDir', Value='[INSTALLFOLDER]', Type='string', KeyPath='yes')
    element(registration, 'RegistryValue', Root='HKLM', Key=r'Software\CHZZK Dev\AutoCategory',
            Name='Version', Value=version, Type='string')
    feature = element(package, 'Feature', Id='MainFeature', Title='CHZZK Auto Category', Level='1')
    for component_id in components + ['InstallRegistration']:
        element(feature, 'ComponentRef', Id=component_id)

    element(package, 'Property', Id='WIXUI_EXITDIALOGOPTIONALCHECKBOXTEXT', Value='CHZZK Auto Category 실행')
    element(package, 'Property', Id='WIXUI_EXITDIALOGOPTIONALCHECKBOX', Value='1')
    element(package, 'CustomAction', Id='LaunchApp', FileRef='AppExe',
            ExeCommand='--after-install', Impersonate='yes', Return='asyncNoWait')
    element(package, 'UIRef', Id='ChzzkInstallUI')
    element(package, 'UIRef', Id='WixUI_ErrorProgressText')
    modern = embedded_ui or ROOT / 'build/msi/modern-ui/ChzzkInstallerUI.CA.dll'
    actions = completion_actions or ROOT / 'build/msi/custom-actions/ChzzkInstallerActions.CA.dll'
    if Path(modern).resolve() == Path(actions).resolve():
        raise ValueError('Embedded UI and custom actions must use separate DLLs.')
    element(package, 'Property', Id='CHZZK_MODERN_UI', Secure='yes')
    element(package, 'Property', Id='CHZZK_USE_NATIVE_UI', Secure='yes')
    element(package, 'Binary', Id='CompletionActionsBinary', SourceFile=str(Path(actions).resolve()))
    element(package, 'CustomAction', Id='ReportUiCompleted', BinaryRef='CompletionActionsBinary',
            DllEntry='ReportCompleted', Execute='immediate', Return='check')
    ui = element(package, 'UI')
    element(ui, 'EmbeddedUI', Id='ChzzkModernUI', SourceFile=str(Path(modern).resolve()),
            SupportBasicUI='no', IgnoreResolveSource='yes',
            IgnoreInstallEnd='no')
    # Only the uninstalling user's startup entries are removed; user data stays intact.
    element(package, 'CustomAction', Id='CleanupUserStartup', FileRef='UpdaterExe',
            ExeCommand='--cleanup-user', Execute='immediate', Impersonate='yes', Return='ignore')
    sequence = element(package, 'InstallExecuteSequence')
    element(sequence, 'Custom', Action='CleanupUserStartup', Before='RemoveFiles',
            Condition='REMOVE = "ALL" AND NOT UPGRADINGPRODUCTCODE')
    element(sequence, 'Custom', Action='ReportUiCompleted', After='InstallFinalize',
            Condition='CHZZK_MODERN_UI = "1"')
    ET.indent(root, space='  ')
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(output, encoding='utf-8', xml_declaration=True)
    return Path(output)


def validate_wrapper(dll, required, forbidden, label):
    """Reject swapped or stale native wrappers before linking the MSI."""
    import pefile  # Installed by the existing PyInstaller build requirements.
    pe = pefile.PE(str(dll))
    try:
        export_table = getattr(pe, 'DIRECTORY_ENTRY_EXPORT', None)
        exports = {entry.name for entry in export_table.symbols} if export_table else set()
        if pe.FILE_HEADER.Machine != 0x8664 or not required <= exports or forbidden & exports:
            raise RuntimeError(f'{label} must be an x64 DLL with the correct, separate entry points.')
    finally:
        pe.close()


def build_dtf_wrapper(env, folder, assembly, required, forbidden, label):
    output = ROOT / 'build/msi' / folder
    output.mkdir(parents=True, exist_ok=True)
    dll = output / f'{assembly}.CA.dll'
    dll.unlink(missing_ok=True)
    subprocess.run(['dotnet', 'build', str(ROOT / 'installer' / folder / f'{assembly}.csproj'),
                    '--configuration', 'Release', '-p:Platform=x64', '--output', str(output)],
                   check=True, cwd=ROOT, env=env)
    if not dll.is_file():
        raise RuntimeError(f'DTF did not produce {dll.name}. Do not substitute the managed .dll.')
    validate_wrapper(dll, required, forbidden, label)
    return dll


def build_embedded_ui(env):
    return build_dtf_wrapper(env, 'modern-ui', 'ChzzkInstallerUI',
                             {b'InitializeEmbeddedUI', b'EmbeddedUIHandler', b'ShutdownEmbeddedUI'},
                             {b'ReportCompleted'}, 'Embedded UI')


def build_completion_actions(env):
    return build_dtf_wrapper(env, 'custom-actions', 'ChzzkInstallerActions',
                             {b'ReportCompleted'},
                             {b'InitializeEmbeddedUI', b'EmbeddedUIHandler', b'ShutdownEmbeddedUI'},
                             'Completion actions')


def build():
    if sys.platform != 'win32' or struct.calcsize('P') != 8:
        raise RuntimeError('MSI builds require 64-bit Windows Python.')
    if not shutil.which('dotnet'):
        raise RuntimeError('Install the .NET 8 SDK (x64), reopen the terminal, and retry.')
    payload = ROOT / 'dist' / 'ChzzkAutoCategory'
    if not (payload / 'ChzzkAutoCategory.exe').is_file():
        raise RuntimeError('Build the app and updater first: build_release.bat')
    (payload / 'msi-install.json').write_text('{"installer": "msi"}\n', encoding='utf-8')
    env = dict(os.environ, DOTNET_ROLL_FORWARD='Major')
    modern_ui = build_embedded_ui(env)
    actions = build_completion_actions(env)
    source = write_source(payload, ROOT / 'build' / 'msi' / 'Product.wxs',
                          embedded_ui=modern_ui, completion_actions=actions)
    tool_dir = ROOT / 'build' / f'wix-{WIX_VERSION}'
    tool = tool_dir / 'wix.exe'
    if not tool.is_file():
        subprocess.run(['dotnet', 'tool', 'install', 'wix', '--tool-path', str(tool_dir),
                        '--version', WIX_VERSION], check=True, cwd=ROOT, env=env)
    for extension in ('WixToolset.UI.wixext', 'WixToolset.Util.wixext'):
        subprocess.run([str(tool), 'extension', 'add', f'{extension}/{WIX_VERSION}'],
                       check=True, cwd=ROOT, env=env)
    output = ROOT / 'dist-installer' / f'ChzzkAutoCategory-{APP_VERSION}.msi'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    subprocess.run([str(tool), 'build', str(source), str(ROOT / 'installer/msi/SetupUI.wxs'),
                    '-arch', 'x64', '-culture', 'ko-KR',
                    '-ext', f'WixToolset.UI.wixext/{WIX_VERSION}',
                    '-ext', f'WixToolset.Util.wixext/{WIX_VERSION}',
                    '-intermediateFolder', str(ROOT / 'build/msi/obj'), '-o', str(output)],
                   check=True, cwd=ROOT, env=env)
    if not output.is_file():
        raise RuntimeError('WiX did not produce an MSI.')
    print('MSI:', output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--generate-only', metavar='PAYLOAD', type=Path,
                        help='Generate WiX XML without compiling an MSI (developer validation).')
    args = parser.parse_args()
    try:
        if args.generate_only:
            print(write_source(args.generate_only, ROOT / 'build/msi/Product.wxs'))
        else:
            build()
    except Exception as exc:
        print(f'MSI build FAILED: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
