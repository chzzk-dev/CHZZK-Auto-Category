import os
import requests

OPEN_API_BASE = 'https://openapi.chzzk.naver.com'
APP_CLIENT_ID = os.environ.get('CHZZK_CLIENT_ID') or 'febf777f-05d0-46b7-8402-2c9b9506bb72'
APP_CLIENT_SECRET = os.environ.get('CHZZK_CLIENT_SECRET', '')


class ChzzkOpenAPIError(RuntimeError):
    pass


class ChzzkOpenAPI:
    """Small client for CHZZK's official Open API category search.

    Category search uses client authentication (Client-Id / Client-Secret) and does
    not require a user OAuth token.
    """

    def __init__(self, client_id=APP_CLIENT_ID, client_secret=APP_CLIENT_SECRET):
        self.client_id = str(client_id or '').strip()
        self.client_secret = str(client_secret or '').strip()
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'CHZZK-Auto-Category',
        })

    @property
    def configured(self):
        return bool(self.client_id and self.client_secret)

    def close(self):
        self.session.close()

    def search_categories(self, query, limit=30):
        text = str(query or '').strip()
        if not text:
            return []
        if not self.configured:
            return []

        try:
            response = self.session.get(
                OPEN_API_BASE + '/open/v1/categories/search',
                params={'query': text, 'size': max(1, min(50, int(limit)))},
                headers={
                    'Client-Id': self.client_id,
                    'Client-Secret': self.client_secret,
                },
                timeout=(5, 10),
            )
        except requests.RequestException as e:
            raise ChzzkOpenAPIError('CHZZK 공식 Open API에 연결할 수 없습니다.') from e

        if response.status_code == 401:
            raise ChzzkOpenAPIError('CHZZK 공식 API Client ID 또는 Client Secret이 올바르지 않습니다.')
        if response.status_code == 429:
            raise ChzzkOpenAPIError('CHZZK 공식 API 요청 제한에 도달했습니다.')
        if not 200 <= response.status_code < 300:
            raise ChzzkOpenAPIError(f'CHZZK 공식 API HTTP {response.status_code} 오류입니다.')

        try:
            body = response.json()
        except ValueError as e:
            raise ChzzkOpenAPIError('CHZZK 공식 API가 JSON이 아닌 응답을 반환했습니다.') from e

        if not isinstance(body, dict) or str(body.get('code')) != '200':
            message = body.get('message') if isinstance(body, dict) else None
            raise ChzzkOpenAPIError(str(message or 'CHZZK 공식 API 응답이 올바르지 않습니다.'))

        content = body.get('content')
        rows = content.get('data') if isinstance(content, dict) else None
        if not isinstance(rows, list):
            return []

        results = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            category_id = str(row.get('categoryId') or '').strip()
            category_type = str(row.get('categoryType') or '').strip()
            category_value = str(row.get('categoryValue') or '').strip()
            if not category_id or not category_type or not category_value:
                continue
            results.append({
                'categoryId': category_id,
                'categoryType': category_type,
                'categoryValue': category_value,
                'posterImageUrl': row.get('posterImageUrl'),
            })
        return results

    def test(self):
        # A tiny, deterministic request that verifies client authentication.
        if not self.configured:
            raise ChzzkOpenAPIError('CHZZK 공식 API 연결 정보가 설정되지 않았습니다.')
        self.search_categories('게임', limit=1)
        return True
