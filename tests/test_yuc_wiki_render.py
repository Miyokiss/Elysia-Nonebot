import asyncio
import importlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch


class _PageContext:
    def __init__(self, page):
        self.page = page

    async def __aenter__(self):
        return self.page

    async def __aexit__(self, exc_type, exc, traceback):
        return None


class YucWikiRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        htmlrender = types.ModuleType("nonebot_plugin_htmlrender")
        htmlrender.get_new_page = Mock()

        cls.missing_attribute = object()
        cls.parent_module = importlib.import_module("src.clover_yuc_wiki")
        cls.original_parent_attribute = getattr(
            cls.parent_module,
            "yuc_wiki",
            cls.missing_attribute,
        )
        cls.module_name = "src.clover_yuc_wiki.yuc_wiki"
        cls.original_module = sys.modules.pop(cls.module_name, None)
        with patch.dict(sys.modules, {"nonebot_plugin_htmlrender": htmlrender}):
            cls.yuc_wiki = importlib.import_module(cls.module_name)

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop(cls.module_name, None)
        if cls.original_module is not None:
            sys.modules[cls.module_name] = cls.original_module
        if cls.original_parent_attribute is cls.missing_attribute:
            if hasattr(cls.parent_module, "yuc_wiki"):
                delattr(cls.parent_module, "yuc_wiki")
        else:
            cls.parent_module.yuc_wiki = cls.original_parent_attribute

    def test_resource_urls_are_normalized_without_mangling_hosts(self):
        normalize = self.yuc_wiki._absolute_resource_url

        self.assertEqual(
            normalize("//fonts.example.com/font.css"),
            "https://fonts.example.com/font.css",
        )
        self.assertEqual(
            normalize(r"\lib\theme\main.css"),
            "https://yuc.wiki/lib/theme/main.css",
        )
        self.assertEqual(
            normalize("http://cdn.example.com/image.png"),
            "https://cdn.example.com/image.png",
        )
        self.assertEqual(
            normalize("/css/main.css"),
            "https://yuc.wiki/css/main.css",
        )

    def test_dispose_html_uses_local_noto_fonts(self):
        response = Mock()
        response.raise_for_status = Mock()
        html = """
<!doctype html>
<html>
<head>
  <link rel="stylesheet" href="/css/main.css">
  <link rel="stylesheet" href="//fonts.loli.net/css?family=Lato">
  <link rel="stylesheet" href="\\lib\\font-awesome\\font-awesome.css">
  <script src="/js/site.js"></script>
</head>
<body>
  <header>header</header>
  <p>本季新番</p>
  <div class="toggle">site toggle</div>
  <i class="fa fa-tv">site icon</i>
  <img data-src="http://cdn.example.com/anime.jpg">
  <aside>aside</aside>
</body>
</html>
"""
        response.content = html.encode("utf-8")
        response.text = "æ¬å­£æ°çª"

        soup = asyncio.run(self.yuc_wiki.dispose_html(response))

        response.raise_for_status.assert_called_once_with()
        self.assertIsNone(soup.find("script"))
        self.assertIsNone(soup.find("header"))
        self.assertIsNone(soup.find("aside"))
        self.assertIsNone(soup.select_one(".toggle"))
        self.assertIsNone(soup.select_one(".fa"))
        self.assertIn("本季新番", soup.get_text())
        self.assertNotIn(response.text, soup.get_text())
        self.assertIsNone(soup.find(href=lambda value: value and "fonts.loli" in value))
        self.assertIsNotNone(soup.find(href="https://yuc.wiki/css/main.css"))
        self.assertIsNone(
            soup.find(href=lambda value: value and "font-awesome" in value)
        )
        image = soup.find("img")
        self.assertEqual(image["src"], "https://cdn.example.com/anime.jpg")
        self.assertNotIn("data-src", image.attrs)

        style = soup.find("style", id="elysia-yuc-local-fonts")
        self.assertEqual(
            style["data-render-version"],
            self.yuc_wiki.RENDER_CACHE_VERSION,
        )
        css = style.string or ""
        self.assertIn(self.yuc_wiki.REGULAR_FONT.resolve().as_uri(), css)
        self.assertIn(self.yuc_wiki.BOLD_FONT.resolve().as_uri(), css)
        self.assertIn('font-family: "Elysia Noto Sans SC"', css)
        self.assertEqual(css.count("font-display: block"), 2)

    def test_renderer_waits_for_fonts_and_uses_versioned_cache(self):
        events = []

        async def goto(*args, **kwargs):
            events.append("goto")

        async def evaluate(expression):
            events.append(expression)

        async def screenshot(**kwargs):
            events.append("screenshot")
            return b"rendered-image"

        page = types.SimpleNamespace(
            goto=AsyncMock(side_effect=goto),
            evaluate=AsyncMock(side_effect=evaluate),
            screenshot=AsyncMock(side_effect=screenshot),
        )
        get_new_page = Mock(return_value=_PageContext(page))

        with tempfile.TemporaryDirectory() as directory:
            html_file = Path(directory) / "202607.html"
            html_file.write_text("<html></html>", encoding="utf-8")
            with (
                patch.object(self.yuc_wiki, "yuc_wiki_path", directory),
                patch.object(self.yuc_wiki, "get_new_page", get_new_page),
            ):
                first = asyncio.run(
                    self.yuc_wiki.get_yuc_wiki_image("202607", 568, 1885)
                )
                second = asyncio.run(
                    self.yuc_wiki.get_yuc_wiki_image("202607", 568, 1885)
                )
                image_file = self.yuc_wiki._image_file("202607")

            self.assertEqual(first, b"rendered-image")
            self.assertEqual(second, b"rendered-image")
            self.assertEqual(
                image_file.name,
                f"202607.{self.yuc_wiki.RENDER_CACHE_VERSION}.jpeg",
            )
            self.assertEqual(image_file.read_bytes(), b"rendered-image")

        self.assertEqual(
            events,
            ["goto", "document.fonts.ready", "screenshot"],
        )
        get_new_page.assert_called_once_with(
            device_scale_factor=2,
            viewport={"width": 568, "height": 1885},
        )
        page.goto.assert_awaited_once_with(
            html_file.resolve().as_uri(),
            wait_until="networkidle",
        )
        page.screenshot.assert_awaited_once_with(
            full_page=True,
            type="jpeg",
            quality=40,
        )


if __name__ == "__main__":
    unittest.main()
