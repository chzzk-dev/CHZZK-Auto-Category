from dataclasses import dataclass
import ntpath
import re


def channel_id(value):
    value = value.strip().rstrip('/').split('/')[-1].split('?')[0]
    if not re.fullmatch(r'[0-9a-fA-F]{32}', value):
        raise ValueError('치지직 채널 주소 또는 32자리 채널 ID를 입력해 주세요.')
    return value.lower()


@dataclass(frozen=True)
class Rule:
    process: str
    category_id: str
    category_name: str
    category_type: str = 'GAME'
    game_name: str = ''
    match_source: str = ''
    process_aliases: tuple = ()

    def __post_init__(self):
        primary = ntpath.basename(str(self.process or '')).strip()
        if not primary or not self.category_id.strip():
            raise ValueError('실행 파일과 카테고리가 필요합니다.')
        if self.category_type not in ('GAME', 'ETC', 'SPORTS'):
            raise ValueError('지원하지 않는 카테고리 종류입니다.')

        aliases = []
        seen = {primary.casefold()}
        for value in self.process_aliases or ():
            name = ntpath.basename(str(value or '')).strip()
            if not name or name.casefold() in seen:
                continue
            seen.add(name.casefold())
            aliases.append(name)
        object.__setattr__(self, 'process', primary)
        object.__setattr__(self, 'process_aliases', tuple(aliases))

    @property
    def key(self):
        return (self.category_type, self.category_id)

    @property
    def processes(self):
        return (self.process, *self.process_aliases)


def select_rule(rules, processes):
    names = {ntpath.basename(p).casefold() for p in processes if p}
    return next((r for r in rules if any(ntpath.basename(p).casefold() in names for p in r.processes)), None)


class Gate:
    """Stable detection, successful-application deduplication, global cooldown."""
    def __init__(self, stable=10, cooldown=30):
        self.stable = stable
        self.cooldown = cooldown
        self.candidate = None
        self.since = 0.0
        self.applied = None
        self.next_allowed = 0.0
        self.failures = 0

    def observe(self, rule, now):
        key = rule.key if rule else None
        if key != self.candidate:
            self.candidate, self.since = key, now
        if key is None:
            self.applied = None  # A new game session must check the server again.
            return False
        return key != self.applied and now - self.since >= self.stable and now >= self.next_allowed

    def success(self, rule, now):
        self.applied = rule.key
        self.failures = 0
        self.next_allowed = now + self.cooldown

    def failure(self, now, retry_after=0):
        self.failures += 1
        self.next_allowed = now + max(retry_after, min(300, 60 * 2 ** min(self.failures - 1, 3)))
