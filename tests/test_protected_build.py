import unittest
from build_protected import dependencies, verify_analysis


class ProtectionChecks(unittest.TestCase):
    def test_app_dependency_closure_includes_credentials_and_worker(self):
        modules, hidden = dependencies('main')
        self.assertTrue({'main', 'worker', 'chzzk_open', 'api', 'core', 'storage', 'bridge', 'autodetect', 'process_detect', 'updater', 'version'} <= set(modules))
        self.assertTrue({'requests', 'PySide6.QtWidgets', 'ctypes.wintypes', 'winreg'} <= set(hidden))
        self.assertNotIn('updater_app', modules)

    def test_compiled_modules_are_accepted(self):
        verify_analysis([('requests', '/third-party/requests.py', 'PYMODULE')],
            [('main.pyd', '/native/main.pyd', 'EXTENSION')], [], ['main'])

    def test_source_fallback_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'bytecode'):
            verify_analysis([('main', '/source/main.py', 'PYMODULE')], [], [], ['main'])

    def test_missing_native_module_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'Missing native'):
            verify_analysis([], [], [], ['main'])

    def test_accidental_source_data_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'source/debug'):
            verify_analysis([], [('main.pyd', '/native/main.pyd', 'EXTENSION')],
                [('main.py', '/source/main.py', 'DATA')], ['main'])


if __name__ == '__main__':
    unittest.main()
