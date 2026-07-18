import asyncio
import importlib
import os
import tempfile
import threading
import unittest
import re
import sys
import types
from collections import namedtuple
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image

from src.clover_image.rua import rua
from src.clover_image.image_response import ImageServiceError, parse_xjh_image_response
from src.clover_lightnovel import wenku8
from src.clover_lightnovel.wenku8 import ProxyProviderError, parse_proxy_host
from src.clover_music.cloud_music.song_info import build_music_card_data
from src.clover_sqlite.tarot_resources import resolve_tarot_image_path
from src.utils.async_utils import run_sync
from src.utils.cache_cleanup import get_stale_files
from src.utils.log_sanitizer import sanitize_log_record
from src.utils.nonebot_compat import _patch_trie_rule


class LogSanitizerTests(unittest.TestCase):
    def test_failed_dispatch_payload_is_removed(self):
        record = {
            "message": (
                "Failed to parse event Dispatch(data={'content': 'secret', "
                "'auth_token': 'token'}, type='GROUP_MESSAGE_CREATE')"
            ),
            "exception": RuntimeError("contains raw payload"),
        }

        sanitize_log_record(record)

        self.assertEqual(
            record["message"],
            "QQ event parse failed: type=GROUP_MESSAGE_CREATE; "
            "error=RuntimeError; raw payload omitted",
        )
        self.assertNotIn("secret", record["message"])
        self.assertIsNone(record["exception"])

    def test_validation_location_is_kept_without_input(self):
        class FakeValidationError(Exception):
            def errors(self):
                return [
                    {
                        "loc": ("data", "author", "id"),
                        "type": "missing",
                        "input": "secret-user-data",
                    }
                ]

        record = {
            "message": (
                "Failed to parse event Dispatch(data={'content': 'secret'}, "
                "type='GROUP_AT_MESSAGE_CREATE')"
            ),
            "exception": FakeValidationError("secret-user-data"),
        }

        sanitize_log_record(record)

        self.assertIn(
            "error=FakeValidationError[data.author.id:missing]", record["message"]
        )
        self.assertNotIn("secret", record["message"])
        self.assertIsNone(record["exception"])

    def test_dispatch_type_comes_from_suffix_not_user_content(self):
        record = {
            "message": (
                "Failed to parse event Dispatch(data={'content': "
                "\"type='PRIVATE_SECRET'\"}, sequence=1, "
                "type='GROUP_MESSAGE_CREATE', id='event-id')"
            ),
            "exception": RuntimeError("secret"),
        }

        sanitize_log_record(record)

        self.assertIn("type=GROUP_MESSAGE_CREATE", record["message"])
        self.assertNotIn("PRIVATE_SECRET", record["message"])

    def test_qq_message_events_are_fully_removed(self):
        group_record = {
            "message": (
                "QQ | [EventType.GROUP_MESSAGE_CREATE]: "
                "https://multimedia.nt.qq.com.cn/download?appid=1&rkey=secret-token"
            ),
            "exception": None,
        }
        c2c_record = {
            "message": (
                "QQ | [EventType.C2C_MESSAGE_CREATE]: Message id from user:\n"
                "[Text(data={'text': 'private-secret'})]"
            ),
            "exception": None,
        }

        sanitize_log_record(group_record)
        sanitize_log_record(c2c_record)

        self.assertEqual(
            group_record["message"],
            "QQ | [EventType.GROUP_MESSAGE_CREATE]: message content omitted",
        )
        self.assertNotIn("secret-token", group_record["message"])
        self.assertEqual(
            c2c_record["message"],
            "QQ | [EventType.C2C_MESSAGE_CREATE]: message content omitted",
        )
        self.assertNotIn("private-secret", c2c_record["message"])

    def test_group_content_cannot_spoof_c2c_log_prefix(self):
        record = {
            "message": (
                "QQ | [EventType.GROUP_MESSAGE_CREATE]: user said "
                "[EventType.C2C_MESSAGE_CREATE] private marker"
            ),
            "exception": None,
        }

        sanitize_log_record(record)

        self.assertEqual(
            record["message"],
            "QQ | [EventType.GROUP_MESSAGE_CREATE]: message content omitted",
        )
        self.assertNotIn("private marker", record["message"])

    def test_openids_and_labeled_user_content_are_removed(self):
        record = {
            "message": (
                "点歌选择超时 User: 0123456789ABCDEF0123456789ABCDEF "
                "Keyword: private song"
            ),
            "exception": None,
        }

        sanitize_log_record(record)

        self.assertEqual(
            record["message"],
            "点歌选择超时 User: <openid omitted> Keyword: <text omitted>",
        )

    def test_multiline_labeled_content_is_removed(self):
        record = {
            "message": "回复等待超时 Content: first line\nprivate second line",
            "exception": None,
        }

        sanitize_log_record(record)

        self.assertEqual(
            record["message"],
            "回复等待超时 Content: <text omitted>",
        )

    def test_chat_and_credential_labels_are_removed(self):
        messages = [
            "Dify processed. Input: private prompt, Output: private answer",
            "Generating TTS\ntext：private speech",
            "request token: private-token",
            "生成超管注册密钥: private-admin-key",
            "code=500, message=private upstream body",
        ]

        for message in messages:
            with self.subTest(message=message):
                record = {"message": message, "exception": None}

                sanitize_log_record(record)

                self.assertNotIn("private", record["message"])
                self.assertIn("<text omitted>", record["message"])

    def test_exception_value_is_replaced_with_safe_summary(self):
        ExceptionRecord = namedtuple("ExceptionRecord", ("type", "value", "traceback"))
        secret = "0123456789ABCDEF0123456789ABCDEF"
        record = {
            "message": "operation failed",
            "exception": ExceptionRecord(
                RuntimeError,
                RuntimeError(f"private {secret}"),
                object(),
            ),
        }

        sanitize_log_record(record)

        self.assertEqual(
            str(record["exception"].value),
            "RuntimeError: details omitted",
        )
        self.assertNotIn(secret, str(record["exception"].value))


class ImageResponseTests(unittest.TestCase):
    def test_protocol_relative_image_url_is_normalized(self):
        result = parse_xjh_image_response(
            200, '{"img": "//img.xjh.me/image.jpg"}', "application/json"
        )
        self.assertEqual(result, "https://img.xjh.me/image.jpg")

    def test_html_error_response_is_rejected_without_body_details(self):
        with self.assertRaisesRegex(ImageServiceError, "HTTP 502") as raised:
            parse_xjh_image_response(502, "<html>private upstream body</html>")
        self.assertNotIn("private upstream body", str(raised.exception))

    def test_http_and_private_image_urls_are_rejected(self):
        for url in ("http://img.xjh.me/image.jpg", "https://127.0.0.1/image"):
            with self.subTest(url=url):
                with self.assertRaises(ImageServiceError):
                    parse_xjh_image_response(
                        200, f'{{"img": "{url}"}}', "application/json"
                    )


class MusicInfoTests(unittest.TestCase):
    def test_missing_high_quality_track_uses_available_quality(self):
        data = build_music_card_data(
            [
                {
                    "name": "Song",
                    "artists": [{"name": "Artist"}],
                    "alias": [],
                    "album": None,
                    "hMusic": None,
                    "mMusic": {"playTime": 125000},
                }
            ],
            None,
        )

        self.assertEqual(data["song_playTime"], "0:02:05")
        self.assertEqual(data["song_artists"], "Artist")
        self.assertEqual(data["song_imgurl"], "")
        self.assertEqual(data["song_comments"], [])


class NoneBotCompatibilityTests(unittest.TestCase):
    def test_empty_message_initializes_command_prefix_without_indexing(self):
        class FakeTrieRule:
            calls = 0

            @classmethod
            def get_value(cls, bot, event, state):
                cls.calls += 1
                return "original"

        class FakeEvent:
            def __init__(self, message):
                self.message = message

            def get_type(self):
                return "message"

            def get_message(self):
                return self.message

        _patch_trie_rule(FakeTrieRule, "prefix")
        state = {}

        result = FakeTrieRule.get_value(None, FakeEvent([]), state)

        self.assertEqual(result, state["prefix"])
        self.assertIsNone(state["prefix"]["command"])
        self.assertEqual(FakeTrieRule.calls, 0)
        self.assertEqual(
            FakeTrieRule.get_value(None, FakeEvent(["text"]), {}), "original"
        )
        self.assertEqual(FakeTrieRule.calls, 1)


class KukufileProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fake_nonebot = types.ModuleType("nonebot")
        fake_nonebot.logger = types.SimpleNamespace(
            warning=lambda *args, **kwargs: None,
            debug=lambda *args, **kwargs: None,
        )
        module_name = "src.clover_providers.cloud_file_api.kukufile"
        sys.modules.pop(module_name, None)
        with patch.dict(sys.modules, {"nonebot": fake_nonebot}):
            cls.kukufile = importlib.import_module(module_name)

    def test_explicit_ok_is_accepted_even_with_html_content_type(self):
        self.assertTrue(
            self.kukufile._auto_delete_succeeded("OK", "text/html; charset=utf-8")
        )
        self.assertFalse(
            self.kukufile._auto_delete_succeeded("OK:ERROR", "text/html; charset=utf-8")
        )

    def test_javascript_style_ok_is_accepted_with_html_content_type(self):
        self.assertTrue(
            self.kukufile._auto_delete_succeeded(
                "result=OK;", "text/html; charset=utf-8"
            )
        )
        self.assertFalse(
            self.kukufile._auto_delete_succeeded(
                "<html>result=OK;</html>", "text/html; charset=utf-8"
            )
        )

    def test_expiration_request_matches_browser_protocol(self):
        class FakeResponse:
            status_code = 200
            text = "result=OK;"
            headers = {"Content-Type": "text/html; charset=utf-8"}

        class FakeSession:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def post(self, *args, **kwargs):
                self.post_args = args
                self.post_kwargs = kwargs
                return FakeResponse()

        session = FakeSession()
        status = ["OK", "https://d.kuku.lu/test-hash"]
        with patch.object(self.kukufile, "_new_session", return_value=session):
            result = self.kukufile._set_expiration(status, 600)

        self.assertEqual(result, "result=OK;")
        self.assertEqual(session.post_args, ("https://d.kuku.lu/view.php",))
        self.assertEqual(session.post_kwargs["params"], {"hash": "test-hash"})
        self.assertEqual(session.post_kwargs["headers"]["Referer"], status[1])
        self.assertEqual(
            session.post_kwargs["data"],
            {"action": "addTimelimit", "set_timelimit": 600},
        )

    def test_html_challenge_is_not_accepted(self):
        self.assertFalse(
            self.kukufile._auto_delete_succeeded(
                "<html>Just a moment</html>", "text/html; charset=utf-8"
            )
        )

    def test_upload_response_rejects_untrusted_download_host(self):
        with self.assertRaises(self.kukufile.KukufileProtocolError):
            self.kukufile._parse_post_upload_response(
                "OK:https://example.com/not-a-kuku-file"
            )

    def test_non_object_server_response_is_a_protocol_error(self):
        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return []

        class FakeSession:
            def post(self, *args, **kwargs):
                return FakeResponse()

        with self.assertRaises(self.kukufile.KukufileProtocolError):
            self.kukufile._request_upload_server(FakeSession(), "probe.txt", 1)

    def test_upload_server_rejects_untrusted_host(self):
        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "result": "OK",
                    "servers": [
                        {
                            "method": "post",
                            "url": "https://127.0.0.1/upload.php",
                            "file_key": "",
                        }
                    ],
                }

        class FakeSession:
            def post(self, *args, **kwargs):
                return FakeResponse()

        with self.assertRaises(self.kukufile.KukufileProtocolError):
            self.kukufile._request_upload_server(FakeSession(), "probe.txt", 1)

    def test_upload_url_validator_rejects_non_strings(self):
        for value in (None, 123, {}, []):
            with self.subTest(value=value):
                self.assertFalse(self.kukufile._is_allowed_upload_url(value, "post"))

    def test_put_upload_uses_detected_media_type(self):
        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

        class FakeSession:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def put(self, *args, **kwargs):
                self.put_headers = kwargs["headers"]
                return FakeResponse()

        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "clip.mp4"
            file_path.write_bytes(b"video")
            session = FakeSession()
            with (
                patch.object(self.kukufile, "_new_session", return_value=session),
                patch.object(
                    self.kukufile,
                    "_request_upload_server",
                    return_value={
                        "method": "put",
                        "url": "https://bucket.r2.cloudflarestorage.com/clip",
                        "file_key": "clip-key",
                    },
                ),
                patch.object(
                    self.kukufile,
                    "_register_put_upload",
                    return_value=["OK", "https://d.kuku.lu/test-hash"],
                ),
            ):
                result = self.kukufile._upload_file(file_path, "clip.mp4")

        self.assertEqual(session.put_headers["Content-Type"], "video/mp4")
        self.assertEqual(result[0], "OK")

    def test_post_upload_keeps_large_file_write_timeout(self):
        class FakeResponse:
            status_code = 200
            text = "OK:https://d.kuku.lu/test-hash"

            def raise_for_status(self):
                return None

        class FakeSession:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def post(self, *args, **kwargs):
                self.post_kwargs = kwargs
                return FakeResponse()

        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "archive.zip"
            file_path.write_bytes(b"archive")
            session = FakeSession()
            with (
                patch.object(self.kukufile, "_new_session", return_value=session),
                patch.object(
                    self.kukufile,
                    "_request_upload_server",
                    return_value={
                        "method": "post",
                        "url": "https://tdc1-d.kuku.lu/upload.php",
                        "file_key": "",
                    },
                ),
            ):
                result = self.kukufile._upload_file(file_path, "archive.zip")

        self.assertEqual(result[0], "OK")
        self.assertEqual(session.post_kwargs["timeout"], (120, 300))

    def test_wrapped_write_timeout_has_actionable_description(self):
        protocol_error = (
            self.kukufile.requests.packages.urllib3.exceptions.ProtocolError(
                "connection aborted", TimeoutError("write timed out")
            )
        )
        error = self.kukufile.requests.ConnectionError(protocol_error)

        self.assertEqual(
            self.kukufile._describe_request_error(error),
            "上传连接写入超时",
        )

    def test_multipart_upload_stream_reads_in_bounded_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "upload.bin"
            file_path.write_bytes(b"x" * (self.kukufile.UPLOAD_CHUNK_SIZE * 2 + 17))
            stream = self.kukufile.MultipartUploadStream(
                file_path,
                "upload.bin",
                "application/octet-stream",
                {"ajax": "1"},
            )

            chunks = list(stream)

        self.assertEqual(sum(map(len, chunks)), len(stream))
        self.assertGreaterEqual(len(chunks), 5)
        self.assertTrue(
            all(len(chunk) <= self.kukufile.UPLOAD_CHUNK_SIZE for chunk in chunks[1:-1])
        )

    def test_async_multipart_upload_streams_bounded_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "upload.bin"
            file_path.write_bytes(b"x" * (self.kukufile.UPLOAD_CHUNK_SIZE * 2 + 17))
            stream = self.kukufile.MultipartUploadStream(
                file_path,
                "upload.bin",
                "application/octet-stream",
                {"ajax": "1"},
            )

            async def collect_chunks():
                return [
                    chunk
                    async for chunk in self.kukufile._iter_multipart_chunks(stream)
                ]

            chunks = asyncio.run(collect_chunks())

        self.assertEqual(sum(map(len, chunks)), len(stream))
        self.assertTrue(
            all(len(chunk) <= self.kukufile.UPLOAD_CHUNK_SIZE for chunk in chunks[1:-1])
        )

    def test_async_post_upload_preserves_content_length(self):
        class FakeResponse:
            status_code = 200
            text = "OK:https://d.kuku.lu/test-hash"

            def raise_for_status(self):
                return None

        class FakeAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, *args, **kwargs):
                self.post_kwargs = kwargs
                self.body = b"".join([chunk async for chunk in kwargs["content"]])
                return FakeResponse()

        async def scenario(file_path, client):
            with (
                patch.object(
                    self.kukufile,
                    "_new_async_client",
                    return_value=client,
                ),
                patch.object(
                    self.kukufile,
                    "_request_upload_server_async",
                    new_callable=AsyncMock,
                    return_value={
                        "method": "post",
                        "url": "https://tdc1-d.kuku.lu/upload.php",
                    },
                ),
            ):
                return await self.kukufile._upload_file_async(file_path, "upload.bin")

        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "upload.bin"
            file_path.write_bytes(b"payload")
            client = FakeAsyncClient()
            result = asyncio.run(scenario(file_path, client))

        self.assertEqual(result[0], "OK")
        self.assertEqual(
            len(client.body), int(client.post_kwargs["headers"]["Content-Length"])
        )
        self.assertIn(b"payload", client.body)

    def test_upload_file_handles_file_removed_after_existence_check(self):
        with (
            patch.object(self.kukufile.Path, "is_file", return_value=True),
            patch.object(
                self.kukufile.Path,
                "stat",
                side_effect=FileNotFoundError("file removed"),
            ),
            patch.object(self.kukufile, "_upload_file") as upload,
        ):
            result = asyncio.run(self.kukufile.Kukufile.upload_file("removed-file.bin"))

        self.assertIsNone(result)
        upload.assert_not_called()

    def test_temporary_upload_sets_expiration_before_returning(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "upload.bin"
            file_path.write_bytes(b"test")
            status = ["OK", "https://d.kuku.lu/test-hash"]
            with (
                patch.object(
                    self.kukufile,
                    "_upload_file_async",
                    new_callable=AsyncMock,
                    return_value=status,
                ) as upload,
                patch.object(
                    self.kukufile,
                    "_expire_with_retry",
                    new_callable=AsyncMock,
                    return_value="OK",
                ) as expire,
            ):
                result = asyncio.run(
                    self.kukufile.Kukufile.upload_temporary_file(file_path)
                )

        self.assertEqual(result, status)
        upload.assert_awaited_once()
        expire.assert_awaited_once_with(status, 600)

    def test_cancelled_temporary_upload_compensates_remote_expiration(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "upload.bin"
            file_path.write_bytes(b"test")
            status = ["OK", "https://d.kuku.lu/test-hash"]
            expiration_started = asyncio.Event()
            expiration_calls = 0

            async def expire(*args):
                nonlocal expiration_calls
                expiration_calls += 1
                if expiration_calls == 1:
                    expiration_started.set()
                    await asyncio.Event().wait()
                return "OK"

            async def scenario():
                with (
                    patch.object(
                        self.kukufile,
                        "_upload_file_async",
                        new_callable=AsyncMock,
                        return_value=status,
                    ),
                    patch.object(
                        self.kukufile,
                        "_expire_with_retry",
                        new_callable=AsyncMock,
                        side_effect=expire,
                    ),
                ):
                    task = asyncio.create_task(
                        self.kukufile.Kukufile.upload_temporary_file(file_path)
                    )
                    await expiration_started.wait()
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task

            asyncio.run(scenario())

        self.assertEqual(expiration_calls, 2)

    def test_repeated_cancel_does_not_stop_expiration_compensation(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "upload.bin"
            file_path.write_bytes(b"test")
            status = ["OK", "https://d.kuku.lu/test-hash"]

            async def scenario():
                initial_expiration_started = asyncio.Event()
                cleanup_started = asyncio.Event()
                release_cleanup = asyncio.Event()
                cleanup_cancelled = False
                expiration_calls = 0

                async def expire(*args):
                    nonlocal cleanup_cancelled, expiration_calls
                    expiration_calls += 1
                    if expiration_calls == 1:
                        initial_expiration_started.set()
                        await asyncio.Event().wait()
                    cleanup_started.set()
                    try:
                        await release_cleanup.wait()
                    except asyncio.CancelledError:
                        cleanup_cancelled = True
                        raise
                    return "OK"

                with (
                    patch.object(
                        self.kukufile,
                        "_upload_file_async",
                        new_callable=AsyncMock,
                        return_value=status,
                    ),
                    patch.object(
                        self.kukufile,
                        "_expire_with_retry",
                        new_callable=AsyncMock,
                        side_effect=expire,
                    ),
                ):
                    task = asyncio.create_task(
                        self.kukufile.Kukufile.upload_temporary_file(file_path)
                    )
                    await initial_expiration_started.wait()
                    task.cancel()
                    await cleanup_started.wait()
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task

                    self.assertFalse(cleanup_cancelled)
                    self.assertEqual(len(self.kukufile._expiration_cleanup_tasks), 1)
                    release_cleanup.set()
                    await asyncio.gather(
                        *tuple(self.kukufile._expiration_cleanup_tasks)
                    )
                    await asyncio.sleep(0)

                self.assertFalse(cleanup_cancelled)
                self.assertFalse(self.kukufile._expiration_cleanup_tasks)

            asyncio.run(scenario())

    def test_cancelled_successful_upload_sets_remote_expiration(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "upload.bin"
            file_path.write_bytes(b"test")
            started = threading.Event()
            release = threading.Event()
            status = ["OK", "https://d.kuku.lu/test-hash"]

            def fake_upload(path, name):
                started.set()
                release.wait(timeout=2)
                return status

            with (
                patch.object(self.kukufile, "_upload_file", side_effect=fake_upload),
                patch.object(
                    self.kukufile, "_set_expiration", return_value="OK"
                ) as set_expiration,
            ):

                async def scenario():
                    task = asyncio.create_task(
                        self.kukufile.Kukufile.upload_file(file_path)
                    )
                    while not started.is_set():
                        await asyncio.sleep(0)
                    task.cancel()
                    release.set()
                    with self.assertRaises(asyncio.CancelledError):
                        await task

                asyncio.run(scenario())

        set_expiration.assert_called_once_with(status, 600)


class CacheCleanupTests(unittest.TestCase):
    def test_only_stale_files_are_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stale = root / "stale.tmp"
            recent = root / "recent.tmp"
            stale.write_text("old", encoding="utf-8")
            recent.write_text("new", encoding="utf-8")
            os.utime(stale, (100, 100))
            os.utime(recent, (950, 950))

            selected = get_stale_files(root, max_age_seconds=100, now=1000)

            self.assertEqual(selected, [stale])


class ProxyResponseTests(unittest.TestCase):
    def test_disabled_proxy_does_not_call_provider(self):
        with (
            patch.object(wenku8.api_config, "proxy_api_enabled", False, create=True),
            patch.object(wenku8.requests, "get") as request,
        ):
            self.assertIsNone(wenku8.get_proxy({"User-Agent": "test"}))
        request.assert_not_called()

    def test_plain_proxy_address_is_accepted(self):
        self.assertEqual(parse_proxy_host("127.0.0.1:8080\n"), "127.0.0.1:8080")

    def test_json_proxy_address_is_accepted(self):
        payload = '{"code": 200, "success": true, "data": ["10.0.0.1:3128"]}'
        self.assertEqual(parse_proxy_host(payload), "10.0.0.1:3128")

    def test_expired_proxy_plan_is_rejected(self):
        payload = '{"code": 601, "success": false, "data": [], "msg": "plan expired"}'
        with self.assertRaisesRegex(ProxyProviderError, "plan expired"):
            parse_proxy_host(payload)

    def test_malformed_proxy_address_is_rejected(self):
        with self.assertRaises(ProxyProviderError):
            parse_proxy_host("not-a-proxy")


class RuaImageModeTests(unittest.TestCase):
    def test_one_bit_avatar_generates_unique_gifs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            overlays = root / "overlays"
            output = root / "output"
            overlays.mkdir()
            output.mkdir()

            avatar = root / "avatar.png"
            Image.new("1", (100, 100), 1).save(avatar)
            for index in range(1, 11):
                Image.new("RGBA", (110, 110), (index, 0, 0, 80)).save(
                    overlays / f"{index}.png"
                )

            with (
                patch("src.clover_image.rua.rua_png", str(overlays)),
                patch("src.clover_image.rua.image_local_qq_image_path", str(output)),
            ):
                first = Path(rua(avatar).add_gif())
                second = Path(rua(avatar).add_gif())

            self.assertTrue(first.is_file())
            self.assertTrue(second.is_file())
            self.assertNotEqual(first, second)
            with Image.open(first) as generated:
                self.assertEqual(generated.format, "GIF")
                self.assertGreater(generated.n_frames, 1)


class TarotResourceTests(unittest.TestCase):
    def test_all_card_image_references_exist(self):
        project_root = Path(__file__).resolve().parents[1]
        model_path = project_root / "src" / "clover_sqlite" / "models" / "tarot.py"
        image_dir = (
            project_root / "src" / "resources" / "image" / "tarot" / "TarotImages"
        )
        references = set(
            re.findall(
                r'image="([^\"]+\.(?:jpg|png))"', model_path.read_text(encoding="utf-8")
            )
        )
        missing = sorted(
            name for name in references if not (image_dir / name).is_file()
        )
        self.assertEqual(missing, [])

    def test_legacy_jpg_record_resolves_to_deployed_png(self):
        resolved = Path(resolve_tarot_image_path("Nine of Wands.jpg"))
        self.assertTrue(resolved.is_file())
        self.assertEqual(resolved.name, "Nine of Wands.png")


class AsyncRunSyncTests(unittest.TestCase):
    def test_cancel_waits_for_worker_and_cleans_result(self):
        with tempfile.TemporaryDirectory() as directory:
            result_path = Path(directory) / "result.tmp"
            started = threading.Event()
            release = threading.Event()

            def blocking_work():
                started.set()
                release.wait(timeout=2)
                result_path.write_text("complete", encoding="utf-8")
                return str(result_path)

            def cleanup(result):
                if result:
                    Path(result).unlink(missing_ok=True)

            async def scenario():
                task = asyncio.create_task(
                    run_sync(blocking_work, _cancel_cleanup=cleanup)
                )
                while not started.is_set():
                    await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
                self.assertFalse(task.done())
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await task

            asyncio.run(scenario())
            self.assertFalse(result_path.exists())


if __name__ == "__main__":
    unittest.main()
