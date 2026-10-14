import os
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from autodetect import (cleanup_auto_mappings, detectable_running_processes,
                        parse_detectable_index, with_game_client_compatibility)
from core import Rule, Gate
from main import Window
from worker import Worker

LOBBY = 'LeagueClient.exe'
CLIENTS = ['LeagueClientUx.exe', 'LeagueClientUxRender.exe']
MATCH = 'League of Legends.exe'
CATEGORY = {'categoryId': 'League_of_Legends', 'categoryValue': '리그 오브 레전드', 'categoryType': 'GAME'}


class LeagueHelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def worker(self, config=None):
        with patch('worker.discord_cache_file', return_value=Path(self.temp.name)/'cache.json'):
            worker = Worker({'channel': 'a'*32, 'chzzk_open_enabled': False, **(config or {})})
        worker.api = Mock()
        worker.api.search.return_value = [CATEGORY]
        worker.startup_talk_attempted = True
        return worker

    def test_discord_helper_entries_cannot_reenable_detection(self):
        payload = [{'name': 'League of Legends', 'executables': [
            {'os': 'win32', 'name': name, 'is_launcher': False}
            for name in [*CLIENTS, LOBBY, MATCH, 'LeagueHelper.exe']]}]
        self.assertEqual(set(parse_detectable_index(payload)), {MATCH.casefold(), LOBBY.casefold()})
        stale = {name.casefold(): [{'name': 'League of Legends', 'aliases': []}]
                 for name in [*CLIENTS, LOBBY, MATCH, 'LeagueHelper.exe']}
        entries = with_game_client_compatibility(stale)
        self.assertEqual(set(entries), {MATCH.casefold(), LOBBY.casefold()})
        self.assertEqual(detectable_running_processes([*CLIENTS, MATCH], entries), [MATCH])

    def test_duplicate_saved_rules_and_pending_clients_are_migrated_once(self):
        old = [asdict(Rule(p, CATEGORY['categoryId'], CATEGORY['categoryValue'],
                          game_name='League of Legends', process_aliases=tuple(CLIENTS)))
               for p in CLIENTS]
        pending = [{'process': p, 'reason': 'category-choice'} for p in CLIENTS]
        rules, pending, _ = cleanup_auto_mappings(old, pending)
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].processes, (MATCH, LOBBY))
        self.assertEqual(pending, [])
        again, _, _ = cleanup_auto_mappings([asdict(rules[0])], [])
        self.assertEqual(again, rules)

    def test_manual_match_rule_takes_precedence_over_migration(self):
        old = Rule(CLIENTS[0], CATEGORY['categoryId'], CATEGORY['categoryValue'], game_name='League of Legends')
        manual = Rule(MATCH, 'Teamfight_Tactics', '전략적 팀 전투')
        rules, _, _ = cleanup_auto_mappings([asdict(old)], [], [asdict(manual)])
        self.assertEqual([r.processes for r in rules], [(LOBBY,)])

    def test_client_churn_causes_no_search_or_popup_then_match_applies_once(self):
        worker = self.worker()
        worker.mapper.entries = with_game_client_compatibility({})
        worker.gate = Gate(stable=0)
        events = []
        worker.event.connect(events.append)
        with patch.object(worker.mapper, 'ensure_index', return_value={}), patch('worker.snapshot_process_names') as snapshot:
            for names in (CLIENTS[:1], CLIENTS, CLIENTS[1:], CLIENTS):
                snapshot.return_value = names
                worker.last_auto_sync = 0
                worker.scan()
            worker.api.search.assert_not_called()
            worker.api.apply.assert_not_called()
            snapshot.return_value = [*CLIENTS, MATCH]
            worker.last_auto_sync = 0
            worker.scan()
            worker.scan()
        self.assertFalse(any(e['kind'] == 'category_choice_required' for e in events))
        self.assertEqual(len(worker.config['auto_rules']), 1)
        self.assertEqual(Rule(**worker.config['auto_rules'][0]).processes, (MATCH, LOBBY))
        worker.api.apply.assert_called_once()

    def test_stale_helper_selection_cannot_restore_blocked_rule(self):
        worker = self.worker()
        token = 'leagueclientux.exe|old'
        worker.category_choice_waiting.add(token)
        worker.command('choose_category_candidate', {
            'process': CLIENTS[0], 'token': token, 'game_name': 'League of Legends',
            'category': CATEGORY, 'save_rule': True})
        self.assertFalse(worker.config.get('auto_rules'))
        self.assertNotIn(token, worker.category_choice_waiting)

    def test_stale_helper_event_cannot_open_dialog(self):
        host = Mock(preview=False, category_choice_dialog_active=False)
        with patch('main.CategoryChoiceDialog') as dialog:
            Window.prompt_category_choice(host, {
                'process': CLIENTS[1], 'token': 'leagueclientux.exe|old',
                'game_name': 'League of Legends', 'candidates': [CATEGORY, dict(CATEGORY)]})
            dialog.assert_not_called()

    def test_lobby_launcher_flag_and_one_representative_per_scan(self):
        payload = [{'name': 'League of Legends', 'executables': [
            {'os': 'win32', 'name': LOBBY, 'is_launcher': True},
            {'os': 'win32', 'name': MATCH, 'is_launcher': False}]}]
        entries = parse_detectable_index(payload)
        self.assertEqual(detectable_running_processes([LOBBY, *CLIENTS], entries), [LOBBY])
        self.assertEqual(detectable_running_processes([LOBBY, MATCH, *CLIENTS], entries), [MATCH])
        self.assertEqual(detectable_running_processes([MATCH], entries), [MATCH])
        self.assertEqual(detectable_running_processes(CLIENTS, entries), [])

    def test_lobby_match_return_uses_one_rule_and_one_application(self):
        worker = self.worker()
        worker.mapper.entries = with_game_client_compatibility({})
        worker.gate = Gate(stable=0)
        events = []
        worker.event.connect(events.append)
        with patch.object(worker.mapper, 'ensure_index', return_value={}), patch('worker.snapshot_process_names') as snapshot:
            for names in ([LOBBY, *CLIENTS], [LOBBY, MATCH, *CLIENTS], [MATCH], [LOBBY]):
                snapshot.return_value = names
                worker.last_auto_sync = 0
                worker.scan()
                worker.scan()
        worker.api.search.assert_called_once()
        worker.api.apply.assert_called_once()
        self.assertEqual(len(worker.config['auto_rules']), 1)
        self.assertEqual(Rule(**worker.config['auto_rules'][0]).processes, (MATCH, LOBBY))
        self.assertFalse(any(e['kind'] == 'category_choice_required' for e in events))

    def test_waiting_or_dismissed_choice_survives_lobby_match_transition(self):
        for dismiss in (False, True):
            with self.subTest(dismiss=dismiss):
                worker = self.worker()
                worker.mapper.entries = with_game_client_compatibility({})
                worker.api.search.return_value = [CATEGORY, dict(CATEGORY, categoryId='second-id')]
                events = []
                worker.event.connect(events.append)
                with patch.object(worker.mapper, 'ensure_index', return_value={}), patch('worker.snapshot_process_names') as snapshot:
                    snapshot.return_value = [LOBBY]
                    worker.scan()
                    choice = next(e for e in events if e['kind'] == 'category_choice_required')
                    if dismiss:
                        worker.command('dismiss_category_choice', {'token': choice['token']})
                    for names in ([LOBBY, MATCH], [MATCH], [LOBBY]):
                        snapshot.return_value = names
                        worker.last_auto_sync = 0
                        worker.scan()
                    self.assertEqual(sum(e['kind'] == 'category_choice_required' for e in events), 1)
                    snapshot.return_value = []
                    worker.refresh_processes()
                    self.assertFalse(worker.category_choice_waiting)
                    self.assertFalse(worker.category_choice_dismissed)

    def test_previous_match_only_rule_restores_lobby_alias(self):
        old = Rule(MATCH, CATEGORY['categoryId'], CATEGORY['categoryValue'], game_name='League of Legends')
        worker = self.worker({'auto_rules': [asdict(old)]})
        self.assertEqual(Rule(**worker.config['auto_rules'][0]).processes, (MATCH, LOBBY))


if __name__ == '__main__':
    unittest.main()
