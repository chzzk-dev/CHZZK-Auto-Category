import queue
import os
import threading
import time
import uuid
from PySide6.QtCore import QThread, Signal
from api import ChzzkAPI, APIError
from core import Rule, Gate, select_rule
from autodetect import (DiscordAutoMapper, serialize_rules, cleanup_auto_mappings,
                        is_ignored_process, detectable_running_processes, game_process_details,
                        category_choice_process_key, league_rule_processes)
from process_detect import process_names as snapshot_process_names
from storage import discord_cache_file, data_dir, get_steam_api_key, save_steam_api_key, steam_environment_key
from steam_lookup import SteamResolver, SteamLookupError, valid_key
from automation import MatchingPipeline, VerifiedCache, choose_representative
from datetime import datetime
from dataclasses import asdict
from chzzk_open import ChzzkOpenAPI, ChzzkOpenAPIError


STARTUP_TALK_RULE = Rule('__startup_talk__', 'talk', 'talk', 'ETC')


def process_names():
    # Anti-cheat friendly mode: read executable names from the Windows process
    # snapshot only. Never open game process handles or inspect memory/modules.
    names = {name for name in snapshot_process_names() if not is_ignored_process(name)}
    return sorted(names, key=str.casefold)


class Worker(QThread):
    event = Signal(object)

    def __init__(self, config, bridge=None):
        super().__init__()
        self.config = config
        self.bridge = bridge
        self.commands = queue.Queue()
        self.cancel = threading.Event()
        self.stop_event = threading.Event()
        self.enabled = False
        self.api = None
        self.gate = Gate()
        self.last_status = None
        self.processes = []
        self.pipeline = MatchingPipeline(self.emit, VerifiedCache(discord_cache_file().parent / 'verified_categories.json'))
        self.verified_rules = {}
        self.validation_retry = {}
        self.last_catalog_sync = 0.0
        self.latest_snapshot = None
        self.snapshot_thread = None
        self.steam = None
        self.last_steam_error = ''
        self.last_matching_summary = {}
        self.mapper = DiscordAutoMapper(
            discord_cache_file(),
            int(self.config.get('discord_refresh_hours', 24)) * 3600,
            aggressive_resolve=self.config.get('auto_aggressive', True),
            resolve_shared_executable=self.config.get('auto_resolve_shared', False),
        )
        self.configure_mapper()
        self.chzzk_open = self.build_chzzk_open_client()
        self.last_auto_sync = 0.0
        self.last_cookie_refresh = 0.0
        self.startup_talk_attempted = False
        self.session_rules = {}
        self.league_session_token = None
        self.league_confirmed_key = None
        self.category_choice_waiting = set()
        self.category_choice_dismissed = set()
        self.sanitize_auto_state(emit=False)

    def configure_mapper(self):
        self.mapper.aggressive_resolve = True
        self.mapper.user_aliases = self.config.get('game_aliases', {})
        self.mapper.category_cache = self.pipeline.cache
        self.mapper.category_ttl = max(1, int(self.config.get('category_sync_hours', 6))) * 3600
        self.mapper.cancelled = self.cancel.is_set
        self.mapper.observer = self.observe_matching
        key = get_steam_api_key() if self.config.get('steam_lookup_enabled', True) else ''
        if self.steam is None or self.steam.key != key:
            if self.steam is not None:
                self.steam.close()
            self.steam = SteamResolver(key, discord_cache_file().parent / 'steam_titles.json',
                                       cancelled=self.cancel.is_set)
        self.mapper.enrich_game = self.enrich_steam_game

    def enrich_steam_game(self, game, process):
        if not self.steam.configured:
            return game
        self.observe_matching(game, process, '분석 중')
        record = self.steam.resolve(game, process)
        if self.steam.last_error and self.steam.last_error != self.last_steam_error:
            self.emit('log', text='[카테고리 검색] ' + self.steam.last_error)
        self.last_steam_error = self.steam.last_error
        if record:
            title = record['localized_name']
            game = dict(game, steam_appid=record['appid'])
            if any('\uac00' <= c <= '\ud7a3' for c in title):
                game['steam_name_ko'] = title
                game['aliases'] = list(dict.fromkeys([title, *game.get('aliases', [])]))
            self.emit('steam_status', text=f"{title} · App ID {record['appid']} · 이름 검증 완료")
        else:
            self.emit('steam_status', text=self.steam.last_error or '정확한 Steam 게임을 찾지 못해 기존 매칭을 사용합니다.')
        return game

    def observe_matching(self, game, process, stage, **fields):
        # Observe per-game state; no search results are shared across game identities.
        old = self.pipeline.states.get(str(game.get('id') or __import__('normalization').normalized_name(game.get('name')) or process.casefold()))
        previous = old.stage if old else None
        fields.update(steam_appid=int(game.get('steam_appid') or 0),
                      localized_name=game.get('steam_name_ko', ''),
                      detection_source='Discord + Steam' if game.get('steam_appid') else 'Discord 게임 목록')
        self.pipeline.transition(game, process, stage, **fields)
        if stage != previous:
            key = (str(game.get('id') or game.get('name') or process), category_choice_process_key(process))
            terminal = stage in ('연결 완료', '확인 필요', '오류')
            signature = (stage, fields.get('category_id', ''), fields.get('category_name', ''), fields.get('error', ''))
            if terminal and self.last_matching_summary.get(key) != signature:
                self.last_matching_summary[key] = signature
                if len(self.last_matching_summary) > 256:
                    self.last_matching_summary.pop(next(iter(self.last_matching_summary)))
                title = game.get('steam_name_ko') or game.get('name') or process
                result = {'연결 완료': '카테고리 연결 완료', '확인 필요': '카테고리 확인 필요',
                          '오류': '카테고리 검색 오류'}[stage]
                category = fields.get('category_name')
                suffix = f' → {category}' if category else ''
                self.emit('log', text=f'[자동 매칭] {title}{suffix} · {result}')
            else:
                self.emit('log', text=f"[카테고리 검색] {game.get('name') or process} · {process} · {stage}", detail=True)

    def rule_game(self, rule):
        records = self.mapper.entries.get(rule.process.casefold(), [])
        game = dict(records[0]) if len(records) == 1 else {'name': rule.game_name or rule.process, 'discord_name': ''}
        if rule.game_name.casefold() == 'teamfight tactics' or rule.category_id.casefold() in ('teamfight_tactics', 'teamfighttactics'):
            game = {'name': 'Teamfight Tactics', 'discord_name': str(game.get('discord_name', game.get('name', '')))}  # Explicit stored category, not process inference.
        game['processes'] = rule.processes
        return game

    def validate_rule(self, rule, force=False):
        key = '|'.join((category_choice_process_key(rule.process), rule.category_type, rule.category_id))
        aliases = self.config.get('game_aliases', {}).get(rule.game_name, [])
        fingerprint = '|'.join([rule.category_id, rule.category_name, *aliases])
        ttl = max(1, int(self.config.get('category_sync_hours', 6))) * 3600
        cached = self.pipeline.cache.get('rule:' + key, fingerprint, ttl)
        if cached and not force:
            return True
        if not force and time.monotonic() < self.validation_retry.get(key, 0):
            return False
        game = self.rule_game(rule)
        self.pipeline.transition(game, rule.process, '검증 중')
        try:
            rows = self.client().search(rule.category_name, self.chzzk_open)
            valid = next((r for r in rows if r.get('categoryId') == rule.category_id
                          and r.get('categoryType') == rule.category_type and r.get('categoryValue')), None)
            if valid is None and rule.category_type != 'GAME':
                valid = self.client().validate_category(rule, self.chzzk_open)
            if valid is None:
                self.validation_retry[key] = time.monotonic() + 300
                self.pipeline.transition(game, rule.process, '확인 필요', error='저장된 카테고리를 검색 결과에서 확인하지 못했습니다.')
                return False
            self.pipeline.cache.put('rule:' + key, fingerprint, valid, game)
            return True
        except Exception as error:
            self.validation_retry[key] = time.monotonic() + max(60, float(getattr(error, 'retry_after', 0) or 0))
            if self.pipeline.cache.get('rule:' + key, fingerprint, ttl, offline=True):
                self.emit('log', text=f'[자동 매칭] {rule.process} · 이전에 검증된 오프라인 연결 재사용')
                return True
            self.pipeline.transition(game, rule.process, '오류', error='카테고리 검증에 연결하지 못했습니다.')
            self.emit('log', text=f'[카테고리 검색] {rule.process} 검증 실패 · {error}')
            return False

    def sync_category_data(self, force=False):
        now = time.monotonic()
        ttl = max(1, int(self.config.get('category_sync_hours', 6))) * 3600
        if not force and now - self.last_catalog_sync < ttl:
            return
        self.last_catalog_sync = now
        self.mapper.clear_search_cache()
        # Refresh only a catalogue already used; never download a whole list unnecessarily.
        if self.api is not None and getattr(self.api, '_category_catalog', None):
            try:
                self.api.load_category_catalog(force=force)
                self.emit('log', text='[카테고리 검색] 기존 카테고리 캐시 동기화 확인')
            except APIError as error:
                self.emit('log', text='[카테고리 검색] 캐시 동기화 실패 · ' + str(error))
        active = {p.casefold() for p in self.processes}
        for rule in self.effective_rules():
            if active.intersection(p.casefold() for p in rule.processes) and not self.cancel.is_set():
                self.validate_rule(rule, force=force)

    def research_game(self, process):
        self.refresh_processes()
        rule = next((r for r in self.effective_rules() if process.casefold() in {p.casefold() for p in r.processes}), None)
        self.mapper.clear_search_cache()
        self.validation_retry.clear()
        if rule is None:
            self.last_auto_sync = 0
            self.maybe_sync_auto(time.monotonic())
            return
        for key, record in list(self.pipeline.cache.records.items()):
            if (category_choice_process_key(rule.process) in key.casefold()
                    or record.get('game', {}).get('name') == rule.game_name):
                self.pipeline.cache.invalidate(key)
        manual = [Rule(**r) for r in self.config.get('rules', [])]
        if rule in manual:
            if self.validate_rule(rule, force=True):
                self.pipeline.transition(self.rule_game(rule), rule.process, '연결 완료',
                                         category_id=rule.category_id, category_name=rule.category_name)
            return
        found, unresolved = self.mapper.discover(self.processes, [r for r in self.effective_rules() if r != rule],
                                                  lambda q: self.client().search(q, self.chzzk_open))
        active = {p.casefold() for p in process_names()}
        found = [r for r in found if active.intersection(p.casefold() for p in r.processes)]
        if self.cancel.is_set():
            return
        if found:
            old = [Rule(**r) for r in self.config.get('auto_rules', [])]
            self.config['auto_rules'] = serialize_rules([r for r in old if r != rule] + found)
            self.emit('auto_rules', data=self.config['auto_rules'])
        else:
            key = '|'.join((category_choice_process_key(rule.process), rule.category_type, rule.category_id))
            self.validation_retry[key] = time.monotonic() + 300
            self.pipeline.transition(self.rule_game(rule), rule.process, '확인 필요', error='다시 검색한 결과를 직접 확인해 주세요.')
            self.config['auto_pending'] = [*self.config.get('auto_pending', []), *unresolved]
            self.emit('auto_pending', data=self.config['auto_pending'])
            for item in unresolved:
                if item.get('reason') == 'category-choice':
                    self.emit('category_choice_required', **{k: item[k] for k in ('token', 'process', 'game_name', 'candidates')})

    def sanitize_auto_state(self, emit=True):
        rules, pending, removed = cleanup_auto_mappings(
            self.config.get('auto_rules', []),
            self.config.get('auto_pending', []),
            manual_rules=self.config.get('rules', []),
        )
        changed = (
            serialize_rules(rules) != self.config.get('auto_rules', []) or
            pending != self.config.get('auto_pending', [])
        )
        if not changed:
            return False
        self.config['auto_rules'] = serialize_rules(rules)
        self.config['auto_pending'] = pending
        if emit:
            self.emit('auto_rules', data=self.config['auto_rules'])
            self.emit('auto_pending', data=self.config['auto_pending'])
            total = int(removed.get('rules', 0)) + int(removed.get('pending', 0))
            if total:
                self.emit('log', text=f'[자동 감지] 런처/중복 항목 {total}개를 정리했습니다.')
        return True

    def submit(self, name, value=None):
        if name in ('configure', 'stop', 'forget') or (name == 'enable' and not value):
            self.cancel.set()
        self.commands.put((name, value))

    def emit(self, kind, **data):
        self.event.emit({'kind': kind, **data})

    def status(self, text):
        if text != self.last_status:
            self.last_status = text
            self.emit('status', text=text)

    def build_chzzk_open_client(self):
        return ChzzkOpenAPI()

    def client(self):
        if self.api is None:
            self.api = ChzzkAPI(self.config['channel'], self.bridge)
            self.api.cancelled = self.cancel.is_set
            self.api.category_ttl = max(1, int(self.config.get('category_sync_hours', 6))) * 3600
        return self.api

    def drop_client(self):
        if self.api:
            self.api.close()
            self.api = None

    def refresh_processes(self, force=False):
        excluded = {str(p).casefold() for p in self.config.get('excluded_processes', [])}
        cached = self.latest_snapshot
        names = cached[1] if not force and cached and time.monotonic() - cached[0] < self.config.get('interval', 5) else process_names()
        self.processes = [p for p in names if p.casefold() not in excluded]
        self.pipeline.snapshot(self.processes)
        self.emit('detected_games', data=self.processes)
        self.publish_running_games()
        active = {category_choice_process_key(name) for name in self.processes}
        self.last_matching_summary = {key: value for key, value in self.last_matching_summary.items()
                                      if key[1] in active}
        self.session_rules = {key: rule for key, rule in self.session_rules.items()
                              if any(category_choice_process_key(p) in active for p in rule.processes)}
        # Lobby/match transitions belong to the same running game session.
        self.category_choice_dismissed = {
            token for token in self.category_choice_dismissed
            if token.split('|', 1)[0] in active
        }
        self.category_choice_waiting = {
            token for token in self.category_choice_waiting
            if token.split('|', 1)[0] in active
        }
        self.update_league_session()
        return self.processes

    def update_league_session(self):
        running = [p for p in self.processes if p.casefold() in ('leagueclient.exe', 'league of legends.exe')]
        if self.config.get('league_mode', 'legacy') != 'ask':
            return
        if not running and self.league_session_token:
            token = self.league_session_token
            self.league_session_token = None
            self.league_confirmed_key = None
            self.emit('league_session_ended', session=token)
        elif running and not self.league_session_token:
            self.league_session_token = uuid.uuid4().hex
            self.league_confirmed_key = None
            self.emit('league_mode_required', session=self.league_session_token, process=running[0])

    def publish_running_games(self):
        manual = [Rule(**r) for r in self.config.get('rules', [])]
        for process in detectable_running_processes(self.processes, self.mapper.entries):
            choices = self.mapper.entries.get(process.casefold(), [])
            chosen = next((r for r in manual if process.casefold() in {p.casefold() for p in r.processes}), None)
            game = dict(choices[0]) if len(choices) == 1 else {'name': ' / '.join(g.get('name', '') for g in choices)}
            if chosen:
                game = {'name': chosen.game_name or chosen.category_name, 'processes': chosen.processes}
            key = __import__('automation').game_key(game, process)
            state = self.pipeline.states.get(key)
            if state is None or not state.running:
                self.pipeline.transition(game, process, '감지됨')
        for r in manual:
            if any(p.casefold() in {n.casefold() for n in self.processes} for p in r.processes):
                game = {'name': r.game_name or r.category_name, 'processes': r.processes}
                key = __import__('automation').game_key(game, r.process)
                if key not in self.pipeline.states or not self.pipeline.states[key].running:
                    self.pipeline.transition(game, r.process, '감지됨')

    def running_game_processes(self):
        """Return only currently-running executables known as games by Discord.

        The manual rule dialog must not show every Windows process (compiler, shell,
        Python, etc.).  We still keep ``self.processes`` as the complete conservative
        process-name snapshot for rule matching, but the UI receives only the
        intersection with Discord's detectable game executable index.
        """
        self.refresh_processes()
        info = self.mapper.ensure_index()

        games = detectable_running_processes(self.processes, self.mapper.entries)
        return games, info

    def effective_rules(self):
        excluded = {str(p).casefold() for p in self.config.get('excluded_processes', [])}
        manual = [Rule(**r) for r in self.config.get('rules', [])]
        session = list(self.session_rules.values())
        auto = [Rule(**r) for r in self.config.get('auto_rules', [])]
        return [r for r in manual + session + auto if not excluded.intersection(p.casefold() for p in r.processes)]

    def maybe_sync_auto(self, now):
        if not self.config.get('auto_detect', True):
            # Pending items represent *currently running* unresolved games only.
            # Turning automatic detection off therefore clears the transient list.
            if self.config.get('auto_pending'):
                self.config['auto_pending'] = []
                self.emit('auto_pending', data=[])
            return
        if not self.config.get('channel'):
            self.mapper.ensure_index()
            self.publish_running_games()
            return
        signature = tuple(p.casefold() for p in self.processes)
        if signature == getattr(self, '_last_auto_signature', None) and now - self.last_auto_sync < 15:
            return
        self._last_auto_signature = signature
        self.last_auto_sync = now
        info = self.mapper.ensure_index()
        self.publish_running_games()
        if info.get('error'):
            self.emit('log', text='[자동 감지] Discord 목록 갱신 실패: ' + info['error'])
        discover_processes = [p for p in self.processes if not (self.config.get('league_mode', 'legacy') == 'ask'
                              and not self.league_confirmed_key
                              and p.casefold() in ('leagueclient.exe', 'league of legends.exe'))]
        new_rules, unresolved = self.mapper.discover(
            discover_processes,
            self.effective_rules(),
            lambda keyword: self.client().search(keyword, self.chzzk_open),
        )

        # Recheck executable names after slow searches; exited games cannot enter the apply queue.
        active = {p.casefold() for p in process_names()}
        new_rules = [r for r in new_rules if active.intersection(p.casefold() for p in r.processes) and not self.cancel.is_set()]
        changed = False
        if new_rules:
            auto_rules = [Rule(**r) for r in self.config.get('auto_rules', [])]
            existing = {p.casefold() for r in auto_rules for p in r.processes}
            for rule in new_rules:
                category = {'categoryId': rule.category_id, 'categoryValue': rule.category_name, 'categoryType': rule.category_type}
                key = '|'.join((category_choice_process_key(rule.process), rule.category_type, rule.category_id))
                aliases = self.config.get('game_aliases', {}).get(rule.game_name, [])
                origin = next((r for r in self.pipeline.cache.records.values() if r.get('category', {}).get('categoryId') == rule.category_id and r.get('game', {}).get('name') == rule.game_name), None)
                self.pipeline.cache.put('rule:' + key, '|'.join([rule.category_id, rule.category_name, *aliases]), category, {'name': rule.game_name}, now=origin['verified_at'] if origin else None)
                if any(p.casefold() in existing for p in rule.processes):
                    continue
                auto_rules.append(rule)
                existing.update(p.casefold() for p in rule.processes)
                changed = True
            if changed:
                merged_rules, _pending_unused, _removed = cleanup_auto_mappings(
                    serialize_rules(auto_rules), [], manual_rules=self.config.get('rules', [])
                )
                self.config['auto_rules'] = serialize_rules(merged_rules)
                self.emit('auto_rules', data=self.config['auto_rules'])
                self.emit('log', text=f'[자동 감지] {len(new_rules)}개 게임 연결을 추가했습니다.')

        # auto_pending is intentionally ephemeral: it mirrors unresolved games from
        # *this* process scan instead of accumulating stale entries across scans/reboots.
        normal_pending = []
        for item in unresolved:
            if not isinstance(item, dict):
                continue
            if item.get('reason') == 'category-choice':
                token = str(item.get('token') or '').strip()
                candidates = [c for c in item.get('candidates', []) if isinstance(c, dict)]
                if token and len(candidates) >= 2 and token not in self.category_choice_dismissed:
                    if token not in self.category_choice_waiting:
                        self.category_choice_waiting.add(token)
                        self.emit(
                            'category_choice_required',
                            token=token,
                            process=str(item.get('process') or ''),
                            game_name=str(item.get('game_name') or ''),
                            candidates=candidates,
                        )
                        self.emit(
                            'log',
                            text=f"[자동 감지] {item.get('game_name') or item.get('process')}의 치지직 카테고리 후보 {len(candidates)}개가 감지되어 선택을 기다립니다.",
                        )
                normal_pending.append(item)
                continue
            normal_pending.append(item)

        # A saved automatic category does not resolve a shared LoL/TFT executable.
        # Keep the current session's mode prompt until a manual/session rule resolves it.
        if self.config.get('league_mode', 'legacy') == 'ask':
            confirmed = {'league-of-legends'} if self.league_confirmed_key else set()
            for item in self.config.get('auto_pending', []):
                if (isinstance(item, dict) and item.get('reason') == 'multi-game'
                        and str(item.get('process', '')).casefold() in ('leagueclient.exe', 'league of legends.exe')
                        and category_choice_process_key(item['process']) not in confirmed
                        and active.intersection(('leagueclient.exe', 'league of legends.exe'))):
                    normal_pending.append(item)

        # Deduplicate the current scan only. A process that stopped running, was resolved,
        # or disappeared from Discord detection is removed from the pending count here.
        pending = []
        seen = set()
        resolved_processes = {
            p.casefold()
            for raw in self.config.get('auto_rules', [])
            for p in Rule(**raw).processes
        }
        for item in normal_pending:
            process = str(item.get('process') or '').strip()
            reason = str(item.get('reason') or '').strip()
            if not process or (process.casefold() in resolved_processes and reason != 'multi-game'):
                continue
            key = (process.casefold(), reason)
            if key in seen:
                continue
            seen.add(key)
            pending.append(item)

        old_pending = [item for item in self.config.get('auto_pending', []) if isinstance(item, dict)]
        if pending != old_pending:
            self.config['auto_pending'] = pending
            self.emit('auto_pending', data=pending)

    def apply_startup_talk_once(self):
        """Apply ETC/talk exactly once per app process before game detection.

        The attempt flag is set before the request so a temporary failure does not cause
        repeated TALK changes every scan. Restarting the app creates a fresh Worker and
        therefore allows one new startup attempt.
        """
        if self.startup_talk_attempted:
            return
        if self.config.get('only_when_live', False) and not self.client().is_live():
            return
        self.startup_talk_attempted = True
        try:
            changed = self.client().apply(STARTUP_TALK_RULE, self.cancel.is_set)
            if changed:
                self.emit('log', text='[기본 카테고리] 앱 시작 · talk 카테고리를 최초 1회 적용했습니다.')
            else:
                self.emit('log', text='[기본 카테고리] 앱 시작 · 이미 talk 카테고리입니다.')
        except APIError as e:
            self.emit('log', text='[기본 카테고리] talk 최초 적용 실패 · ' + str(e))

    def scan(self):
        self.refresh_processes()
        now = time.monotonic()
        if self.league_session_token and not self.league_confirmed_key:
            for state in list(self.pipeline.states.values()):
                if state.running and any(p.casefold() in ('leagueclient.exe', 'league of legends.exe') for p in state.processes):
                    self.pipeline.transition({'id': state.key, 'name': state.game_name, 'processes': state.processes},
                                             state.process, '확인 필요', error='이번 실행의 게임 모드를 선택해 주세요.')
            self.gate.observe(None, now)
            self.status('LoL / TFT 게임 모드를 먼저 선택해 주세요')
            return
        self.apply_startup_talk_once()
        self.maybe_sync_auto(now)
        # Fresh names defeat results arriving after game exit or replacement.
        self.refresh_processes(force=True)
        rules = self.effective_rules()
        manual = [Rule(**r) for r in self.config.get('rules', [])]
        rule = choose_representative(rules, self.processes, manual, self.config.get('preferred_process', ''))
        if rule is None:
            self.gate.observe(None, now)
            self.status('감지 중 · 대표 게임을 기다립니다' if not rules else '감지 중 · 여러 게임은 대표 게임을 선택해 주세요')
            return
        game = self.rule_game(rule)
        # LoL and TFT share executables. Name-only scans must never infer the mode.
        if (self.config.get('league_mode', 'legacy') == 'ask'
                and any(p.casefold() in ('leagueclient.exe', 'league of legends.exe') for p in rule.processes)
                and self.league_confirmed_key != rule.key):
            self.pipeline.transition(game, rule.process, '확인 필요', error='이번 실행에서 롤 / 롤토체스를 먼저 선택해 주세요.')
            self.gate.observe(None, now)
            self.status('LoL / TFT 게임 모드를 먼저 선택해 주세요')
            return
        if not self.validate_rule(rule) or self.cancel.is_set():
            self.gate.observe(None, time.monotonic())
            self.status('카테고리 검증 대기 · ' + rule.category_name)
            return
        self.refresh_processes(force=True)
        if not any(p.casefold() in {n.casefold() for n in self.processes} for p in rule.processes):
            self.gate.observe(None, time.monotonic())
            return
        stage = '적용 완료' if self.gate.applied == rule.key else '적용 대기'
        state = self.pipeline.transition(game, rule.process, stage, category_id=rule.category_id,
                                         category_name=rule.category_name, confidence_label='검색 결과 ID 검증 완료',
                                         verified_at=datetime.now().isoformat(timespec='seconds'), representative=True)
        for other in self.pipeline.states.values():
            if other is not state and other.representative:
                other.representative = False
                self.emit('pipeline_state', data=asdict(other))
        now = time.monotonic()
        if self.gate.observe(rule, now) and self.pipeline.ready(rule, state):
            try:
                if self.config.get('only_when_live', False) and not self.client().is_live():
                    self.status('방송 시작 대기 · ' + rule.category_name)
                    return
                self.pipeline.transition(game, rule.process, '적용 중')
                changed = self.client().apply(rule, self.cancel.is_set)
                self.gate.success(rule, time.monotonic())
                self.pipeline.transition(game, rule.process, '적용 완료')
                self.status(f'적용됨 · {rule.category_name}')
                self.emit('applied', text=f'{rule.process} → {rule.category_name}', changed=changed, category_name=rule.category_name)
            except APIError as e:
                if e.auth:
                    self.emit('error', operation='check', text='치지직 인증을 다시 확인해 주세요.')
                if e.permanent:
                    self.enabled = False
                    self.emit('enabled', value=False)
                self.gate.failure(time.monotonic(), e.retry_after)
                self.pipeline.transition(game, rule.process, '오류', error='카테고리를 변경하지 못했습니다. 연결을 확인하고 다시 시도해 주세요.')
                self.status('자동 변경 실패 · 연결을 확인해 주세요')
                self.emit('log', text='[카테고리 변경] ' + str(e))
        elif self.gate.applied == rule.key:
            self.status(f'적용됨 · {rule.category_name}')
        elif now < self.gate.next_allowed:
            self.status(f'재요청 대기 · {rule.category_name}')
        else:
            self.status(f'실행 확인 중 · {rule.process} → {rule.category_name}')

    def command(self, name, value):
        if name == 'stop':
            self.enabled = False
            self.stop_event.set()
        elif name == 'configure':
            self.drop_client()
            old_channel = self.config.get('channel')
            self.config = value
            if old_channel != value.get('channel'):
                self.gate = Gate()
            self.cancel.clear()
            self.mapper = DiscordAutoMapper(
                discord_cache_file(),
                int(self.config.get('discord_refresh_hours', 24)) * 3600,
                aggressive_resolve=self.config.get('auto_aggressive', True),
                resolve_shared_executable=self.config.get('auto_resolve_shared', False),
            )
            if self.chzzk_open is not None:
                self.chzzk_open.close()
            self.chzzk_open = self.build_chzzk_open_client()
            self.configure_mapper()
            self.validation_retry.clear()
            self.last_auto_sync = 0.0
            self.category_choice_waiting.clear()
            self.category_choice_dismissed.clear()
            self.sanitize_auto_state(emit=True)
        elif name == 'enable':
            self.enabled = bool(value)
            self.cancel.clear()
            if self.enabled:
                self.cancel.clear()
                self.gate = Gate()
            else:
                self.status('일시정지 · 자동 변경이 꺼져 있습니다')
            self.emit('enabled', value=self.enabled)
        elif name == 'check':
            current = self.client().settings()
            self.emit('checked', text='연결 성공 · ' + str((current.get('category') or {}).get('categoryValue', '카테고리 없음')), category_name=str((current.get('category') or {}).get('categoryValue') or '카테고리 없음'))
        elif name == 'quick_game_mode':
            import unicodedata
            from normalization import normalized_name
            targets = {'League of Legends': ('리그 오브 레전드', 'League of Legends'),
                       'Teamfight Tactics': ('전략적 팀 전투', 'Teamfight Tactics')}
            token = value.get('token')
            game = value.get('game')
            process = value.get('process', '')
            try:
                if game not in targets or process.casefold() not in ('leagueclient.exe', 'league of legends.exe'):
                    raise ValueError('Invalid game selection')
                session = value.get('session')
                if session:
                    self.refresh_processes(force=True)
                    if session != self.league_session_token:
                        raise ValueError('Game session ended')
                exact = {}
                for query in targets[game]:
                    rows = self.mapper._cached_search(query, lambda q: self.client().search(q, self.chzzk_open))
                    for c in rows:
                        candidate_name = c.get('categoryValue', '')
                        # TFT's CHZZK title includes the current set/season subtitle.
                        # Scope this exception to explicit TFT selection; other editions remain distinct.
                        if game == 'Teamfight Tactics':
                            candidate_name = unicodedata.normalize('NFKC', str(candidate_name)).partition(':')[0]
                        if (c.get('categoryId') and c.get('categoryType', 'GAME') == 'GAME'
                                and normalized_name(candidate_name) in {normalized_name(n) for n in targets[game]}):
                            exact[c['categoryId']] = c
                    if exact:
                        break
                if len(exact) != 1 or self.cancel.is_set():
                    raise ValueError('Category could not be uniquely verified')
                if session:
                    self.refresh_processes(force=True)
                    if session != self.league_session_token:
                        raise ValueError('Game session ended')
                c = next(iter(exact.values()))
                rule = Rule(process, c['categoryId'], c['categoryValue'], 'GAME', game,
                            '사용자 카테고리 선택 · 검색 결과 검증',
                            tuple(p for p in ('LeagueClient.exe', 'League of Legends.exe') if p.casefold() != process.casefold()))
                self.emit('quick_rule_ready', token=token, session=session, data=asdict(rule))
            except Exception as exc:
                self.emit('log', text='[카테고리 검색] 빠른 게임 선택 실패: ' + str(exc))
                self.emit('quick_rule_error', token=token, text='카테고리를 확인하지 못했습니다. 다시 누르거나 다른 카테고리를 선택해 주세요.')
        elif name == 'confirm_league_mode':
            self.refresh_processes(force=True)
            if value.get('session') != self.league_session_token or not self.league_session_token:
                return
            rule = Rule(**value['rule'])
            if not any(p.casefold() in ('leagueclient.exe', 'league of legends.exe') for p in rule.processes):
                return
            # Only a rule actually persisted by the UI can unblock this session.
            if not any(r.key == rule.key and set(r.processes) == set(rule.processes) for r in self.effective_rules()):
                return
            self.league_confirmed_key = rule.key
            self.config['auto_pending'] = [p for p in self.config.get('auto_pending', [])
                                           if str(p.get('process', '')).casefold() not in ('leagueclient.exe', 'league of legends.exe')]
            self.emit('auto_pending', data=self.config['auto_pending'])
            self.gate = Gate(stable=self.gate.stable, cooldown=self.gate.cooldown)
        elif name == 'search':
            data = self.mapper._cached_search(value['keyword'], lambda query: self.client().search(query, self.chzzk_open))
            self.emit('search', request=value['request'], data=data,
                      official=bool(self.chzzk_open and self.chzzk_open.configured))
        elif name == 'steam_test':
            try:
                key = str((value or {}).get('key') or '').strip()
                if key:
                    if not valid_key(key):
                        raise SteamLookupError('32자리 Steam Web API 키를 입력해 주세요.')
                    if steam_environment_key() not in ('', key):
                        raise SteamLookupError('Steam 환경변수 키가 우선합니다. 입력란을 비워 연결을 확인하거나 환경변수 키를 변경해 주세요.')
                    probe = SteamResolver(key, discord_cache_file().parent / 'steam_titles.json',
                                          cancelled=self.cancel.is_set)
                    try:
                        probe.test_connection()
                    finally:
                        probe.close()
                    save_steam_api_key(key)
                self.configure_mapper()
                if key:
                    pass  # The candidate was checked before replacing the saved key.
                elif self.steam.configured:
                    self.steam.test_connection()
                else:
                    default_key = get_steam_api_key()
                    if not valid_key(default_key):
                        raise SteamLookupError('Steam 연결 정보를 확인할 수 없습니다. 최신 공식 설치본을 설치해 주세요.')
                    probe = SteamResolver(default_key, discord_cache_file().parent / 'steam_titles.json',
                                          cancelled=self.cancel.is_set)
                    try:
                        probe.test_connection()
                    finally:
                        probe.close()
                suffix = '한국어 이름 조회 사용' if self.config.get('steam_lookup_enabled', True) else '자동 조회는 꺼져 있습니다'
                self.emit('steam_status', text='Steam API 연결 확인 완료 · ' + suffix, ok=True)
                self.last_auto_sync = 0
            except (SteamLookupError, OSError, RuntimeError) as error:
                self.emit('steam_status', text=str(error), ok=False)
        elif name == 'steam_forget':
            save_steam_api_key('')
            self.configure_mapper()
            self.emit('steam_status', text='개인 키를 삭제했습니다. 기본 연결 정보가 있으면 자동으로 사용합니다.')
        elif name == 'chzzk_open_test':
            if self.chzzk_open is None or not self.chzzk_open.configured:
                raise ChzzkOpenAPIError('공식 API 인증 정보가 포함되지 않은 빌드입니다. 최신 공식 설치본을 설치해 주세요.')
            ok = self.chzzk_open.test()
            self.emit('chzzk_open_tested', ok=bool(ok))
        elif name == 'processes':
            games, info = self.running_game_processes()
            if info.get('error'):
                self.emit('log', text='[게임 목록] Discord 목록 갱신 실패: ' + str(info['error']))
            self.emit(
                'processes',
                data=games,
                source='discord-detectable',
                game_details=game_process_details(games, self.mapper.entries),
                scanned_count=len(self.processes),
                index_count=len(self.mapper.entries),
                warning=str(info.get('error') or ''),
            )
        elif name == 'research_game':
            self.research_game(str(value or ''))
        elif name == 'sync_auto':
            self.sync_category_data(force=True)
            self.mapper.clear_search_cache()
            self.refresh_processes()
            self.last_auto_sync = 0.0
            self.maybe_sync_auto(time.monotonic())
        elif name == 'choose_category_candidate':
            data = value if isinstance(value, dict) else {}
            token = str(data.get('token') or '').strip()
            process = str(data.get('process') or '').strip()
            game_name = str(data.get('game_name') or '').strip()
            category = data.get('category') if isinstance(data.get('category'), dict) else {}
            save_rule = bool(data.get('save_rule', True))
            if is_ignored_process(process):
                self.category_choice_waiting.discard(token)
                return
            if token and process and category.get('categoryId') and category.get('categoryValue'):
                rule = Rule(
                    process,
                    str(category.get('categoryId')),
                    str(category.get('categoryValue')),
                    str(category.get('categoryType') or 'GAME'),
                    game_name or process.rsplit('.', 1)[0],
                    str(category.get('matchSource') or '사용자 카테고리 선택'),
                )
                rule = Rule(rule.process, rule.category_id, rule.category_name,
                            rule.category_type, rule.game_name, rule.match_source,
                            tuple(p for p in league_rule_processes(rule)
                                  if p.casefold() != rule.process.casefold()))
                if save_rule:
                    auto_rules = [Rule(**r) for r in self.config.get('auto_rules', [])]
                    auto_rules = [r for r in auto_rules if process.casefold() not in {p.casefold() for p in r.processes}]
                    auto_rules.append(rule)
                    self.config['auto_rules'] = serialize_rules(auto_rules)
                    self.emit('auto_rules', data=self.config['auto_rules'])
                    mode = '자동 규칙 저장'
                else:
                    self.session_rules[process.casefold()] = rule
                    mode = '이번 실행에서만 적용'
                self.category_choice_waiting.discard(token)
                self.category_choice_dismissed.discard(token)
                self.last_auto_sync = time.monotonic()
                self.gate = Gate()
                self.emit('log', text=f'[자동 감지] 카테고리 선택 · {process} → {rule.category_name} · {mode}')
        elif name == 'dismiss_category_choice':
            token = str((value or {}).get('token') if isinstance(value, dict) else value or '').strip()
            if token:
                self.category_choice_waiting.discard(token)
                self.category_choice_dismissed.add(token)
                self.emit('log', text='[자동 감지] 카테고리 후보 선택을 현재 게임 실행 동안 건너뜁니다.')
        elif name == 'forget':
            self.enabled = False
            self.drop_client()
            self.emit('enabled', value=False)
            self.status('로그인 정보 삭제됨')

    def watch_process_changes(self):
        previous = None
        while not self.stop_event.is_set():
            try:
                names = tuple(process_names())
                self.latest_snapshot = (time.monotonic(), names)
                if names != previous:
                    previous = names
                    excluded = {p.casefold() for p in self.config.get('excluded_processes', [])}
                    active = [p for p in names if p.casefold() not in excluded]
                    self.emit('detected_games', data=active, game_details=game_process_details(active, self.mapper.entries))
            except OSError:
                self.emit('error', operation='detection', text='실행 중인 게임을 확인할 수 없습니다. 감지를 다시 시작해 주세요.')
            self.stop_event.wait(self.config.get('interval', 5))

    def run(self):
        self.snapshot_thread = threading.Thread(target=self.watch_process_changes, name='ChzzkProcessWatcher', daemon=True)
        self.snapshot_thread.start()
        next_scan = time.monotonic()
        try:
            while not self.stop_event.is_set():
                timeout = max(0, next_scan - time.monotonic())
                try:
                    name, value = self.commands.get(timeout=timeout)
                    try:
                        self.command(name, value)
                    except Exception as e:
                        detail = str(e) if isinstance(e, (APIError, ChzzkOpenAPIError, ValueError, RuntimeError)) else type(e).__name__
                        label = {'check': '치지직 연결', 'search': '카테고리 검색', 'chzzk_open_test': '공식 API 연결'}.get(name, name)
                        self.emit('log', text=f'[{label}] {detail}')
                        message = {'check': '치지직 계정을 확인할 수 없습니다. 스튜디오 로그인 후 다시 연결해 주세요.',
                                   'search': '게임 카테고리를 검색하지 못했습니다. 다시 검색하거나 직접 선택해 주세요.',
                                   'chzzk_open_test': '공식 API 연결을 확인하지 못했습니다. 잠시 후 다시 확인해 주세요.'}.get(name, '작업을 완료하지 못했습니다. 연결을 확인하고 다시 시도해 주세요.')
                        self.emit('error', operation=name, text=message)
                except queue.Empty:
                    pass
                if time.monotonic() >= next_scan:
                    try:
                        self.sync_category_data()
                        if self.enabled:
                            self.scan()
                        elif self.config.get('auto_detect', True):
                            self.refresh_processes()
                            self.maybe_sync_auto(time.monotonic())
                    except Exception:
                        self.enabled = False
                        self.emit('enabled', value=False)
                        self.status('감지를 중단했습니다. 계정 설정과 게임 규칙을 확인해 주세요.')
                    next_scan = time.monotonic() + self.config.get('interval', 5)
        finally:
            self.stop_event.set()
            if self.snapshot_thread:
                self.snapshot_thread.join(timeout=3)
            self.drop_client()
            if self.chzzk_open is not None:
                self.chzzk_open.close()
            if self.steam is not None:
                self.steam.close()
