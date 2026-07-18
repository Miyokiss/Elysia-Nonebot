import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import nonebot

try:
    nonebot.get_driver()
except ValueError:
    nonebot.init(log_level="WARNING")

from src.clover_html import help as help_render


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, response=None, error=None, **kwargs):
        self.response = response
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, *args, **kwargs):
        if self.error is not None:
            raise self.error
        return self.response


class SlowClient(FakeClient):
    async def post(self, *args, **kwargs):
        await asyncio.Event().wait()


class HelpRenderTests(unittest.TestCase):
    def test_afdian_response_is_reduced_to_safe_template_data(self):
        result = help_render._parse_afdian_response(
            {
                "ec": 200,
                "data": {
                    "total_count": 4,
                    "list": [
                        {"user": {"name": "A", "avatar": "https://a"}},
                        {"user": {"name": "B", "avatar": "https://b"}},
                        {"user": {"name": "C", "avatar": "https://c"}},
                        {"user": {"name": "D", "avatar": "https://d"}},
                    ],
                },
            }
        )

        self.assertEqual(result["total_count"], 4)
        self.assertEqual([item["name"] for item in result["top_list"]], ["A", "B", "C"])

    def test_afdian_timeout_returns_empty_data(self):
        async def scenario():
            request = httpx.Request("POST", help_render.AFDIAN_URL)
            timeout = httpx.ReadTimeout("timed out", request=request)
            with patch.object(
                help_render.httpx,
                "AsyncClient",
                side_effect=lambda **kwargs: FakeClient(error=timeout),
            ):
                return await help_render.get_afdian_data()

        self.assertEqual(
            asyncio.run(scenario()),
            {"total_count": 0, "top_list": []},
        )

    def test_afdian_request_has_total_timeout(self):
        async def scenario():
            with (
                patch.object(
                    help_render.httpx,
                    "AsyncClient",
                    side_effect=lambda **kwargs: SlowClient(),
                ),
                patch.object(help_render, "AFDIAN_TOTAL_TIMEOUT_SECONDS", 0.001),
            ):
                return await help_render.get_afdian_data()

        self.assertEqual(
            asyncio.run(scenario()),
            {"total_count": 0, "top_list": []},
        )

    def test_concurrent_help_requests_share_one_render(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as directory:
                first = Path(directory) / "first.png"
                second = Path(directory) / "second.png"
                render = AsyncMock(return_value=b"image-bytes")
                with (
                    patch.object(help_render, "_help_image_cache", None),
                    patch.object(help_render, "_help_render_lock", asyncio.Lock()),
                    patch.object(help_render, "_render_help_image", render),
                ):
                    results = await asyncio.gather(
                        help_render.help_info_img([], str(first)),
                        help_render.help_info_img([], str(second)),
                    )

                self.assertEqual(results, [True, True])
                self.assertEqual(render.await_count, 1)
                self.assertEqual(first.read_bytes(), b"image-bytes")
                self.assertEqual(second.read_bytes(), b"image-bytes")

        asyncio.run(scenario())

    def test_template_render_has_total_timeout(self):
        async def never_finishes(**kwargs):
            await asyncio.Event().wait()

        async def scenario():
            with (
                patch.object(
                    help_render, "get_afdian_data", AsyncMock(return_value={})
                ),
                patch.object(help_render, "template_to_pic", new=never_finishes),
                patch.object(help_render, "HELP_RENDER_TIMEOUT_SECONDS", 0.001),
            ):
                await help_render._render_help_image([])

        with self.assertRaises(asyncio.TimeoutError):
            asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
