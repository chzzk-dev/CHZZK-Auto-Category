import os
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from main import Window
from storage import normalize_config

ROOT = Path(__file__).resolve().parent.parent


class ImmediateStopWorker(QObject):
    finished = Signal()

    def isRunning(self):
        return True

    def submit(self, command):
        if command != 'stop':
            raise AssertionError(command)
        self.finished.emit()


class ShutdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_fast_worker_shutdown_still_finishes_app_exit_once(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'LOCALAPPDATA': folder}):
            window = Window(normalize_config({'autostart': False, 'auto_update': False,
                                              'auto_start_change': False}), preview=True)
            self.addCleanup(window.deleteLater)
            worker = ImmediateStopWorker()
            with patch.object(window, 'worker', worker), patch.object(window, 'finish_quit') as finish:
                window.quit_app()
                window.quit_app()
                finish.assert_called_once_with()


HOST_SCRIPT = '''
import os
from pathlib import Path
import subprocess
import sys
import time
root, folder, mode = sys.argv[1:]
folder = Path(folder)
with (folder / 'helper.log').open('w', encoding='utf-8') as log:
    helper = subprocess.Popen([sys.executable, str(folder / 'helper.py'), root,
                               str(folder), str(os.getpid())], stdout=log, stderr=log)
(folder / 'helper-pid.tmp').write_text(str(helper.pid))
(folder / 'helper-pid.tmp').replace(folder / 'helper.pid')
if mode == 'normal':
    while not (folder / 'ready').exists() and helper.poll() is None:
        time.sleep(0.02)
else:
    time.sleep(45)
'''


HELPER_SCRIPT = '''
import hashlib
import io
import json
from pathlib import Path
import sys
from unittest.mock import patch
root, folder, parent_pid = sys.argv[1:]
sys.path.insert(0, root)
import updater_app
folder, parent_pid = Path(folder), int(parent_pid)
install = folder / 'app'
install.mkdir()
(install / updater_app.APP_EXE_NAME).write_bytes(b'previous app')
payload = b'verified fixture MSI'
info = {'version': '4.12.14', 'package_name': 'ChzzkAutoCategory-4.12.14.msi',
        'package_url': 'https://example.test/fixture.msi', 'checksum_url': 'https://example.test/hash'}
response = io.BytesIO(payload)
response.headers = {}
worker = updater_app.UpdateWorker(parent_pid, info['version'], install, restart=False)
failed, completed, installed = [], [], []
worker.failed.connect(failed.append)
worker.finished_ok.connect(completed.append)
wait_parent_exit = updater_app._wait_parent_exit
def wait(pid, timeout=18):
    return wait_parent_exit(pid, timeout=1 if timeout == 18 else timeout)
def install_msi(package, destination, log):
    assert not updater_app._pid_running(parent_pid), 'Parent still holds the app files'
    assert package.read_bytes() == payload
    installed.append(True)
    return False
with patch.object(updater_app, '_wait_parent_exit', side_effect=wait), \\
     patch.object(updater_app, '_latest_release', return_value=info), \\
     patch.object(updater_app, '_expected_hash', return_value=hashlib.sha256(payload).hexdigest()), \\
     patch.object(updater_app, '_request', return_value=response), \\
     patch.object(updater_app, 'CONFIG_DIR', folder / 'config'), \\
     patch.object(updater_app, '_install_msi', side_effect=install_msi):
    (folder / 'ready').write_text('ready')
    worker.run()
(folder / 'result.tmp').write_text(json.dumps({'failed': failed, 'completed': completed,
                                              'installed': installed}), encoding='utf-8')
(folder / 'result.tmp').replace(folder / 'result.json')
'''


@unittest.skipUnless(os.name == 'nt', 'Requires actual Windows process termination')
class WindowsUpdaterLifecycleTests(unittest.TestCase):
    def test_updater_finishes_after_normal_and_forced_parent_exit(self):
        import psutil
        for mode in ('normal', 'forced'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                (folder / 'host.py').write_text(HOST_SCRIPT, encoding='utf-8')
                (folder / 'helper.py').write_text(HELPER_SCRIPT, encoding='utf-8')
                helper = None
                with (folder / 'host.log').open('w', encoding='utf-8') as log:
                    host = subprocess.Popen([sys.executable, str(folder / 'host.py'), str(ROOT),
                                             str(folder), mode], stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 8
                    while not (folder / 'helper.pid').exists() and time.monotonic() < deadline:
                        time.sleep(0.02)
                    self.assertTrue((folder / 'helper.pid').exists(), 'Fixture did not launch the updater')
                    helper = psutil.Process(int((folder / 'helper.pid').read_text()))
                    host.wait(timeout=15)
                    if mode == 'normal':
                        self.assertEqual(host.returncode, 0)
                    else:
                        self.assertNotEqual(host.returncode, 0)
                    result_path = folder / 'result.json'
                    deadline = time.monotonic() + 10
                    while not result_path.exists() and helper.is_running() and time.monotonic() < deadline:
                        time.sleep(0.02)
                    diagnostic = (folder / 'helper.log').read_text(encoding='utf-8')
                    self.assertTrue(result_path.exists(), 'Updater exited with its parent. ' + diagnostic)
                    result = json.loads(result_path.read_text(encoding='utf-8'))
                    self.assertEqual(result['failed'], [], diagnostic)
                    self.assertEqual(result['installed'], [True])
                    self.assertEqual(result['completed'], [str(folder / 'app' / 'ChzzkAutoCategory.exe')])
                    helper.wait(timeout=5)
                finally:
                    if host.poll() is None:
                        host.kill()
                        host.wait(timeout=5)
                    if helper is not None:
                        try:
                            helper.kill()
                            helper.wait(timeout=5)
                        except psutil.NoSuchProcess:
                            pass


if __name__ == '__main__':
    unittest.main()
