import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from autodetect import DiscordAutoMapper, detectable_running_processes, parse_detectable_index, cleanup_auto_mappings
from core import Rule
from worker import Worker


CATEGORY = {'categoryId': 'celeste', 'categoryValue': 'Celeste', 'categoryType': 'GAME'}


class LookupOnlyIndex(dict):
    def items(self):
        raise AssertionError('The full Discord index must not be scanned')

    def __iter__(self):
        raise AssertionError('The full Discord index must not be scanned')


class DetectionLookupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.mapper = DiscordAutoMapper(Path(self.temp.name) / 'games.json')
        self.mapper.entries = {'celeste.exe': [{'name': 'Celeste', 'aliases': []}]}

    def test_only_active_names_are_looked_up_in_large_index(self):
        entries = LookupOnlyIndex({f'title{i}.exe': [{'name': str(i)}] for i in range(10000)})
        entries.update(self.mapper.entries)
        self.assertEqual(detectable_running_processes(
            ['unknown.exe', 'CELESTE.EXE', 'celeste.exe', 'setup.exe'], entries), ['CELESTE.EXE'])

    def test_download_is_reduced_to_windows_executable_game_and_aliases(self):
        payload = [{'id': 'discord-id', 'name': 'Celeste', 'aliases': ['셀레스트'],
                    'icon': 'discard-icon', 'description': 'discard-description',
                    'executables': [
                        {'os': 'win32', 'name': r'bin\Celeste.exe'},
                        {'os': 'linux', 'name': 'linux.exe'},
                        {'os': 'win32', 'name': 'javaw.exe'},
                        {'os': 'win32', 'name': '>special.exe'},
                        {'os': 'win32', 'name': '*wild.exe'},
                        {'os': 'win32', 'name': 'arg.exe', 'arguments': '--game=celeste'},
                        {'os': 'win32', 'name': 'bootstrap.exe', 'is_launcher': True}]}]
        self.assertEqual(parse_detectable_index(payload), {
            'celeste.exe': [{'name': 'Celeste', 'aliases': ['셀레스트'], 'id': 'discord-id'}]})

    def test_registration_then_saved_rule_skips_category_search(self):
        search = Mock(return_value=[CATEGORY])
        rules, pending = self.mapper.discover(['Celeste.exe', 'other.exe'], [], search)
        self.assertEqual([r.category_id for r in rules], ['celeste'])
        self.assertEqual(pending, [])
        search.reset_mock()
        self.assertEqual(self.mapper.discover(['Celeste.exe', 'other.exe'], rules, search), ([], []))
        search.assert_not_called()

    def test_saved_alias_also_skips_search(self):
        search = Mock()
        rule = Rule('main.exe', 'celeste', 'Celeste', process_aliases=('Celeste.exe',))
        self.assertEqual(self.mapper.discover(['Celeste.exe'], [rule], search), ([], []))
        search.assert_not_called()

    def test_localized_overrides_keep_verified_ids_and_survive_rule_cleanup(self):
        for process, name, korean in [('MIMESIS.exe', 'MIMESIS', '미메시스'),
                                      ('Smilemo.exe', 'SMILEMO', '스마일모'),
                                      ('Buckshot Roulette.exe', 'Buckshot Roulette', '벅샷 룰렛')]:
            with self.subTest(process=process):
                self.mapper.clear_search_cache()
                self.mapper.entries = {process.casefold(): [{'name': name, 'aliases': []}]}
                category = {'categoryId': 'actual-api-id', 'categoryValue': korean, 'categoryType': 'GAME'}
                search = Mock(return_value=[dict(category, categoryId='other', categoryValue=korean+' 관련 게임'), category])
                rules, pending = self.mapper.discover([process], [], search)
                search.assert_called_once_with(korean)
                self.assertEqual(pending, [])
                self.assertEqual([(r.category_id, r.category_name) for r in rules], [('actual-api-id', korean)])
                self.assertEqual(cleanup_auto_mappings(rules, [])[0], rules)
                search.reset_mock()
                self.assertEqual(self.mapper.discover([process], rules, search), ([], []))
                search.assert_not_called()
                self.mapper.clear_search_cache()
                rules, pending = self.mapper.discover([process.upper()], [], Mock(return_value=[]))
                self.assertEqual(rules, [])
                self.assertEqual(pending[0]['reason'], 'category-not-found')

    def test_shared_filename_never_guesses_from_category_search(self):
        self.mapper.entries['celeste.exe'].append({'name': 'Another Game', 'aliases': []})
        self.mapper.resolve_shared_executable = True  # legacy configuration
        search = Mock(return_value=[CATEGORY])
        rules, pending = self.mapper.discover(['Celeste.exe'], [], search)
        self.assertEqual(rules, [])
        self.assertEqual(pending[0]['reason'], 'multi-game')
        search.assert_not_called()

    def test_unresolved_game_does_not_repeat_identical_requests_each_scan(self):
        search = Mock(return_value=[])
        with patch('autodetect.time.monotonic', return_value=100):
            self.mapper.discover(['Celeste.exe'], [], search)
            self.mapper.discover(['Celeste.exe'], [], search)
        search.assert_called_once_with('Celeste')

    def test_empty_and_failed_queries_retry_after_one_minute(self):
        for result in ([], RuntimeError('offline')):
            with self.subTest(result=result):
                self.mapper.clear_search_cache()
                search = Mock(side_effect=result) if isinstance(result, Exception) else Mock(return_value=result)
                def query():
                    try:
                        self.mapper._cached_search('Celeste', search)
                    except RuntimeError:
                        pass
                with patch('autodetect.time.monotonic', return_value=100):
                    query()
                with patch('autodetect.time.monotonic', return_value=159):
                    query()
                self.assertEqual(search.call_count, 1)
                with patch('autodetect.time.monotonic', return_value=160):
                    query()
                self.assertEqual(search.call_count, 2)

    def test_successful_search_cache_expires_and_does_not_leak_mutations(self):
        search = Mock(return_value=[dict(CATEGORY)])
        with patch('autodetect.time.monotonic', return_value=100):
            result = self.mapper._cached_search('Celeste', search)
            result[0]['categoryValue'] = 'mutated'
        with patch('autodetect.time.monotonic', return_value=399):
            result = self.mapper._cached_search('CELESTE', search)
            self.assertEqual(result[0]['categoryValue'], 'Celeste')
        search.assert_called_once()
        with patch('autodetect.time.monotonic', return_value=400):
            self.mapper._cached_search('Celeste', search)
        self.assertEqual(search.call_count, 2)

    def test_search_cache_has_a_fixed_upper_bound(self):
        for i in range(140):
            self.mapper._cached_search(str(i), lambda _: [])
        self.assertEqual(len(self.mapper._search_cache), 128)
        self.assertNotIn('0', self.mapper._search_cache)

    def test_fresh_index_is_not_copied_each_scan(self):
        self.mapper._loaded = True
        self.mapper.updated_at = time.time()
        self.mapper.ensure_index()
        entries = self.mapper.entries
        with patch.object(self.mapper, 'refresh') as refresh:
            self.mapper.ensure_index()
            self.mapper.ensure_index()
        self.assertIs(self.mapper.entries, entries)
        refresh.assert_not_called()

    def test_manual_sync_clears_search_cache_before_discovery(self):
        with patch('worker.discord_cache_file', return_value=Path(self.temp.name) / 'worker.json'):
            worker = Worker({'channel': 'a'*32, 'chzzk_open_enabled': False})
        worker.mapper._cached_search('Celeste', lambda _: [])
        with patch.object(worker, 'refresh_processes'), patch.object(worker, 'maybe_sync_auto') as sync:
            sync.side_effect = lambda _: self.assertFalse(worker.mapper._search_cache)
            worker.command('sync_auto', None)
            sync.assert_called_once()


if __name__ == '__main__':
    unittest.main()
