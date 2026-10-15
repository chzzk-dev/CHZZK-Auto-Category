import copy
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import requests
from autodetect import DiscordAutoMapper, cleanup_auto_mappings
from steam_lookup import SteamResolver, SteamLookupError, STORE_SEARCH, APP_LIST, STORE_DETAILS, TTL
from worker import Worker
from core import Rule
from diagnostics import redact
from storage import get_steam_api_key, save_steam_api_key, normalize_config

KEY = 'a' * 32  # A synthetic test credential, never a usable key.
GAME = {'id': 'discord-hollow', 'name': 'Hollow Knight', 'aliases': []}
APPID = 367520
KOREAN = '할로우 나이트'


def response(payload, status=200, headers=None):
    return Mock(status_code=status, headers=headers or {}, json=Mock(return_value=payload))


def results(appid=APPID, name='Hollow Knight', localized=KOREAN):
    return [response({'items': [{'id': APPID, 'name': 'Hollow Knight', 'type': 'app'}]}),
            response({'response': {'apps': [{'appid': appid, 'name': name}]}}),
            response({str(APPID): {'success': True, 'data': {'steam_appid': APPID,
                     'type': 'game', 'name': localized}}})]


class SteamLookupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'steam.json'
        self.session = Mock()
        self.resolver = SteamResolver(KEY, self.path, session=self.session)
        self.addCleanup(self.resolver.close)

    def resolve(self):
        return self.resolver.resolve(copy.deepcopy(GAME), 'hollow_knight.exe')

    def test_exact_identity_keyed_validation_and_localized_name_order(self):
        self.session.get.side_effect = results()
        record = self.resolve()
        self.assertEqual(record['appid'], APPID)
        self.assertEqual(record['localized_name'], KOREAN)
        calls = self.session.get.call_args_list
        self.assertEqual([call.args[0] for call in calls], [STORE_SEARCH, APP_LIST, STORE_DETAILS])
        self.assertEqual(calls[1].kwargs['params']['key'], KEY)
        options = json.loads(calls[1].kwargs['params']['input_json'])
        self.assertEqual((options['last_appid'], options['max_results']), (APPID-1, 1))
        self.assertEqual(calls[2].kwargs['params']['l'], 'koreana')
        self.assertNotIn(KEY, self.path.read_text())

    def test_cache_reused_in_memory_and_after_restart_without_network(self):
        self.session.get.side_effect = results()
        self.resolve()
        self.session.get.reset_mock()
        self.assertEqual(self.resolve()['appid'], APPID)
        restarted = SteamResolver(KEY, self.path, session=self.session)
        self.assertEqual(restarted.resolve(GAME, 'HOLLOW_KNIGHT.EXE')['appid'], APPID)
        self.session.get.assert_not_called()

    def test_missing_key_never_requests_steam(self):
        self.resolver.key = ''
        self.assertIsNone(self.resolve())
        self.session.get.assert_not_called()

    def test_shared_name_ids_and_wrong_edition_never_auto_resolve(self):
        for items in ([{'id': i, 'type': 'app', 'name': 'Hollow Knight'} for i in (1, 2)],
                      [{'id': 1, 'type': 'app', 'name': 'Hollow Knight II'}]):
            with self.subTest(items=items):
                self.resolver.records.clear()
                self.session.get.reset_mock()
                self.session.get.side_effect = [response({'items': items})]
                self.assertIsNone(self.resolve())
                self.assertEqual(self.session.get.call_count, 1)
                self.assertIsNone(self.resolve())
                self.assertEqual(self.session.get.call_count, 1)

    def test_official_id_and_name_must_both_match(self):
        for appid, name in ((APPID+1, 'Hollow Knight'), (APPID, 'Hollow Knight II')):
            self.resolver.records.clear()
            self.session.get.reset_mock()
            self.session.get.side_effect = results(appid=appid, name=name)
            self.assertIsNone(self.resolve())
            self.assertEqual(self.session.get.call_count, 2)

    def test_localized_response_cannot_belong_to_another_app(self):
        responses = results()
        responses[-1] = response({str(APPID): {'success': True,
            'data': {'steam_appid': APPID+1, 'type': 'game', 'name': KOREAN}}})
        self.session.get.side_effect = responses
        self.assertIsNone(self.resolve())

    def test_retry_after_and_auth_errors_do_not_loop_or_expose_key(self):
        for status, retry in ((429, 120), (403, 600)):
            with self.subTest(status=status):
                self.resolver.retry_at = 0
                self.session.get.reset_mock()
                self.session.get.side_effect = [response({}, status, {'Retry-After': '120'})]
                with patch('steam_lookup.time.time', return_value=1000):
                    self.assertIsNone(self.resolve())
                    self.assertIsNone(self.resolve())
                self.assertEqual(self.session.get.call_count, 1)
                self.assertEqual(self.resolver.retry_at, 1000+retry)
                self.assertNotIn(KEY, self.resolver.last_error)

    def test_timeout_url_key_is_never_retained(self):
        self.session.get.side_effect = requests.Timeout(APP_LIST + '?key=' + KEY)
        self.assertIsNone(self.resolve())
        self.assertNotIn(KEY, self.resolver.last_error)
        self.assertNotIn(KEY, redact(APP_LIST + '?key=' + KEY + '&other=1'))

    def test_expired_verified_cache_can_fall_back_offline_but_not_forever(self):
        self.session.get.side_effect = results()
        self.resolve()
        record = next(iter(self.resolver.records.values()))
        record['verified_at'] = time.time() - TTL - 1
        self.session.get.side_effect = requests.Timeout('offline')
        self.assertTrue(self.resolve()['offline'])
        record['verified_at'] = time.time() - 31*86400
        self.assertIsNone(self.resolve())

    def test_cancelled_lookup_does_not_write_or_register(self):
        cancelled = [False]
        self.resolver.cancelled = lambda: cancelled[0]
        first = results()[0]
        def cancel_after_json():
            cancelled[0] = True
            return {'items': [{'id': APPID, 'name': 'Hollow Knight', 'type': 'app'}]}
        first.json.side_effect = cancel_after_json
        self.session.get.side_effect = [first]
        self.assertIsNone(self.resolve())
        self.assertFalse(self.path.exists())
        self.assertEqual(self.session.get.call_count, 1)

    def test_malformed_official_response_is_an_error_not_success(self):
        self.session.get.side_effect = [response({'response': {}})]
        with self.assertRaises(SteamLookupError):
            self.resolver.test_connection()

    def test_worker_feeds_korean_identity_to_chzzk_once_and_preserves_saved_mapping(self):
        with patch('worker.discord_cache_file', return_value=Path(self.temp.name)/'discord.json'), \
                patch('worker.get_steam_api_key', return_value=''):
            worker = Worker({'channel': 'a'*32})
        worker.steam.close()
        worker.steam = self.resolver
        self.session.get.side_effect = results()
        worker.mapper.entries = {'hollow_knight.exe': [copy.deepcopy(GAME)]}
        category = {'categoryId': 'opaque-ko-id', 'categoryValue': KOREAN, 'categoryType': 'GAME'}
        search = Mock(return_value=[category])
        rules, pending = worker.mapper.discover(['hollow_knight.exe'], [], search)
        self.assertEqual(pending, [])
        search.assert_called_once_with(KOREAN)
        self.assertEqual(rules[0].category_id, 'opaque-ko-id')
        self.assertIn(str(APPID), rules[0].match_source)
        clean, _, _ = cleanup_auto_mappings([asdict(rules[0])], [])
        self.assertEqual(clean, rules)
        self.assertEqual(worker.mapper.entries['hollow_knight.exe'][0]['aliases'], [])

    def test_existing_manual_mapping_and_shared_executables_skip_steam(self):
        mapper = DiscordAutoMapper(self.path)
        mapper.entries = {'shared.exe': [copy.deepcopy(GAME)]}
        mapper.enrich_game = Mock(side_effect=AssertionError('Unnecessary Steam request'))
        saved = Rule('shared.exe', 'manual', '수동 연결')
        self.assertEqual(mapper.discover(['shared.exe'], [saved], Mock()), ([], []))
        mapper.entries['shared.exe'].append({'name': 'Another Game'})
        rules, pending = mapper.discover(['shared.exe'], [], Mock())
        self.assertFalse(rules)
        self.assertEqual(pending[0]['reason'], 'multi-game')

    def test_invalid_new_key_preserves_the_existing_saved_key(self):
        with patch('worker.discord_cache_file', return_value=Path(self.temp.name)/'discord.json'), \
                patch('worker.get_steam_api_key', return_value=''), \
                patch.dict(os.environ, {'STEAM_WEB_API_KEY': ''}):
            worker = Worker({'channel': 'a'*32})
            with patch('worker.SteamResolver.test_connection', side_effect=SteamLookupError('인증 실패')), \
                    patch('worker.save_steam_api_key') as save:
                worker.command('steam_test', {'key': KEY})
                save.assert_not_called()

    def test_game_exit_while_steam_resolves_never_saves_or_applies(self):
        with patch('worker.discord_cache_file', return_value=Path(self.temp.name)/'discord.json'), \
                patch('worker.get_steam_api_key', return_value=''):
            worker = Worker({'channel': 'a'*32, 'auto_detect': True})
        worker.steam.close()
        worker.steam = self.resolver
        worker.mapper.entries = {'hollow_knight.exe': [copy.deepcopy(GAME)]}
        worker.api = Mock()
        worker.api.search.return_value = [{'categoryId': 'opaque', 'categoryValue': KOREAN, 'categoryType': 'GAME'}]
        worker.startup_talk_attempted = True
        snapshots = [['hollow_knight.exe']]
        responses = results()
        last = responses[-1]
        def game_exits():
            snapshots[0] = []
            return {str(APPID): {'success': True, 'data': {'steam_appid': APPID, 'type': 'game', 'name': KOREAN}}}
        last.json.side_effect = game_exits
        self.session.get.side_effect = responses
        with patch.object(worker.mapper, 'ensure_index', return_value={}), \
                patch('worker.snapshot_process_names', side_effect=lambda: snapshots[0]):
            worker.scan()
        self.assertEqual(worker.config.get('auto_rules', []), [])
        worker.api.apply.assert_not_called()


class SteamKeyStorageTests(unittest.TestCase):
    def test_bundled_key_requires_no_user_setup_and_env_names_override(self):
        with patch('storage.APP_STEAM_WEB_API_KEY', KEY), patch('storage.sys.platform', 'linux'), \
                patch.dict(os.environ, {'STEAM_WEB_API': '', 'STEAM_WEB_API_KEY': ''}):
            self.assertEqual(get_steam_api_key(), KEY)
            with patch.dict(os.environ, {'STEAM_WEB_API_KEY': 'b'*32}):
                self.assertEqual(get_steam_api_key(), 'b'*32)
                with patch.dict(os.environ, {'STEAM_WEB_API': 'c'*32}):
                    self.assertEqual(get_steam_api_key(), 'c'*32)

    def test_personal_key_survives_upgrade_and_deleting_it_restores_bundled_key(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {
                'LOCALAPPDATA': d, 'STEAM_WEB_API': '', 'STEAM_WEB_API_KEY': ''}), \
                patch('storage.sys.platform', 'win32'), patch('storage.APP_STEAM_WEB_API_KEY', 'b'*32), \
                patch('storage._dpapi_protect', side_effect=lambda b: b[::-1]), \
                patch('storage._dpapi_unprotect', side_effect=lambda b: b[::-1]):
            self.assertEqual(get_steam_api_key(), 'b'*32)
            save_steam_api_key(KEY)
            self.assertEqual(get_steam_api_key(), KEY)
            save_steam_api_key('')
            self.assertEqual(get_steam_api_key(), 'b'*32)
            with patch('storage._dpapi_unprotect', side_effect=ValueError('invalid')):
                (Path(d)/'ChzzkAutoCategory/steam_key.dat').write_bytes(b'invalid')
                self.assertEqual(get_steam_api_key(), 'b'*32)

    def test_key_is_not_stored_in_config_and_windows_storage_round_trip(self):
        config = normalize_config({'steam_api_key': KEY, 'rules': [{'saved': 'preserved'}]})
        self.assertNotIn('steam_api_key', config)
        self.assertEqual(config['rules'], [{'saved': 'preserved'}])
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'LOCALAPPDATA': d, 'STEAM_WEB_API_KEY': ''}), \
                patch('storage.sys.platform', 'win32'), \
                patch('storage._dpapi_protect', side_effect=lambda b: b[::-1] + b'cipher'), \
                patch('storage._dpapi_unprotect', side_effect=lambda b: b[:-6][::-1]):
            save_steam_api_key(KEY)
            self.assertEqual(get_steam_api_key(), KEY)
            self.assertNotIn(KEY.encode(), (Path(d)/'ChzzkAutoCategory/steam_key.dat').read_bytes())
            save_steam_api_key('')
            self.assertEqual(get_steam_api_key(), '')

    @unittest.skipUnless(sys.platform == 'win32', 'Actual DPAPI needs Windows')
    def test_actual_windows_dpapi(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'LOCALAPPDATA': d, 'STEAM_WEB_API_KEY': ''}):
            save_steam_api_key(KEY)
            self.assertEqual(get_steam_api_key(), KEY)
            self.assertNotIn(KEY.encode(), (Path(d)/'ChzzkAutoCategory/steam_key.dat').read_bytes())


if __name__ == '__main__':
    unittest.main()
