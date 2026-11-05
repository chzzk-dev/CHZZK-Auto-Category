import json
import os
import tempfile
import time
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from autodetect import (DiscordAutoMapper, detectable_running_processes,
                        game_process_details, migrate_riot_rules,
                        with_game_client_compatibility)
from core import Gate, Rule
from automation import VerifiedCache, game_key
from storage import normalize_config
from worker import Worker, process_names

TFT = 'TFTClient-Win64-Shipping.exe'
TFT_PATH = r'C:\Riot Games\Teamfight Tactics\Live\TFT\Binaries\Win64\TFTClient-Win64-Shipping.exe'
LOL = 'League of Legends.exe'
LOBBY = 'LeagueClient.exe'
TFT_CATEGORY = {'categoryId': 'live-tft-id', 'categoryValue': '전략적 팀 전투 : 신비의 숲', 'categoryType': 'GAME'}
LOL_CATEGORY = {'categoryId': 'live-lol-id', 'categoryValue': '리그 오브 레전드', 'categoryType': 'GAME'}


class StandaloneTFTTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name) / 'discord.json'
        self.mapper = DiscordAutoMapper(self.cache)
        self.mapper.entries = with_game_client_compatibility({})

    def test_user_executable_is_known_offline_and_case_insensitive(self):
        self.assertEqual(detectable_running_processes([TFT_PATH, TFT.upper(), 'RiotClientServices.exe'], self.mapper.entries), [TFT])
        detail = game_process_details([TFT], self.mapper.entries)[TFT.casefold()]
        self.assertEqual(detail, {'name': 'Teamfight Tactics', 'keyword': '전략적 팀 전투'})

    def test_fresh_old_cache_gets_tft_without_download(self):
        self.cache.write_text(json.dumps({'version': 2, 'updated_at': time.time(), 'entries': {
            LOBBY.casefold(): [{'id': 'lol', 'name': 'League of Legends'}]}}))
        with patch.object(self.mapper, 'refresh') as refresh:
            self.mapper.ensure_index()
        refresh.assert_not_called()
        self.assertEqual(detectable_running_processes([TFT], self.mapper.entries), [TFT])

    def test_first_launch_offline_still_has_both_games(self):
        with patch.object(self.mapper, 'refresh', side_effect=RuntimeError('offline')):
            self.assertTrue(self.mapper.ensure_index()['error'])
        self.assertEqual(detectable_running_processes([TFT, LOL], self.mapper.entries), [LOL, TFT])

    def test_legacy_discord_shared_entries_are_separated(self):
        entries = with_game_client_compatibility({
            LOBBY.casefold(): [{'id': 'lol', 'name': 'League of Legends', 'aliases': ['TFT']},
                              {'id': 'tft', 'name': 'Teamfight Tactics'}],
            TFT.casefold(): [{'id': 'lol', 'name': 'League of Legends'},
                            {'id': 'tft', 'name': 'Teamfight Tactics', 'aliases': ['LoL']}],
        })
        self.assertEqual([g['name'] for g in entries[LOBBY.casefold()]], ['League of Legends'])
        self.assertEqual([g['name'] for g in entries[TFT.casefold()]], ['Teamfight Tactics'])
        self.assertEqual(entries[TFT.casefold()][0]['id'], 'tft')
        self.assertNotIn('TFT', entries[LOBBY.casefold()][0]['aliases'])
        self.assertNotIn('LoL', entries[TFT.casefold()][0]['aliases'])
        self.assertEqual(with_game_client_compatibility(entries), entries)

    def test_tft_category_with_season_uses_actual_returned_id(self):
        for title in ('전략적 팀 전투', '전략적 팀 전투 : 신비의 숲', 'Teamfight Tactics：Set 20'):
            with self.subTest(title=title):
                self.mapper.clear_search_cache()
                search = Mock(return_value=[dict(TFT_CATEGORY, categoryValue=title), LOL_CATEGORY])
                rules, pending = self.mapper.discover([TFT], [], search)
                self.assertEqual(pending, [])
                self.assertEqual([(r.category_id, r.category_name, r.processes) for r in rules],
                                 [('live-tft-id', title, (TFT,))])
                search.assert_called_once_with('전략적 팀 전투')

    def test_tft_never_matches_mobile_lol_or_related_titles(self):
        for title in ('리그 오브 레전드', '전략적 팀 전투 모바일 : 시즌', 'Teamfight Tactics Mobile', 'TFT Companion'):
            self.mapper.clear_search_cache()
            rules, pending = self.mapper.discover([TFT], [], lambda _: [dict(TFT_CATEGORY, categoryValue=title)])
            self.assertEqual(rules, [])
            self.assertEqual(pending[0]['reason'], 'category-not-found')

    def test_distinct_tft_categories_still_require_category_confirmation(self):
        rules, pending = self.mapper.discover([TFT], [], lambda _: [TFT_CATEGORY, dict(TFT_CATEGORY, categoryId='other-id')])
        self.assertEqual(rules, [])
        self.assertEqual(pending[0]['reason'], 'category-choice')
        self.assertEqual({c['categoryId'] for c in pending[0]['candidates']}, {'live-tft-id', 'other-id'})

    def seed_wrong_category_cache(self):
        self.mapper.category_cache = VerifiedCache(Path(self.temp.name) / 'verified.json')
        game = self.mapper.entries[TFT.casefold()][0]
        fingerprint = json.dumps([game.get('name'), game.get('id'), game.get('aliases')], ensure_ascii=False, sort_keys=True)
        self.mapper.category_cache.put(game_key(game, TFT), fingerprint, LOL_CATEGORY, game)

    def test_old_verified_lol_category_cannot_override_tft_process(self):
        self.seed_wrong_category_cache()
        search = Mock(return_value=[TFT_CATEGORY])
        rules, pending = self.mapper.discover([TFT], [], search)
        self.assertEqual(pending, [])
        self.assertEqual([r.category_id for r in rules], ['live-tft-id'])
        search.assert_called_once_with('전략적 팀 전투')

    def test_wrong_offline_cache_never_maps_tft_to_lol(self):
        self.seed_wrong_category_cache()
        rules, pending = self.mapper.discover([TFT], [], Mock(side_effect=RuntimeError('offline')))
        self.assertEqual(rules, [])
        self.assertEqual(pending[0]['reason'], 'category-not-found')

    def test_saved_tft_shared_rule_migrates_once_preserving_category(self):
        old = asdict(Rule(LOBBY, 'live-tft-id', TFT_CATEGORY['categoryValue'],
                          game_name='LeagueClient', match_source='사용자 카테고리 선택',
                          process_aliases=(LOL, 'LeagueClientUx.exe')))
        config = normalize_config({'league_mode': 'ask', 'rules': [old], 'auto_rules': [old],
                                   'auto_pending': [{'process': LOBBY, 'reason': 'multi-game'}]})
        self.assertEqual(config['league_mode'], 'auto')
        self.assertEqual(config['auto_pending'], [])
        for key in ('rules', 'auto_rules'):
            rule = Rule(**config[key][0])
            self.assertEqual(rule.processes, (TFT,))
            self.assertEqual(rule.game_name, 'Teamfight Tactics')
            self.assertEqual(rule.category_id, old['category_id'])
            self.assertEqual(rule.category_name, old['category_name'])
            self.assertEqual(rule.match_source, old['match_source'])
        self.assertEqual(normalize_config(config), config)

    def test_lol_rule_and_unrelated_custom_rule_remain_separate(self):
        old = [asdict(Rule(LOBBY, 'live-lol-id', '리그 오브 레전드', game_name='League of Legends')),
               asdict(Rule('Celeste.exe', 'talk', '잡담', 'ETC'))]
        migrated = [Rule(**r) for r in migrate_riot_rules(old)]
        self.assertEqual(migrated[0].processes, (LOL, LOBBY))
        self.assertEqual(asdict(migrated[1]), old[1])

    def test_tft_does_not_compete_with_idle_lol_lobby(self):
        with patch('worker.snapshot_process_names', return_value=[LOBBY, TFT, 'RiotClientServices.exe']):
            self.assertEqual(process_names(), [TFT])
        with patch('worker.snapshot_process_names', return_value=[LOBBY, LOL, TFT]):
            self.assertEqual(process_names(), [LOL, TFT])

    def worker(self, config=None):
        with patch('worker.discord_cache_file', return_value=self.cache):
            worker = Worker(normalize_config({'channel': 'a'*32, **(config or {})}))
        worker.api = Mock()
        worker.api.search.side_effect = lambda q, *_: [TFT_CATEGORY] if '전략적 팀 전투' in q else [LOL_CATEGORY]
        worker.api.apply.return_value = True
        worker.startup_talk_attempted = True
        worker.mapper.entries = self.mapper.entries
        worker.gate = Gate(stable=0, cooldown=0)
        self.addCleanup(worker.steam.close)
        self.addCleanup(worker.chzzk_open.close)
        return worker

    def test_switch_between_games_automatically_without_mode_dialog(self):
        worker = self.worker()
        events = []
        worker.event.connect(events.append)
        with patch.object(worker.mapper, 'ensure_index', return_value={}), patch('worker.snapshot_process_names') as snapshot:
            for names in ([LOBBY], [LOBBY, TFT], [LOBBY, LOL], [TFT], []):
                snapshot.return_value = names
                worker.scan()
                worker.scan()
        self.assertEqual([call.args[0].category_id for call in worker.api.apply.call_args_list],
                         ['live-lol-id', 'live-tft-id', 'live-lol-id', 'live-tft-id'])
        self.assertFalse(any(e['kind'] in ('league_mode_required', 'category_choice_required') for e in events))
        self.assertFalse(any(s.running for s in worker.pipeline.states.values()))
        self.assertEqual(len(worker.config['auto_rules']), 2)

    def test_saved_legacy_tft_mapping_cannot_turn_lol_into_tft(self):
        old = Rule(LOBBY, 'live-tft-id', TFT_CATEGORY['categoryValue'], game_name='Teamfight Tactics', process_aliases=(LOL,))
        worker = self.worker({'rules': [asdict(old)], 'league_mode': 'ask'})
        with patch.object(worker.mapper, 'ensure_index', return_value={}), patch('worker.snapshot_process_names', return_value=[LOL]):
            worker.scan()
            worker.scan()
        self.assertEqual(worker.api.apply.call_args.args[0].category_id, 'live-lol-id')
        self.assertEqual(Rule(**worker.config['rules'][0]).processes, (TFT,))

    def test_discord_tft_id_remains_one_runtime_row_during_application(self):
        worker = self.worker()
        worker.mapper.entries[TFT.casefold()][0]['id'] = 'discord-tft'
        with patch.object(worker.mapper, 'ensure_index', return_value={}), patch('worker.snapshot_process_names', return_value=[TFT]):
            worker.scan()
            worker.scan()
        self.assertEqual(set(worker.pipeline.states), {'discord-tft'})
        self.assertEqual(worker.pipeline.states['discord-tft'].stage, '적용 완료')
        worker.api.apply.assert_called_once()

    def test_tft_exit_during_search_cannot_apply_late_result(self):
        worker = self.worker()
        active = [TFT]
        def search(*_):
            active.clear()
            return [TFT_CATEGORY]
        worker.api.search.side_effect = search
        with patch.object(worker.mapper, 'ensure_index', return_value={}), patch('worker.snapshot_process_names', side_effect=lambda: list(active)):
            worker.scan()
        self.assertEqual(worker.config['auto_rules'], [])
        worker.api.apply.assert_not_called()

    def test_tft_search_failure_never_uses_lol_category(self):
        worker = self.worker()
        worker.api.search.side_effect = RuntimeError('offline')
        with patch.object(worker.mapper, 'ensure_index', return_value={}), patch('worker.snapshot_process_names', return_value=[TFT]):
            worker.scan()
        worker.api.apply.assert_not_called()
        self.assertEqual(worker.config['auto_rules'], [])
        self.assertEqual(worker.config['auto_pending'][0]['reason'], 'category-not-found')


if __name__ == '__main__':
    unittest.main()
