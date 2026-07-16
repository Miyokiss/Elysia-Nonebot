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
            upload.assert_awaited_once_with(
                "title",
                "https://example.com/video.mp4",
                123,
                video_size=47_459_739,
            )
            delayed_send.assert_awaited_once()

        asyncio.run(scenario())

    def test_oversized_kukufile_video_is_rejected_before_download(self):
        async def scenario():
            with (
                patch.object(bili_vid_search.biliVideos, "video_download") as download,
                patch.object(
                    bili_vid_search.Kukufile,
                    "upload_file",
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
            download.assert_not_called()
            upload.assert_not_awaited()

        asyncio.run(scenario())

    def test_delayed_group_message_omits_reply_fields(self):
        class FakeGroupEvent:
            group_openid = "group-id"

        class FakeC2CEvent:
            pass

        async def scenario():
            bot = types.SimpleNamespace(
                send_to_group=AsyncMock(),
                send_to_c2c=AsyncMock(),
            )
            with (
                patch.object(
                    bili_vid_search, "GroupMessageCreateEvent", FakeGroupEvent
                ),
                patch.object(bili_vid_search, "C2CMessageCreateEvent", FakeC2CEvent),
            ):
                await bili_vid_search._send_delayed_message(
                    bot, FakeGroupEvent(), "result"
                )

            bot.send_to_group.assert_awaited_once_with(
                group_openid="group-id", message="result"
            )
            bot.send_to_c2c.assert_not_awaited()

        asyncio.run(scenario())

    def test_delayed_c2c_message_omits_reply_fields(self):
        class FakeGroupEvent:
            pass

        class FakeC2CEvent:
            author = types.SimpleNamespace(id="user-id")

        async def scenario():
            bot = types.SimpleNamespace(
                send_to_group=AsyncMock(),
                send_to_c2c=AsyncMock(),
            )
            with (
                patch.object(
                    bili_vid_search, "GroupMessageCreateEvent", FakeGroupEvent
                ),
                patch.object(bili_vid_search, "C2CMessageCreateEvent", FakeC2CEvent),
            ):
                await bili_vid_search._send_delayed_message(
                    bot, FakeC2CEvent(), "result"
                )

            bot.send_to_c2c.assert_awaited_once_with(
                openid="user-id", message="result"
            )
            bot.send_to_group.assert_not_awaited()

        asyncio.run(scenario())

    def test_delayed_guild_messages_omit_reply_fields(self):
        class FakeGroupEvent:
            pass

        class FakeC2CEvent:
            pass

        class FakeDirectEvent:
            guild_id = "guild-id"

        class FakeGuildEvent:
            channel_id = "channel-id"

        async def scenario():
            bot = types.SimpleNamespace(
                send_to_dms=AsyncMock(),
                send_to_channel=AsyncMock(),
            )
            with (
                patch.object(
                    bili_vid_search, "GroupMessageCreateEvent", FakeGroupEvent
                ),
                patch.object(bili_vid_search, "C2CMessageCreateEvent", FakeC2CEvent),
                patch.object(
                    bili_vid_search, "DirectMessageCreateEvent", FakeDirectEvent
                ),
                patch.object(bili_vid_search, "GuildMessageEvent", FakeGuildEvent),
            ):
                await bili_vid_search._send_delayed_message(
                    bot, FakeDirectEvent(), "direct-result"
                )
                await bili_vid_search._send_delayed_message(
                    bot, FakeGuildEvent(), "guild-result"
                )

            bot.send_to_dms.assert_awaited_once_with(
                guild_id="guild-id", message="direct-result"
            )
            bot.send_to_channel.assert_awaited_once_with(
                channel_id="channel-id", message="guild-result"
            )

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
