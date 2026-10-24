from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from activity_stats import ActivityStats


class ActivityStatsTests(unittest.TestCase):
    def game(self, **changes):
        return {'process': 'Game.exe', 'running': True, 'category_id': 'game',
                'stage': '연결 완료', **changes}

    def test_repeated_pipeline_updates_and_duplicate_processes_count_one_session(self):
        stats = ActivityStats()
        stats.observe([self.game(), self.game(process='GAME.EXE')])
        stats.observe([self.game(stage='적용 대기')])
        stats.observe([self.game(stage='검색 중')])
        stats.observe([self.game(stage='적용 완료')])
        self.assertEqual(stats.totals(), {'detected': 1, 'matched': 1, 'changed': 0, 'pending': 0})
        stats.observe([])
        stats.observe([self.game()])
        self.assertEqual(stats.totals()['detected'], 2)
        self.assertEqual(stats.totals()['matched'], 2)

    def test_confirmations_and_new_category_connections_are_counted_once_per_session(self):
        stats = ActivityStats()
        for _ in range(3):
            stats.observe([self.game(stage='확인 필요', category_id='')])
        stats.observe([self.game()])
        stats.observe([self.game(category_id='different')])
        stats.observe([self.game(stage='확인 필요', category_id='')])
        self.assertEqual(stats.totals()['pending'], 1)
        self.assertEqual(stats.totals()['matched'], 2)

    def test_periods_and_day_rollover_do_not_mix_outside_dates(self):
        day = [date(2026, 10, 1)]
        stats = ActivityStats(today=lambda: day[0])
        stats.increment(changed=4)
        day[0] += timedelta(days=23)
        stats.increment(changed=2)
        day[0] += timedelta(days=6)
        stats.increment(changed=1)
        self.assertEqual(stats.totals(1)['changed'], 1)
        self.assertEqual(stats.totals(7)['changed'], 3)
        self.assertEqual(stats.totals(30)['changed'], 7)
        day[0] += timedelta(days=1)
        self.assertEqual(stats.totals(1)['changed'], 0)
        self.assertEqual(stats.totals(7)['changed'], 1)
        self.assertEqual(stats.totals(30)['changed'], 3)

    def test_restart_restores_aggregates_without_saving_process_or_game_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'activity-stats.json'
            first = ActivityStats(path)
            first.observe([self.game()])
            first.increment(changed=1)
            restored = ActivityStats(path)
            self.assertEqual(restored.totals(), first.totals())
            self.assertNotIn('Game.exe', path.read_text())
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])

    def test_invalid_and_expired_history_does_not_invent_counts(self):
        today = date(2026, 10, 24)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stats.json'
            path.write_text(json.dumps({'days': {'2026-10-24': {'detected': 3, 'changed': True, 'matched': -2},
                                                'bad-date': {'detected': 50},
                                                '2026-01-01': {'detected': 40}}}))
            stats = ActivityStats(path, today=lambda: today)
            self.assertEqual(stats.totals(30), {'detected': 3, 'matched': 0, 'changed': 0, 'pending': 0})
            path.write_text('broken json')
            self.assertEqual(ActivityStats(path).totals()['detected'], 0)

    def test_failed_save_preserves_previous_file_and_does_not_interrupt_live_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stats.json'
            stats = ActivityStats(path)
            stats.increment(changed=1)
            previous = path.read_bytes()
            with patch('activity_stats.os.replace', side_effect=OSError('read only')):
                stats.increment(changed=1)
            self.assertEqual(stats.totals()['changed'], 2)
            self.assertEqual(path.read_bytes(), previous)
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])
