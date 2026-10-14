import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QWidget
from autodetect import (DiscordAutoMapper, parse_detectable_index,
    detectable_running_processes, game_process_details)
from api import ChzzkAPI, APIError
from core import Gate
from worker import Worker
from main import RuleDialog

CATEGORY = {'categoryId': 'league_of_legends', 'categoryValue': '리그 오브 레전드', 'categoryType': 'GAME'}
PAYLOAD = [{'name': 'League of Legends', 'aliases': ['LoL'], 'executables': [
    {'os': 'win32', 'name': 'leagueclientux.exe', 'is_launcher': True},
    {'os': 'win32', 'name': 'League of Legends.exe', 'is_launcher': False},
    {'os': 'win32', 'name': 'RiotClientServices.exe', 'is_launcher': True}]}]

class LeagueDetectionTests(unittest.TestCase):
    def test_only_match_executable_retained_and_lobby_blocked(self):
        entries = parse_detectable_index(PAYLOAD)
        self.assertEqual(detectable_running_processes(['LeagueClientUx.exe', 'RiotClientServices.exe', 'League of Legends.exe'], entries), ['League of Legends.exe'])
        bad = [{'name': 'Different Game', 'executables': PAYLOAD[0]['executables'][:1]}]
        self.assertNotIn('leagueclientux.exe', parse_detectable_index(bad))

    def test_previous_fresh_cache_drops_clients_without_download(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'games.json'
            path.write_text(json.dumps({'updated_at': time.time(), 'entries': {
                'leagueclientux.exe': [{'name': 'League of Legends', 'aliases': []}]}}))
            mapper = DiscordAutoMapper(path)
            with patch.object(mapper, 'refresh') as refresh:
                mapper.ensure_index()
            refresh.assert_not_called()
            self.assertNotIn('leagueclientux.exe', mapper.entries)
            self.assertEqual(detectable_running_processes(['LeagueClientUx.exe', 'League of Legends.exe'], mapper.entries), ['League of Legends.exe'])

    def test_offline_first_run_has_league_fallback_and_retry_delay(self):
        with tempfile.TemporaryDirectory() as d:
            mapper = DiscordAutoMapper(Path(d)/'games.json')
            with patch.object(mapper, 'refresh', side_effect=RuntimeError('offline')) as refresh:
                self.assertTrue(mapper.ensure_index()['error'])
                mapper.ensure_index()
            self.assertEqual(refresh.call_count, 1)
            self.assertEqual(detectable_running_processes(['LeagueClientUx.exe','cl.exe','setup.exe','League of Legends.exe'], mapper.entries), ['League of Legends.exe'])

    def test_match_to_korean_category_registration_and_apply(self):
        with tempfile.TemporaryDirectory() as d, patch('worker.discord_cache_file', return_value=Path(d)/'games.json'):
            worker = Worker({'channel': 'a'*32, 'chzzk_open_enabled': False})
            worker.api = Mock()
            worker.api.search.return_value = [CATEGORY]
            worker.api.apply.return_value = True
            worker.startup_talk_attempted = True
            worker.gate = Gate(stable=0)
            with patch('worker.snapshot_process_names', return_value=['League of Legends.exe']), patch.object(worker.mapper, 'refresh', side_effect=RuntimeError('offline')):
                worker.scan()
                worker.scan()
            self.assertEqual(worker.api.search.call_args.args[0], '리그 오브 레전드')
            self.assertEqual(worker.api.apply.call_count, 1)
            self.assertEqual(worker.api.apply.call_args.args[0].category_id, CATEGORY['categoryId'])

    def test_category_connection_failure_is_not_empty_success(self):
        client = ChzzkAPI('a'*32, None)
        try:
            with patch.object(client, 'search_catalog', side_effect=APIError('offline')), patch.object(client, 'bridge_request', side_effect=APIError('disconnected')):
                with self.assertRaisesRegex(APIError, '연결하지 못했습니다'):
                    client.search('리그 오브 레전드')
            with patch.object(client, 'search_catalog', return_value=[]), patch.object(client, 'bridge_request', return_value={'results': []}):
                self.assertEqual(client.search('검색 결과 없는 게임'), [])
        finally:
            client.close()

    def test_studio_korean_search_works_without_public_catalog(self):
        client = ChzzkAPI('a'*32, None)
        try:
            with patch.object(client, 'search_catalog', side_effect=APIError('offline')), patch.object(client, 'bridge_request', return_value={'results': [CATEGORY]}) as bridge:
                rows = client.search('리그 오브 레전드')
            self.assertEqual(rows[0]['categoryId'], CATEGORY['categoryId'])
            self.assertEqual(bridge.call_args.args[1]['keyword'], '리그 오브 레전드')
        finally:
            client.close()

class DummyWorker(QObject):
    event = Signal(object)
    def __init__(self):
        super().__init__()
        self.submit = Mock()

class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_detected_game_prefills_korean_query_and_preserves_user_query(self):
        parent = QWidget()
        parent.worker = DummyWorker()
        dialog = RuleDialog(parent)
        entries = parse_detectable_index(PAYLOAD)
        details = game_process_details(['League of Legends.exe'], entries)
        event = {'kind': 'processes', 'data': ['League of Legends.exe'], 'game_details': details}
        dialog.on_event(event)
        self.assertEqual(dialog.keyword.text(), '리그 오브 레전드')
        dialog.search()
        self.assertEqual(parent.worker.submit.call_args.args[1]['keyword'], '리그 오브 레전드')
        dialog.keyword.setText('전략적 팀 전투')
        dialog._mark_keyword_user_edited('전략적 팀 전투')
        dialog.on_event(event)
        self.assertEqual(dialog.keyword.text(), '전략적 팀 전투')
        dialog.detach()
        dialog.deleteLater()
        parent.deleteLater()

if __name__ == '__main__':
    unittest.main()
