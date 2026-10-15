"""Verified game state and cache, separate from unresolved user-choice items."""
import copy
from datetime import datetime
import json
from pathlib import Path
import time
from dataclasses import dataclass, asdict
from normalization import normalized_name

STAGES = ('감지됨', '분석 중', '검색 중', '검증 중', '연결 완료', '적용 대기', '적용 중',
          '적용 완료', '확인 필요', '오류')


def game_key(game, process):
    # IDs are preserved from Discord; older caches use canonical names.
    return str(game.get('id') or normalized_name(game.get('name')) or process.casefold())


@dataclass
class GameState:
    key: str
    process: str
    game_name: str
    stage: str = '감지됨'
    running: bool = True
    generation: int = 0
    category_id: str = ''
    category_name: str = ''
    confidence_label: str = '아직 검증하지 않음'
    verified_at: str = ''
    last_detected_at: str = ''
    representative: bool = False
    error: str = ''
    processes: tuple = ()
    discord_name: str = ''
    steam_appid: int = 0
    localized_name: str = ''
    detection_source: str = 'Discord 게임 목록'


class VerifiedCache:
    def __init__(self, path):
        self.path = Path(path)
        self.records = {}
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(data, dict) and data.get('version') == 1 and isinstance(data.get('games'), dict):
                self.records = data['games']
        except (OSError, ValueError):
            pass

    def get(self, key, fingerprint, ttl, offline=False, now=None):
        record = self.records.get(str(key))
        now = time.time() if now is None else now
        if not isinstance(record, dict) or record.get('fingerprint') != fingerprint:
            return None
        category = record.get('category')
        if (not record.get('verified') or not isinstance(category, dict)
                or not all(category.get(k) for k in ('categoryId', 'categoryValue', 'categoryType'))):
            return None
        age = now - float(record.get('verified_at', 0))
        # Stale validated data is allowed offline for at most seven days.
        if age < 0 or age > (max(ttl, 7*86400) if offline else ttl):
            return None
        return copy.deepcopy(record)

    def put(self, key, fingerprint, category, game=None, now=None):
        if not isinstance(category, dict) or not all(category.get(k) for k in ('categoryId', 'categoryValue', 'categoryType')):
            raise ValueError('검증된 카테고리 정보가 필요합니다.')
        if category['categoryType'] not in ('GAME', 'ETC', 'SPORTS'):
            raise ValueError('지원하지 않는 카테고리입니다.')
        self.records[str(key)] = dict(fingerprint=fingerprint, category=dict(category), game=game or {},
                                      verified=True, verified_at=(float(category.get('_verifiedAt') or time.time()) if now is None else now))
        if len(self.records) > 2048:
            oldest = min(self.records, key=lambda k: self.records[k].get('verified_at', 0))
            self.records.pop(oldest)
        self._save()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps({'version': 1, 'games': self.records}, ensure_ascii=False), encoding='utf-8')
        temp.replace(self.path)

    def invalidate(self, key):
        if self.records.pop(str(key), None) is not None:
            self._save()


class MatchingPipeline:
    def __init__(self, emit, cache):
        self.emit = emit
        self.cache = cache
        self.states = {}
        self.generation = 0
        self.active = set()
        self.last_signature = None

    def snapshot(self, processes):
        active = {p.casefold() for p in processes}
        if active != self.active:
            self.generation += 1
            self.active = active
            for state in self.states.values():
                running = bool(active & {p.casefold() for p in state.processes or (state.process,)})
                if state.running != running:
                    state.running = running
                    state.representative = False
                    self.emit('pipeline_state', data=asdict(state))

    def transition(self, game, process, stage, **fields):
        if stage not in STAGES:
            raise ValueError('알 수 없는 처리 상태입니다.')
        key = game_key(game, process)
        state = self.states.get(key)
        if state is None:
            state = GameState(key, process, str(game.get('name') or process),
                              discord_name=str(game.get('discord_name', game.get('name') or '')))
            self.states[key] = state
            if len(self.states) > 256:
                old = next((k for k, v in self.states.items() if not v.running and k != key), None)
                if old:
                    self.states.pop(old)
                    self.emit('pipeline_remove', key=old)
        state.process = process
        state.processes = tuple(game.get('processes') or (process,))
        state.generation = self.generation
        state.stage = stage
        state.running = bool(self.active & {p.casefold() for p in state.processes})
        state.last_detected_at = datetime.now().isoformat(timespec='seconds')
        for name, value in fields.items():
            setattr(state, name, value)
        self.emit('pipeline_state', data=asdict(state))
        return state

    def ready(self, rule, state):
        return bool(state.running and state.generation == self.generation
                    and state.stage in ('연결 완료', '적용 대기', '적용 중', '적용 완료')
                    and (state.category_id, state.category_name) == (rule.category_id, rule.category_name))


def choose_representative(rules, processes, manual_rules=(), preferred=''):
    names = {p.casefold() for p in processes}
    running = [r for r in rules if names & {p.casefold() for p in r.processes}]
    if preferred:
        explicit = [r for r in running if preferred.casefold() in {p.casefold() for p in r.processes}]
        if len(explicit) == 1:
            return explicit[0]
    manual = [r for r in manual_rules if r in running]
    if manual:
        return manual[0]  # Persisted user priority order remains authoritative.
    distinct = {r.key for r in running}
    if len(distinct) == 1 and running:
        return running[0]
    playing = [r for r in running if r.process.casefold() == 'league of legends.exe'
               and 'league of legends.exe' in names]
    return playing[0] if len(playing) == 1 else None
