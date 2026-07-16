import asyncio
import importlib
import sys
import types
import unittest
from unittest.mock import ANY, AsyncMock, Mock, patch

import httpx

from src.clover_report.bili_hotwords import BiliHotwordFetchError


class _PlaywrightContext:
    def __init__(self):
        self.browser = types.SimpleNamespace(close=AsyncMock())
        self.playwright = types.SimpleNamespace(
            chromium=types.SimpleNamespace(launch=AsyncMock(return_value=self.browser))
        )

    async def __aenter__(self):
        return self.playwright

    async def __aexit__(self, exc_type, exc, traceback):
        return None


class DailyReportCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        htmlrender = types.ModuleType("nonebot_plugin_htmlrender")
        htmlrender.template_to_pic = AsyncMock(return_value=b"unused")
        cls.missing_attribute = object()
        cls.parent_module = importlib.import_module("src.clover_report")
        cls.original_parent_attribute = getattr(
            cls.parent_module,
            "data_source",
            cls.missing_attribute,
        )
        cls.module_name = "src.clover_report.data_source"
        cls.original_module = sys.modules.pop(cls.module_name, None)
        with patch.dict(sys.modules, {"nonebot_plugin_htmlrender": htmlrender}):
            cls.data_source = importlib.import_module(cls.module_name)

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop(cls.module_name, None)
        if cls.original_module is not None:
            sys.modules[cls.module_name] = cls.original_module
        if cls.original_parent_attribute is cls.missing_attribute:
            if hasattr(cls.parent_module, "data_source"):
                delattr(cls.parent_module, "data_source")
        else:
            cls.parent_module.data_source = cls.original_parent_attribute

    def _render_report(self, bili_result):
        report = self.data_source.Report
        playwright_context = _PlaywrightContext()
        get_bili = AsyncMock()
        if isinstance(bili_result, BaseException):
            get_bili.side_effect = bili_result
        else:
            get_bili.return_value = bili_result
        with (
            patch.object(self.data_source.os.path, "exists", return_value=False),
            patch.object(report, "get_hitokoto", AsyncMock(return_value="一言")),
            patch.object(report, "get_bili", get_bili),
            patch.object(report, "get_six", AsyncMock(return_value=["新闻"])),
            patch.object(report, "get_anime", AsyncMock(return_value=[])),
            patch.object(report, "get_it", AsyncMock(return_value=["资讯"])),
            patch.object(self.data_source, "get_festivals_dates", return_value=[]),
            patch.object(
                self.data_source,
                "async_playwright",
                return_value=playwright_context,
            ),
            patch.object(
                self.data_source,
                "template_to_pic",
                AsyncMock(return_value=b"report-image"),
            ),
            patch.object(
                self.data_source,
                "save_img",
                AsyncMock(),
            ) as save_img,
        ):
            result = asyncio.run(report.get_report_image())
        return result, save_img

    def test_bili_failure_returns_image_without_caching_it(self):
        result, save_img = self._render_report(
            BiliHotwordFetchError("all sources failed")
        )

        self.assertEqual(result, b"report-image")
        save_img.assert_not_awaited()

    def test_successful_bili_result_is_cached(self):
        result, save_img = self._render_report(["热点"])

        self.assertEqual(result, b"report-image")
        save_img.assert_awaited_once_with(b"report-image")

    def test_report_uses_current_and_legacy_bili_sources(self):
        fetch = AsyncMock(return_value=["热点"])
        report = self.data_source.Report

        with patch.object(self.data_source, "fetch_bili_hotwords", fetch):
            result = asyncio.run(report.get_bili())

        self.assertEqual(result, ["热点"])
        fetch.assert_awaited_once_with(
            self.data_source.AsyncHttpx.get,
            urls=(report.bili_url, report.bili_fallback_url),
        )

    def test_report_generation_is_serialized(self):
        report = self.data_source.Report
        active_generations = 0
        max_active_generations = 0

        async def generate():
            nonlocal active_generations, max_active_generations
            active_generations += 1
            max_active_generations = max(
                max_active_generations,
                active_generations,
            )
            await asyncio.sleep(0)
            active_generations -= 1
            return b"report-image"

        async def run_concurrently():
            return await asyncio.gather(
                report.get_report_image(),
                report.get_report_image(),
            )

        with patch.object(
            report,
            "_generate_report_image",
            AsyncMock(side_effect=generate),
        ):
            results = asyncio.run(run_concurrently())

        self.assertEqual(results, [b"report-image", b"report-image"])
        self.assertEqual(max_active_generations, 1)

    def test_retryable_request_errors_exclude_bilibili_412(self):
        request = httpx.Request("GET", "https://example.com")
        blocked = httpx.Response(412, request=request)
        unavailable = httpx.Response(503, request=request)

        self.assertFalse(
            self.data_source._is_retryable_request_error(
                httpx.HTTPStatusError(
                    "blocked",
                    request=request,
                    response=blocked,
                )
            )
        )
        self.assertTrue(
            self.data_source._is_retryable_request_error(
                httpx.HTTPStatusError(
                    "unavailable",
                    request=request,
                    response=unavailable,
                )
            )
        )
        self.assertTrue(
            self.data_source._is_retryable_request_error(
                httpx.ReadError("connection interrupted", request=request)
            )
        )


class _Matcher:
    def __init__(self):
        self.send = AsyncMock()
        self.finish = AsyncMock()

    def handle(self):
        return lambda function: function


class DailyReportPluginTests(unittest.TestCase):
    def test_generated_bytes_are_sent_without_a_cached_file(self):
        matcher = _Matcher()
        report = types.SimpleNamespace(
            get_report_image=AsyncMock(return_value=b"report-image")
        )
        attachment = object()
        file_image = Mock(return_value=attachment)

        nonebot = types.ModuleType("nonebot")
        nonebot.__path__ = []
        nonebot.logger = types.SimpleNamespace(error=lambda *args, **kwargs: None)
        adapters = types.ModuleType("nonebot.adapters")
        adapters.__path__ = []
        qq = types.ModuleType("nonebot.adapters.qq")
        qq.MessageSegment = types.SimpleNamespace(file_image=file_image)
        plugin_api = types.ModuleType("nonebot.plugin")
        plugin_api.on_command = lambda *args, **kwargs: matcher
        rule = types.ModuleType("nonebot.rule")
        rule.to_me = lambda: None
        data_source = types.ModuleType("src.clover_report.data_source")
        data_source.Report = report
        path_config = types.ModuleType("src.configs.path_config")
        path_config.temp_path = "unused/"

        module_name = "src.plugins.daily_report"
        parent_module = importlib.import_module("src.plugins")
        missing_attribute = object()
        original_parent_attribute = getattr(
            parent_module,
            "daily_report",
            missing_attribute,
        )
        original_module = sys.modules.pop(module_name, None)
        try:
            with patch.dict(
                sys.modules,
                {
                    "nonebot": nonebot,
                    "nonebot.adapters": adapters,
                    "nonebot.adapters.qq": qq,
                    "nonebot.plugin": plugin_api,
                    "nonebot.rule": rule,
                    "src.clover_report.data_source": data_source,
                    "src.configs.path_config": path_config,
                },
            ):
                daily_report = importlib.import_module(module_name)

            with patch.object(daily_report.os.path, "exists", return_value=False):
                asyncio.run(daily_report.handle_function())
        finally:
            sys.modules.pop(module_name, None)
            if original_module is not None:
                sys.modules[module_name] = original_module
            if original_parent_attribute is missing_attribute:
                if hasattr(parent_module, "daily_report"):
                    delattr(parent_module, "daily_report")
            else:
                parent_module.daily_report = original_parent_attribute

        report.get_report_image.assert_awaited_once_with()
        file_image.assert_called_once_with(
            b"report-image",
            file_name=ANY,
        )
        matcher.finish.assert_awaited_once_with(attachment)


if __name__ == "__main__":
    unittest.main()
