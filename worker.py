import queue
import threading
import time
from PySide6.QtCore import QThread, Signal
from api import ChzzkAPI, APIError
from core import Rule, Gate, select_rule
from autodetect import (DiscordAutoMapper, serialize_rules, cleanup_auto_mappings,
                        is_ignored_process, detectable_running_processes, game_process_details,
                        category_choice_process_key, league_rule_processes)
from process_detect import process_names as snapshot_process_names
from storage import discord_cache_file
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
        self.mapper = DiscordAutoMapper(
            discord_cache_file(),
            int(self.config.get('discord_refresh_hours', 24)) * 3600,
            aggressive_resolve=self.config.get('auto_aggressive', True),
            resolve_shared_executable=self.config.get('auto_resolve_shared', False),
        )
        self.chzzk_open = self.build_chzzk_open_client()
        self.last_auto_sync = 0.0
        self.last_cookie_refresh = 0.0
        self.startup_talk_attempted = False
        self.session_rules = {}
        self.category_choice_waiting = set()
        self.category_choice_dismissed = set()
        self.sanitize_auto_state(emit=False)

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
        if not self.config.get('chzzk_open_enabled', True):
            return None
        return ChzzkOpenAPI()

    def client(self):
        if self.api is None:
            self.api = ChzzkAPI(self.config['channel'], self.bridge)
        return self.api

    def drop_client(self):
        if self.api:
            self.api.close()
            self.api = None

    def refresh_processes(self):
        self.processes = process_names()
        active = {category_choice_process_key(name) for name in self.processes}
        # Lobby/match transitions belong to the same running game session.
        self.category_choice_dismissed = {
            token for token in self.category_choice_dismissed
            if token.split('|', 1)[0] in active
        }
        self.category_choice_waiting = {
            token for token in self.category_choice_waiting
            if token.split('|', 1)[0] in active
        }
        return self.processes

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
        manual = [Rule(**r) for r in self.config.get('rules', [])]
        session = list(self.session_rules.values())
        auto = [Rule(**r) for r in self.config.get('auto_rules', [])]
        return manual + session + auto

    def maybe_sync_auto(self, now):
        if not self.config.get('auto_detect', True):
            # Pending items represent *currently running* unresolved games only.
            # Turning automatic detection off therefore clears the transient list.
            if self.config.get('auto_pending'):
                self.config['auto_pending'] = []
                self.emit('auto_pending', data=[])
            return
        if not self.config.get('channel'):
            return
        if now - self.last_auto_sync < 15:
            return
        self.last_auto_sync = now
        info = self.mapper.ensure_index()
        if info.get('error'):
            self.emit('log', text='[자동 감지] Discord 목록 갱신 실패: ' + info['error'])
        new_rules, unresolved = self.mapper.discover(
            self.processes,
            self.effective_rules(),
            lambda keyword: self.client().search(keyword, self.chzzk_open),
        )

        changed = False
        if new_rules:
            auto_rules = [Rule(**r) for r in self.config.get('auto_rules', [])]
            existing = {p.casefold() for r in auto_rules for p in r.processes}
            for rule in new_rules:
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
                continue
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
            if not process or process.casefold() in resolved_processes:
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
        self.apply_startup_talk_once()
        self.refresh_processes()
        now = time.monotonic()
        self.maybe_sync_auto(now)
        rules = self.effective_rules()
        rule = select_rule(rules, self.processes)
        now = time.monotonic()

        if rule is None:
            self.gate.observe(None, now)
            self.status('감지 중 · 등록된 게임 실행을 기다립니다')
            return

        if self.gate.observe(rule, now):
            try:
                changed = self.client().apply(rule, self.cancel.is_set)
                self.gate.success(rule, time.monotonic())
                self.status(f'적용됨 · {rule.category_name}')
                self.emit('applied', text=f'{rule.process} → {rule.category_name}', changed=changed)
            except APIError as e:
                if e.permanent:
                    self.enabled = False
                    self.emit('enabled', value=False)
                self.gate.failure(time.monotonic(), e.retry_after)
                message = '[자동 변경] ' + str(e)
                self.status(message)
                self.emit('log', text=message)
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
            self.config = value
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
            self.last_auto_sync = 0.0
            self.session_rules = {}
            self.category_choice_waiting.clear()
            self.category_choice_dismissed.clear()
            self.sanitize_auto_state(emit=True)
        elif name == 'enable':
            self.enabled = bool(value)
            if self.enabled:
                self.cancel.clear()
                self.gate = Gate()
            else:
                self.status('일시정지 · 자동 변경이 꺼져 있습니다')
            self.emit('enabled', value=self.enabled)
        elif name == 'check':
            current = self.client().settings()
            self.emit('checked', text='연결 성공 · ' + str((current.get('category') or {}).get('categoryValue', '카테고리 없음')))
        elif name == 'search':
            data = self.client().search(value['keyword'], self.chzzk_open)
            self.emit('search', request=value['request'], data=data,
                      official=bool(self.chzzk_open and self.chzzk_open.configured))
        elif name == 'chzzk_open_test':
            if self.chzzk_open is None or not self.chzzk_open.configured:
                raise ChzzkOpenAPIError('CHZZK 공식 Open API 보조 검색을 켜 주세요.')
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
        elif name == 'sync_auto':
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

    def run(self):
        next_scan = time.monotonic()
        try:
            while not self.stop_event.is_set():
                timeout = max(0, next_scan - time.monotonic()) if self.enabled else None
                try:
                    name, value = self.commands.get(timeout=timeout)
                    try:
                        self.command(name, value)
                    except Exception as e:
                        message = str(e) if isinstance(e, (APIError, ChzzkOpenAPIError, ValueError, RuntimeError)) else '작업 실패. 계정 설정과 네트워크를 확인해 주세요.'
                        label = {'check': '연결 확인', 'search': '카테고리 검색', 'chzzk_open_test': 'CHZZK 공식 API 연결 확인'}.get(name, name)
                        message = f'[{label}] {message}'
                        self.emit('error', operation=name, text=message)
                except queue.Empty:
                    pass
                if self.enabled and time.monotonic() >= next_scan:
                    try:
                        self.scan()
                    except Exception:
                        self.enabled = False
                        self.emit('enabled', value=False)
                        self.status('감지를 중단했습니다. 계정 설정과 게임 규칙을 확인해 주세요.')
                    next_scan = time.monotonic() + self.config.get('interval', 5)
        finally:
            self.drop_client()
            if self.chzzk_open is not None:
                self.chzzk_open.close()
