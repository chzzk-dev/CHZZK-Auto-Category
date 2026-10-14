import unittest

from autodetect import (cleanup_auto_mappings, detectable_running_processes,
                        is_ignored_process, parse_detectable_index)


class GameProcessFilterTests(unittest.TestCase):
    def test_only_running_discord_detectable_games_are_returned(self):
        processes = [
            'cl.exe', 'python.exe', 'VRChat.exe', 'TslGame.exe',
            'TslGame_BE.exe', 'ExecPubg.exe',
            'explorer.exe', 'EasyAntiCheat_EOS.exe',
        ]
        entries = {
            'vrchat.exe': [{'name': 'VRChat', 'aliases': []}],
            'tslgame.exe': [{'name': 'PUBG: BATTLEGROUNDS', 'aliases': []}],
            'tslgame_be.exe': [{'name': 'PUBG: BATTLEGROUNDS', 'aliases': []}],
            'execpubg.exe': [{'name': 'PUBG: Test Server', 'aliases': []}],
            'someclosedgame.exe': [{'name': 'Closed Game', 'aliases': []}],
        }
        self.assertEqual(
            detectable_running_processes(processes, entries),
            ['TslGame.exe', 'VRChat.exe'],
        )

    def test_empty_or_unknown_processes_are_not_shown(self):
        self.assertEqual(
            detectable_running_processes(['cl.exe', 'python.exe'], {'vrchat.exe': [{'name': 'VRChat'}]}),
            [],
        )

    def test_generic_dev_tool_is_rejected_even_if_discord_index_contains_it(self):
        entries = {
            'cl.exe': [{'name': 'Some Bad Generic Mapping', 'aliases': []}],
            'vrchat.exe': [{'name': 'VRChat', 'aliases': []}],
        }
        self.assertEqual(
            detectable_running_processes(['cl.exe', 'VRChat.exe'], entries),
            ['VRChat.exe'],
        )


    def test_generic_installers_are_never_games(self):
        for name in (
            'setup.exe', 'Setup64.exe', 'setup_x64.exe', 'install.exe',
            'installer.exe', 'uninstall.exe', 'unins000.exe', 'update.exe',
            'patch.exe', 'bootstrapper.exe',
        ):
            self.assertTrue(is_ignored_process(name), name)

    def test_setup_is_rejected_even_if_discord_claims_it_is_a_game(self):
        payload = [{
            'name': 'Hidden & Dangerous 2: Courage Under Fire',
            'aliases': [],
            'executables': [
                {'os': 'win32', 'name': 'setup.exe', 'is_launcher': False},
                {'os': 'win32', 'name': 'realgame.exe', 'is_launcher': False},
            ],
        }]
        index = parse_detectable_index(payload)
        self.assertNotIn('setup.exe', index)
        self.assertIn('realgame.exe', index)

    def test_old_setup_auto_rule_and_pending_entry_are_cleaned(self):
        rules, pending, removed = cleanup_auto_mappings(
            [{
                'process': 'setup.exe',
                'category_id': 'bad-category',
                'category_name': '파이어 엠블렘 만자천홍',
                'category_type': 'GAME',
                'game_name': 'Hidden & Dangerous 2: Courage Under Fire',
                'match_source': 'CHZZK 비공식 API → Studio 검증',
                'process_aliases': [],
            }],
            [{
                'process': 'setup.exe',
                'reason': 'category-ambiguous',
                'games': ['Hidden & Dangerous 2: Courage Under Fire'],
            }],
        )
        self.assertEqual(rules, [])
        self.assertEqual(pending, [])
        self.assertEqual(removed['rules'], 1)
        self.assertEqual(removed['pending'], 1)

    def test_pubg_helper_processes_are_never_shown(self):
        entries = {
            'tslgame.exe': [{'name': 'PUBG: BATTLEGROUNDS', 'aliases': []}],
            'tslgame_be.exe': [{'name': 'PUBG: BATTLEGROUNDS', 'aliases': []}],
            'execpubg.exe': [{'name': 'PUBG: Test Server', 'aliases': []}],
        }
        self.assertEqual(
            detectable_running_processes(
                ['TslGame_BE.exe', 'ExecPubg.exe', 'TslGame.exe'],
                entries,
            ),
            ['TslGame.exe'],
        )


if __name__ == '__main__':
    unittest.main()
