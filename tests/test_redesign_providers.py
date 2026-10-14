import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import requests
from api import ChzzkAPI, APIError
from chzzk_open import ChzzkOpenAPI, ChzzkOpenAPIError
from network_policy import retry_seconds

CAT = {'categoryId': 'Minecraft', 'categoryValue': '마인크래프트', 'categoryType': 'GAME'}


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'LOCALAPPDATA': self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.bridge = Mock()
        self.api = ChzzkAPI('a'*32, self.bridge)
        self.addCleanup(self.api.close)

    def test_official_small_query_precedes_whole_catalogue(self):
        official = Mock(configured=True)
        official.search_categories.return_value = [CAT]
        with patch.object(self.api, 'search_catalog') as full:
            result = self.api.search('Minecraft', official)
        full.assert_not_called()
        self.assertEqual(result[0]['categoryId'], 'Minecraft')
        self.assertEqual(result[0]['_matchSource'], 'CHZZK 공식 Open API')

    def test_official_missing_auth_keeps_existing_provider(self):
        official = ChzzkOpenAPI('', '')
        self.addCleanup(official.close)
        with patch.object(self.api, 'search_catalog', return_value=[CAT]) as catalog, \
                patch.object(self.api, '_studio_validate_korean_candidates'), patch.object(official.session, 'get') as request:
            self.assertEqual(self.api.search('Minecraft', official)[0]['categoryId'], 'Minecraft')
        catalog.assert_called_once()
        request.assert_not_called()

    def test_official_error_falls_back_once(self):
        official = Mock(configured=True)
        official.search_categories.side_effect = ChzzkOpenAPIError('authentication', auth=True)
        with patch.object(self.api, 'search_catalog', return_value=[CAT]), patch.object(self.api, '_studio_validate_korean_candidates'):
            self.assertEqual(self.api.search('Minecraft', official)[0]['categoryId'], 'Minecraft')
        official.search_categories.assert_called_once()

    def test_catalogue_cache_survives_restart_and_avoids_network(self):
        with patch.object(self.api, '_load_unofficial_chzzk_catalog', return_value=[CAT]):
            self.api.load_category_catalog()
        second = ChzzkAPI('a'*32, self.bridge)
        self.addCleanup(second.close)
        with patch.object(second, '_load_unofficial_chzzk_catalog') as request:
            self.assertEqual(second.load_category_catalog()[0]['categoryId'], 'Minecraft')
            request.assert_not_called()

    def test_cache_expires_and_refreshes(self):
        self.api._category_catalog = [CAT]
        self.api._category_catalog_at = time.time() - 7*3600
        self.api.category_ttl = 6*3600
        with patch.object(self.api, '_load_unofficial_chzzk_catalog', return_value=[dict(CAT, categoryValue='새 이름')]) as request:
            self.assertEqual(self.api.load_category_catalog()[0]['categoryValue'], '새 이름')
        request.assert_called_once()

    def test_offline_catalogue_has_limited_age_and_backoff(self):
        with patch.object(self.api, '_load_unofficial_chzzk_catalog', side_effect=APIError('offline')) as first, \
                patch.object(self.api, '_load_dico_catalog_fallback', side_effect=APIError('offline')) as second:
            for _ in range(2):
                with self.assertRaises(APIError):
                    self.api.load_category_catalog()
        self.assertEqual(first.call_count, 1)
        self.assertEqual(second.call_count, 1)

    def test_actual_request_params_and_missing_auth(self):
        client = ChzzkOpenAPI('test-client', 'test-secret')
        self.addCleanup(client.close)
        response = Mock(status_code=200)
        response.json.return_value = {'code': 200, 'content': {'data': [CAT]}}
        with patch.object(client.session, 'get', return_value=response) as request:
            self.assertEqual(client.search_categories('마인크래프트', 100), [dict(CAT, posterImageUrl=None)])
        self.assertTrue(request.call_args.args[0].endswith('/open/v1/categories/search'))
        self.assertEqual(request.call_args.kwargs['params'], {'query': '마인크래프트', 'size': 50})
        self.assertIn('Client-Secret', request.call_args.kwargs['headers'])

    def test_official_429_and_auth_use_bounded_retries(self):
        for code, seconds in ((429, 120), (401, 300)):
            client = ChzzkOpenAPI('test', 'test')
            self.addCleanup(client.close)
            response = Mock(status_code=code, headers={'Retry-After': '120'})
            with patch.object(client.session, 'get', return_value=response) as request:
                with self.assertRaises(ChzzkOpenAPIError) as failure:
                    client.search_categories('test')
                self.assertEqual(failure.exception.retry_after, seconds)
                with self.assertRaises(ChzzkOpenAPIError):
                    client.search_categories('test')
                request.assert_called_once()

    def test_official_timeout_is_user_safe(self):
        client = ChzzkOpenAPI('test', 'sensitive-placeholder')
        self.addCleanup(client.close)
        with patch.object(client.session, 'get', side_effect=requests.Timeout('sensitive-placeholder')):
            with self.assertRaises(ChzzkOpenAPIError) as failure:
                client.search_categories('test')
        self.assertNotIn('sensitive-placeholder', str(failure.exception))

    def test_live_unknown_status_does_not_guess(self):
        for value, expected in (({'status': 'OPEN'}, True), ({'status': 'CLOSE'}, False)):
            with patch.object(self.api, 'bridge_request', return_value=value):
                self.assertEqual(self.api.is_live(), expected)
        with patch.object(self.api, 'bridge_request', return_value={}), self.assertRaises(APIError):
            self.api.is_live()

    def test_retry_after_bounded_seconds_and_invalid_value(self):
        self.assertEqual(retry_seconds('120'), 120)
        self.assertEqual(retry_seconds('99999999'), 3600)
        self.assertEqual(retry_seconds('wrong'), 60)

    def test_manual_etc_and_sports_results_are_preserved(self):
        from core import Rule
        for row in ({'categoryId': 'talk', 'categoryValue': 'talk', 'categoryType': 'ETC'},
                    {'categoryId': 'football', 'categoryValue': '축구', 'categoryType': 'SPORTS'}):
            official = Mock(configured=True)
            official.search_categories.return_value = [row]
            result = self.api.search(row['categoryValue'], official)
            self.assertEqual(result[0]['categoryType'], row['categoryType'])
            rule = Rule('Custom.exe', row['categoryId'], row['categoryValue'], row['categoryType'])
            with patch.object(self.api, 'search', return_value=[]), \
                    patch.object(self.api, 'bridge_request', return_value={'results': [row]}):
                self.assertEqual(self.api.validate_category(rule), row)


if __name__ == '__main__':
    unittest.main()
