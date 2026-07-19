import asyncio
import types
import unittest
from datetime import date
from io import BytesIO
from unittest.mock import AsyncMock, Mock, patch

import nonebot
from PIL import Image

try:
    nonebot.get_driver()
except ValueError:
    nonebot.init(log_level="WARNING")

from src.clover_image.image_generation import GeneratedImage, ImageDimensions
from src.clover_image.image_prompt_assistant import PromptAssistantRequestType
from src.clover_providers.cloud_file_api import rustfs as rustfs_module
from src.plugins import image_generation as image_plugin


class NativeMessageTests(unittest.TestCase):
    def test_markdown_and_keyboard_use_native_qq_models(self):
        message = image_plugin._native_markdown_message("## 完成")

        self.assertEqual(
            [segment.type for segment in message],
            ["markdown", "keyboard"],
        )
        self.assertEqual(
            message["markdown"][0].data["markdown"].content,
            "## 完成",
        )

        keyboard = message["keyboard"][0].data["keyboard"].model_dump()
        buttons = keyboard["content"]["rows"][0]["buttons"]
        self.assertEqual(
            [button["render_data"]["label"] for button in buttons],
            ["生图", "生图助手"],
        )
        self.assertEqual(
            [button["action"]["data"] for button in buttons],
            ["/生图 ", "/生图助手 "],
        )
        for button in buttons:
            with self.subTest(label=button["render_data"]["label"]):
                action = button["action"]
                self.assertEqual(action["type"], 2)
                self.assertEqual(action["permission"]["type"], 2)
                self.assertFalse(action["reply"])
                self.assertFalse(action["enter"])

    def test_assistant_keyboard_prefills_generated_prompt(self):
        prompt = 'Cafe\u0301\r\n雨夜\t*霓虹* "镜头" \\path @everyone'

        message = image_plugin._native_markdown_message(
            "## 反推提示词",
            generation_prompt=prompt,
        )

        keyboard = message["keyboard"][0].data["keyboard"].model_dump()
        buttons = keyboard["content"]["rows"][0]["buttons"]
        self.assertEqual(
            buttons[0]["action"]["data"],
            '/生图 Café 雨夜 *霓虹* "镜头" \\path @everyone',
        )
        self.assertEqual(buttons[1]["action"]["data"], "/生图助手 ")
        self.assertFalse(buttons[0]["action"]["enter"])

    def test_dynamic_keyboards_do_not_share_prompts(self):
        first = image_plugin._native_markdown_message(
            "first",
            generation_prompt="第一条提示词",
        )
        second = image_plugin._native_markdown_message(
            "second",
            generation_prompt="第二条提示词",
        )

        first_data = (
            first["keyboard"][0].data["keyboard"].content.rows[0].buttons[0].action.data
        )
        second_data = (
            second["keyboard"][0]
            .data["keyboard"]
            .content.rows[0]
            .buttons[0]
            .action.data
        )
        self.assertEqual(first_data, "/生图 第一条提示词")
        self.assertEqual(second_data, "/生图 第二条提示词")


class PublicModelVersionTests(unittest.TestCase):
    def test_known_model_names_are_reduced_to_public_versions(self):
        cases = {
            "gpt-image-2": "2",
            "doubao-seedream-5-0-260128": "5.0",
            "gpt-5.6-terra": "5.6",
            "provider/gpt-image-2": "2",
            "unrecognized-model": "未知",
        }

        for model, expected in cases.items():
            with self.subTest(model=model):
                self.assertEqual(
                    image_plugin._public_model_version(model),
                    expected,
                )


class CompletionTextTests(unittest.TestCase):
    def test_generation_markdown_contains_version_and_hosted_image(self):
        model = "provider/gpt-image-2"
        image_url = (
            "https://rustfs.example/generated/image.png?X-Amz-Signature=a+b&token=raw"
        )

        content = image_plugin._generation_completion_text(
            model=model,
            mode=image_plugin.ImageGenerationMode.REFERENCE,
            dimensions=ImageDimensions(1920, 1088),
            elapsed_seconds=1.236,
            remaining_quota="4 次",
            markdown=True,
            image_url=image_url,
            image_dimensions=ImageDimensions(640, 480),
        )

        self.assertIn(
            f"![生图 #640px #480px]({image_url})",
            content,
        )
        for expected in (
            "**版本**：2",
            "**模式**：参考图",
            "**分辨率**：1920x1088",
            r"**用时**：1\.24 秒",
            "**今日剩余**：4 次",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, content)
        self.assertNotIn("**模型**", content)
        self.assertNotIn(model, content)

    def test_prompt_markdown_escapes_content_and_only_shows_version(self):
        prompt = "雨夜 *霓虹* [镜头](url) #电影感!"
        model = "gpt-5.6-terra"

        content = image_plugin._prompt_assistant_completion_text(
            prompt=prompt,
            model=model,
            request_type=PromptAssistantRequestType.TEXT_TO_PROMPT,
            elapsed_seconds=2.5,
            remaining_quota="8 次",
            markdown=True,
        )

        self.assertIn(
            r"雨夜 \*霓虹\* \[镜头\]\(url\) \#电影感\!",
            content,
        )
        self.assertIn("**版本**：5\\.6", content)
        self.assertNotIn(prompt, content)
        self.assertNotIn("**模型**", content)
        self.assertNotIn(model, content)

    def test_prompt_plain_fallback_retains_prompt_and_details(self):
        prompt = "雨夜 *霓虹* [镜头](url) #电影感!"
        model = "doubao-seedream-5-0-260128"

        content = image_plugin._prompt_assistant_completion_text(
            prompt=prompt,
            model=model,
            request_type=PromptAssistantRequestType.IMAGE_TEXT_TO_PROMPT,
            elapsed_seconds=2.5,
            remaining_quota="8 次",
            markdown=False,
        )

        for expected in (
            prompt,
            "版本：5.0",
            "类型：图文反推",
            "用时：2.50 秒",
            "今日剩余：8 次",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, content)
        self.assertNotIn("模型：", content)
        self.assertNotIn(model, content)


class GeneratedImageDimensionsTests(unittest.TestCase):
    def test_reads_dimensions_from_generated_image_bytes(self):
        buffer = BytesIO()
        Image.new("RGB", (37, 19), color="white").save(buffer, format="PNG")

        dimensions = image_plugin._generated_image_dimensions(
            buffer.getvalue(),
            fallback=ImageDimensions(1024, 1024),
        )

        self.assertEqual(dimensions, ImageDimensions(37, 19))

    def test_invalid_image_bytes_use_supplied_fallback(self):
        fallback = ImageDimensions(1920, 1088)

        dimensions = image_plugin._generated_image_dimensions(
            b"not an image",
            fallback=fallback,
        )

        self.assertEqual(dimensions, fallback)


class HostedGeneratedImageTests(unittest.TestCase):
    def setUp(self):
        self.result = GeneratedImage(
            content=b"generated-image",
            media_type="image/jpeg",
            filename="generated.jpg",
            model="gpt-image-2",
        )
        self.dimensions = ImageDimensions(640, 480)

    def test_uploads_bytes_and_returns_download_url(self):
        upload_bytes = AsyncMock(return_value=True)
        get_download_url = AsyncMock(
            return_value="https://rustfs.example/generated.jpg?signature=raw"
        )
        delete_file = AsyncMock()

        with (
            patch.object(image_plugin.rustfs_api, "upload_bytes", upload_bytes),
            patch.object(
                image_plugin.rustfs_api,
                "get_download_url",
                get_download_url,
            ),
            patch.object(image_plugin.rustfs_api, "delete_file", delete_file),
            patch.object(
                image_plugin.uuid,
                "uuid4",
                return_value=types.SimpleNamespace(hex="fixed-id"),
            ),
        ):
            hosted = asyncio.run(
                image_plugin._host_generated_image(
                    self.result,
                    self.dimensions,
                )
            )

        self.assertIsNotNone(hosted)
        object_key = hosted.object_key
        self.assertRegex(
            object_key,
            r"^image-generation/\d{4}/\d{2}/\d{2}/fixed-id\.jpg$",
        )
        self.assertEqual(hosted.url, get_download_url.return_value)
        self.assertEqual(hosted.dimensions, self.dimensions)
        upload_bytes.assert_awaited_once_with(
            self.result.content,
            object_key,
            content_type="image/jpeg",
        )
        get_download_url.assert_awaited_once_with(
            object_key=object_key,
            expires_in=image_plugin._RUSTFS_IMAGE_URL_EXPIRES_SECONDS,
        )
        delete_file.assert_not_awaited()

    def test_upload_failure_skips_download_url(self):
        upload_bytes = AsyncMock(return_value=False)
        get_download_url = AsyncMock()

        with (
            patch.object(image_plugin.rustfs_api, "upload_bytes", upload_bytes),
            patch.object(
                image_plugin.rustfs_api,
                "get_download_url",
                get_download_url,
            ),
        ):
            hosted = asyncio.run(
                image_plugin._host_generated_image(
                    self.result,
                    self.dimensions,
                )
            )

        self.assertIsNone(hosted)
        get_download_url.assert_not_awaited()

    def test_missing_download_url_deletes_uploaded_object(self):
        upload_bytes = AsyncMock(return_value=True)
        get_download_url = AsyncMock(return_value="")
        delete_file = AsyncMock(return_value=True)

        with (
            patch.object(image_plugin.rustfs_api, "upload_bytes", upload_bytes),
            patch.object(
                image_plugin.rustfs_api,
                "get_download_url",
                get_download_url,
            ),
            patch.object(image_plugin.rustfs_api, "delete_file", delete_file),
            patch.object(
                image_plugin.uuid,
                "uuid4",
                return_value=types.SimpleNamespace(hex="failed-url"),
            ),
        ):
            hosted = asyncio.run(
                image_plugin._host_generated_image(
                    self.result,
                    self.dimensions,
                )
            )

        self.assertIsNone(hosted)
        object_key = upload_bytes.await_args.args[1]
        get_download_url.assert_awaited_once_with(
            object_key=object_key,
            expires_in=image_plugin._RUSTFS_IMAGE_URL_EXPIRES_SECONDS,
        )
        delete_file.assert_awaited_once_with(object_key=object_key)

    def test_cancellation_during_presign_deletes_uploaded_object(self):
        upload_bytes = AsyncMock(return_value=True)
        get_download_url = AsyncMock(side_effect=asyncio.CancelledError())
        delete_file = AsyncMock(return_value=True)

        with (
            patch.object(image_plugin.rustfs_api, "upload_bytes", upload_bytes),
            patch.object(
                image_plugin.rustfs_api,
                "get_download_url",
                get_download_url,
            ),
            patch.object(image_plugin.rustfs_api, "delete_file", delete_file),
        ):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(
                    image_plugin._host_generated_image(
                        self.result,
                        self.dimensions,
                    )
                )

        object_key = upload_bytes.await_args.args[1]
        delete_file.assert_awaited_once_with(object_key=object_key)

    def test_schedules_cleanup_after_presigned_url_expiry(self):
        async def scenario():
            delayed_delete = AsyncMock(return_value=True)
            cleanup_tasks = set()
            with (
                patch.object(
                    image_plugin.rustfs_api,
                    "delayed_delete_file",
                    delayed_delete,
                ),
                patch.object(
                    image_plugin,
                    "_hosted_image_cleanup_tasks",
                    cleanup_tasks,
                ),
            ):
                image_plugin._schedule_hosted_image_cleanup(
                    "image-generation/result.png"
                )
                await asyncio.gather(*tuple(cleanup_tasks))
            return delayed_delete

        delayed_delete = asyncio.run(scenario())

        delayed_delete.assert_awaited_once_with(
            "image-generation/result.png",
            delay=image_plugin._RUSTFS_IMAGE_DELETE_DELAY_SECONDS,
        )


class RustFSUploadBytesTests(unittest.TestCase):
    def test_put_object_includes_content_type_and_cancellation_cleanup(self):
        api = rustfs_module.RustFSAPI.__new__(rustfs_module.RustFSAPI)
        api.bucket_name = "default-bucket"
        api.s3 = Mock()
        run_sync = AsyncMock(return_value={})

        with patch.object(rustfs_module, "run_sync", run_sync):
            uploaded = asyncio.run(
                api.upload_bytes(
                    b"image bytes",
                    "generated/result.webp",
                    content_type="image/webp",
                )
            )

        self.assertTrue(uploaded)
        args = run_sync.await_args.args
        kwargs = run_sync.await_args.kwargs
        self.assertIs(args[0], api.s3.put_object)
        self.assertEqual(kwargs["Bucket"], "default-bucket")
        self.assertEqual(kwargs["Key"], "generated/result.webp")
        self.assertEqual(kwargs["Body"], b"image bytes")
        self.assertEqual(kwargs["ContentType"], "image/webp")
        cleanup = kwargs["_cancel_cleanup"]
        self.assertTrue(callable(cleanup))

        cleanup(None)

        api.s3.delete_object.assert_called_once_with(
            Bucket="default-bucket",
            Key="generated/result.webp",
        )

    def test_delayed_delete_retries_transient_failure(self):
        api = rustfs_module.RustFSAPI.__new__(rustfs_module.RustFSAPI)
        api.delete_file = AsyncMock(side_effect=[False, True])
        sleep = AsyncMock()

        with patch.object(rustfs_module.asyncio, "sleep", sleep):
            deleted = asyncio.run(
                api.delayed_delete_file(
                    "image-generation/result.png",
                    delay=3600,
                    attempts=3,
                    retry_delay=30,
                )
            )

        self.assertTrue(deleted)
        self.assertEqual(api.delete_file.await_count, 2)
        self.assertEqual(
            [call.args[0] for call in sleep.await_args_list],
            [3600, 30],
        )


class RemainingQuotaTextTests(unittest.TestCase):
    def test_finite_quota_subtracts_stored_usage(self):
        get_or_none = AsyncMock(return_value=types.SimpleNamespace(request_count=3))

        with patch.object(
            image_plugin.ImageGenerationUsage,
            "get_or_none",
            get_or_none,
        ):
            result = asyncio.run(
                image_plugin._remaining_daily_quota_text(
                    "user-1",
                    user_limit=10,
                    namespace="prompt_assistant",
                )
            )

        self.assertEqual(result, "7 次")
        get_or_none.assert_awaited_once_with(
            scope_id="prompt_assistant:user:user-1",
            request_date=date.today(),
        )

    def test_unlimited_quota_does_not_query_usage(self):
        get_or_none = AsyncMock()

        with patch.object(
            image_plugin.ImageGenerationUsage,
            "get_or_none",
            get_or_none,
        ):
            result = asyncio.run(
                image_plugin._remaining_daily_quota_text(
                    "user-2",
                    user_limit=0,
                )
            )

        self.assertEqual(result, "不限")
        get_or_none.assert_not_awaited()

    def test_query_error_returns_unknown(self):
        get_or_none = AsyncMock(side_effect=RuntimeError("database unavailable"))
        fake_logger = Mock()
        fake_logger.opt.return_value = fake_logger

        with (
            patch.object(
                image_plugin.ImageGenerationUsage,
                "get_or_none",
                get_or_none,
            ),
            patch.object(image_plugin, "logger", fake_logger),
        ):
            result = asyncio.run(
                image_plugin._remaining_daily_quota_text(
                    "user-3",
                    user_limit=10,
                )
            )

        self.assertEqual(result, "未知")
        fake_logger.warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
