import asyncio
import unittest
from unittest.mock import AsyncMock

import httpx

from src.clover_report.bili_hotwords import (
    BILI_HOTWORD_HEADERS,
    BILI_HOTWORD_URLS,
    BiliHotwordFetchError,
    BiliHotwordResponseError,
    fetch_bili_hotwords,
    parse_bili_hotwords,
)


def _response(payload: object) -> httpx.Response:
    return httpx.Response(200, json=payload)


def _http_error(status_code: int, url: str) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", url)
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=request,
        response=response,
    )


class BiliHotwordParserTests(unittest.TestCase):
    def test_current_response_uses_display_name(self):
        payload = {
            "code": 0,
            "data": {
                "trending": {
                    "list": [
                        {"keyword": "BLG T1", "show_name": "BLG战胜T1"},
                        {"keyword": "防汛", "show_name": ""},
                    ]
                }
            },
        }

        self.assertEqual(parse_bili_hotwords(payload), ["BLG战胜T1", "防汛"])

    def test_invalid_display_name_falls_back_to_keyword(self):
        payload = {
            "code": 0,
            "list": [
                {"show_name": "   ", "keyword": "空白展示名"},
                {"show_name": 123, "keyword": "错误类型展示名"},
            ],
        }

        self.assertEqual(
            parse_bili_hotwords(payload),
            ["空白展示名", "错误类型展示名"],
        )

    def test_legacy_response_filters_bad_entries_and_limits_results(self):
        items: list[object] = [None, {"keyword": ""}]
        items.extend({"keyword": f"热点 {index}"} for index in range(12))

        result = parse_bili_hotwords({"code": 0, "list": items})

        self.assertEqual(result, [f"热点 {index}" for index in range(10)])

    def test_invalid_contract_is_rejected(self):
        invalid_payloads = (
            [],
            {"code": -412, "list": [{"keyword": "ignored"}]},
            {"code": 0},
            {"code": 0, "list": [None, {"keyword": ""}]},
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(BiliHotwordResponseError):
                    parse_bili_hotwords(payload)


class BiliHotwordFetchTests(unittest.TestCase):
    def test_current_source_receives_browser_headers(self):
        request_get = AsyncMock(
            return_value=_response(
                {
                    "code": 0,
                    "data": {"trending": {"list": [{"keyword": "热点"}]}},
                }
            )
        )

        result = asyncio.run(fetch_bili_hotwords(request_get))

        self.assertEqual(result, ["热点"])
        request_get.assert_awaited_once_with(
            BILI_HOTWORD_URLS[0],
            headers=BILI_HOTWORD_HEADERS,
        )

    def test_412_from_current_source_uses_legacy_fallback(self):
        request_get = AsyncMock(
            side_effect=[
                _http_error(412, BILI_HOTWORD_URLS[0]),
                _response({"code": 0, "list": [{"keyword": "备用热点"}]}),
            ]
        )

        result = asyncio.run(fetch_bili_hotwords(request_get))

        self.assertEqual(result, ["备用热点"])
        self.assertEqual(request_get.await_count, 2)
        self.assertEqual(request_get.await_args_list[1].args[0], BILI_HOTWORD_URLS[1])
        self.assertEqual(
            request_get.await_args_list[1].kwargs["headers"],
            BILI_HOTWORD_HEADERS,
        )

    def test_malformed_current_source_uses_legacy_fallback(self):
        request_get = AsyncMock(
            side_effect=[
                _response({"code": 0, "data": {}}),
                _response({"code": 0, "list": [{"keyword": "备用热点"}]}),
            ]
        )

        result = asyncio.run(fetch_bili_hotwords(request_get))

        self.assertEqual(result, ["备用热点"])
        self.assertEqual(request_get.await_count, 2)

    def test_total_timeout_raises_domain_error(self):
        async def slow_request(*args, **kwargs):
            await asyncio.sleep(1)
            return _response({"code": 0, "list": [{"keyword": "太迟"}]})

        with self.assertRaisesRegex(BiliHotwordFetchError, "请求超时"):
            asyncio.run(fetch_bili_hotwords(slow_request, timeout=0.001))

    def test_slow_current_source_uses_legacy_fallback(self):
        calls = 0

        async def request_get(url, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                await asyncio.sleep(1)
            return _response({"code": 0, "list": [{"keyword": "备用热点"}]})

        result = asyncio.run(
            fetch_bili_hotwords(
                request_get,
                timeout=1,
                source_timeout=0.001,
            )
        )

        self.assertEqual(result, ["备用热点"])
        self.assertEqual(calls, 2)

    def test_all_sources_failing_raises_domain_error(self):
        request_get = AsyncMock(
            side_effect=[
                _http_error(412, BILI_HOTWORD_URLS[0]),
                _http_error(503, BILI_HOTWORD_URLS[1]),
            ]
        )

        with self.assertRaises(BiliHotwordFetchError):
            asyncio.run(fetch_bili_hotwords(request_get))

        self.assertEqual(request_get.await_count, 2)


if __name__ == "__main__":
    unittest.main()
