import os
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from autodetect import DiscordAutoMapper, LEAGUE_EXECUTABLES, cleanup_auto_mappings, with_game_client_compatibility
from core import Rule, Gate
from worker import Worker


LOL = {'categoryId': 'League_of_Legends', 'categoryValue': '리그 오브 레전드', 'categoryType': 'GAME'}
RELATED = [
    {'categoryId': 'League_of_Legends_Wild_Rift', 'categoryValue': '리그 오브 레전드: 와일드 리프트', 'categoryType': 'GAME'},
    {'categoryId': 'Bandle_Tale_A_League_of_Legends_Story', 'categoryValue': '밴들 이야기: 리그 오브 레전드 이야기', 'categoryType': 'GAME'},
    {'categoryId': 'CONV_RGENCE_A_League_of_Legends_Story', 'categoryValue': '시간/교차: 리그 오브 레전드 이야기', 'categoryType': 'GAME'},
]


class SingleCategoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.mapper = DiscordAutoMapper(Path(self.temp.name) / 'cache.json')
        self.mapper.entries = with_game_client_compatibility({})

    def test_screenshot_candidates_choose_only_original_and_group_processes(self):
        search = Mock(return_value=[*RELATED, LOL])
        rules, pending = self.mapper.discover(list(LEAGUE_EXECUTABLES), [], search)
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].category_id, LOL['categoryId'])
        self.assertEqual({p.casefold() for p in rules[0].processes}, set(LEAGUE_EXECUTABLES))
        self.assertEqual(pending, [])
        search.assert_called_once_with('리그 오브 레전드')

    def test_lol_does_not_register_a_spinoff_when_original_is_missing(self):
        for results in (RELATED, RELATED[:1]):
            self.mapper.clear_search_cache()
            rules, pending = self.mapper.discover(['league of legends.exe'], [], lambda _: results)
            self.assertEqual(rules, [])
            self.assertEqual(pending[0]['reason'], 'category-not-found')

    def test_existing_client_rule_migrates_to_match_without_new_search(self):
        old = Rule('LeagueClient.exe', LOL['categoryId'], LOL['categoryValue'], game_name='League of Legends')
        rules, pending, _ = cleanup_auto_mappings([asdict(old)], [])
        search = Mock()
        self.assertEqual(self.mapper.discover(['LeagueClientUx.exe', 'League of Legends.exe'], rules, search), ([], []))
        search.assert_not_called()
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].processes, ('League of Legends.exe', 'LeagueClient.exe'))

    def test_migration_does_not_add_client_aliases(self):
        old = Rule('LeagueClient.exe', LOL['categoryId'], LOL['categoryValue'], game_name='League of Legends')
        manual = Rule('LeagueClientUx.exe', 'Teamfight_Tactics', '전략적 팀 전투')
        rules, _, _ = cleanup_auto_mappings([asdict(old)], [], [asdict(manual)])
        self.assertNotIn('leagueclientux.exe', {p.casefold() for p in rules[0].processes})

    def test_exact_identity_works_for_other_titles(self):
        self.mapper.entries = {'celeste.exe': [{'name': 'Celeste', 'aliases': ['셀레스트']}]}
        rows = [
            {'categoryId': 'Celeste_Classic', 'categoryValue': '셀레스트 클래식', 'categoryType': 'GAME'},
            {'categoryId': 'Celeste', 'categoryValue': '셀레스트', 'categoryType': 'GAME'}]
        rules, pending = self.mapper.discover(['celeste.exe'], [], lambda _: rows)
        self.assertEqual([r.category_id for r in rules], ['Celeste'])
        self.assertEqual(pending, [])

    def test_two_categories_with_same_exact_title_are_still_ambiguous(self):
        other = dict(LOL, categoryId='another-id')
        rules, pending = self.mapper.discover(['league of legends.exe'], [], lambda _: [LOL, other])
        self.assertEqual(rules, [])
        self.assertEqual(pending[0]['reason'], 'category-choice')

    def test_worker_registers_one_rule_and_applies_without_choice_popup(self):
        with patch('worker.discord_cache_file', return_value=Path(self.temp.name)/'worker.json'):
            worker = Worker({'channel': 'a'*32, 'chzzk_open_enabled': False})
        worker.mapper.entries = self.mapper.entries
        worker.api = Mock()
        worker.api.search.return_value = [*RELATED, LOL]
        worker.api.apply.return_value = True
        worker.startup_talk_attempted = True
        worker.gate = Gate(stable=0)
        events = []
        worker.event.connect(events.append)
        with patch.object(worker.mapper, 'ensure_index', return_value={}), patch('worker.snapshot_process_names', return_value=list(LEAGUE_EXECUTABLES)):
            worker.scan()
            worker.scan()
        self.assertEqual(len(worker.config['auto_rules']), 1)
        self.assertFalse(any(e['kind'] == 'category_choice_required' for e in events))
        worker.api.apply.assert_called_once()
        self.assertEqual(worker.api.apply.call_args.args[0].category_id, LOL['categoryId'])


if __name__ == '__main__':
    unittest.main()
