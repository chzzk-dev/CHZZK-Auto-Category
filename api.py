import copy
import re
import time
from difflib import SequenceMatcher

import requests

from core import channel_id
from bridge import BridgeError

BASE = 'https://api.chzzk.naver.com'
PUBLIC_CATEGORIES_URL = 'https://chzzk.dico.page/api/categories'
CATEGORY_CATALOG_TTL = 30 * 60
UNOFFICIAL_CATEGORIES_PATH = '/service/v1/categories/live'
SETTINGS_PATH = '/manage/v1/channels/{channel}/live-setting/normal'
FIELDS = ('defaultLiveTitle', 'defaultThumbnailImageUrl', 'dropsCampaignNo',
          'paidPromotion', 'adult', 'krOnlyViewing', 'tags', 'clipActive',
          'replayPublishType', 'watchPartyNo', 'timeMachineActive', 'paidProductId',
          'cvExposure', 'streamerShopCatalogTagActive', 'channelDonationBoardMessage',
          'aiCaptionActive', 'broadcastLanguage')
REQUIRED = ('defaultLiveTitle', 'paidPromotion', 'adult', 'krOnlyViewing',
            'tags', 'clipActive', 'replayPublishType')


class APIError(Exception):
    def __init__(self, message, auth=False, retry_after=0, permanent=False):
        super().__init__(message)
        self.auth, self.retry_after = auth, retry_after
        self.permanent = permanent or auth


def category_key(settings):
    c = settings.get('category') or {}
    return (c.get('categoryType'), c.get('categoryId') or c.get('liveCategory'))


def normalize_text(value):
    return re.sub(r'[^0-9a-z\u3131-\u318e\uac00-\ud7a3]+', '', str(value or '').casefold())


def tokenize(value):
    return [v for v in re.findall(r'[a-z0-9]+|[\u3131-\u318e\uac00-\ud7a3]+',
                                  str(value or '').casefold()) if len(v) > 1]


def contains_hangul(value):
    return bool(re.search(r'[\u3131-\u318e\uac00-\ud7a3]', str(value or '')))


def to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_payload(settings, rule):
    missing = [key for key in REQUIRED if key not in settings]
    if missing:
        raise APIError('방송 설정 필수 항목이 없습니다: ' + ', '.join(missing), permanent=True)
    payload = {key: copy.deepcopy(settings[key]) for key in FIELDS if key in settings}
    party = settings.get('watchParty')
    if isinstance(party, dict):
        if party.get('category'):
            raise APIError('같이보기에서 카테고리를 지정하고 있어 자동 변경을 중단했습니다.', permanent=True)
        if 'watchPartyNo' in party:
            payload['watchPartyNo'] = party['watchPartyNo']
        board = party.get('donationBoardInfo')
        if isinstance(board, dict) and 'channelDonationBoardMessage' in board:
            payload['channelDonationBoardMessage'] = board['channelDonationBoardMessage']
    payload.update(categoryType=rule.category_type, liveCategory=rule.category_id)
    return payload


class ChzzkAPI:
    def __init__(self, channel, bridge):
        self.channel = channel_id(channel)
        self.bridge = bridge
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'ko-KR,ko;q=0.9',
            'Origin': 'https://chzzk.naver.com',
            'Referer': 'https://chzzk.naver.com/',
            'Front-Client-Platform-Type': 'PC',
            'Front-Client-Product-Type': 'web',
        })
        self._category_catalog = []
        self._category_catalog_at = 0.0
        self._category_catalog_source = ''

    def close(self):
        self.session.close()

    def bridge_request(self, action, payload, context):
        if self.bridge is None:
            raise APIError('Chrome 확장프로그램 브리지가 준비되지 않았습니다.', auth=True)
        try:
            response = self.bridge.request(action, payload, timeout=20)
        except BridgeError as e:
            raise APIError(str(e), auth=True) from None

        if not isinstance(response, dict):
            raise APIError(f'Chrome 확장프로그램 응답 형식이 올바르지 않습니다. {context}')

        status = to_int(response.get('status'), default=-1)
        body = response.get('body')

        if status in (401, 403):
            raise APIError(
                f'HTTP {status} {context}. Chrome에서 치지직 스튜디오 로그인을 확인해 주세요.',
                auth=True,
            )
        if status == 429:
            raise APIError(f'HTTP 429 {context}. 요청 제한으로 잠시 대기합니다.', retry_after=60)
        if not 200 <= status < 300:
            hint = ' 채널 ID와 치지직 스튜디오 상태를 확인해 주세요.' if status == 404 else ''
            raise APIError(f'HTTP {status} {context}.{hint}', permanent=400 <= status < 500)

        if not isinstance(body, dict) or str(body.get('code')) != '200':
            code = str(body.get('code', 'unknown')) if isinstance(body, dict) else 'unknown'
            code = code if re.fullmatch(r'[0-9]{1,8}', code) else 'unknown'
            raise APIError(
                f'치지직 응답 코드 {code} {context}.',
                auth=code in ('401', '403'),
                permanent=code.isdigit() and 400 <= int(code) < 500 and code != '429',
            )
        return body.get('content')

    def settings(self):
        value = self.bridge_request(
            'settings',
            {'channel': self.channel},
            '[GET /manage/v1/channels/{channelId}/live-setting/normal]',
        )
        if not isinstance(value, dict):
            raise APIError('방송 설정을 읽지 못했습니다. 채널 관리 권한을 확인해 주세요.')
        return value

    @staticmethod
    def _normalize_category_rows(rows, source):
        categories = []
        seen = set()
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            category_id = str(row.get('categoryId') or '').strip()
            category_type = str(row.get('categoryType') or '').strip()
            category_value = str(row.get('categoryValue') or '').strip()
            if not category_id or not category_type or not category_value:
                continue
            if category_type != 'GAME':
                continue
            key = (category_type, category_id)
            if key in seen:
                continue
            seen.add(key)
            categories.append({
                'categoryId': category_id,
                'categoryType': category_type,
                'categoryValue': category_value,
                'posterImageUrl': row.get('posterImageUrl'),
                'openLiveCount': to_int(row.get('openLiveCount') or 0, default=0),
                '_catalogSource': source,
            })
        return categories

    def _load_unofficial_chzzk_catalog(self):
        """Crawl CHZZK's public web category feed and follow page.next as-is."""
        rows = []
        params = {'size': 50}
        seen_cursors = set()

        for _page in range(120):
            try:
                response = self.session.get(BASE + UNOFFICIAL_CATEGORIES_PATH,
                                            params=params, timeout=(5, 10))
                response.raise_for_status()
                body = response.json()
            except requests.RequestException as e:
                raise APIError('CHZZK 비공식 카테고리 API에 연결할 수 없습니다.') from e
            except ValueError as e:
                raise APIError('CHZZK 비공식 카테고리 API 응답이 JSON이 아닙니다.') from e

            if not isinstance(body, dict) or str(body.get('code')) != '200':
                raise APIError('CHZZK 비공식 카테고리 API 응답 코드가 올바르지 않습니다.')
            content = body.get('content')
            if not isinstance(content, dict):
                break
            data = content.get('data')
            if isinstance(data, list):
                rows.extend(data)

            page = content.get('page')
            next_value = page.get('next') if isinstance(page, dict) else None
            if not isinstance(next_value, dict) or not next_value:
                break
            cursor = tuple(sorted((str(k), str(v)) for k, v in next_value.items() if v is not None))
            if not cursor or cursor in seen_cursors:
                break
            seen_cursors.add(cursor)
            params = {'size': 50}
            params.update({k: v for k, v in next_value.items() if v is not None})

        categories = self._normalize_category_rows(rows, 'CHZZK 비공식 API')
        if not categories:
            raise APIError('CHZZK 비공식 API에서 게임 카테고리를 찾지 못했습니다.')
        return categories

    def _load_dico_catalog_fallback(self):
        try:
            response = self.session.get(PUBLIC_CATEGORIES_URL, timeout=(5, 10))
            response.raise_for_status()
            body = response.json()
        except requests.RequestException as e:
            raise APIError('카테고리 폴백 API에 연결할 수 없습니다.') from e
        except ValueError as e:
            raise APIError('카테고리 폴백 API 응답이 JSON이 아닙니다.') from e

        content = body.get('content') if isinstance(body, dict) else None
        rows = content.get('data') if isinstance(content, dict) else None
        categories = self._normalize_category_rows(rows, 'Dico 카탈로그 폴백')
        if not categories:
            raise APIError('카테고리 폴백 API에서 게임 카테고리를 찾지 못했습니다.')
        return categories

    def load_category_catalog(self, force=False):
        if (not force and self._category_catalog and
                time.time() - self._category_catalog_at < CATEGORY_CATALOG_TTL):
            return list(self._category_catalog)

        error = None
        try:
            categories = self._load_unofficial_chzzk_catalog()
            source = 'CHZZK 비공식 API'
        except APIError as e:
            error = e
            try:
                categories = self._load_dico_catalog_fallback()
                source = 'Dico 카탈로그 폴백'
            except APIError:
                if self._category_catalog:
                    return list(self._category_catalog)
                raise error

        self._category_catalog = categories
        self._category_catalog_at = time.time()
        self._category_catalog_source = source
        return list(categories)

    def search_catalog(self, keyword, limit=30, extra_score=0):
        query = str(keyword or '').strip()
        if not query:
            return []
        normalized_query = normalize_text(query)
        query_tokens = set(tokenize(query))
        categories = self.load_category_catalog()
        scored = []

        for category in categories:
            value = str(category.get('categoryValue') or '')
            category_id = str(category.get('categoryId') or '')
            value_norm = normalize_text(value)
            id_text = category_id.replace('_', ' ')
            id_norm = normalize_text(id_text)
            id_tokens = set(tokenize(id_text))
            value_tokens = set(tokenize(value))

            score = int(extra_score)
            if value_norm == normalized_query:
                score += 360
            elif id_norm == normalized_query:
                # Discord's canonical English name frequently lines up with CHZZK categoryId.
                score += 345
            elif len(normalized_query) >= 6 and normalized_query in id_norm:
                score += 235
            elif len(normalized_query) >= 6 and id_norm in normalized_query and len(id_norm) >= 5:
                score += 205
            elif len(normalized_query) >= 6 and normalized_query in value_norm:
                score += 220
            elif len(normalized_query) >= 6 and value_norm in normalized_query and len(value_norm) >= 5:
                score += 190
            else:
                ratios = [
                    SequenceMatcher(None, normalized_query, value_norm).ratio() if value_norm else 0,
                    SequenceMatcher(None, normalized_query, id_norm).ratio() if id_norm else 0,
                ]
                ratio = max(ratios)
                token_overlap = max(len(query_tokens & id_tokens), len(query_tokens & value_tokens))
                if ratio < 0.58 and token_overlap == 0:
                    continue
                score += int(ratio * 120) + token_overlap * 35

            if contains_hangul(value):
                score += 25
            score += min(40, to_int(category.get('openLiveCount'), 0))
            item = dict(category)
            item.update({
                '_smartScore': score,
                '_matchSource': category.get('_catalogSource') or 'CHZZK 비공식 API',
                '_matchedKeyword': query,
                '_koreanCandidate': value if contains_hangul(value) else '',
                '_discordName': query,
            })
            scored.append((score, to_int(category.get('openLiveCount'), 0), item))

        scored.sort(key=lambda item: (item[0], item[1], item[2].get('categoryValue', '')), reverse=True)
        return [item for _score, _live, item in scored[:max(1, int(limit))]]

    @staticmethod
    def _merge_results(target, rows, bonus=0, source='', matched_keyword='', korean_name='', discord_name=''):
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            key = (str(row.get('categoryType') or ''), str(row.get('categoryId') or ''))
            if not all(key):
                continue
            item = dict(row)
            item['_smartScore'] = int(item.get('_smartScore') or 0) + int(bonus)
            if source:
                item['_matchSource'] = source
            if matched_keyword:
                item['_matchedKeyword'] = matched_keyword
            if korean_name:
                item['_koreanCandidate'] = korean_name
            elif contains_hangul(item.get('categoryValue')):
                item['_koreanCandidate'] = item.get('categoryValue')
            if discord_name:
                item['_discordName'] = discord_name
            old = target.get(key)
            if old is None or int(item.get('_smartScore') or 0) > int(old.get('_smartScore') or 0):
                target[key] = item

    def _score_official_row(self, row, query, rank):
        value = str(row.get('categoryValue') or '')
        category_id = str(row.get('categoryId') or '').replace('_', ' ')
        q = normalize_text(query)
        v = normalize_text(value)
        cid = normalize_text(category_id)
        score = max(0, 180 - rank * 8)
        if q and cid == q:
            score += 300
        elif q and v == q:
            score += 300
        elif len(q) >= 6 and (q in cid or cid in q):
            score += 170
        elif len(q) >= 6 and (q in v or v in q):
            score += 150
        else:
            ratio = max(
                SequenceMatcher(None, q, cid).ratio() if cid else 0,
                SequenceMatcher(None, q, v).ratio() if v else 0,
            )
            score += int(ratio * 100)
        if contains_hangul(value):
            score += 25
        return score

    def _studio_validate_korean_candidates(self, merged, query, limit=3):
        """Validate top Korean candidates using Studio autocomplete.

        English is never sent to Studio autocomplete; only Korean categoryValue strings are used.
        """
        candidates = sorted(
            merged.values(),
            key=lambda item: int(item.get('_smartScore') or 0),
            reverse=True,
        )
        tried = set()
        checked = 0
        for candidate in candidates:
            korean = str(candidate.get('_koreanCandidate') or candidate.get('categoryValue') or '').strip()
            if not contains_hangul(korean):
                continue
            norm = normalize_text(korean)
            if not norm or norm in tried:
                continue
            tried.add(norm)
            checked += 1
            if checked > limit:
                break
            try:
                content = self.bridge_request(
                    'search_categories',
                    {'channel': self.channel, 'keyword': korean},
                    '[GET /manage/v1/auto-complete/categories]',
                )
            except APIError:
                continue
            rows = content.get('results') if isinstance(content, dict) else None
            if not isinstance(rows, list):
                continue
            valid = [row for row in rows if isinstance(row, dict) and
                     all(row.get(k) for k in ('categoryId', 'categoryType', 'categoryValue'))]
            for rank, row in enumerate(valid[:12]):
                exact = (
                    str(row.get('categoryType')) == str(candidate.get('categoryType')) and
                    str(row.get('categoryId')) == str(candidate.get('categoryId'))
                )
                if exact:
                    key = (str(candidate.get('categoryType') or ''), str(candidate.get('categoryId') or ''))
                    current = merged.get(key)
                    if current is not None:
                        current = dict(current)
                        current['_smartScore'] = int(current.get('_smartScore') or 0) + 420
                        current['_matchSource'] = str(current.get('_matchSource') or 'CHZZK') + ' → Studio 검증'
                        current['_matchedKeyword'] = korean
                        current['_koreanCandidate'] = korean
                        current['_discordName'] = query
                        merged[key] = current
                        continue
                bonus = max(40, 120 - rank * 8)
                self._merge_results(
                    merged,
                    [row],
                    bonus=bonus,
                    source='CHZZK Studio 한국어 검색',
                    matched_keyword=korean,
                    korean_name=korean,
                    discord_name=query,
                )

    def search_smart(self, keyword, official=None, limit=30):
        query = str(keyword or '').strip()
        if not query:
            return []

        merged = {}
        errors = []
        successful_queries = 0

        # 1) Unofficial public CHZZK category catalogue. This is especially useful when
        # Discord gives an English game name because categoryId is often English while
        # categoryValue is the Korean name shown in CHZZK.
        try:
            catalog_rows = self.search_catalog(query, limit=max(30, limit))
            successful_queries += 1
            self._merge_results(merged, catalog_rows, discord_name=query)
        except APIError:
            errors.append('공개 카테고리 목록 연결 실패')
            catalog_rows = []

        # 2) Official Open API category search, when the user configured client auth.
        if official is not None and getattr(official, 'configured', False):
            try:
                official_rows = official.search_categories(query, limit=min(50, max(20, limit)))
                successful_queries += 1
            except Exception:
                errors.append('공식 API 검색 실패')
                official_rows = []
            for rank, row in enumerate(official_rows):
                if str(row.get('categoryType') or '') != 'GAME':
                    continue
                score = self._score_official_row(row, query, rank)
                row = dict(row)
                row['_smartScore'] = score
                self._merge_results(
                    merged,
                    [row],
                    source='CHZZK 공식 Open API',
                    matched_keyword=query,
                    korean_name=str(row.get('categoryValue') or '') if contains_hangul(row.get('categoryValue')) else '',
                    discord_name=query,
                )

        # 3) Final Korean candidate verification with the Studio internal autocomplete.
        # This is where we obey CHZZK Studio's Korean-search behavior: English is never
        # sent to this endpoint.
        if merged:
            self._studio_validate_korean_candidates(merged, query, limit=3)
        elif contains_hangul(query):
            # Manual Korean search can go straight to Studio when catalog lookup failed.
            try:
                content = self.bridge_request(
                    'search_categories',
                    {'channel': self.channel, 'keyword': query},
                    '[GET /manage/v1/auto-complete/categories]',
                )
                successful_queries += 1
            except APIError:
                errors.append('Chrome 확장/Studio 검색 연결 실패')
                content = None
            rows = content.get('results') if isinstance(content, dict) else None
            valid = [row for row in rows or [] if isinstance(row, dict) and
                     all(row.get(k) for k in ('categoryId', 'categoryType', 'categoryValue'))]
            self._merge_results(
                merged,
                valid,
                bonus=220,
                source='CHZZK Studio 한국어 검색',
                matched_keyword=query,
                korean_name=query,
                discord_name=query,
            )

        if not merged and errors and successful_queries == 0:
            raise APIError('카테고리 검색에 연결하지 못했습니다: ' + ' / '.join(errors))

        results = sorted(
            merged.values(),
            key=lambda item: (
                int(item.get('_smartScore') or 0),
                1 if contains_hangul(item.get('categoryValue')) else 0,
                item.get('categoryValue', ''),
            ),
            reverse=True,
        )
        return results[:max(1, int(limit))]

    def search(self, keyword, official=None):
        return self.search_smart(keyword, official=official, limit=30)

    def apply(self, rule, cancelled=lambda: False):
        current = self.settings()
        if category_key(current) == rule.key:
            return False
        payload = build_payload(current, rule)
        if cancelled():
            raise APIError('변경 요청이 취소되었습니다.')
        self.bridge_request(
            'put_settings',
            {'channel': self.channel, 'settings': payload},
            '[PUT /manage/v1/channels/{channelId}/live-setting/normal]',
        )
        if category_key(self.settings()) != rule.key:
            raise APIError('변경 후 카테고리가 일치하지 않습니다. 방송 설정을 확인해 주세요.')
        return True
