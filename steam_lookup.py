"""Bounded per-game Steam identity checks and localized-title cache."""
import copy
from collections import deque
import hashlib
import json
from pathlib import Path
import re
import time

import requests
from normalization import normalized_name
from network_policy import retry_seconds

STORE_SEARCH = 'https://store.steampowered.com/api/storesearch/'
STORE_DETAILS = 'https://store.steampowered.com/api/appdetails'
APP_LIST = 'https://api.steampowered.com/IStoreService/GetAppList/v1/'
TTL = 7 * 86400
OFFLINE_TTL = 30 * 86400


class SteamLookupError(RuntimeError):
    def __init__(self, message, retry_after=60):
        super().__init__(message)
        self.retry_after = max(60, min(3600, float(retry_after)))


def valid_key(value):
    return bool(re.fullmatch(r'[0-9a-fA-F]{32}', str(value or '').strip()))


class SteamResolver:
    def __init__(self, key, cache_file, session=None, cancelled=None):
        self.key = str(key or '').strip()
        self.path = Path(cache_file)
        self.session = session or requests.Session()
        self.cancelled = cancelled or (lambda: False)
        self.records = {}
        self.retry_at = 0
        self.last_error = ''
        self.requests_at = deque(maxlen=60)
        try:
            payload = json.loads(self.path.read_text(encoding='utf-8'))
            if payload.get('version') == 1 and isinstance(payload.get('games'), dict):
                for name, item in list(payload['games'].items())[-512:]:
                    if self._valid_record(item):
                        self.records[name] = item
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    @property
    def configured(self):
        return valid_key(self.key)

    @staticmethod
    def _valid_record(item):
        return (isinstance(item, dict) and type(item.get('appid')) is int
                and 0 < item['appid'] < 2**32 and isinstance(item.get('name'), str)
                and isinstance(item.get('localized_name'), str)
                and 0 < len(item['name']) <= 300 and 0 < len(item['localized_name']) <= 300
                and isinstance(item.get('verified_at'), (int, float)))

    def close(self):
        self.session.close()

    def _get(self, url, params, deadline):
        if self.cancelled():
            raise SteamLookupError('Steam 조회가 취소되었습니다.')
        now = time.monotonic()
        if deadline <= now:
            raise SteamLookupError('Steam 조회 시간이 초과되었습니다.')
        while self.requests_at and now - self.requests_at[0] >= 60:
            self.requests_at.popleft()
        if len(self.requests_at) >= 60:
            raise SteamLookupError('Steam 조회가 많아 잠시 기다립니다.')
        self.requests_at.append(now)
        try:
            response = self.session.get(url, params=params,
                timeout=(min(5, deadline-now), min(10, deadline-now)))
            try:
                if self.cancelled():
                    raise SteamLookupError('Steam 조회가 취소되었습니다.')
                if response.status_code in (401, 403):
                    message = ('Steam API 인증을 확인해 주세요.' if url == APP_LIST
                               else 'Steam 상점 조회가 제한되어 기존 매칭을 사용합니다.')
                    raise SteamLookupError(message, 600)
                if response.status_code == 429:
                    raise SteamLookupError('Steam 요청 제한으로 잠시 기다립니다.',
                                           retry_seconds(response.headers.get('Retry-After')))
                if response.status_code != 200:
                    raise SteamLookupError(f'Steam 조회 실패 (HTTP {response.status_code})')
                result = response.json()
                if not isinstance(result, dict):
                    raise SteamLookupError('Steam 응답 형식을 확인할 수 없습니다.')
                return result
            finally:
                response.close()
        except (requests.RequestException, ValueError):
            # Requests errors can include the URL and its key parameter. Never retain them.
            raise SteamLookupError('Steam에 연결하지 못했습니다. 기존 매칭을 사용합니다.') from None

    def _official(self, appid, deadline):
        options = {'last_appid': appid - 1, 'max_results': 1, 'include_games': True,
                   'include_dlc': False, 'include_software': False, 'include_videos': False,
                   'include_hardware': False}
        payload = self._get(APP_LIST, {'key': self.key, 'input_json': json.dumps(options)}, deadline)
        response = payload.get('response')
        if not isinstance(response, dict) or not isinstance(response.get('apps'), list):
            raise SteamLookupError('Steam 공식 API의 응답 형식을 확인할 수 없습니다.')
        rows = response['apps']
        return next((row for row in rows if isinstance(row, dict)
                     and row.get('appid') == appid and row.get('name')), None)

    def test_connection(self):
        if not self.configured:
            raise SteamLookupError('32자리 Steam Web API 키를 입력해 주세요.')
        self.retry_at = 0
        try:
            self._official(1, time.monotonic() + 15)
        except SteamLookupError as error:
            self.last_error = str(error)
            self.retry_at = time.time() + error.retry_after
            raise
        # App ID 1 need not exist. A successful response containing a list proves access.
        self.last_error = ''
        return True

    def resolve(self, game, process):
        if not self.configured or self.cancelled():
            return None
        names = [str(game.get('name') or '').strip(), *game.get('aliases', [])]
        targets = {normalized_name(n) for n in names if normalized_name(n)}
        fingerprint = hashlib.sha256(json.dumps([game.get('id'), sorted(targets), process.casefold()],
                                                ensure_ascii=False).encode()).hexdigest()
        previous = self.records.get(fingerprint)
        now = time.time()
        if self._valid_record(previous) and 0 <= now - previous['verified_at'] <= TTL:
            self.last_error = ''
            return copy.deepcopy(previous)
        if (previous and previous.get('retry_at', 0) > now) or now < self.retry_at:
            return self._offline(previous, now)
        self.last_error = ''
        deadline = time.monotonic() + 20
        try:
            payload = self._get(STORE_SEARCH, {'term': names[0], 'l': 'english', 'cc': 'KR'}, deadline)
            if not isinstance(payload.get('items'), list):
                raise SteamLookupError('Steam 검색 응답 형식을 확인할 수 없습니다.')
            matches = {row['id'] for row in payload.get('items', [])[:30]
                       if isinstance(row, dict) and row.get('type') == 'app'
                       and type(row.get('id')) is int and 0 < row['id'] < 2**32
                       and normalized_name(row.get('name')) in targets}
            record = None
            if len(matches) == 1:
                appid = matches.pop()
                official = self._official(appid, deadline)
                if official and normalized_name(official['name']) in targets:
                    payload = self._get(STORE_DETAILS, {'appids': appid, 'l': 'koreana', 'cc': 'KR'}, deadline)
                    app = payload.get(str(appid), {})
                    if not isinstance(app, dict) or not isinstance(app.get('data', {}), dict):
                        raise SteamLookupError('Steam 한국어 이름을 확인할 수 없습니다.')
                    data = app.get('data', {})
                    if (app.get('success') is True and data.get('type') == 'game'
                            and data.get('steam_appid') == appid and data.get('name')):
                        record = {'appid': appid, 'name': str(official['name']),
                                  'localized_name': str(data['name']), 'verified_at': now}
                        if not self._valid_record(record):
                            record = None
            if self.cancelled():
                return None
            self.records[fingerprint] = record or {'retry_at': now + 600}
            self._save()
            return copy.deepcopy(record)
        except SteamLookupError as error:
            if self.cancelled():
                return None
            self.last_error = str(error)
            self.retry_at = now + error.retry_after
            return self._offline(previous, now)

    def _offline(self, previous, now):
        if self._valid_record(previous) and 0 <= now - previous['verified_at'] <= OFFLINE_TTL:
            return dict(previous, offline=True)
        return None

    def _save(self):
        while len(self.records) > 512:
            self.records.pop(next(iter(self.records)))
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix('.tmp')
            temp.write_text(json.dumps({'version': 1, 'games': self.records}, ensure_ascii=False), encoding='utf-8')
            temp.replace(self.path)
        except OSError:
            pass  # A read-only profile must not prevent using this verified result.
