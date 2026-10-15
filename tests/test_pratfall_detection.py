import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from autodetect import (DiscordAutoMapper, detectable_running_processes, cleanup_auto_mappings,
                        parse_detectable_index, with_verified_executable_compatibility)
from core import Rule
from worker import Worker

# Relevant fields captured from Discord's public response on 2026-10-15.
DISCORD_ROW = {'id': '1468444820484784333', 'name': 'Pratfall', 'aliases': [],
               'executables': [], 'third_party_skus': [{'distributor': 'steam', 'id': '4244510'}]}
CATEGORY = {'categoryId': 'test-api-pratfall-id', 'categoryValue': '프랫폴', 'categoryType': 'GAME'}


class PratfallDetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'discord.json'
        self.mapper = DiscordAutoMapper(self.path)

    def fresh_old_cache(self):
        self.path.write_text(json.dumps({'updated_at': time.time(), 'entries': {
            'celeste.exe': [{'name': 'Celeste', 'aliases': [], 'id': 'other'}]}}))

    def test_discord_game_without_executables_is_reproduced_and_refresh_repaired(self):
        self.assertEqual(parse_detectable_index([DISCORD_ROW]), {})
        other = {'name': 'Celeste', 'executables': [{'os': 'win32', 'name': 'Celeste.exe'}]}
        response = Mock(json=Mock(return_value=[DISCORD_ROW, other]))
        with patch('autodetect.requests.get', return_value=response):
            self.mapper.refresh()
        self.assertEqual(detectable_running_processes(['PRATFALL.EXE'], self.mapper.entries), ['PRATFALL.EXE'])
        self.assertEqual(self.mapper.entries['pratfall.exe'][0]['id'], DISCORD_ROW['id'])

    def test_existing_fresh_cache_is_fixed_without_redownload_or_timestamp_reset(self):
        self.fresh_old_cache()
        original_time = json.loads(self.path.read_text())['updated_at']
        with patch.object(self.mapper, 'refresh') as refresh:
            self.mapper.ensure_index()
            entries = self.mapper.entries
            self.mapper.ensure_index()
            refresh.assert_not_called()
        self.assertIs(self.mapper.entries, entries)
        self.assertEqual(self.mapper.updated_at, original_time)
        self.assertIn('celeste.exe', entries)
        self.assertEqual(detectable_running_processes(['Pratfall.exe'], entries), ['Pratfall.exe'])

    def test_offline_first_start_still_uses_verified_binary(self):
        with patch.object(self.mapper, 'refresh', side_effect=RuntimeError('offline')):
            self.assertIn('offline', self.mapper.ensure_index()['error'])
        self.assertEqual(detectable_running_processes(['Pratfall.exe'], self.mapper.entries), ['Pratfall.exe'])

    def test_helpers_and_guessed_names_never_detect_as_pratfall(self):
        entries = with_verified_executable_compatibility({})
        self.assertEqual(detectable_running_processes([
            'GameLauncher.exe', 'crashpad_handler.exe', 'SteamWorkshopUploader.exe',
            'Pratfall.console.exe', 'SomeOtherGame.exe'], entries), [])
        self.assertEqual(detectable_running_processes(['Pratfall.exe', 'pratfall.EXE'], entries), ['Pratfall.exe'])

    def test_upstream_mapping_is_deduplicated_but_conflicting_game_stays_ambiguous(self):
        source = {'pratfall.exe': [{'id': DISCORD_ROW['id'], 'name': 'Pratfall', 'aliases': ['Pratfall KR']}]}
        entries = with_verified_executable_compatibility(source)
        self.assertEqual(len(entries['pratfall.exe']), 1)
        self.assertIn('프랫폴', entries['pratfall.exe'][0]['aliases'])
        self.assertEqual(source['pratfall.exe'][0]['aliases'], ['Pratfall KR'])
        self.assertEqual(with_verified_executable_compatibility(entries), entries)
        self.mapper.entries = with_verified_executable_compatibility({
            'pratfall.exe': [{'id': 'different-game', 'name': 'Different Game', 'aliases': []}]})
        search = Mock(return_value=[CATEGORY])
        rules, pending = self.mapper.discover(['Pratfall.exe'], [], search)
        self.assertEqual(rules, [])
        self.assertEqual(pending[0]['reason'], 'multi-game')
        search.assert_not_called()

    def test_korean_category_validation_and_manual_rule_priority(self):
        self.fresh_old_cache()
        self.mapper.ensure_index()
        rules, pending = self.mapper.discover(['Pratfall.exe'], [], Mock(return_value=[CATEGORY]))
        self.assertEqual(pending, [])
        self.assertEqual([(r.process, r.category_id, r.category_name) for r in rules],
                         [('Pratfall.exe', CATEGORY['categoryId'], '프랫폴')])
        self.assertEqual(cleanup_auto_mappings(rules, [])[0], rules)
        invalid = Rule('Pratfall.exe', 'unrelated', '다른 게임', game_name='Pratfall')
        self.assertEqual(cleanup_auto_mappings([invalid], [])[0], [])
        manual = Rule('Pratfall.exe', 'manual', '사용자 지정')
        search = Mock()
        self.assertEqual(self.mapper.discover(['Pratfall.exe'], [manual], search), ([], []))
        search.assert_not_called()

    def test_missing_category_is_not_registered(self):
        self.mapper.entries = with_verified_executable_compatibility({})
        rules, pending = self.mapper.discover(['Pratfall.exe'], [], Mock(return_value=[]))
        self.assertEqual(rules, [])
        self.assertEqual(pending[0]['reason'], 'category-not-found')

    def test_worker_saves_verified_korean_rule_and_does_not_repeat_search(self):
        with patch('worker.discord_cache_file', return_value=self.path):
            worker = Worker({'channel': 'a'*32, 'chzzk_open_enabled': False,
                             'steam_lookup_enabled': False})
        worker.mapper.entries = with_verified_executable_compatibility({})
        worker.api = Mock()
        worker.api.search.return_value = [CATEGORY]
        worker.startup_talk_attempted = True
        with patch.object(worker.mapper, 'ensure_index', return_value={}), \
                patch('worker.snapshot_process_names', return_value=['Pratfall.exe']):
            worker.scan()
            self.assertEqual(len(worker.config['auto_rules']), 1)
            self.assertEqual(worker.config['auto_rules'][0]['category_name'], '프랫폴')
            worker.api.search.reset_mock()
            worker.last_auto_sync = 0
            worker.scan()
            worker.api.search.assert_not_called()
            self.assertEqual(len(worker.config['auto_rules']), 1)


if __name__ == '__main__':
    unittest.main()
