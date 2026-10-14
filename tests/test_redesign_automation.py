import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from dataclasses import asdict

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from automation import MatchingPipeline, VerifiedCache, choose_representative
from normalization import normalized_name, search_name, edition_conflict, alias_conflicts
from autodetect import DiscordAutoMapper, with_game_client_compatibility, detectable_running_processes
from core import Rule, Gate
from worker import Worker
from storage import normalize_config


def category(id, name=None):
    return {'categoryId': id, 'categoryValue': name or id, 'categoryType': 'GAME'}


class IdentityTests(unittest.TestCase):
    def test_unicode_width_case_roman_and_spacing(self):
        self.assertEqual(normalized_name('ＤＡＲＫ Souls Ⅲ'), normalized_name('Dark Souls 3'))
        self.assertEqual(normalized_name(' 리그  오브 레전드 '), '리그오브레전드')
        self.assertEqual(search_name('Game: Remastered Client'), 'Game Remastered')
        self.assertNotEqual(normalized_name('Game II'), normalized_name('Game III'))

    def test_editions_never_match_from_a_shared_token(self):
        for game, wrong in [('Minecraft', 'Minecraft Dungeons'), ('PUBG: BATTLEGROUNDS', 'PUBG Mobile'),
                            ('Overwatch', 'Overwatch 2'), ('Counter-Strike', 'Counter-Strike 2'),
                            ('League of Legends', 'League of Legends Wild Rift'), ('Dark Souls II', 'Dark Souls III')]:
            with self.subTest(game=game):
                self.assertTrue(edition_conflict([game], category(wrong)))
                with tempfile.TemporaryDirectory() as d:
                    mapper = DiscordAutoMapper(Path(d) / 'discord.json')
                    mapper.entries = {'unique.exe': [{'name': game, 'aliases': []}]}
                    rules, pending = mapper.discover(['unique.exe'], [], lambda _: [category(wrong)])
                    self.assertEqual(rules, [])
                    self.assertTrue(pending)

    def test_fuzzy_single_result_does_not_auto_apply(self):
        with tempfile.TemporaryDirectory() as d:
            mapper = DiscordAutoMapper(Path(d) / 'discord.json')
            mapper.entries = {'stardew.exe': [{'name': 'Stardew Valley', 'aliases': []}]}
            rules, pending = mapper.discover(['stardew.exe'], [], lambda _: [category('Stardew Valey')])
            self.assertFalse(rules)
            self.assertTrue(pending)

    def test_alias_collision_detected_after_unicode_normalization(self):
        self.assertTrue(alias_conflicts({'One': ['ＦＯＯ'], 'Two': ['foo']}))
        self.assertFalse(alias_conflicts({'One': ['foo', 'FOO']}))

    def test_user_korean_alias_works_for_unlisted_localization(self):
        with tempfile.TemporaryDirectory() as d:
            mapper = DiscordAutoMapper(Path(d) / 'discord.json')
            mapper.entries = {'novel.exe': [{'name': 'A Novel Game', 'aliases': []}]}
            mapper.user_aliases = {'A Novel Game': ['새로운 게임']}
            calls = []
            def search(q):
                calls.append(q)
                return [category('opaque-id', '새로운 게임')] if q == '새로운 게임' else []
            rules, pending = mapper.discover(['novel.exe'], [], search)
            self.assertEqual(rules[0].category_id, 'opaque-id')
            self.assertEqual(pending, [])
            self.assertIn('새로운 게임', calls)

    def test_same_discord_identity_has_one_representative(self):
        entries = {'real.exe': [{'id': '42', 'name': 'Novel Game'}],
                   'real-helper.exe': [{'id': '42', 'name': 'Novel Game'}]}
        self.assertEqual(detectable_running_processes(['real-helper.exe', 'real.exe'], entries), ['real.exe'])

    def test_shared_executable_is_never_guessed(self):
        with tempfile.TemporaryDirectory() as d:
            mapper = DiscordAutoMapper(Path(d)/'discord.json')
            mapper.entries = {'shared.exe': [{'name': 'One'}, {'name': 'Two'}]}
            search = Mock()
            rules, pending = mapper.discover(['shared.exe'], [], search)
            self.assertEqual(rules, [])
            self.assertEqual(pending[0]['reason'], 'multi-game')
            search.assert_not_called()


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = VerifiedCache(Path(self.temp.name)/'cache.json')
        self.events = []
        self.pipeline = MatchingPipeline(lambda kind, **kw: self.events.append((kind, kw)), self.cache)
        self.rule = Rule('Game.exe', 'Novel_Game', '새 게임', game_name='Novel Game')

    def test_searching_and_invalid_states_cannot_enter_apply_queue(self):
        self.pipeline.snapshot(['Game.exe'])
        for stage in ('감지됨', '분석 중', '검색 중', '검증 중', '확인 필요', '오류'):
            state = self.pipeline.transition({'name': 'Novel Game'}, 'Game.exe', stage,
                                             category_id=self.rule.category_id, category_name=self.rule.category_name)
            self.assertFalse(self.pipeline.ready(self.rule, state), stage)
        self.pipeline.transition({'name': 'Novel Game'}, 'Game.exe', '연결 완료')
        self.assertTrue(self.pipeline.ready(self.rule, state))

    def test_late_search_after_game_exit_is_not_ready(self):
        self.pipeline.snapshot(['Game.exe'])
        state = self.pipeline.transition({'name': 'Novel Game'}, 'Game.exe', '검색 중')
        self.pipeline.snapshot([])
        self.pipeline.transition({'name': 'Novel Game'}, 'Game.exe', '연결 완료',
                                 category_id=self.rule.category_id, category_name=self.rule.category_name)
        self.assertFalse(self.pipeline.ready(self.rule, state))

    def test_games_have_independent_results_and_generation(self):
        self.pipeline.snapshot(['A.exe', 'B.exe'])
        a = self.pipeline.transition({'id': 'a', 'name': 'A'}, 'A.exe', '연결 완료', category_id='a')
        b = self.pipeline.transition({'id': 'b', 'name': 'B'}, 'B.exe', '검색 중')
        self.assertNotEqual(a.key, b.key)
        self.assertEqual(a.category_id, 'a')
        self.assertEqual(b.category_id, '')
        self.pipeline.snapshot(['B.exe'])
        self.assertFalse(a.running)
        self.assertTrue(b.running)

    def test_cache_persists_and_does_not_leak_mutations(self):
        self.cache.put('game', 'signature', category('a'), now=1000)
        loaded = VerifiedCache(self.cache.path)
        value = loaded.get('game', 'signature', 3600, now=2000)
        value['category']['categoryId'] = 'b'
        self.assertEqual(loaded.get('game', 'signature', 3600, now=2000)['category']['categoryId'], 'a')
        self.assertIsNone(loaded.get('game', 'different aliases', 3600, now=2000))
        self.assertIsNone(loaded.get('game', 'signature', 3600, now=5000))
        self.assertIsNotNone(loaded.get('game', 'signature', 3600, now=5000, offline=True))
        self.assertIsNone(loaded.get('game', 'signature', 3600, now=1000000, offline=True))

    def test_malformed_or_unverified_cache_is_not_used(self):
        for data in ('broken', json.dumps({'version': 1, 'games': {'x': {'verified': False}}})):
            self.cache.path.write_text(data)
            loaded = VerifiedCache(self.cache.path)
            self.assertIsNone(loaded.get('x', '', 3600))
        with self.assertRaises(ValueError):
            self.cache.put('x', '', {'categoryId': 'missing-fields'})

    def test_invalidated_cache_stays_invalid_after_restart(self):
        self.cache.put('game', 'signature', category('a'))
        self.cache.invalidate('game')
        self.assertIsNone(VerifiedCache(self.cache.path).get('game', 'signature', 3600))

    def test_offline_reuse_does_not_refresh_verification_timestamp(self):
        old = dict(category('a'), _verifiedAt=1000)
        self.cache.put('game', 'signature', old)
        self.assertEqual(self.cache.records['game']['verified_at'], 1000)
        self.assertIsNone(self.cache.get('game', 'signature', 3600, offline=True, now=1000000))

    def test_representative_manual_explicit_and_safe_ambiguity(self):
        a, b = Rule('A.exe', 'a', 'A'), Rule('B.exe', 'b', 'B')
        self.assertIsNone(choose_representative([a, b], ['A.exe', 'B.exe']))
        self.assertEqual(choose_representative([a, b], ['A.exe', 'B.exe'], [b]), b)
        self.assertEqual(choose_representative([a, b], ['A.exe', 'B.exe'], [b], 'A.exe'), a)
        self.assertEqual(choose_representative([a, b], ['A.exe']), a)


class WorkerSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        with patch('worker.discord_cache_file', return_value=Path(self.temp.name)/'discord.json'):
            self.worker = Worker(normalize_config({'channel': 'a'*32, 'chzzk_open_enabled': False}))
        self.worker.startup_talk_attempted = True
        self.worker.api = Mock()
        self.worker.gate = Gate(stable=0)
        self.worker.mapper.entries = {'minecraft.exe': [{'id': 'mc', 'name': 'Minecraft', 'aliases': []}]}
        self.worker.api.search.return_value = [category('Minecraft', '마인크래프트')]
        self.events = []
        self.worker.event.connect(self.events.append)

    def test_minecraft_verified_before_apply_and_deduplicated(self):
        with patch.object(self.worker.mapper, 'ensure_index', return_value={}), patch('worker.snapshot_process_names', return_value=['Minecraft.exe']):
            self.worker.scan()
            self.worker.scan()
        stages = [e['data']['stage'] for e in self.events if e['kind'] == 'pipeline_state']
        self.assertLess(stages.index('검색 중'), stages.index('적용 대기'))
        self.assertLess(stages.index('검증 중'), stages.index('적용 중'))
        self.worker.api.apply.assert_called_once()

    def test_game_exit_during_search_never_registers_or_applies(self):
        names = ['Minecraft.exe']
        def search(*_):
            names.clear()
            return [category('Minecraft', '마인크래프트')]
        self.worker.api.search.side_effect = search
        with patch.object(self.worker.mapper, 'ensure_index', return_value={}), patch('worker.snapshot_process_names', side_effect=lambda: list(names)):
            self.worker.scan()
        self.assertEqual(self.worker.config['auto_rules'], [])
        self.worker.api.apply.assert_not_called()

    def test_auth_error_or_timeout_does_not_enter_apply_queue(self):
        from api import APIError
        for error in (APIError('auth', auth=True), APIError('timeout'), APIError('rate', retry_after=120)):
            with self.subTest(error=error):
                self.worker.mapper.clear_search_cache()
                self.worker.api.search.side_effect = error
                with patch.object(self.worker.mapper, 'ensure_index', return_value={}), patch('worker.snapshot_process_names', return_value=['Minecraft.exe']):
                    self.worker.last_auto_sync = 0
                    self.worker.scan()
                self.worker.api.apply.assert_not_called()

    def test_lol_and_tft_require_explicit_rule_in_name_only_mode(self):
        self.worker.mapper.entries = with_game_client_compatibility({})
        self.worker.api.search.return_value = [category('League_of_Legends', '리그 오브 레전드')]
        with patch.object(self.worker.mapper, 'ensure_index', return_value={}), patch('worker.snapshot_process_names', return_value=['LeagueClient.exe']):
            self.worker.scan()
        self.worker.api.apply.assert_not_called()
        self.assertTrue(any(e['kind'] == 'status' and 'LoL / TFT' in e['text'] for e in self.events))
        tft = Rule('LeagueClient.exe', 'Teamfight_Tactics', '전략적 팀 전투', game_name='Teamfight Tactics',
                   process_aliases=('League of Legends.exe',))
        self.worker.config['rules'] = [asdict(tft)]
        self.worker.api.search.return_value = [category('Teamfight_Tactics', '전략적 팀 전투')]
        with patch.object(self.worker.mapper, 'ensure_index', return_value={}), patch('worker.snapshot_process_names', return_value=['League of Legends.exe']):
            self.worker.last_auto_sync = 0
            self.worker.scan()
        self.worker.api.apply.assert_called_once()
        self.assertEqual(self.worker.api.apply.call_args.args[0].category_id, 'Teamfight_Tactics')

    def test_lol_mode_pending_is_not_deleted_and_readded_each_scan(self):
        self.worker.mapper.entries = with_game_client_compatibility({})
        self.worker.api.search.return_value = [category('League_of_Legends', '리그 오브 레전드')]
        with patch.object(self.worker.mapper, 'ensure_index', return_value={}), patch('worker.snapshot_process_names', return_value=['LeagueClient.exe']):
            self.worker.scan()
            pending = list(self.worker.config['auto_pending'])
            self.assertTrue(any(p.get('reason') == 'multi-game' for p in pending))
            self.events.clear()
            for _ in range(4):
                self.assertFalse(self.worker.sanitize_auto_state())
                self.worker.last_auto_sync = 0
                self.worker.scan()
                self.assertEqual(self.worker.config['auto_pending'], pending)
        self.assertFalse(any(e['kind'] == 'log' and '정리했습니다' in e.get('text', '') for e in self.events))
        self.assertFalse(any(e['kind'] == 'auto_pending' for e in self.events))
        self.worker.api.apply.assert_not_called()
        with patch.object(self.worker.mapper, 'ensure_index', return_value={}), patch('worker.snapshot_process_names', return_value=[]):
            self.worker.last_auto_sync = 0
            self.worker.scan()
        self.assertEqual(self.worker.config['auto_pending'], [])

    def test_live_only_holds_an_offline_broadcast(self):
        self.worker.config['only_when_live'] = True
        self.worker.api.is_live.return_value = False
        with patch.object(self.worker.mapper, 'ensure_index', return_value={}), patch('worker.snapshot_process_names', return_value=['Minecraft.exe']):
            self.worker.scan()
        self.worker.api.apply.assert_not_called()

    def test_excluded_process_never_applies(self):
        self.worker.config['excluded_processes'] = ['Minecraft.exe']
        with patch.object(self.worker.mapper, 'ensure_index', return_value={}), patch('worker.snapshot_process_names', return_value=['Minecraft.exe']):
            self.worker.scan()
        self.worker.api.apply.assert_not_called()

    def test_manual_research_rechecks_even_with_a_fresh_cache(self):
        rule = Rule('Minecraft.exe', 'Minecraft', '마인크래프트', game_name='Minecraft')
        self.worker.config['rules'] = [asdict(rule)]
        with patch('worker.snapshot_process_names', return_value=['Minecraft.exe']):
            self.worker.refresh_processes()
            self.assertTrue(self.worker.validate_rule(rule))
            self.worker.research_game('Minecraft.exe')
        self.assertEqual(self.worker.api.search.call_count, 2)

    def test_session_choice_survives_settings_save_but_not_game_exit(self):
        rule = Rule('Minecraft.exe', 'Minecraft', '마인크래프트', game_name='Minecraft')
        self.worker.session_rules = {'minecraft.exe': rule}
        self.worker.command('configure', dict(self.worker.config))
        self.assertIn('minecraft.exe', self.worker.session_rules)
        with patch('worker.snapshot_process_names', return_value=[]):
            self.worker.refresh_processes()
        self.assertEqual(self.worker.session_rules, {})


if __name__ == '__main__':
    unittest.main()
