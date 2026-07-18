import asyncio
import base64
import types
import unittest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import httpx
import nonebot

try:
    nonebot.get_driver()
except ValueError:
    nonebot.init(log_level="WARNING")

from nonebot.adapters.qq import Message
from nonebot.exception import FinishedException

from src.clover_image import image_generation as image_api
from src.clover_sqlite.models.image_generation import DailyQuotaStatus
from src.plugins import image_generation as image_plugin


PNG_BYTES = b"\x89PNG\r\n\x1a\nquota-test-image"


def api_response(
    status_code: int,
    *,
    payload: dict | None = None,
    content: bytes | None = None,
    url: str = "https://provider.test/v1/images/generations",
) -> httpx.Response:
    request = httpx.Request("POST", url)
    if payload is not None:
        return httpx.Response(status_code, json=payload, request=request)
    return httpx.Response(status_code, content=content or b"", request=request)


def successful_image_response() -> httpx.Response:
    return api_response(
        200,
        payload={
            "data": [
                {"b64_json": base64.b64encode(PNG_BYTES).decode("ascii")}
            ]
        },
    )


class SequenceClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    @asynccontextmanager
    async def stream(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        outcome.request = httpx.Request(method, url)
        yield outcome


def make_client() -> image_api.ImageGenerationClient:
    providers = (
        image_api.ImageGenerationProvider(
            model="quota-provider-a",
            kind=image_api.ImageGenerationProviderKind.GPT,
            base_url="https://provider-a.test",
            api_key="dummy-key-a",
        ),
        image_api.ImageGenerationProvider(
            model="quota-provider-b",
            kind=image_api.ImageGenerationProviderKind.SEEDREAM,
            base_url="https://provider-b.test",
            api_key="dummy-key-b",
        ),
    )
    return image_api.ImageGenerationClient(
        providers=providers,
        size="1024x1024",
        seedream_size="2K",
        timeout_seconds=10,
    )


class QuotaMetadataTests(unittest.TestCase):
    def test_402_with_empty_body_is_quota_exhaustion(self):
        metadata = image_api._response_error_metadata(api_response(402))

        self.assertTrue(metadata.quota_exhausted)
        self.assertEqual(metadata.codes, frozenset())

    def test_429_insufficient_quota_code_is_quota_exhaustion(self):
        metadata = image_api._response_error_metadata(
            api_response(
                429,
                payload={"error": {"code": "insufficient_quota"}},
            )
        )

        self.assertTrue(metadata.quota_exhausted)
        self.assertIn("insufficient_quota", metadata.codes)

    def test_camel_case_code_and_chinese_balance_message_are_detected(self):
        responses = (
            api_response(
                429,
                payload={"error": {"code": "InsufficientBalance"}},
            ),
            api_response(
                429,
                payload={"error": {"message": "账户余额不足，请充值后重试"}},
            ),
            api_response(
                403,
                payload={"error": "该令牌额度已耗尽"},
            ),
            api_response(
                403,
                payload={"detail": "本日额度已达上限"},
            ),
        )

        for response in responses:
            with self.subTest(body=response.text):
                metadata = image_api._response_error_metadata(response)
                self.assertTrue(metadata.quota_exhausted)

    def test_ordinary_rate_limit_is_not_quota_exhaustion(self):
        metadata = image_api._response_error_metadata(
            api_response(
                429,
                payload={
                    "error": {
                        "code": "rate_limit_exceeded",
                        "message": "Rate limit reached; retry later",
                    }
                },
            )
        )

        self.assertFalse(metadata.quota_exhausted)


class QuotaFallbackTests(unittest.TestCase):
    def test_first_provider_quota_exhaustion_falls_back_to_second_success(self):
        async def scenario():
            client = make_client()
            transport = SequenceClient(
                [
                    api_response(
                        429,
                        payload={"error": {"code": "insufficient_quota"}},
                    ),
                    successful_image_response(),
                ]
            )
            with patch.object(
                image_api.httpx,
                "AsyncClient",
                return_value=transport,
            ):
                result = await client.generate("a lighthouse at dusk")
            return result, transport

        result, transport = asyncio.run(scenario())

        self.assertEqual(result.model, "quota-provider-b")
        self.assertEqual(result.content, PNG_BYTES)
        self.assertEqual(len(transport.calls), 2)

    def test_all_providers_quota_exhausted_raises_dedicated_error(self):
        async def scenario():
            client = make_client()
            transport = SequenceClient(
                [
                    api_response(402),
                    api_response(
                        429,
                        payload={"error": {"code": "insufficient_quota"}},
                    ),
                ]
            )
            with patch.object(
                image_api.httpx,
                "AsyncClient",
                return_value=transport,
            ):
                await client.generate("a lighthouse at dusk")

        with self.assertRaises(image_api.ImageGenerationQuotaExhaustedError):
            asyncio.run(scenario())

    def test_quota_plus_connection_failure_is_a_general_error(self):
        async def scenario():
            client = make_client()
            failed_request = httpx.Request(
                "POST",
                "https://provider-b.test/v1/images/generations",
            )
            transport = SequenceClient(
                [
                    api_response(402),
                    httpx.ConnectError("offline", request=failed_request),
                ]
            )
            with patch.object(
                image_api.httpx,
                "AsyncClient",
                return_value=transport,
            ):
                await client.generate("a lighthouse at dusk")

        with self.assertRaises(image_api.ImageGenerationError) as raised:
            asyncio.run(scenario())

        self.assertNotIsInstance(
            raised.exception,
            image_api.ImageGenerationQuotaExhaustedError,
        )


class QuotaPluginReplyTests(unittest.TestCase):
    def test_plugin_uses_dedicated_safe_reply_without_provider_body(self):
        async def scenario():
            provider_body = "PRIVATE-UPSTREAM-BILLING-BODY"
            matcher = types.SimpleNamespace(
                finish=AsyncMock(side_effect=FinishedException())
            )
            event = types.SimpleNamespace(
                attachments=None,
                reply=None,
                msg_elements=None,
                get_user_id=lambda: "quota-test-user",
            )
            with (
                patch.object(image_plugin, "generate_image", matcher),
                patch.object(
                    image_plugin,
                    "reserve_user_request",
                    return_value=0,
                ),
                patch.object(
                    image_plugin,
                    "reserve_daily_generation_usage",
                    new_callable=AsyncMock,
                    return_value=DailyQuotaStatus.ALLOWED,
                ),
                patch.object(
                    image_plugin,
                    "_send_progress_safely",
                    new_callable=AsyncMock,
                ),
                patch.object(
                    image_plugin.image_generation_client,
                    "generate",
                    new_callable=AsyncMock,
                    side_effect=image_api.ImageGenerationQuotaExhaustedError(
                        provider_body
                    ),
                ),
            ):
                with self.assertRaises(FinishedException):
                    await image_plugin.handle_generate_image(
                        event,
                        Message("a lighthouse at dusk"),
                    )
            return matcher, provider_body

        matcher, provider_body = asyncio.run(scenario())
        reply = matcher.finish.await_args.args[0]

        self.assertIn("当前请求可用的生图渠道额度均已用完", reply)
        self.assertNotIn(provider_body, reply)
        matcher.finish.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
