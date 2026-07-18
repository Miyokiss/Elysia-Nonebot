import asyncio
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import nonebot

try:
    nonebot.get_driver()
except ValueError:
    nonebot.init(
        log_level="WARNING",
        qq_bots=[],
        kukufile_user_key="",
    )

from src.clover_videos.billibili import biliVideos
from src.plugins import bili_vid_search


class FakeDownloadResponse:
    def __init__(self, chunks=(), content_length=None):
        self.chunks = list(chunks)
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield from self.chunks


class FakeAsyncContent:
    def __init__(self, chunks):
        self.chunks = chunks

    async def iter_chunked(self, chunk_size):
        for chunk in self.chunks:
            yield chunk


class FakeAsyncDownloadResponse:
    def __init__(self, chunks=(), content_length=None):
        self.content = FakeAsyncContent(chunks)
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def raise_for_status(self):
        return None


class FakeAsyncSession:
    def __init__(self, response, **kwargs):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def get(self, *args, **kwargs):
        return self.response


class FakeApiResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.response = FakeApiResponse(payload)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def get(self, *args, **kwargs):
        return self.response


class BiliVideoInfoTests(unittest.TestCase):
    def test_playurl_metadata_is_preserved(self):
        payload = {
            "data": {
                "format": "mp4720",
                "durl": [
                    {
                        "url": "https://example.com/video.mp4",
                        "backup_url": ["https://backup.example.com/video.mp4", None],
                        "size": "47459739",
                        "length": 231040,
                    }
                ],
            }
        }
        with patch.object(
            biliVideos.requests, "Session", return_value=FakeSession(payload)
        ):
            result = biliVideos.get_video_file_info("BV1test", 123)

        self.assertEqual(result["url"], "https://example.com/video.mp4")
        self.assertEqual(result["backup_urls"], ["https://backup.example.com/video.mp4"])
        self.assertEqual(result["size"], 47_459_739)
        self.assertEqual(result["length"], 231_040)
        self.assertEqual(result["format"], "mp4720")

    def test_multi_segment_response_is_rejected(self):
        payload = {
            "data": {
                "durl": [
                    {"url": "https://example.com/part-1.mp4"},
                    {"url": "https://example.com/part-2.mp4"},
                ]
            }
        }
        with patch.object(
            biliVideos.requests, "Session", return_value=FakeSession(payload)
        ):
            result = biliVideos.get_video_file_info("BV1test", 123)

        self.assertIsNone(result)

    def test_legacy_url_helper_remains_compatible(self):
        with patch.object(
            biliVideos,
            "get_video_file_info",
            return_value={"url": "https://example.com/video.mp4"},
        ):
            result = biliVideos.get_video_file_url("BV1test", 123)

        self.assertEqual(result, "https://example.com/video.mp4")


class BiliVideoDownloadTests(unittest.TestCase):
    def test_expected_size_over_limit_skips_request(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "video.mp4"
            with patch.object(biliVideos.requests, "get") as request:
                result = biliVideos.video_download(
                    "https://example.com/video.mp4",
                    destination,
                    max_size=10,
                    expected_size=11,
                )

            self.assertFalse(result)
            request.assert_not_called()
            self.assertFalse(destination.exists())
            self.assertFalse(Path(f"{destination}.part").exists())

    def test_content_length_over_limit_is_rejected_before_write(self):
        response = FakeDownloadResponse(chunks=[b"unused"], content_length=11)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "video.mp4"
            with patch.object(biliVideos.requests, "get", return_value=response):
                result = biliVideos.video_download(
                    "https://example.com/video.mp4",
                    destination,
                    max_size=10,
                )

            self.assertFalse(result)
            self.assertFalse(destination.exists())
            self.assertFalse(Path(f"{destination}.part").exists())

    def test_stream_over_limit_removes_partial_file(self):
        response = FakeDownloadResponse(chunks=[b"12345678", b"abcd"])
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "video.mp4"
            with patch.object(biliVideos.requests, "get", return_value=response):
                result = biliVideos.video_download(
                    "https://example.com/video.mp4",
                    destination,
                    max_size=10,
                )

            self.assertFalse(result)
            self.assertFalse(destination.exists())
            self.assertFalse(Path(f"{destination}.part").exists())

    def test_expected_size_mismatch_removes_partial_file(self):
        response = FakeDownloadResponse(chunks=[b"abc"], content_length=3)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "video.mp4"
            with patch.object(biliVideos.requests, "get", return_value=response):
                result = biliVideos.video_download(
                    "https://example.com/video.mp4",
                    destination,
                    max_size=10,
                    expected_size=4,
                )

            self.assertFalse(result)
            self.assertFalse(destination.exists())
            self.assertFalse(Path(f"{destination}.part").exists())

    def test_successful_download_is_atomically_published(self):
        response = FakeDownloadResponse(chunks=[b"abc", b"def"], content_length=6)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "video.mp4"
            with patch.object(biliVideos.requests, "get", return_value=response):
                result = biliVideos.video_download(
                    "https://example.com/video.mp4",
                    destination,
                    max_size=10,
                    expected_size=6,
                )

            self.assertTrue(result)
            self.assertEqual(destination.read_bytes(), b"abcdef")
            self.assertFalse(Path(f"{destination}.part").exists())

    def test_async_stream_over_limit_removes_partial_file(self):
        async def scenario():
            response = FakeAsyncDownloadResponse(chunks=[b"abc", b"def"])
            with tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "video.mp4"
                with patch.object(
                    biliVideos.aiohttp,
                    "ClientSession",
                    side_effect=lambda **kwargs: FakeAsyncSession(
                        response, **kwargs
                    ),
                ):
                    result = await biliVideos.video_download_async(
                        "https://example.com/video.mp4",
                        destination,
                        max_size=5,
                    )

                self.assertFalse(result)
                self.assertFalse(destination.exists())
                self.assertFalse(Path(f"{destination}.part").exists())

        asyncio.run(scenario())

    def test_async_download_cancellation_removes_partial_file(self):
        async def scenario():
            started = asyncio.Event()

            class BlockingContent:
                async def iter_chunked(self, chunk_size):
                    yield b"partial"
                    started.set()
                    await asyncio.Event().wait()

            response = FakeAsyncDownloadResponse()
            response.content = BlockingContent()
            with tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "video.mp4"
                with patch.object(
                    biliVideos.aiohttp,
                    "ClientSession",
                    side_effect=lambda **kwargs: FakeAsyncSession(
                        response, **kwargs
                    ),
                ):
                    task = asyncio.create_task(
                        biliVideos.video_download_async(
                            "https://example.com/video.mp4", destination
                        )
                    )
                    await started.wait()
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task

                self.assertFalse(destination.exists())
                self.assertFalse(Path(f"{destination}.part").exists())

        asyncio.run(scenario())


class BiliVideoFallbackTests(unittest.TestCase):
    def test_qq_video_limit_boundary(self):
        limit = bili_vid_search.QQ_REMOTE_VIDEO_LIMIT
        self.assertFalse(bili_vid_search._should_use_video_fallback(limit - 1))
        self.assertFalse(bili_vid_search._should_use_video_fallback(limit))
        self.assertTrue(bili_vid_search._should_use_video_fallback(limit + 1))
        self.assertFalse(bili_vid_search._should_use_video_fallback(None))

    def test_large_video_bypasses_qq_remote_fetch(self):
        async def scenario():
            with (
                patch.object(
                    bili_vid_search.bili_bv_search,
                    "send",
                    new_callable=AsyncMock,
                ) as direct_send,
                patch.object(
                    bili_vid_search,
                    "post_video_kuku_file",
                    new_callable=AsyncMock,
                    return_value=False,
                ) as upload,
                patch.object(
                    bili_vid_search,
                    "_send_delayed_safely",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as delayed_send,
            ):
                await bili_vid_search._send_video_or_fallback(
                    "title",
                    "https://example.com/video.mp4",
                    123,
                    object(),
                    object(),
                    video_size=47_459_739,
                )

            direct_send.assert_not_awaited()
            upload.assert_awaited_once()
            self.assertEqual(
                upload.await_args.args,
                ("title", "https://example.com/video.mp4", 123),
            )
            self.assertEqual(upload.await_args.kwargs["video_size"], 47_459_739)
            delayed_send.assert_awaited_once()

        asyncio.run(scenario())

    def test_system_busy_can_fall_back_to_cloud_delivery(self):
        exc = types.SimpleNamespace(code=50015014)

        self.assertTrue(bili_vid_search._can_use_video_fallback(exc))

    def test_oversized_kukufile_video_is_rejected_before_download(self):
        async def scenario():
            with (
                patch.object(
                    bili_vid_search.biliVideos,
                    "video_download_async",
                    new_callable=AsyncMock,
                ) as download,
                patch.object(
                    bili_vid_search.Kukufile,
                    "upload_temporary_file",
                    new_callable=AsyncMock,
                ) as upload,
            ):
                result = await bili_vid_search.post_video_kuku_file(
                    "title",
                    "https://example.com/video.mp4",
                    123,
                    video_size=bili_vid_search.MAX_UPLOAD_SIZE + 1,
                )

            self.assertFalse(result)
            download.assert_not_awaited()
            upload.assert_not_awaited()

        asyncio.run(scenario())

    def test_delayed_message_preserves_original_event_context(self):
        async def scenario():
            event = object()
            bot = types.SimpleNamespace(send=AsyncMock())

            await bili_vid_search._send_delayed_message(bot, event, "result")

            bot.send.assert_awaited_once_with(event=event, message="result")

        asyncio.run(scenario())

    def test_cloud_fallback_returns_at_deadline_without_cancelling_cleanup(self):
        async def scenario():
            release = asyncio.Event()

            async def slow_upload(*args, **kwargs):
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    await release.wait()
                    raise

            with (
                patch.object(
                    bili_vid_search,
                    "CLOUD_FALLBACK_TIMEOUT_SECONDS",
                    0.001,
                ),
                patch.object(
                    bili_vid_search,
                    "post_video_kuku_file",
                    new=slow_upload,
                ),
            ):
                completed, result = await bili_vid_search._post_video_with_deadline(
                    "title", "url", 123
                )

                self.assertFalse(completed)
                self.assertIsNone(result)
                self.assertEqual(len(bili_vid_search._background_uploads), 1)
                release.set()
                await asyncio.gather(
                    *tuple(bili_vid_search._background_uploads),
                    return_exceptions=True,
                )
                await asyncio.sleep(0)

            self.assertFalse(bili_vid_search._background_uploads)

        asyncio.run(scenario())

    def test_search_result_falls_back_to_text_after_media_error(self):
        async def scenario():
            with patch.object(
                bili_vid_search.bili_vid,
                "send",
                new_callable=AsyncMock,
                side_effect=[RuntimeError("bad media"), None],
            ) as send:
                result = await bili_vid_search._send_search_result(
                    object(), "text result"
                )

            self.assertTrue(result)
            self.assertEqual(send.await_count, 2)
            self.assertEqual(send.await_args_list[1].args, ("text result",))

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
