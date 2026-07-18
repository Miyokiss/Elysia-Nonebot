import asyncio
import base64
import gzip
import json
import tempfile
import types
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import nonebot
from tortoise import Tortoise

try:
    nonebot.get_driver()
except ValueError:
    nonebot.init(log_level="WARNING")

from nonebot.adapters.qq import Message
from nonebot.adapters.qq.exception import ActionFailed
from nonebot.internal.driver import Response

from src.clover_image import image_generation as image_api
from src.clover_sqlite.models.image_generation import (
    DailyQuotaStatus,
    ImageGenerationUsage,
)
from src.plugins import image_generation as image_plugin


PNG_BYTES = b"\x89PNG\r\n\x1a\nimage-data"


def image_response(url: str = "https://api.test/v1/images/generations"):
    return httpx.Response(
        200,
        json={"data": [{"b64_json": base64.b64encode(PNG_BYTES).decode()}]},
        request=httpx.Request("POST", url),
    )


class FakePostClient:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [image_response()])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if response.request.url != httpx.URL(url):
            response.request = httpx.Request("POST", url)
        return response

    @asynccontextmanager
    async def stream(self, method, url, **kwargs):
        if method != "POST":
            raise AssertionError(f"unexpected method: {method}")
        yield await self.post(url, **kwargs)


class RoundRobinTests(unittest.TestCase):
    def test_models_rotate_without_advancing_for_fallback_candidates(self):
        balancer = image_api.RoundRobinModelBalancer(("model-a", "model-b"))

        self.assertEqual(balancer.next_order(), ("model-a", "model-b"))
        self.assertEqual(balancer.next_order(), ("model-b", "model-a"))
        self.assertEqual(balancer.next_order(), ("model-a", "model-b"))


class ImageRequestTests(unittest.TestCase):
    def setUp(self):
        self.reference = image_api.reference_image_from_bytes(PNG_BYTES)

    def make_client(self, models=("gpt-image-2", "doubao-seedream-test")):
        return image_api.ImageGenerationClient(
            base_url="https://api.test",
            api_key="test-key",
            models=models,
            size="1024x1024",
            seedream_size="2K",
            timeout_seconds=30,
        )

    def test_natural_generation_uses_json_generations_for_both_models(self):
        async def scenario():
            service = self.make_client()
            for model in service.balancer.models:
                fake = FakePostClient()
                await service._request_model(
                    fake,
                    provider=service.providers_by_model[model],
                    prompt="a landscape",
                    reference=None,
                )
                url, kwargs = fake.calls[0]
                self.assertTrue(url.endswith("/v1/images/generations"))
                self.assertEqual(kwargs["json"]["model"], model)
                expected_size = "2K" if model.startswith("doubao-seedream") else "1024x1024"
                self.assertEqual(kwargs["json"]["size"], expected_size)
                self.assertNotIn("image", kwargs["json"])
                self.assertNotIn("files", kwargs)

        asyncio.run(scenario())

    def test_gpt_reference_uses_multipart_edits(self):
        async def scenario():
            service = self.make_client()
            fake = FakePostClient()
            await service._request_model(
                fake,
                provider=service.providers_by_model["gpt-image-2"],
                prompt="change the lighting",
                reference=self.reference,
            )
            url, kwargs = fake.calls[0]
            self.assertTrue(url.endswith("/v1/images/edits"))
            self.assertEqual(kwargs["data"]["model"], "gpt-image-2")
            self.assertEqual(kwargs["files"]["image"][1], PNG_BYTES)
            self.assertNotIn("json", kwargs)

        asyncio.run(scenario())

    def test_seedream_reference_uses_generation_image_data_url(self):
        async def scenario():
            service = self.make_client()
            fake = FakePostClient()
            await service._request_model(
                fake,
                provider=service.providers_by_model["doubao-seedream-test"],
                prompt="change the lighting",
                reference=self.reference,
            )
            url, kwargs = fake.calls[0]
            self.assertTrue(url.endswith("/v1/images/generations"))
            self.assertTrue(kwargs["json"]["image"].startswith("data:image/png;base64,"))
            self.assertNotIn("files", kwargs)

        asyncio.run(scenario())

    def test_independent_provider_urls_and_keys_do_not_mix(self):
        async def scenario():
            providers = (
                image_api.ImageGenerationProvider(
                    model="gpt-image-2",
                    kind=image_api.ImageGenerationProviderKind.GPT,
                    base_url="https://gpt.test",
                    api_key="gpt-provider-key",
                ),
                image_api.ImageGenerationProvider(
                    model="doubao-seedream-test",
                    kind=image_api.ImageGenerationProviderKind.SEEDREAM,
                    base_url="https://seedream.test",
                    api_key="seedream-provider-key",
                ),
            )
            service = image_api.ImageGenerationClient(providers=providers)
            calls = []
            for provider in providers:
                fake = FakePostClient()
                await service._request_model(
                    fake,
                    provider=provider,
                    prompt="prompt",
                    reference=None,
                )
                calls.append(fake.calls[0])
            return calls

        calls = asyncio.run(scenario())

        self.assertTrue(calls[0][0].startswith("https://gpt.test/"))
        self.assertEqual(
            calls[0][1]["headers"]["Authorization"],
            "Bearer gpt-provider-key",
        )
        self.assertTrue(calls[1][0].startswith("https://seedream.test/"))
        self.assertEqual(
            calls[1][1]["headers"]["Authorization"],
            "Bearer seedream-provider-key",
        )
        self.assertNotIn("seedream-provider-key", repr(calls[0][1]))
        self.assertNotIn("gpt-provider-key", repr(calls[1][1]))

    def test_retryable_status_falls_back_to_second_model(self):
        async def scenario():
            first = httpx.Response(
                503,
                json={"error": {"code": "no_available_channel"}},
                request=httpx.Request("POST", "https://api.test/first"),
            )
            fake = FakePostClient([first, image_response()])
            service = self.make_client(("model-a", "model-b"))
            with patch.object(image_api.httpx, "AsyncClient", return_value=fake):
                result = await service.generate("prompt")
            return result, fake

        result, fake = asyncio.run(scenario())

        self.assertEqual(result.model, "model-b")
        self.assertEqual(
            [call[1]["json"]["model"] for call in fake.calls],
            ["model-a", "model-b"],
        )

    def test_provider_auth_failure_falls_back_to_second_model(self):
        async def scenario():
            first = httpx.Response(
                403,
                json={"error": {"code": "permission_denied"}},
                request=httpx.Request("POST", "https://api.test/first"),
            )
            fake = FakePostClient([first, image_response()])
            service = self.make_client(("model-a", "model-b"))
            with patch.object(image_api.httpx, "AsyncClient", return_value=fake):
                result = await service.generate("prompt")
            return result, fake

        result, fake = asyncio.run(scenario())

        self.assertEqual(result.model, "model-b")
        self.assertEqual(len(fake.calls), 2)

    def test_all_provider_auth_failures_are_configuration_error(self):
        async def scenario():
            responses = [
                httpx.Response(
                    401,
                    json={"error": {"code": "invalid_api_key"}},
                    request=httpx.Request("POST", "https://api.test/first"),
                ),
                httpx.Response(
                    403,
                    json={"error": {"code": "permission_denied"}},
                    request=httpx.Request("POST", "https://api.test/second"),
                ),
            ]
            fake = FakePostClient(responses)
            service = self.make_client(("model-a", "model-b"))
            with patch.object(image_api.httpx, "AsyncClient", return_value=fake):
                await service.generate("prompt")

        with self.assertRaises(image_api.ImageGenerationConfigurationError):
            asyncio.run(scenario())

    def test_non_retryable_status_does_not_call_second_model(self):
        async def scenario():
            response = httpx.Response(
                400,
                json={"error": {"code": "content_policy_violation"}},
                request=httpx.Request("POST", "https://api.test/first"),
            )
            fake = FakePostClient([response])
            service = self.make_client(("model-a", "model-b"))
            with patch.object(image_api.httpx, "AsyncClient", return_value=fake):
                with self.assertRaises(image_api.ImageGenerationHTTPError):
                    await service.generate("prompt")
            return fake

        fake = asyncio.run(scenario())
        self.assertEqual(len(fake.calls), 1)

    def test_ambiguous_server_error_does_not_call_second_model(self):
        async def scenario():
            response = httpx.Response(
                503,
                json={"error": {"code": "upstream_error"}},
                request=httpx.Request("POST", "https://api.test/first"),
            )
            fake = FakePostClient([response])
            service = self.make_client(("model-a", "model-b"))
            with patch.object(image_api.httpx, "AsyncClient", return_value=fake):
                with self.assertRaises(image_api.ImageGenerationHTTPError):
                    await service.generate("prompt")
            return fake

        fake = asyncio.run(scenario())
        self.assertEqual(len(fake.calls), 1)

    def test_connect_failure_falls_back_but_read_timeout_does_not(self):
        async def connect_scenario():
            request = httpx.Request("POST", "https://api.test/first")
            fake = FakePostClient(
                [httpx.ConnectError("connect failed", request=request), image_response()]
            )
            service = self.make_client(("model-a", "model-b"))
            with patch.object(image_api.httpx, "AsyncClient", return_value=fake):
                result = await service.generate("prompt")
            return result, fake

        async def read_scenario():
            request = httpx.Request("POST", "https://api.test/first")
            fake = FakePostClient([httpx.ReadTimeout("read failed", request=request)])
            service = self.make_client(("model-a", "model-b"))
            with patch.object(image_api.httpx, "AsyncClient", return_value=fake):
                with self.assertRaisesRegex(
                    image_api.ImageGenerationError,
                    "结果未知",
                ):
                    await service.generate("prompt")
            return fake

        connect_result, connect_fake = asyncio.run(connect_scenario())
        read_fake = asyncio.run(read_scenario())

        self.assertEqual(connect_result.model, "model-b")
        self.assertEqual(len(connect_fake.calls), 2)
        self.assertEqual(len(read_fake.calls), 1)

    def test_total_generation_deadline_stops_a_slow_response(self):
        class SlowPostClient(FakePostClient):
            @asynccontextmanager
            async def stream(self, method, url, **kwargs):
                await asyncio.sleep(0.05)
                yield image_response(url)

        async def scenario():
            service = image_api.ImageGenerationClient(
                base_url="https://api.test",
                api_key="test-key",
                models=("model-a", "model-b"),
                size="1024x1024",
                seedream_size="2K",
                timeout_seconds=0.01,
            )
            with patch.object(
                image_api.httpx,
                "AsyncClient",
                return_value=SlowPostClient(),
            ):
                await service.generate("prompt")

        with self.assertRaisesRegex(
            image_api.ImageGenerationError,
            "结果未知",
        ):
            asyncio.run(scenario())

    def test_external_result_url_does_not_receive_api_authorization(self):
        async def scenario():
            service = self.make_client()
            with patch.object(
                image_api,
                "_download_image",
                new_callable=AsyncMock,
                return_value=(PNG_BYTES, "image/png"),
            ) as download:
                await service._download_generated_image("https://cdn.test/image.png")
            return download

        download = asyncio.run(scenario())
        self.assertIsNone(download.await_args.kwargs["headers"])

    def test_same_origin_result_uses_the_successful_provider_key(self):
        async def scenario():
            providers = (
                image_api.ImageGenerationProvider(
                    model="gpt-image-2",
                    kind=image_api.ImageGenerationProviderKind.GPT,
                    base_url="https://shared.test",
                    api_key="gpt-provider-key",
                ),
                image_api.ImageGenerationProvider(
                    model="doubao-seedream-test",
                    kind=image_api.ImageGenerationProviderKind.SEEDREAM,
                    base_url="https://shared.test",
                    api_key="seedream-provider-key",
                ),
            )
            service = image_api.ImageGenerationClient(providers=providers)
            with patch.object(
                image_api,
                "_download_image",
                new_callable=AsyncMock,
                return_value=(PNG_BYTES, "image/png"),
            ) as download:
                await service._download_generated_image(
                    "https://shared.test/image.png",
                    provider=providers[1],
                )
            return download

        download = asyncio.run(scenario())

        self.assertEqual(
            download.await_args.kwargs["headers"]["Authorization"],
            "Bearer seedream-provider-key",
        )


class ImageResponseTests(unittest.TestCase):
    def test_base64_response_is_decoded(self):
        payload = image_api._extract_generation_payload(image_response())

        self.assertEqual(payload.content, PNG_BYTES)
        self.assertEqual(payload.media_type, "image/png")

    def test_result_url_is_preserved_for_bounded_download(self):
        response = httpx.Response(
            200,
            json={"data": [{"url": "https://cdn.test/image.png"}]},
            request=httpx.Request("POST", "https://api.test/v1/images/generations"),
        )

        payload = image_api._extract_generation_payload(response)

        self.assertEqual(payload.url, "https://cdn.test/image.png")
        self.assertIsNone(payload.content)

    def test_invalid_base64_is_rejected_without_echoing_body(self):
        response = httpx.Response(
            200,
            json={"data": [{"b64_json": "private-invalid-value"}]},
            request=httpx.Request("POST", "https://api.test/v1/images/generations"),
        )

        with self.assertRaises(image_api.ImageGenerationError) as raised:
            image_api._extract_generation_payload(response)

        self.assertNotIn("private-invalid-value", str(raised.exception))

    def test_gzip_response_is_decoded_once_and_parsed(self):
        payload = json.dumps(
            {
                "data": [
                    {"b64_json": base64.b64encode(PNG_BYTES).decode("ascii")}
                ]
            }
        ).encode()

        async def scenario():
            response = httpx.Response(
                200,
                headers={"Content-Encoding": "gzip"},
                content=gzip.compress(payload),
                request=httpx.Request("POST", "https://api.test/image"),
            )
            fake = FakePostClient([response])
            return await image_api._bounded_post(
                fake,
                "https://api.test/image",
                json={},
            )

        response = asyncio.run(scenario())
        generation = image_api._extract_generation_payload(response)

        self.assertNotIn("Content-Encoding", response.headers)
        self.assertEqual(generation.content, PNG_BYTES)

    def test_streamed_response_is_stopped_at_size_limit(self):
        async def scenario():
            response = httpx.Response(
                200,
                content=b"123456789",
                request=httpx.Request("POST", "https://api.test/image"),
            )
            fake = FakePostClient([response])
            with patch.object(image_api, "MAX_RESPONSE_BYTES", 8):
                with self.assertRaisesRegex(
                    image_api.ImageGenerationError,
                    "超过大小限制",
                ):
                    await image_api._bounded_post(fake, "https://api.test/image")

        asyncio.run(scenario())

    def test_unsupported_reference_format_is_rejected_explicitly(self):
        with self.assertRaisesRegex(
            image_api.UnsupportedReferenceImageError,
            "PNG、JPEG 或 WebP",
        ):
            image_api.reference_image_from_bytes(b"GIF89aimage-data")


class PluginParsingTests(unittest.TestCase):
    def attachment(self, content_type="image/png", url="https://qq.test/image"):
        return types.SimpleNamespace(content_type=content_type, url=url)

    def test_plain_prompt_selects_natural_mode(self):
        request = image_plugin.parse_generation_request("樱花树下的少女")

        self.assertEqual(request.mode, image_plugin.ImageGenerationMode.NATURAL)
        self.assertEqual(request.prompt, "樱花树下的少女")

    def test_attached_image_implicitly_selects_reference_mode(self):
        request = image_plugin.parse_generation_request(
            "改成夜景",
            has_reference_image=True,
        )

        self.assertEqual(request.mode, image_plugin.ImageGenerationMode.REFERENCE)

    def test_selfie_mode_takes_precedence_over_attached_image(self):
        request = image_plugin.parse_generation_request(
            "自拍：在海边",
            has_reference_image=True,
        )

        self.assertEqual(request.mode, image_plugin.ImageGenerationMode.SELFIE)
        self.assertEqual(request.prompt, "在海边")

    def test_current_image_has_priority_over_quoted_image(self):
        event = types.SimpleNamespace(
            attachments=[self.attachment(url="https://qq.test/current")],
            reply=types.SimpleNamespace(
                attachments=[self.attachment(url="https://qq.test/reply")]
            ),
            msg_elements=None,
        )

        self.assertEqual(
            image_plugin.find_reference_image_url(event),
            "https://qq.test/current",
        )

    def test_quoted_image_is_found_and_non_images_are_ignored(self):
        event = types.SimpleNamespace(
            attachments=[self.attachment("audio/mpeg", "https://qq.test/audio")],
            reply=types.SimpleNamespace(
                attachments=[self.attachment(url="https://qq.test/reply")]
            ),
            msg_elements=None,
        )

        self.assertEqual(
            image_plugin.find_reference_image_url(event),
            "https://qq.test/reply",
        )

    def test_guild_attachment_without_content_type_is_accepted(self):
        event = types.SimpleNamespace(
            attachments=[types.SimpleNamespace(url="https://qq.test/guild-image")],
            reply=None,
            msg_elements=None,
        )

        self.assertEqual(
            image_plugin.find_reference_image_url(event),
            "https://qq.test/guild-image",
        )


class UsageLimitTests(unittest.TestCase):
    def test_capacity_rejects_excess_work_and_recovers_after_release(self):
        capacity = image_plugin.GenerationCapacity(1)

        self.assertTrue(capacity.try_acquire())
        self.assertFalse(capacity.try_acquire())
        capacity.release()
        self.assertTrue(capacity.try_acquire())

    def test_user_cooldown_returns_remaining_seconds(self):
        with (
            patch.object(image_plugin, "image_generation_user_cooldown", 60.0),
            patch.object(image_plugin, "_last_user_requests", {}),
        ):
            self.assertEqual(image_plugin.reserve_user_request("user", now=100.0), 0)
            self.assertEqual(image_plugin.reserve_user_request("user", now=101.0), 59)
            self.assertEqual(image_plugin.reserve_user_request("user", now=160.0), 0)

    def test_daily_usage_limits_are_persisted_in_database(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as directory:
                database = Path(directory) / "quota.db"
                database_url = f"sqlite://{database.as_posix()}"
                await Tortoise.init(
                    config={
                        "connections": {
                            "default": database_url,
                            "second": database_url,
                        },
                        "apps": {
                            "models": {
                                "models": [
                                    "src.clover_sqlite.models.image_generation"
                                ],
                                "default_connection": "default",
                            }
                        },
                    }
                )
                await Tortoise.generate_schemas()
                try:
                    sequential = [
                        await ImageGenerationUsage.reserve_daily_usage(
                            "user-a", user_limit=2
                        ),
                        await ImageGenerationUsage.reserve_daily_usage(
                            "user-a", user_limit=2
                        ),
                        await ImageGenerationUsage.reserve_daily_usage(
                            "user-a", user_limit=2
                        ),
                        await ImageGenerationUsage.reserve_daily_usage(
                            "user-b", user_limit=2
                        ),
                    ]

                    await ImageGenerationUsage.all().delete()
                    concurrent = await asyncio.gather(
                        ImageGenerationUsage.reserve_daily_usage(
                            "concurrent-user", user_limit=1
                        ),
                        ImageGenerationUsage.reserve_daily_usage(
                            "concurrent-user",
                            user_limit=1,
                            connection_name="second",
                        ),
                    )

                    await ImageGenerationUsage.all().delete()
                    namespace_isolation = [
                        await ImageGenerationUsage.reserve_daily_usage(
                            "shared-user", user_limit=1
                        ),
                        await ImageGenerationUsage.reserve_daily_usage(
                            "shared-user",
                            user_limit=1,
                            namespace="prompt_assistant",
                        ),
                        await ImageGenerationUsage.reserve_daily_usage(
                            "shared-user", user_limit=1
                        ),
                        await ImageGenerationUsage.reserve_daily_usage(
                            "shared-user",
                            user_limit=1,
                            namespace="prompt_assistant",
                        ),
                    ]

                    await ImageGenerationUsage.all().delete()
                    unlimited = [
                        await ImageGenerationUsage.reserve_daily_usage(
                            "unlimited-user", user_limit=0
                        ),
                        await ImageGenerationUsage.reserve_daily_usage(
                            "unlimited-user",
                            user_limit=0,
                            namespace="prompt_assistant",
                        ),
                    ]
                    unlimited_row_count = await ImageGenerationUsage.all().count()
                    return (
                        sequential,
                        concurrent,
                        namespace_isolation,
                        unlimited,
                        unlimited_row_count,
                    )
                finally:
                    await Tortoise.close_connections()

        (
            sequential,
            concurrent,
            namespace_isolation,
            unlimited,
            unlimited_row_count,
        ) = asyncio.run(scenario())
        self.assertEqual(
            sequential,
            [
                DailyQuotaStatus.ALLOWED,
                DailyQuotaStatus.ALLOWED,
                DailyQuotaStatus.USER_LIMIT_REACHED,
                DailyQuotaStatus.ALLOWED,
            ],
        )
        self.assertCountEqual(
            concurrent,
            [DailyQuotaStatus.ALLOWED, DailyQuotaStatus.USER_LIMIT_REACHED],
        )
        self.assertEqual(
            namespace_isolation,
            [
                DailyQuotaStatus.ALLOWED,
                DailyQuotaStatus.ALLOWED,
                DailyQuotaStatus.USER_LIMIT_REACHED,
                DailyQuotaStatus.USER_LIMIT_REACHED,
            ],
        )
        self.assertEqual(
            unlimited,
            [DailyQuotaStatus.ALLOWED, DailyQuotaStatus.ALLOWED],
        )
        self.assertEqual(unlimited_row_count, 0)


class PluginHandlerTests(unittest.TestCase):
    def test_selfie_mode_uses_sender_avatar_and_cleans_it_up(self):
        async def scenario():
            reference = image_api.reference_image_from_bytes(PNG_BYTES)
            result = image_api.GeneratedImage(
                content=PNG_BYTES,
                media_type="image/png",
                filename="generated.png",
                model="gpt-image-2",
            )
            matcher = types.SimpleNamespace(finish=AsyncMock())
            event = types.SimpleNamespace(
                attachments=None,
                reply=None,
                msg_elements=None,
                get_user_id=lambda: "user-openid",
            )
            with (
                patch.object(image_plugin, "generate_image", matcher),
                patch.object(
                    image_plugin,
                    "download_qq_image",
                    new_callable=AsyncMock,
                    return_value="avatar.jpg",
                ) as download_avatar,
                patch.object(
                    image_plugin,
                    "read_reference_image",
                    new_callable=AsyncMock,
                    return_value=reference,
                ),
                patch.object(
                    image_plugin.image_generation_client,
                    "generate",
                    new_callable=AsyncMock,
                    return_value=result,
                ) as generate,
                patch.object(
                    image_plugin,
                    "_send_progress_safely",
                    new_callable=AsyncMock,
                ),
                patch.object(
                    image_plugin,
                    "reserve_daily_generation_usage",
                    new_callable=AsyncMock,
                    return_value=DailyQuotaStatus.ALLOWED,
                ),
                patch.object(
                    image_plugin,
                    "delete_file",
                    new_callable=AsyncMock,
                ) as delete,
            ):
                await image_plugin.handle_generate_image(
                    event,
                    Message("自拍"),
                )
            return download_avatar, generate, delete, matcher

        download_avatar, generate, delete, matcher = asyncio.run(scenario())

        download_avatar.assert_awaited_once_with("user-openid", size=640)
        prompt = generate.await_args.args[0]
        self.assertIn(image_plugin.SELFIE_PROMPT_PREFIX, prompt)
        self.assertIn(image_plugin.DEFAULT_SELFIE_PROMPT, prompt)
        self.assertEqual(generate.await_args.kwargs["reference"].content, PNG_BYTES)
        delete.assert_awaited_once_with("avatar.jpg")
        matcher.finish.assert_awaited_once()

    def test_image_send_failure_gets_text_fallback(self):
        async def scenario():
            result = image_api.GeneratedImage(
                content=PNG_BYTES,
                media_type="image/png",
                filename="generated.png",
                model="gpt-image-2",
            )
            send_failure = ActionFailed(
                Response(
                    400,
                    content='{"code": 40034006, "message": "upload failed"}',
                )
            )
            matcher = types.SimpleNamespace(
                finish=AsyncMock(side_effect=[send_failure, None])
            )
            event = types.SimpleNamespace(
                attachments=None,
                reply=None,
                msg_elements=None,
                get_user_id=lambda: "send-failure-user",
            )
            with (
                patch.object(image_plugin, "generate_image", matcher),
                patch.object(
                    image_plugin.image_generation_client,
                    "generate",
                    new_callable=AsyncMock,
                    return_value=result,
                ),
                patch.object(
                    image_plugin,
                    "_send_progress_safely",
                    new_callable=AsyncMock,
                ),
                patch.object(
                    image_plugin,
                    "reserve_daily_generation_usage",
                    new_callable=AsyncMock,
                    return_value=DailyQuotaStatus.ALLOWED,
                ),
            ):
                await image_plugin.handle_generate_image(event, Message("landscape"))
            return matcher

        matcher = asyncio.run(scenario())

        self.assertEqual(matcher.finish.await_count, 2)
        self.assertIn("发送失败", matcher.finish.await_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
