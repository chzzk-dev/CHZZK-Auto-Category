"""Small daily counters; game names and process paths are never persisted."""
from datetime import date, timedelta
import json
import os
from pathlib import Path
import tempfile

COUNTERS = ('detected', 'matched', 'changed', 'pending')
MATCHED_STAGES = {'연결 완료', '적용 대기', '적용 중', '적용 완료'}


class ActivityStats:
    def __init__(self, path=None, today=date.today):
        self.path = Path(path) if path is not None else None
        self.today = today
        self.days = {}
        self.running = set()
        self.matched = set()
        self.pending = set()
        if self.path is not None:
            try:
                payload = json.loads(self.path.read_text(encoding='utf-8'))
                for day, values in payload.get('days', {}).items():
                    try:
                        parsed = date.fromisoformat(day)
                    except (ValueError, TypeError):
                        continue
                    if (self.today() - timedelta(days=89) <= parsed <= self.today()
                            and isinstance(values, dict)):
                        self.days[day] = {key: values[key] for key in COUNTERS
                                          if type(values.get(key)) is int and values[key] >= 0}
            except (OSError, ValueError, TypeError, AttributeError):
                self.days = {}

    def increment(self, **counts):
        if any(key not in COUNTERS or type(value) is not int or value < 0 for key, value in counts.items()):
            raise ValueError('Invalid activity counter')
        if not any(counts.values()):
            return
        today = self.today()
        self.days = {day: values for day, values in self.days.items()
                     if (today - timedelta(days=89)).isoformat() <= day <= today.isoformat()}
        bucket = self.days.setdefault(today.isoformat(), {})
        for key, value in counts.items():
            bucket[key] = bucket.get(key, 0) + value
        self._save()

    def observe(self, games):
        running, matched, pending = set(), set(), set()
        for game in games:
            process = str(game.get('process') or '').casefold()
            if not process or not game.get('running'):
                continue
            running.add(process)
            category = str(game.get('category_id') or game.get('category_name') or '')
            if game.get('stage') in MATCHED_STAGES and category:
                matched.add((process, category))
            if game.get('stage') == '확인 필요':
                pending.add(process)
        counts = {'detected': len(running - self.running),
                  'matched': len(matched - self.matched),
                  'pending': len(pending - self.pending)}
        self.running = running
        self.matched = {item for item in self.matched | matched if item[0] in running}
        self.pending = (self.pending | pending) & running
        self.increment(**counts)

    def totals(self, period=1):
        if period not in (1, 7, 30):
            raise ValueError('Invalid statistics period')
        end = self.today()
        start = end - timedelta(days=period - 1)
        return {key: sum(values.get(key, 0) for day, values in self.days.items()
                         if start.isoformat() <= day <= end.isoformat()) for key in COUNTERS}

    def _save(self):
        if self.path is None:
            return
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                             prefix='activity-', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({'schema': 1, 'days': self.days}, stream, ensure_ascii=False)
            os.replace(temporary, self.path)
        except OSError:
            pass  # Statistics must never interrupt detection or category changes.
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
