import asyncio
import os
import tempfile
import threading
import unittest
import re
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from src.clover_image.rua import rua
from src.clover_lightnovel import wenku8
from src.clover_lightnovel.wenku8 import ProxyProviderError, parse_proxy_host
from src.clover_sqlite.tarot_resources import resolve_tarot_image_path
from src.utils.async_utils import run_sync
from src.utils.cache_cleanup import get_stale_files
from src.utils.log_sanitizer import sanitize_log_record


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
            "QQ event parse failed: type=GROUP_MESSAGE_CREATE; raw payload omitted",
        )
        self.assertNotIn("secret", record["message"])
        self.assertIsNone(record["exception"])


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
        image_dir = project_root / "src" / "resources" / "image" / "tarot" / "TarotImages"
        references = set(
            re.findall(r'image="([^\"]+\.(?:jpg|png))"', model_path.read_text(encoding="utf-8"))
        )
        missing = sorted(name for name in references if not (image_dir / name).is_file())
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
