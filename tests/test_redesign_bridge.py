import json
import threading
import time
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
from bridge import LocalExtensionBridge, BridgeError

ID = 'a' * 32


def info(**changes):
    return {'type': 'extension_info', 'extensionId': ID, 'version': '0.6.0', 'protocolVersion': 1,
            'browser': 'Chrome', 'connected': True, 'sessionId': 'session-a', 'sequence': 1, **changes}


class BridgeStateTests(unittest.TestCase):
    def setUp(self):
        self.bridge = LocalExtensionBridge(extension_id=ID)

    def test_missing_extension_has_no_invented_version(self):
        self.assertEqual(self.bridge.extension_status()['state'], '설치 확인 불가')
        self.assertIsNone(self.bridge.extension_status()['version'])

    def test_real_info_connection_and_stale_version(self):
        with patch('bridge.time.monotonic', return_value=100):
            self.bridge.connected_at = 100
            self.bridge.receive_extension_info(info(), ID)
            self.assertEqual(self.bridge.extension_status()['version'], '0.6.0')
            self.assertEqual(self.bridge.extension_status()['compatibility'], '정상')
        with patch('bridge.time.monotonic', return_value=141):
            state = self.bridge.extension_status()
            self.assertEqual(state['state'], '응답 없음')
            self.assertIsNone(state['version'])

    def test_connected_old_extension_has_unknown_version(self):
        self.bridge.connected_at = time.monotonic()
        self.assertEqual(self.bridge.extension_status()['state'], '버전 확인 불가')
        self.assertIsNone(self.bridge.extension_status()['version'])

    def test_protocol_mismatch_prevents_commands(self):
        self.bridge.server = object()
        self.bridge.connected_at = time.monotonic()
        self.bridge.receive_extension_info(info(protocolVersion=7), ID)
        self.assertEqual(self.bridge.extension_status()['state'], '버전 호환 불가')
        with self.assertRaisesRegex(BridgeError, '호환'):
            self.bridge.request('settings')
        self.assertEqual(self.bridge.commands.qsize(), 0)

    def test_older_heartbeat_and_duplicate_do_not_replace_version(self):
        self.assertTrue(self.bridge.receive_extension_info(info(sequence=3), ID))
        self.assertFalse(self.bridge.receive_extension_info(info(version='0.5.3', sequence=2), ID))
        self.assertFalse(self.bridge.receive_extension_info(info(sequence=3), ID))
        self.assertEqual(self.bridge.extension_info['version'], '0.6.0')

    def test_bad_type_identity_version_or_sequence_rejected(self):
        for change in ({'type': 'settings'}, {'extensionId': 'b'*32}, {'version': 'fake'},
                       {'protocolVersion': '1'}, {'protocolVersion': True}, {'sequence': -1},
                       {'connected': False}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.bridge.receive_extension_info(info(**change), ID)

    def test_restart_has_no_saved_version_claim(self):
        self.bridge.receive_extension_info(info(), ID)
        fresh = LocalExtensionBridge(extension_id=ID)
        self.assertIsNone(fresh.extension_status()['version'])

    def test_expired_or_unknown_results_never_accumulate(self):
        self.assertFalse(self.bridge.accept_result({'id': 'unknown', 'ok': True}))
        self.bridge.pending_ids['old'] = time.monotonic() - 1
        self.assertFalse(self.bridge.accept_result({'id': 'old', 'ok': True}))
        self.bridge.pending_ids['fresh'] = time.monotonic() + 10
        self.assertTrue(self.bridge.accept_result({'id': 'fresh', 'ok': True}))
        self.assertFalse(self.bridge.accept_result({'id': 'fresh', 'ok': True}))
        self.assertEqual(list(self.bridge.results), ['fresh'])

    def test_cancelled_request_removes_queued_request_identity(self):
        self.bridge.server = object()
        self.bridge.connected_at = time.monotonic()
        with self.assertRaisesRegex(BridgeError, '취소'):
            self.bridge.request('settings', cancelled=lambda: True)
        self.assertEqual(self.bridge.pending_ids, {})


class HttpBridgeTests(unittest.TestCase):
    def setUp(self):
        self.bridge = LocalExtensionBridge(port=0, extension_id=ID)
        self.bridge.start()
        self.addCleanup(self.bridge.stop)
        self.base = 'http://127.0.0.1:' + str(self.bridge.server.server_address[1])

    def post(self, path, payload, origin=ID):
        request = urllib.request.Request(self.base + path, data=json.dumps(payload).encode(),
                                         headers={'Content-Type': 'application/json', 'X-Extension-Id': origin,
                                                  'Origin': 'chrome-extension://' + origin})
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_actual_http_info_accepts_manifest_payload_and_rejects_wrong_origin(self):
        self.assertEqual(self.post('/extension/info', info())[0], 200)
        self.assertEqual(self.bridge.extension_status()['version'], '0.6.0')
        self.assertEqual(self.post('/extension/info', info(), origin='b'*32)[0], 403)
        self.assertEqual(self.post('/extension/info', {'type': 'bad'})[0], 400)

    def test_command_poll_and_response_complete_one_request(self):
        self.post('/extension/info', info())
        outcome = []
        t = threading.Thread(target=lambda: outcome.append(self.bridge.request('settings', {'channel': 'a'*32}, timeout=2)))
        t.start()
        code, body = self.post('/extension/poll', info(sequence=2))
        self.assertEqual(code, 200)
        command = body['command']
        self.assertEqual(command['action'], 'settings')
        self.assertEqual(self.post('/extension/result', {'id': command['id'], 'ok': True, 'result': {'status': 200}})[0], 200)
        t.join(3)
        self.assertFalse(t.is_alive())
        self.assertEqual(outcome, [{'status': 200}])
        self.assertEqual(self.bridge.pending_ids, {})

    def test_old_extension_payload_remains_compatible(self):
        self.assertEqual(self.post('/health', {})[0], 200)
        self.assertTrue(self.bridge.connected)
        self.assertEqual(self.bridge.extension_status()['state'], '버전 확인 불가')


if __name__ == '__main__':
    unittest.main()
