"""Discord SKU -> keyless Steam -> verified CHZZK, with deterministic HTTP mocks."""
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import requests
from autodetect import DiscordAutoMapper, parse_detectable_index
from steam_lookup import SteamResolver, STORE_DETAILS, TTL, valid_app_ids
from worker import Worker

APPID = 367520
GAME = {'id': 'discord-hollow', 'name': 'Hollow Knight', 'aliases': [],
        'steam_app_ids': [APPID]}
ROW = {'id': GAME['id'], 'name': GAME['name'], 'aliases': [],
       'executables': [{'os': 'win32', 'name': 'hollow_knight.exe'}],
       'third_party_skus': [{'distributor': 'steam', 'id': str(APPID)}]}


def details(appid=APPID, name='할로우 나이트', kind='game', success=True):
    return Mock(status_code=200, headers={}, json=Mock(return_value={str(APPID): {
        'success': success, 'data': {'steam_appid': appid, 'type': kind, 'name': name}}}))


class DiscordSteamIDTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.session = Mock()
        self.resolver = SteamResolver('', self.directory / 'steam.json', session=self.session)
        self.addCleanup(self.resolver.close)

    def test_discord_skus_filter_distributors_and_preserve_unique_ids(self):
        row = copy.deepcopy(ROW)
        row['third_party_skus'] += [{'distributor': 'steam', 'id': APPID},
            {'distributor': 'gog', 'id': '42'}, {'distributor': 'steam', 'id': True},
            {'distributor': 'steam', 'id': '0'}, {'distributor': 'steam', 'id': '4294967296'},
            {'distributor': 'steam', 'id': 'https://example.invalid/367520'}, None]
        parsed = parse_detectable_index([row])
        self.assertEqual(parsed['hollow_knight.exe'][0], GAME)
        self.assertEqual(row['third_party_skus'][0]['id'], str(APPID))
        for malformed in ('123', {}, None, True):
            self.assertEqual(valid_app_ids(malformed), [])

    def test_keyless_direct_route_is_one_https_request_even_with_unused_key(self):
        for key in ('', 'a'*32):
            with self.subTest(key_present=bool(key)):
                self.resolver.key = key
                self.resolver.records.clear()
                self.session.get.reset_mock()
                self.session.get.return_value = details()
                record = self.resolver.resolve(GAME, 'hollow_knight.exe')
                self.assertEqual(record['localized_name'], '할로우 나이트')
                self.session.get.assert_called_once()
                call = self.session.get.call_args
                self.assertEqual(call.args[0], STORE_DETAILS)
                self.assertEqual(call.kwargs['params'], {'appids': APPID, 'l': 'koreana', 'cc': 'KR'})
                self.assertNotIn('key', call.kwargs['params'])

    def test_direct_cache_survives_restart_without_key(self):
        self.session.get.return_value = details()
        self.resolver.resolve(GAME, 'hollow_knight.exe')
        self.session.get.reset_mock()
        restarted = SteamResolver('', self.resolver.path, session=self.session)
        self.assertEqual(restarted.resolve(GAME, 'HOLLOW_KNIGHT.EXE')['appid'], APPID)
        self.session.get.assert_not_called()

    def test_changed_appid_cannot_reuse_old_cache(self):
        self.session.get.return_value = details()
        self.resolver.resolve(GAME, 'hollow_knight.exe')
        self.session.get.reset_mock()
        self.session.get.return_value = details(appid=APPID+1)
        self.assertIsNone(self.resolver.resolve(dict(GAME, steam_app_ids=[APPID+1]), 'hollow_knight.exe'))
        self.session.get.assert_called_once()

    def test_multiple_steam_editions_never_choose_first_or_use_name_fallback(self):
        self.resolver.key = 'a'*32
        self.assertIsNone(self.resolver.resolve(dict(GAME, steam_app_ids=[APPID, APPID+1]), 'hollow_knight.exe'))
        self.session.get.assert_not_called()

    def test_direct_mismatched_id_dlc_missing_or_invalid_name_never_register(self):
        for options in ({'appid': APPID+1}, {'kind': 'dlc'}, {'success': False},
                        {'name': ''}, {'name': ' '*10}, {'name': 'x'*301}, {'name': ['wrong']}):
            with self.subTest(options=options):
                self.resolver.records.clear()
                self.session.get.return_value = details(**options)
                self.assertIsNone(self.resolver.resolve(GAME, 'hollow_knight.exe'))

    def test_english_store_name_is_preserved_without_invented_translation(self):
        self.session.get.return_value = details(name='Hollow Knight')
        self.assertEqual(self.resolver.resolve(GAME, 'hollow_knight.exe')['localized_name'], 'Hollow Knight')

    def test_rate_limit_backoff_and_negative_cache_prevent_repeated_requests(self):
        self.session.get.return_value = Mock(status_code=429, headers={'Retry-After': '120'})
        with patch('steam_lookup.time.time', return_value=1000):
            self.assertIsNone(self.resolver.resolve(GAME, 'hollow_knight.exe'))
            self.assertIsNone(self.resolver.resolve(GAME, 'hollow_knight.exe'))
        self.assertEqual(self.resolver.retry_at, 1120)
        self.session.get.assert_called_once()
        self.resolver.retry_at = 0
        self.session.get.reset_mock()
        self.session.get.return_value = details(success=False)
        for _ in range(2):
            self.assertIsNone(self.resolver.resolve(GAME, 'hollow_knight.exe'))
        self.session.get.assert_called_once()

    def test_direct_offline_cache_retains_verified_title(self):
        self.session.get.return_value = details()
        self.resolver.resolve(GAME, 'hollow_knight.exe')
        next(iter(self.resolver.records.values()))['verified_at'] = time.time()-TTL-1
        self.session.get.side_effect = requests.Timeout('offline')
        self.assertTrue(self.resolver.resolve(GAME, 'hollow_knight.exe')['offline'])

    def test_cancel_during_direct_response_never_saves_result(self):
        cancelled = [False]
        self.resolver.cancelled = lambda: cancelled[0]
        result = details()
        def cancel():
            cancelled[0] = True
            return details().json()
        result.json.side_effect = cancel
        self.session.get.return_value = result
        self.assertIsNone(self.resolver.resolve(GAME, 'hollow_knight.exe'))
        self.assertFalse(self.resolver.path.exists())

    def test_discord_cache_round_trip_retains_ids_without_redownload(self):
        path = self.directory/'discord.json'
        mapper = DiscordAutoMapper(path)
        with patch('autodetect.requests.get', return_value=Mock(json=Mock(return_value=[ROW]))):
            mapper.refresh()
        restarted = DiscordAutoMapper(path)
        with patch.object(restarted, 'refresh') as refresh:
            restarted.ensure_index()
            restarted.ensure_index()
            refresh.assert_not_called()
        self.assertEqual(restarted.entries['hollow_knight.exe'][0]['steam_app_ids'], [APPID])

    def test_legacy_cache_refreshes_once_but_offline_data_is_preserved(self):
        path = self.directory/'discord.json'
        path.write_text(json.dumps({'updated_at': time.time(), 'entries': {
            'hollow_knight.exe': [{k: v for k, v in GAME.items() if k != 'steam_app_ids'}]}}))
        mapper = DiscordAutoMapper(path)
        original = path.read_text()
        with patch('autodetect.requests.get', side_effect=requests.Timeout('offline')) as get:
            self.assertTrue(mapper.ensure_index()['used_cache'])
            self.assertTrue(mapper.ensure_index()['used_cache'])
            get.assert_called_once()
        self.assertEqual(path.read_text(), original)
        self.assertEqual(mapper.entries['hollow_knight.exe'][0]['id'], GAME['id'])
        mapper._retry_at = 0
        with patch('autodetect.requests.get', return_value=Mock(json=Mock(return_value=[ROW]))) as get:
            self.assertTrue(mapper.ensure_index()['refreshed'])
            mapper.ensure_index()
            get.assert_called_once()
        self.assertEqual(json.loads(path.read_text())['version'], 2)
        self.assertEqual(mapper.entries['hollow_knight.exe'][0]['steam_app_ids'], [APPID])

    def test_keyless_worker_matches_korean_category_before_registering_rule(self):
        with patch('worker.discord_cache_file', return_value=self.directory/'discord.json'), \
                patch('worker.get_steam_api_key', return_value=''):
            worker = Worker({'channel': 'a'*32})
        self.addCleanup(worker.steam.close)
        worker.steam.close()
        worker.steam = self.resolver
        worker.mapper.entries = {'hollow_knight.exe': [copy.deepcopy(GAME)]}
        self.session.get.return_value = details()
        search = Mock(return_value=[{'categoryId': 'actual-ko-category',
                                    'categoryValue': '할로우 나이트', 'categoryType': 'GAME'}])
        rules, pending = worker.mapper.discover(['hollow_knight.exe'], [], search)
        self.assertEqual(pending, [])
        search.assert_called_once_with('할로우 나이트')
        self.assertEqual(rules[0].category_id, 'actual-ko-category')
        self.assertEqual(worker.mapper.entries['hollow_knight.exe'][0], GAME)
        worker.config['steam_lookup_enabled'] = False
        self.session.get.reset_mock()
        self.assertEqual(worker.enrich_steam_game(GAME, 'hollow_knight.exe'), GAME)
        self.session.get.assert_not_called()

    def test_connection_test_uses_store_without_key_or_official_api(self):
        self.session.get.return_value = Mock(status_code=200, json=Mock(return_value={
            '2827200': {'success': True, 'data': {'steam_appid': 2827200,
                          'type': 'game', 'name': '미메시스'}}}))
        self.assertTrue(self.resolver.test_store_connection())
        self.assertEqual(self.session.get.call_args.args[0], STORE_DETAILS)
        self.assertNotIn('key', self.session.get.call_args.kwargs['params'])

    def test_worker_connection_ignores_optional_web_key_authentication(self):
        with patch('worker.discord_cache_file', return_value=self.directory/'discord.json'), \
                patch('worker.get_steam_api_key', return_value='a'*32):
            worker = Worker({'channel': 'a'*32})
            self.addCleanup(worker.steam.close)
            with patch.object(worker.steam, 'test_store_connection', return_value=True) as public, \
                    patch.object(worker.steam, 'test_connection') as keyed, \
                    patch.object(worker, 'emit') as emit:
                worker.command('steam_test', None)
            public.assert_called_once()
            keyed.assert_not_called()
            self.assertTrue(any(c.kwargs.get('ok') for c in emit.call_args_list))

    def test_two_games_use_independent_direct_results_and_cache_entries(self):
        other = dict(GAME, id='other-game', name='Celeste', steam_app_ids=[504230])
        self.session.get.side_effect = [details(), Mock(status_code=200, json=Mock(return_value={
            '504230': {'success': True, 'data': {'steam_appid': 504230,
                        'type': 'game', 'name': '셀레스트'}}}))]
        self.assertEqual(self.resolver.resolve(GAME, 'hollow_knight.exe')['localized_name'], '할로우 나이트')
        self.assertEqual(self.resolver.resolve(other, 'celeste.exe')['localized_name'], '셀레스트')
        self.session.get.reset_mock()
        self.assertEqual(self.resolver.resolve(GAME, 'hollow_knight.exe')['appid'], APPID)
        self.assertEqual(self.resolver.resolve(other, 'celeste.exe')['appid'], 504230)
        self.session.get.assert_not_called()


if __name__ == '__main__':
    unittest.main()
