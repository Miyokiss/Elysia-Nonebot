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

from src.clover_image import image_generation as image_api
from src.clover_sqlite.models.image_generation import DailyQuotaStatus
from src.plugins import image_generation as image_plugin


PNG_BYTES = b"\x89PNG\r\n\x1a\nsize-test-image"


def dimensions(width, height):
    return image_api.ImageDimensions(width=width, height=height)


def image_response(
    url="https://provider.test/v1/images/generations",
):
    return httpx.Response(
        200,
        json={
            "data": [
                {"b64_json": base64.b64encode(PNG_BYTES).decode("ascii")}
            ]
        },
        request=httpx.Request("POST", url),
    )


def error_response(status_code, code):
    return httpx.Response(
        status_code,
        json={"error": {"code": code}},
        request=httpx.Request(
            "POST",
            "https://provider.test/v1/images/generations",
        ),
    )


class SequenceClient:
    def __init__(self, responses=None):
        self.responses = list(responses or [image_response()])
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    @asynccontextmanager
    async def stream(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        response.request = httpx.Request(method, url)
        yield response


def provider(kind, *, name=None):
    is_gpt = kind is image_api.ImageGenerationProviderKind.GPT
    return image_api.ImageGenerationProvider(
        model=name or ("gpt-image-test" if is_gpt else "seedream-test"),
        kind=kind,
        base_url=(
            "https://gpt-provider.test"
            if is_gpt
            else "https://seedream-provider.test"
        ),
        api_key="dummy-test-key",
    )


def make_client(providers):
    return image_api.ImageGenerationClient(
        providers=providers,
        size="1024x1024",
        seedream_size="2K",
        timeout_seconds=10,
    )


class ImageSizeParsingTests(unittest.TestCase):
    def assert_parsed(self, value, expected_prompt, width, height):
        request = image_plugin.parse_generation_request(value)

        self.assertEqual(request.prompt, expected_prompt)
        self.assertEqual(request.dimensions, dimensions(width, height))

    def test_leading_bare_dimensions_support_all_separators(self):
        for separator in ("x", "X", "×", "*"):
            with self.subTest(separator=separator):
                self.assert_parsed(
                    f"1920{separator}1088 赛博朋克城市",
                    "赛博朋克城市",
                    1920,
                    1088,
                )

    def test_marked_dimensions_support_safe_output_directives(self):
        cases = (
            ("分辨率 1024x1024 猫咪", "猫咪", 1024, 1024),
            (
                "城市 输出尺寸：3840*2160 夜景",
                "城市 夜景",
                3840,
                2160,
            ),
            ("size 1920X1088 skyline", "skyline", 1920, 1088),
            (
                "portrait output resolution: 1024×1536",
                "portrait",
                1024,
                1536,
            ),
        )

        for value, prompt, width, height in cases:
            with self.subTest(value=value):
                self.assert_parsed(value, prompt, width, height)

    def test_chinese_landscape_4k_aliases(self):
        for alias in ("横向", "横版", "横屏", "横图"):
            with self.subTest(alias=alias):
                self.assert_parsed(
                    f"{alias}4K 星空",
                    "星空",
                    3840,
                    2160,
                )

    def test_chinese_portrait_4k_aliases(self):
        for alias in ("竖向", "竖版", "竖屏", "竖图"):
            with self.subTest(alias=alias):
                self.assert_parsed(
                    f"{alias}4k 人像",
                    "人像",
                    2160,
                    3840,
                )

    def test_size_directive_composes_with_selfie_and_reference_modes(self):
        selfie = image_plugin.parse_generation_request("自拍 横图4K 海边")
        reference = image_plugin.parse_generation_request(
            "参考图 resolution 3840x2160 夜景"
        )

        self.assertEqual(selfie.mode, image_plugin.ImageGenerationMode.SELFIE)
        self.assertEqual(selfie.prompt, "海边")
        self.assertEqual(selfie.dimensions, dimensions(3840, 2160))
        self.assertEqual(
            reference.mode,
            image_plugin.ImageGenerationMode.REFERENCE,
        )
        self.assertEqual(reference.prompt, "夜景")
        self.assertEqual(reference.dimensions, dimensions(3840, 2160))

    def test_unmarked_size_like_subject_text_is_not_a_directive(self):
        prompts = (
            "桌上有一台4K显示器",
            "a 4K monitor on a desk",
            "一台 1920x1080 显示器",
            "a 1920x1080 monitor on a desk",
            "一台显示器，分辨率 1920x1080",
            "a landscape 4K monitor on a desk",
        )

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                request = image_plugin.parse_generation_request(prompt)
                self.assertEqual(request.prompt, prompt)
                self.assertIsNone(request.dimensions)

    def test_size_removal_preserves_multiline_prompt_text(self):
        request = image_plugin.parse_generation_request(
            "输出尺寸 1024x1024\n海报文字：\n第一行\n第二行"
        )

        self.assertEqual(request.dimensions, dimensions(1024, 1024))
        self.assertEqual(request.prompt, "海报文字：\n第一行\n第二行")

    def test_size_removal_cleans_standalone_lines_brackets_and_punctuation(self):
        cases = (
            (
                "第一行\n输出尺寸 1024x1024\n第二行",
                "第一行\n第二行",
            ),
            ("城市（输出尺寸 1024x1024）夜景", "城市 夜景"),
            ("猫，输出尺寸 1024x1024，狗", "猫，狗"),
        )

        for value, expected_prompt in cases:
            with self.subTest(value=value):
                request = image_plugin.parse_generation_request(value)
                self.assertEqual(request.dimensions, dimensions(1024, 1024))
                self.assertEqual(request.prompt, expected_prompt)

    def test_subject_resolution_after_output_directive_is_preserved(self):
        cases = (
            (
                "输出尺寸 1024x1024，一台显示器，分辨率 1920x1080",
                "一台显示器，分辨率 1920x1080",
            ),
            (
                "1024x1024 a landscape 4K monitor on a desk",
                "a landscape 4K monitor on a desk",
            ),
            (
                "输出尺寸 1024x1024，画面里是一台横向4K 显示器",
                "画面里是一台横向4K 显示器",
            ),
        )

        for value, expected_prompt in cases:
            with self.subTest(value=value):
                request = image_plugin.parse_generation_request(value)
                self.assertEqual(request.dimensions, dimensions(1024, 1024))
                self.assertEqual(request.prompt, expected_prompt)

    def test_duplicate_equivalent_directives_are_all_removed(self):
        cases = (
            "横向4K 尺寸 3840x2160 猫",
            "size 3840x2160 size 3840x2160 cat",
        )

        expected_prompts = ("猫", "cat")
        for value, expected_prompt in zip(cases, expected_prompts):
            with self.subTest(value=value):
                request = image_plugin.parse_generation_request(value)
                self.assertEqual(
                    request.dimensions,
                    dimensions(3840, 2160),
                )
                self.assertEqual(request.prompt, expected_prompt)

    def test_conflicting_size_directives_are_rejected(self):
        prompts = (
            "1024x1024 size 2048x2048 cat",
            "横图4K 竖图4K 人像",
            "横图4K 尺寸 1024x1024 人像",
            "分辨率 1024x1024 尺寸 1024x1536 cat",
            (
                "1024x1024 输出尺寸 1024x1024 "
                "尺寸 2048x2048 cat"
            ),
            (
                "横向4K 输出尺寸 3840x2160 "
                "尺寸 1024x1024 cat"
            ),
        )

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                with self.assertRaises(image_api.InvalidImageSizeError):
                    image_plugin.parse_generation_request(prompt)

    def test_unspecified_size_remains_none(self):
        request = image_plugin.parse_generation_request("樱花树下的少女")

        self.assertEqual(request.prompt, "樱花树下的少女")
        self.assertIsNone(request.dimensions)


class RequestedDimensionsValidationTests(unittest.TestCase):
    def setUp(self):
        self.client = make_client(
            (
                provider(image_api.ImageGenerationProviderKind.GPT),
                provider(image_api.ImageGenerationProviderKind.SEEDREAM),
            )
        )

    def test_seedream_global_boundary_is_accepted(self):
        self.client.validate_requested_dimensions(dimensions(4096, 4096))

    def test_non_positive_or_above_seedream_max_is_rejected(self):
        invalid_values = (
            (0, 1024),
            (1024, 0),
            (-16, 1024),
            (1024, -16),
            (4097, 1024),
            (1024, 4097),
            (5000, 5000),
        )

        for width, height in invalid_values:
            with self.subTest(width=width, height=height):
                with self.assertRaises(image_api.InvalidImageSizeError):
                    self.client.validate_requested_dimensions(
                        dimensions(width, height)
                    )

    def test_unsupported_by_gpt_but_supported_by_seedream_is_globally_valid(self):
        for width, height in (
            (800, 800),
            (1920, 1080),
            (3856, 1600),
            (4096, 4096),
        ):
            with self.subTest(width=width, height=height):
                self.client.validate_requested_dimensions(
                    dimensions(width, height)
                )


class ProviderDimensionCapabilityTests(unittest.TestCase):
    def test_gpt_accepts_each_exact_boundary(self):
        valid_values = (
            (640, 1024),       # 655,360 pixels: inclusive minimum.
            (2880, 2880),      # 8,294,400 pixels: inclusive maximum.
            (3840, 2160),      # Maximum edge and maximum pixels.
            (2160, 3840),
            (1920, 640),       # Inclusive 3:1 aspect ratio.
        )

        async def scenario(width, height):
            client = make_client(
                (provider(image_api.ImageGenerationProviderKind.GPT),)
            )
            transport = SequenceClient()
            with patch.object(
                image_api.httpx,
                "AsyncClient",
                return_value=transport,
            ):
                result = await client.generate(
                    "boundary test",
                    dimensions=dimensions(width, height),
                )
            return result, transport

        for width, height in valid_values:
            with self.subTest(width=width, height=height):
                result, transport = asyncio.run(scenario(width, height))
                self.assertEqual(result.model, "gpt-image-test")
                self.assertEqual(
                    transport.calls[0][2]["json"]["size"],
                    f"{width}x{height}",
                )

    def test_gpt_rejects_each_capability_violation_before_http(self):
        invalid_values = (
            (3856, 1600),      # Edge exceeds 3,840.
            (4096, 2160),      # Documented over-limit 4K variant.
            (1920, 1080),      # Height is not a multiple of 16.
            (3840, 2170),      # Documented non-multiple variant.
            (1936, 640),       # Aspect ratio exceeds 3:1.
            (3840, 1024),      # Documented over-3:1 variant.
            (800, 800),        # Pixel count is below 655,360.
            (512, 512),        # Documented below-minimum variant.
            (3840, 2176),      # Pixel count exceeds 8,294,400.
        )

        async def scenario(width, height):
            client = make_client(
                (provider(image_api.ImageGenerationProviderKind.GPT),)
            )
            with patch.object(image_api.httpx, "AsyncClient") as constructor:
                with self.assertRaises(image_api.InvalidImageSizeError):
                    await client.generate(
                        "invalid for GPT",
                        dimensions=dimensions(width, height),
                    )
            constructor.assert_not_called()

        for width, height in invalid_values:
            with self.subTest(width=width, height=height):
                asyncio.run(scenario(width, height))

    def test_invalid_numeric_default_is_configuration_error(self):
        async def scenario():
            client = image_api.ImageGenerationClient(
                providers=(
                    provider(image_api.ImageGenerationProviderKind.GPT),
                ),
                size="4096x2160",
                seedream_size="2K",
            )
            with self.assertRaises(
                image_api.ImageGenerationConfigurationError
            ):
                await client.generate("invalid configured default")

        asyncio.run(scenario())

    def test_unknown_default_size_tokens_are_configuration_errors(self):
        cases = (
            (
                provider(image_api.ImageGenerationProviderKind.GPT),
                {"size": "bogus", "seedream_size": "2K"},
            ),
            (
                provider(image_api.ImageGenerationProviderKind.SEEDREAM),
                {"size": "1024x1024", "seedream_size": "5K"},
            ),
        )

        async def scenario(configured_provider, configured_sizes):
            client = image_api.ImageGenerationClient(
                providers=(configured_provider,),
                **configured_sizes,
            )
            with patch.object(image_api.httpx, "AsyncClient") as constructor:
                with self.assertRaises(
                    image_api.ImageGenerationConfigurationError
                ):
                    await client.generate("invalid configured token")
            constructor.assert_not_called()

        for configured_provider, configured_sizes in cases:
            with self.subTest(kind=configured_provider.kind):
                asyncio.run(scenario(configured_provider, configured_sizes))

    def test_4096_square_skips_gpt_and_only_requests_seedream(self):
        async def scenario():
            client = make_client(
                (
                    provider(image_api.ImageGenerationProviderKind.GPT),
                    provider(image_api.ImageGenerationProviderKind.SEEDREAM),
                )
            )
            transport = SequenceClient()
            with patch.object(
                image_api.httpx,
                "AsyncClient",
                return_value=transport,
            ):
                result = await client.generate(
                    "large square",
                    dimensions=dimensions(4096, 4096),
                )
            return result, transport

        result, transport = asyncio.run(scenario())

        self.assertEqual(result.model, "seedream-test")
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(
            transport.calls[0][2]["json"],
            {
                "model": "seedream-test",
                "prompt": "large square",
                "size": "4096x4096",
            },
        )

    def test_seedream_only_size_reports_eligible_quota_scope(self):
        async def scenario():
            client = make_client(
                (
                    provider(image_api.ImageGenerationProviderKind.GPT),
                    provider(image_api.ImageGenerationProviderKind.SEEDREAM),
                )
            )
            transport = SequenceClient(
                (error_response(429, "insufficient_quota"),)
            )
            with patch.object(
                image_api.httpx,
                "AsyncClient",
                return_value=transport,
            ):
                await client.generate(
                    "large square",
                    dimensions=dimensions(4096, 4096),
                )

        with self.assertRaisesRegex(
            image_api.ImageGenerationQuotaExhaustedError,
            "支持当前分辨率的生图渠道",
        ):
            asyncio.run(scenario())

    def test_5000_square_is_rejected_before_http_client_construction(self):
        async def scenario():
            client = make_client(
                (
                    provider(image_api.ImageGenerationProviderKind.GPT),
                    provider(image_api.ImageGenerationProviderKind.SEEDREAM),
                )
            )
            with patch.object(image_api.httpx, "AsyncClient") as constructor:
                with self.assertRaises(image_api.InvalidImageSizeError):
                    await client.generate(
                        "too large",
                        dimensions=dimensions(5000, 5000),
                    )
            constructor.assert_not_called()

        asyncio.run(scenario())


class DimensionPayloadTests(unittest.TestCase):
    def setUp(self):
        self.gpt = provider(image_api.ImageGenerationProviderKind.GPT)
        self.seedream = provider(
            image_api.ImageGenerationProviderKind.SEEDREAM
        )
        self.client = make_client((self.gpt, self.seedream))
        self.reference = image_api.reference_image_from_bytes(PNG_BYTES)

    def test_gpt_natural_generation_uses_explicit_dimensions_in_json(self):
        async def scenario():
            transport = SequenceClient()
            await self.client._request_model(
                transport,
                provider=self.gpt,
                prompt="landscape",
                reference=None,
                dimensions=dimensions(3840, 2160),
            )
            return transport

        transport = asyncio.run(scenario())

        self.assertEqual(
            transport.calls[0][2]["json"]["size"],
            "3840x2160",
        )

    def test_gpt_reference_generation_uses_explicit_dimensions_in_multipart(self):
        async def scenario():
            transport = SequenceClient()
            await self.client._request_model(
                transport,
                provider=self.gpt,
                prompt="portrait edit",
                reference=self.reference,
                dimensions=dimensions(2160, 3840),
            )
            return transport

        transport = asyncio.run(scenario())
        call = transport.calls[0]

        self.assertTrue(call[1].endswith("/v1/images/edits"))
        self.assertEqual(call[2]["data"]["size"], "2160x3840")
        self.assertNotIn("json", call[2])

    def test_seedream_reference_generation_uses_explicit_dimensions_in_json(self):
        async def scenario():
            transport = SequenceClient()
            await self.client._request_model(
                transport,
                provider=self.seedream,
                prompt="large edit",
                reference=self.reference,
                dimensions=dimensions(4096, 4096),
            )
            return transport

        transport = asyncio.run(scenario())
        payload = transport.calls[0][2]["json"]

        self.assertEqual(payload["size"], "4096x4096")
        self.assertTrue(payload["image"].startswith("data:image/png;base64,"))

    def test_none_dimensions_preserves_provider_specific_defaults(self):
        async def scenario():
            gpt_transport = SequenceClient()
            seedream_transport = SequenceClient()
            await self.client._request_model(
                gpt_transport,
                provider=self.gpt,
                prompt="default GPT",
                reference=None,
                dimensions=None,
            )
            await self.client._request_model(
                seedream_transport,
                provider=self.seedream,
                prompt="default Seedream",
                reference=None,
                dimensions=None,
            )
            return gpt_transport, seedream_transport

        gpt_transport, seedream_transport = asyncio.run(scenario())

        self.assertEqual(
            gpt_transport.calls[0][2]["json"]["size"],
            "1024x1024",
        )
        self.assertEqual(
            seedream_transport.calls[0][2]["json"]["size"],
            "2K",
        )

    def test_numeric_configured_size_is_normalized_for_api_payload(self):
        async def scenario():
            client = image_api.ImageGenerationClient(
                providers=(self.gpt,),
                size="1920×1088",
                seedream_size="2K",
            )
            transport = SequenceClient()
            await client._request_model(
                transport,
                provider=self.gpt,
                prompt="normalized default",
                reference=None,
            )
            return transport

        transport = asyncio.run(scenario())

        self.assertEqual(
            transport.calls[0][2]["json"]["size"],
            "1920x1088",
        )


class DimensionBalancingTests(unittest.TestCase):
    def test_round_robin_fallback_keeps_explicit_dimensions(self):
        async def scenario():
            client = make_client(
                (
                    provider(image_api.ImageGenerationProviderKind.GPT),
                    provider(image_api.ImageGenerationProviderKind.SEEDREAM),
                )
            )
            transport = SequenceClient(
                (
                    error_response(429, "insufficient_quota"),
                    image_response(),
                    error_response(503, "no_available_channel"),
                    image_response(),
                )
            )
            with patch.object(
                image_api.httpx,
                "AsyncClient",
                return_value=transport,
            ):
                first = await client.generate(
                    "first",
                    dimensions=dimensions(3840, 2160),
                )
                second = await client.generate(
                    "second",
                    dimensions=dimensions(3840, 2160),
                )
            return first, second, transport

        first, second, transport = asyncio.run(scenario())

        self.assertEqual(first.model, "seedream-test")
        self.assertEqual(second.model, "gpt-image-test")
        self.assertEqual(
            [call[2]["json"]["model"] for call in transport.calls],
            [
                "gpt-image-test",
                "seedream-test",
                "seedream-test",
                "gpt-image-test",
            ],
        )
        self.assertEqual(
            [call[2]["json"]["size"] for call in transport.calls],
            ["3840x2160"] * 4,
        )


class DimensionPluginForwardingTests(unittest.TestCase):
    def test_configuration_failure_precedes_capacity_and_quota_reservation(self):
        async def scenario():
            matcher = types.SimpleNamespace(finish=AsyncMock())
            event = types.SimpleNamespace(
                attachments=None,
                reply=None,
                msg_elements=None,
                get_user_id=lambda: "config-failure-user",
            )
            with (
                patch.object(image_plugin, "generate_image", matcher),
                patch.object(
                    image_plugin.image_generation_client,
                    "validate_request",
                    side_effect=image_api.ImageGenerationConfigurationError(
                        "invalid default size"
                    ),
                ),
                patch.object(
                    image_plugin._generation_capacity,
                    "try_acquire",
                ) as acquire,
                patch.object(
                    image_plugin,
                    "reserve_user_request",
                ) as reserve_cooldown,
                patch.object(
                    image_plugin,
                    "reserve_daily_generation_usage",
                    new_callable=AsyncMock,
                ) as reserve_quota,
            ):
                await image_plugin.handle_generate_image(
                    event,
                    Message("1024x1024 skyline"),
                )
            return matcher, acquire, reserve_cooldown, reserve_quota

        matcher, acquire, reserve_cooldown, reserve_quota = asyncio.run(
            scenario()
        )

        acquire.assert_not_called()
        reserve_cooldown.assert_not_called()
        reserve_quota.assert_not_awaited()
        self.assertIn("尚未正确配置", matcher.finish.await_args.args[0])

    def test_handler_forwards_clean_prompt_and_dimensions(self):
        async def scenario():
            result = image_api.GeneratedImage(
                content=PNG_BYTES,
                media_type="image/png",
                filename="generated.png",
                model="gpt-image-test",
            )
            matcher = types.SimpleNamespace(finish=AsyncMock())
            event = types.SimpleNamespace(
                attachments=None,
                reply=None,
                msg_elements=None,
                get_user_id=lambda: "size-test-user",
            )
            with (
                patch.object(image_plugin, "generate_image", matcher),
                patch.object(
                    image_plugin,
                    "_generation_capacity",
                    image_plugin.GenerationCapacity(1),
                ),
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
                    return_value=result,
                ) as generate,
            ):
                await image_plugin.handle_generate_image(
                    event,
                    Message("3840x2160 skyline"),
                )
            return generate

        generate = asyncio.run(scenario())

        generate.assert_awaited_once_with(
            "skyline",
            reference=None,
            dimensions=dimensions(3840, 2160),
        )


if __name__ == "__main__":
    unittest.main()
