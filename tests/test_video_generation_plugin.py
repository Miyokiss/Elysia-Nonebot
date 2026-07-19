import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import nonebot

try:
    nonebot.get_driver()
except ValueError:
    nonebot.init(log_level="WARNING")

from nonebot.adapters.qq import Message
from nonebot.adapters.qq.exception import NetworkError

from src.clover_sqlite.models.image_generation import DailyQuotaStatus
from src.clover_videos.video_generation import (
    GeneratedVideo,
    MAX_PROMPT_LENGTH,
    VideoGenerationHTTPError,
    VideoGenerationMode,
    VideoGenerationQuotaExhaustedError,
    VideoGenerationTimeoutError,
)
from src.plugins import video_generation as video_plugin


def attachment(
    url: str,
    content_type: str | None,
    *,
    size: int | None = None,
    filename: str | None = None,
):
    return SimpleNamespace(
        url=url,
        content_type=content_type,
        size=size,
        filename=filename,
    )


def event_with_media(*, current=(), reply=(), elements=()):
    return SimpleNamespace(
        attachments=list(current),
        reply=SimpleNamespace(attachments=list(reply)) if reply else None,
        msg_elements=[SimpleNamespace(attachments=list(item)) for item in elements],
        get_user_id=lambda: "user-1",
    )


class VideoGenerationMediaTests(unittest.TestCase):
    def test_current_media_wins_over_reply_and_msg_elements(self):
        current = attachment(
            "https://media.test/current.png",
            "image/png",
            size=100,
        )
        replied = attachment(
            "https://media.test/replied.mp4",
            "video/mp4",
            size=200,
        )
        fallback = attachment(
            "https://media.test/fallback.mov",
            "video/quicktime",
            size=300,
        )

        media = video_plugin.find_reference_media(
            event_with_media(
                current=(current,),
                reply=(replied,),
                elements=((fallback,),),
            )
        )

        self.assertEqual(
            media,
            (
                video_plugin.InputMedia(
                    "image",
                    "https://media.test/current.png",
                    100,
                    None,
                ),
            ),
        )

    def test_reply_then_msg_elements_are_used_as_fallbacks(self):
        replied = attachment(
            "https://media.test/replied.mp4",
            "video/mp4",
            size=200,
        )
        fallback = attachment(
            "https://media.test/fallback.png",
            "image/png",
        )

        reply_media = video_plugin.find_reference_media(
            event_with_media(reply=(replied,), elements=((fallback,),))
        )
        element_media = video_plugin.find_reference_media(
            event_with_media(elements=((), (fallback,)))
        )

        self.assertEqual(reply_media[0].kind, "video")
        self.assertEqual(element_media[0].url, "https://media.test/fallback.png")

    def test_unknown_mime_can_use_filename_but_explicit_other_mime_is_ignored(self):
        inferred = attachment(
            "https://media.test/download?token=one",
            None,
            filename="clip.MP4",
        )
        ignored = attachment(
            "https://media.test/not-video.mp4",
            "application/pdf",
        )

        media = video_plugin.find_reference_media(
            event_with_media(current=(inferred, ignored))
        )

        self.assertEqual(len(media), 1)
        self.assertEqual(media[0].kind, "video")


class VideoGenerationCommandTests(unittest.TestCase):
    def test_three_modes_are_selected_from_command_and_media(self):
        text_request = video_plugin.parse_generation_request("海边日落")
        image_request = video_plugin.parse_generation_request(
            "让人物挥手",
            media=(
                video_plugin.InputMedia(
                    "image", "https://media.test/portrait.png"
                ),
            ),
        )
        video_request = video_plugin.parse_generation_request(
            "参考运镜",
            media=(
                video_plugin.InputMedia(
                    "image", "https://media.test/style.png"
                ),
                video_plugin.InputMedia(
                    "video", "https://media.test/motion.mp4"
                ),
            ),
        )

        self.assertIs(text_request.mode, VideoGenerationMode.TEXT)
        self.assertIs(image_request.mode, VideoGenerationMode.IMAGE)
        self.assertIs(video_request.mode, VideoGenerationMode.REFERENCE_VIDEO)
        self.assertEqual(
            video_request.image_urls,
            ("https://media.test/style.png",),
        )
        self.assertEqual(video_request.video_url, "https://media.test/motion.mp4")

    def test_explicit_modes_validate_required_and_conflicting_media(self):
        cases = (
            ("文生视频 风景", (video_plugin.InputMedia("image", "https://m.test/a.png"),)),
            ("图生视频 动起来", ()),
            ("参考视频 模仿运镜", (video_plugin.InputMedia("image", "https://m.test/a.png"),)),
            ("图生视频 动起来", (video_plugin.InputMedia("video", "https://m.test/a.mp4"),)),
        )
        for command, media in cases:
            with self.subTest(command=command):
                with self.assertRaises(video_plugin.VideoGenerationInputError):
                    video_plugin.parse_generation_request(command, media=media)

    def test_media_count_and_declared_size_limits_are_enforced(self):
        oversized_image = video_plugin.InputMedia(
            "image",
            "https://media.test/large.png",
            video_plugin.MAX_REFERENCE_IMAGE_BYTES + 1,
        )
        oversized_video = video_plugin.InputMedia(
            "video",
            "https://media.test/large.mp4",
            video_plugin.MAX_REFERENCE_VIDEO_BYTES + 1,
        )
        too_many_images = tuple(
            video_plugin.InputMedia("image", f"https://media.test/{index}.png")
            for index in range(5)
        )

        for media in ((oversized_image,), (oversized_video,), too_many_images):
            with self.subTest(media_count=len(media)):
                with self.assertRaises(video_plugin.VideoGenerationInputError):
                    video_plugin.parse_generation_request("生成", media=media)


class VideoDownloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_origin_download_uses_bearer_and_accepts_mp4(self):
        seen_authorization = None
        original_client = httpx.AsyncClient

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal seen_authorization
            seen_authorization = request.headers.get("Authorization")
            return httpx.Response(
                200,
                headers={"Content-Type": "video/mp4"},
                content=b"\x00\x00\x00\x18ftypisomvideo",
            )

        transport = httpx.MockTransport(handler)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "video.mp4"
            with patch.object(
                video_plugin.httpx,
                "AsyncClient",
                side_effect=lambda **kwargs: original_client(
                    transport=transport,
                    **kwargs,
                ),
            ):
                await video_plugin.download_generated_video(
                    f"{video_plugin.video_generation_base_url}/v1/videos/task/content",
                    destination,
                )

        self.assertEqual(
            seen_authorization,
            f"Bearer {video_plugin.video_generation_api_key}",
        )

    async def test_external_download_never_receives_api_authorization(self):
        seen_authorization = "unset"
        original_client = httpx.AsyncClient

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal seen_authorization
            seen_authorization = request.headers.get("Authorization")
            return httpx.Response(
                200,
                headers={"Content-Type": "video/mp4"},
                content=b"\x00\x00\x00\x18ftypisomvideo",
            )

        transport = httpx.MockTransport(handler)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "video.mp4"
            with patch.object(
                video_plugin.httpx,
                "AsyncClient",
                side_effect=lambda **kwargs: original_client(
                    transport=transport,
                    **kwargs,
                ),
            ):
                await video_plugin.download_generated_video(
                    "https://cdn.test/video.mp4",
                    destination,
                )

        self.assertIsNone(seen_authorization)

    async def test_invalid_body_and_oversized_response_are_rejected_and_cleaned(self):
        cases = (
            httpx.Response(
                200,
                headers={"Content-Type": "text/html"},
                content=b"<html>not video</html>",
            ),
            httpx.Response(
                200,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(
                        video_plugin.MAX_GENERATED_VIDEO_BYTES + 1
                    ),
                },
                content=b"",
            ),
        )
        original_client = httpx.AsyncClient
        for index, response in enumerate(cases):
            async def handler(request, response=response):
                response.request = request
                return response

            transport = httpx.MockTransport(handler)
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "video.mp4"
                with (
                    patch.object(
                        video_plugin.httpx,
                        "AsyncClient",
                        side_effect=lambda **kwargs: original_client(
                            transport=transport,
                            **kwargs,
                        ),
                    ),
                    self.assertRaises(video_plugin.VideoDeliveryError),
                ):
                    await video_plugin.download_generated_video(
                        "https://cdn.test/video.mp4",
                        destination,
                    )
                self.assertFalse(destination.exists())
                self.assertFalse(Path(f"{destination}.part").exists())


class VideoDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_result_uses_qq_remote_video(self):
        bot = SimpleNamespace(send=AsyncMock())
        result = GeneratedVideo(
            url="https://cdn.test/final.mp4",
            task_id="task-1",
            model="Seedance2.0",
        )

        await video_plugin._send_generated_video(bot, object(), result)

        message = bot.send.await_args.kwargs["message"]
        self.assertEqual(message.type, "video")
        self.assertEqual(message.data["url"], result.url)

    async def test_private_result_is_downloaded_and_local_file_is_cleaned(self):
        bot = SimpleNamespace(send=AsyncMock())
        result = GeneratedVideo(
            url=f"{video_plugin.video_generation_base_url}/v1/videos/task/content",
            task_id="task-2",
            model="Seedance2.0",
        )

        async def fake_download(url, destination):
            destination.write_bytes(b"video-data")
            return destination

        with tempfile.TemporaryDirectory() as directory, patch.object(
            video_plugin,
            "video_path",
            directory,
        ), patch.object(
            video_plugin,
            "download_generated_video",
            side_effect=fake_download,
        ) as download:
            await video_plugin._send_generated_video(bot, object(), result)
            self.assertEqual(list(Path(directory).iterdir()), [])

        download.assert_awaited_once()
        message = bot.send.await_args.kwargs["message"]
        self.assertEqual(message.type, "file_video")
        self.assertEqual(message.data["content"], b"video-data")

    async def test_remote_send_failure_falls_back_to_local_upload(self):
        bot = SimpleNamespace(
            send=AsyncMock(side_effect=[NetworkError("failed"), None])
        )
        result = GeneratedVideo(
            url="https://cdn.test/final.mp4",
            task_id="task-3",
            model="Seedance2.0",
        )

        async def fake_download(url, destination):
            destination.write_bytes(b"video-data")
            return destination

        with tempfile.TemporaryDirectory() as directory, patch.object(
            video_plugin,
            "video_path",
            directory,
        ), patch.object(
            video_plugin,
            "download_generated_video",
            side_effect=fake_download,
        ):
            await video_plugin._send_generated_video(bot, object(), result)

        self.assertEqual(bot.send.await_count, 2)
        self.assertEqual(
            bot.send.await_args_list[1].kwargs["message"].type,
            "file_video",
        )


class VideoGenerationHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_handler_reserves_quota_generates_and_sends(self):
        fake_event = event_with_media()
        fake_bot = object()
        result = GeneratedVideo(
            url="https://cdn.test/final.mp4",
            task_id="task-success",
            model="Seedance2.0",
        )
        capacity = SimpleNamespace(try_acquire=Mock(return_value=True), release=Mock())

        with (
            patch.object(video_plugin, "_generation_capacity", capacity),
            patch.object(video_plugin, "reserve_user_request", return_value=0),
            patch.object(
                video_plugin.ImageGenerationUsage,
                "reserve_daily_usage",
                AsyncMock(return_value=DailyQuotaStatus.ALLOWED),
            ) as reserve_quota,
            patch.object(
                video_plugin.video_generation_client,
                "generate",
                AsyncMock(return_value=result),
            ) as generate,
            patch.object(
                video_plugin,
                "_send_generated_video",
                AsyncMock(),
            ) as send_video,
            patch.object(video_plugin.generate_video, "send", AsyncMock()),
            patch.object(video_plugin.generate_video, "finish", AsyncMock()) as finish,
        ):
            await video_plugin.handle_generate_video(
                fake_event,
                fake_bot,
                Message("雨夜城市"),
            )

        reserve_quota.assert_awaited_once_with(
            "user-1",
            user_limit=video_plugin.video_generation_daily_user_limit,
            namespace="video_generation",
        )
        self.assertIs(generate.await_args.args[0].mode, VideoGenerationMode.TEXT)
        send_video.assert_awaited_once_with(fake_bot, fake_event, result)
        self.assertIn("生视频完成", finish.await_args.args[0])
        capacity.release.assert_called_once_with()

    async def test_invalid_prompt_is_rejected_before_capacity_or_api(self):
        fake_event = event_with_media()
        capacity = SimpleNamespace(
            try_acquire=Mock(return_value=True),
            release=Mock(),
        )

        with (
            patch.object(video_plugin, "_generation_capacity", capacity),
            patch.object(video_plugin.generate_video, "finish", AsyncMock()) as finish,
        ):
            await video_plugin.handle_generate_video(
                fake_event,
                object(),
                Message("x" * (MAX_PROMPT_LENGTH + 1)),
            )

        self.assertIn("不能超过", finish.await_args.args[0])
        capacity.try_acquire.assert_not_called()
        capacity.release.assert_not_called()

    async def test_quota_error_gets_specific_user_message_and_releases_capacity(self):
        fake_event = event_with_media()
        capacity = SimpleNamespace(try_acquire=Mock(return_value=True), release=Mock())

        with (
            patch.object(video_plugin, "_generation_capacity", capacity),
            patch.object(video_plugin, "reserve_user_request", return_value=0),
            patch.object(
                video_plugin.ImageGenerationUsage,
                "reserve_daily_usage",
                AsyncMock(return_value=DailyQuotaStatus.ALLOWED),
            ),
            patch.object(
                video_plugin.video_generation_client,
                "generate",
                AsyncMock(side_effect=VideoGenerationQuotaExhaustedError(403)),
            ),
            patch.object(video_plugin.generate_video, "send", AsyncMock()),
            patch.object(video_plugin.generate_video, "finish", AsyncMock()) as finish,
        ):
            await video_plugin.handle_generate_video(
                fake_event,
                object(),
                Message("雨夜城市"),
            )

        self.assertIn("额度不足", finish.await_args.args[0])
        capacity.release.assert_called_once_with()

    async def test_http_401_logs_diagnostics_and_reports_auth_failure(self):
        fake_event = event_with_media()
        capacity = SimpleNamespace(try_acquire=Mock(return_value=True), release=Mock())
        error = VideoGenerationHTTPError(
            401,
            code="invalid_token",
            error_type="new_api_error",
            detail="Invalid token",
            request_id="req-401-test",
        )

        with (
            patch.object(video_plugin, "_generation_capacity", capacity),
            patch.object(video_plugin, "reserve_user_request", return_value=0),
            patch.object(
                video_plugin.ImageGenerationUsage,
                "reserve_daily_usage",
                AsyncMock(return_value=DailyQuotaStatus.ALLOWED),
            ),
            patch.object(
                video_plugin.video_generation_client,
                "generate",
                AsyncMock(side_effect=error),
            ),
            patch.object(video_plugin.generate_video, "send", AsyncMock()),
            patch.object(video_plugin.generate_video, "finish", AsyncMock()) as finish,
            patch.object(video_plugin.logger, "warning", Mock()) as warning,
        ):
            await video_plugin.handle_generate_video(
                fake_event,
                object(),
                Message("雨夜城市"),
            )

        log_message = warning.call_args.args[0]
        self.assertIn("HTTP 401", log_message)
        self.assertIn("code=invalid_token", log_message)
        self.assertIn("type=new_api_error", log_message)
        self.assertIn("detail=Invalid token", log_message)
        self.assertIn("request_id=req-401-test", log_message)
        self.assertIn("鉴权失败", finish.await_args.args[0])
        capacity.release.assert_called_once_with()

    async def test_timeout_warns_against_duplicate_submission(self):
        fake_event = event_with_media()
        capacity = SimpleNamespace(try_acquire=Mock(return_value=True), release=Mock())

        with (
            patch.object(video_plugin, "_generation_capacity", capacity),
            patch.object(video_plugin, "reserve_user_request", return_value=0),
            patch.object(
                video_plugin.ImageGenerationUsage,
                "reserve_daily_usage",
                AsyncMock(return_value=DailyQuotaStatus.ALLOWED),
            ),
            patch.object(
                video_plugin.video_generation_client,
                "generate",
                AsyncMock(side_effect=VideoGenerationTimeoutError("timeout")),
            ),
            patch.object(video_plugin.generate_video, "send", AsyncMock()),
            patch.object(video_plugin.generate_video, "finish", AsyncMock()) as finish,
        ):
            await video_plugin.handle_generate_video(
                fake_event,
                object(),
                Message("雨夜城市"),
            )

        self.assertIn("请勿立即重复提交", finish.await_args.args[0])
        capacity.release.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
