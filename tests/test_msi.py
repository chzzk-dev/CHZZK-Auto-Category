import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from installer.build_msi import NS, ROOT, write_source, validate_version, validate_wrapper
import release
import updater
import updater_app

Q = {'w': NS}


class MsiPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = self.root / '한글 경로 & space'
        (self.payload / '_internal' / 'plugins').mkdir(parents=True)
        for name in ('ChzzkAutoCategory.exe', 'ChzzkAutoUpdater.exe', 'msi-install.json', '_internal/plugins/qwindows.dll'):
            (self.payload / name).write_bytes(b'test fixture')

    def source(self, name='Product.wxs'):
        return ET.parse(write_source(self.payload, self.root / name)).getroot()

    def test_every_payload_file_is_owned_and_escaped(self):
        root = self.source()
        sources = [Path(f.attrib['Source']) for f in root.findall('.//w:File', Q)]
        self.assertCountEqual([p.resolve() for p in sources], [p.resolve() for p in self.payload.rglob('*') if p.is_file()])
        self.assertEqual(len(root.findall('.//w:Shortcut', Q)), 1)
        self.assertEqual(root.find('.//w:MediaTemplate', Q).get('EmbedCab'), 'yes')
        launch = root.find(".//w:CustomAction[@Id='LaunchApp']", Q)
        self.assertEqual(launch.get('ExeCommand'), '--after-install')
        icons = {icon.get('Id'): Path(icon.get('SourceFile')) for icon in root.findall('.//w:Icon', Q)}
        shortcut = root.find('.//w:Shortcut', Q)
        app_file = root.find(".//w:File[@Id='AppExe']", Q)
        self.assertEqual(Path(shortcut.get('Icon')).suffix, Path(app_file.get('Source')).suffix)
        self.assertEqual(icons[shortcut.get('Icon')], Path(app_file.get('Source')))
        arp = root.find(".//w:Property[@Id='ARPPRODUCTICON']", Q)
        self.assertEqual(icons[arp.get('Value')].suffix, '.ico')


    def test_components_remain_stable_when_new_file_is_added(self):
        def mapping(root):
            return {c.get('Id'): c.get('Guid') for c in root.findall('.//w:Component', Q)}
        before = mapping(self.source())
        (self.payload / '_internal/new.dll').write_bytes(b'new')
        after = mapping(self.source('Next.wxs'))
        self.assertTrue(before.items() <= after.items())
        self.assertEqual(len(after), len(before) + 1)

    def test_modern_ui_does_not_intercept_passive_updates(self):
        root = self.source()
        embedded = root.find('.//w:EmbeddedUI', Q)
        self.assertEqual(embedded.get('SupportBasicUI'), 'no')
        self.assertEqual(embedded.get('IgnoreResolveSource'), 'yes')
        self.assertEqual(Path(embedded.get('SourceFile')).name, 'ChzzkInstallerUI.CA.dll')
        complete = root.find(".//w:Custom[@Action='ReportUiCompleted']", Q)
        self.assertEqual(complete.get('After'), 'InstallFinalize')
        self.assertEqual(complete.get('Condition'), 'CHZZK_MODERN_UI = "1"')
        self.assertIsNotNone(root.find(".//w:Property[@Id='CHZZK_MODERN_UI'][@Secure='yes']", Q))
        self.assertIsNotNone(root.find(".//w:UIRef[@Id='ChzzkInstallUI']", Q))

    def test_ui_and_completion_actions_use_distinct_dlls(self):
        root = self.source()
        embedded = root.find('.//w:EmbeddedUI', Q)
        action = root.find(".//w:CustomAction[@Id='ReportUiCompleted']", Q)
        binary = root.find(f".//w:Binary[@Id='{action.get('BinaryRef')}']", Q)
        self.assertNotEqual(embedded.get('SourceFile'), binary.get('SourceFile'))
        self.assertEqual(Path(binary.get('SourceFile')).name, 'ChzzkInstallerActions.CA.dll')
        with self.assertRaisesRegex(ValueError, 'separate DLLs'):
            write_source(self.payload, self.root / 'Wrong.wxs', embedded_ui='same.dll', completion_actions='same.dll')

    def test_old_completion_source_is_not_included_by_ui_project(self):
        project = ET.parse(ROOT / 'installer/modern-ui/ChzzkInstallerUI.csproj').getroot()
        self.assertEqual(project.find('PropertyGroup/EnableDefaultCompileItems').text, 'false')
        includes = {item.get('Include') for item in project.findall('ItemGroup/Compile')}
        self.assertEqual(includes, {'EmbeddedInstallerUI.cs', 'InstallState.cs', 'SetupWindow.cs', 'InstallerDiagnostics.cs'})
        resource = project.find("ItemGroup/EmbeddedResource[@Include='SetupWindow.xaml']")
        self.assertEqual(resource.get('LogicalName'), 'Chzzk.Installer.SetupWindow.xaml')

    def test_native_wrapper_validation_rejects_mixed_exports(self):
        import types
        def pe(names, machine=0x8664):
            return types.SimpleNamespace(
                FILE_HEADER=types.SimpleNamespace(Machine=machine),
                DIRECTORY_ENTRY_EXPORT=types.SimpleNamespace(symbols=[types.SimpleNamespace(name=n) for n in names]),
                close=Mock(),
            )
        required = {b'InitializeEmbeddedUI', b'EmbeddedUIHandler', b'ShutdownEmbeddedUI'}
        forbidden = {b'ReportCompleted'}
        module = types.SimpleNamespace(PE=Mock())
        with patch.dict('sys.modules', {'pefile': module}):
            for names, machine in [(required | forbidden, 0x8664), (required, 0x14c), ({b'ReportCompleted'}, 0x8664)]:
                fixture = pe(names, machine)
                module.PE.return_value = fixture
                with self.assertRaisesRegex(RuntimeError, 'separate entry points'):
                    validate_wrapper('fixture.dll', required, forbidden, 'UI')
                fixture.close.assert_called_once()
            fixture = pe(required)
            module.PE.return_value = fixture
            validate_wrapper('fixture.dll', required, forbidden, 'UI')
            fixture.close.assert_called_once()

    def test_legacy_uninstaller_is_never_packaged(self):
        (self.payload / 'ChzzkAutoUninstall.exe').write_bytes(b'old')
        with self.assertRaisesRegex(ValueError, 'Legacy installer'):
            self.source()

    def test_legacy_install_is_blocked_in_both_registry_views(self):
        root = self.source()
        searches = root.findall('.//w:RegistrySearch', Q)
        legacy = [s for s in searches if s.get('Name') == 'UninstallString']
        self.assertEqual(len(legacy), 4)
        self.assertIn('LEGACY_HKLM64', root.find('.//w:Launch', Q).get('Condition'))
        cleanup = root.find(".//w:Custom[@Action='CleanupUserStartup']", Q)
        self.assertIn('NOT UPGRADINGPRODUCTCODE', cleanup.get('Condition'))

    def test_missing_runtime_fails_before_build(self):
        (self.payload / 'ChzzkAutoUpdater.exe').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing build output'):
            self.source()

    def test_msi_version_limits(self):
        for value in ('4.11.1.2', '../bad', '256.0.0', '1.256.0', '1.1.65536'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_version(value)
        self.assertEqual(validate_version('4.11.1'), '4.11.1')

    def test_release_exports_msi_only_with_matching_checksum(self):
        downloads = self.root / 'website/downloads'
        downloads.mkdir(parents=True)
        for name in ('ChzzkAutoCategory-Setup.exe', 'ChzzkAutoCategory-4.10.0.zip', 'ChzzkAutoCategory-4.10.0.msi'):
            (downloads / name).write_bytes(b'old')
        installer = self.root / 'dist-installer' / f'ChzzkAutoCategory-{release.APP_VERSION}.msi'
        installer.parent.mkdir()
        installer.write_bytes(bytes.fromhex('D0CF11E0A1B11AE1') + b'test fixture, not a real MSI')
        with patch.object(release, 'ROOT', self.root), patch.object(release, 'WEB_DOWNLOADS', downloads):
            target, checksum, manifest = release.create_release()
        self.assertEqual({p.name for p in downloads.iterdir()}, {target.name, 'SHA256SUMS.txt', 'latest.json', f'RELEASE_NOTES-{release.APP_VERSION}.md'})
        self.assertIn(hashlib.sha256(target.read_bytes()).hexdigest(), checksum.read_text())
        meta = json.loads(manifest.read_text())
        self.assertEqual(meta['setupUrl'], meta['packageUrl'])
        self.assertTrue(meta['setupUrl'].endswith('.msi'))
        self.assertEqual(meta['installerType'], 'msi')
        self.assertTrue(meta['releaseNotesUrl'].endswith(f'RELEASE_NOTES-{release.APP_VERSION}.md'))


class MsiUpdateTests(unittest.TestCase):
    def latest(self, assets, tag='v4.12.0'):
        body = io.BytesIO(json.dumps({'tag_name': tag, 'assets': assets}).encode())
        with patch.object(updater, '_github_request', return_value=body):
            return updater.fetch_latest_release()

    def test_msi_selected_and_zip_ignored(self):
        info = self.latest([
            {'name': 'ChzzkAutoCategory-99.0.0.zip', 'browser_download_url': 'https://example.test/old.zip'},
            {'name': 'ChzzkAutoCategory-4.12.0.msi', 'browser_download_url': 'https://example.test/new.msi'},
        ])
        self.assertEqual(info['version'], '4.12.0')
        self.assertTrue(info['package_url'].endswith('.msi'))
        self.assertIsNone(self.latest([{'name': 'ChzzkAutoCategory-4.12.0.zip', 'browser_download_url': 'https://example.test/a.zip'}]))
        self.assertIsNone(self.latest([{'name': 'ChzzkAutoCategory-4.13.0.msi', 'browser_download_url': 'https://example.test/wrong.msi'}]))

    def run_worker(self, digest='', fail_install=None):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = root / 'app'
            install.mkdir()
            exe = install / 'ChzzkAutoCategory.exe'
            exe.write_bytes(b'original app')
            worker = updater_app.UpdateWorker(0, '4.12.0', install)
            failed, complete = [], []
            worker.failed.connect(failed.append)
            worker.finished_ok.connect(complete.append)
            response = io.BytesIO(b'new MSI bytes')
            response.headers = {}
            info = {'version': '4.12.0', 'package_name': 'ChzzkAutoCategory-4.12.0.msi',
                    'checksum_url': 'https://example.test/hash', 'package_url': 'https://example.test/new.msi'}
            with patch.object(updater_app, '_latest_release', return_value=info), \
                 patch.object(updater_app, '_expected_hash', return_value=digest), \
                 patch.object(updater_app, '_request', return_value=response), \
                 patch.object(updater_app, 'CONFIG_DIR', root / 'config'), \
                 patch.object(updater_app, '_install_msi', return_value=False, side_effect=fail_install) as install_msi:
                worker.run()
                self.assertEqual(exe.read_bytes(), b'original app')
                return failed, complete, install_msi.call_count

    def test_missing_checksum_prevents_install_and_keeps_old_files(self):
        failed, complete, count = self.run_worker()
        self.assertTrue(failed)
        self.assertFalse(complete)
        self.assertEqual(count, 0)

    def test_bad_checksum_prevents_install_and_keeps_old_files(self):
        failed, complete, count = self.run_worker('0' * 64)
        self.assertTrue(failed)
        self.assertFalse(complete)
        self.assertEqual(count, 0)

    def test_install_failure_keeps_files_and_emits_error(self):
        failed, complete, count = self.run_worker(hashlib.sha256(b'new MSI bytes').hexdigest(), RuntimeError('cancelled'))
        self.assertEqual(failed, ['cancelled'])
        self.assertFalse(complete)
        self.assertEqual(count, 1)

    def test_success_delegates_to_windows_installer(self):
        failed, complete, count = self.run_worker(hashlib.sha256(b'new MSI bytes').hexdigest())
        self.assertFalse(failed)
        self.assertEqual(len(complete), 1)
        self.assertEqual(count, 1)

    def test_msi_result_codes_and_space_safe_arguments(self):
        # Build Paths before mocking os.name so this test can run on Linux.
        package, install, log = Path('/temp dir/new.msi'), Path('/app dir'), Path('/log.txt')
        for code in (0, 3010, 1641, 1602, 1618, 1603, 1639):
            with self.subTest(code=code), patch.object(updater_app.os, 'name', 'nt'), \
                 patch.object(updater_app, 'Path', side_effect=lambda v: type(package)(v)), \
                 patch.object(updater_app.subprocess, 'run', return_value=Mock(returncode=code)) as run:
                if code in (0, 3010, 1641):
                    self.assertEqual(updater_app._install_msi(package, install, log), code != 0)
                else:
                    with self.assertRaises(RuntimeError):
                        updater_app._install_msi(package, install, log)
                args = run.call_args.args[0]
                self.assertIsInstance(args, str)
                self.assertIn('INSTALLFOLDER="' + str(install) + '"', args)
                self.assertIn('/norestart', args)
                self.assertFalse(run.call_args.kwargs['shell'])

    def test_msi_property_quotes_only_the_value_for_windows_paths(self):
        package = r'C:\Temp\다운로드 & test\new.msi'
        log = r'C:\Temp\업데이트 로그\install.log'
        for folder in (r'C:\Program Files\CHZZK Auto Category', 'C:\\한글 설치 & test\\', 'C:\\'):
            with self.subTest(folder=folder):
                command = updater_app._msi_install_command(package, folder, log)
                self.assertIn('INSTALLFOLDER="' + folder + '"', command)
                self.assertNotIn('"INSTALLFOLDER=', command)
                self.assertIn('"' + package + '"', command)
                self.assertIn('/L*v "' + log + '"', command)

    def test_invalid_property_value_does_not_start_windows_installer(self):
        for folder in ('', 'C:\\bad"path', 'C:\\bad\npath', 'C:\\bad\rpath', 'C:\\bad\x00path'):
            with self.subTest(folder=folder), patch.object(updater_app.os, 'name', 'nt'), \
                    patch.object(updater_app.subprocess, 'run') as run:
                with self.assertRaises(ValueError):
                    updater_app._install_msi('new.msi', folder, 'install.log')
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
