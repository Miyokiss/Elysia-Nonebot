from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from nonebot_plugin_htmlrender import get_new_page

from src.configs.path_config import yuc_wiki_path


BASE_URL = "https://yuc.wiki/"
FORECAST_URL = "https://yuc.wiki/new"
FONT_FAMILY = "Elysia Noto Sans SC"
RENDER_CACHE_VERSION = "utf8-noto-v2"

FONT_DIR = Path(__file__).resolve().parents[1] / "clover_html" / "res" / "font"
REGULAR_FONT = FONT_DIR / "NotoSansSC-Regular.otf"
BOLD_FONT = FONT_DIR / "NotoSansSC-Bold.otf"


async def get_yuc_wiki(keyword: str) -> str | None:
    """Fetch and render the current season or forecast anime page."""
    if keyword == "本季新番":
        template_name = await generate_season_url()
        url = urljoin(BASE_URL, template_name)
    else:
        template_name = "forecast_anime"
        url = FORECAST_URL

    try:
        response = requests.get(url, timeout=20)
        if response.status_code != 200:
            return None

        soup = await dispose_html(response)
        html_file = _html_file(template_name)
        html_file.write_text(str(soup), encoding="utf-8")
        await get_yuc_wiki_image(template_name, 568, 1885)
        return str(_image_file(template_name))
    except Exception as exc:
        print(f"Error occurred: {exc}")
        return None


async def generate_season_url() -> str:
    """Return the upstream page slug for the current calendar quarter."""
    now = datetime.now()
    quarter_month = ((now.month - 1) // 3) * 3 + 1
    return f"{now.year}{quarter_month:02d}"


def _absolute_resource_url(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    if normalized.startswith("//"):
        normalized = f"https:{normalized}"
    else:
        normalized = urljoin(BASE_URL, normalized)

    parsed = urlsplit(normalized)
    if parsed.scheme == "http":
        normalized = urlunsplit(parsed._replace(scheme="https"))
    return normalized


def _inject_local_fonts(soup: BeautifulSoup) -> None:
    head = soup.head
    if head is None:
        head = soup.new_tag("head")
        soup.insert(0, head)

    style = soup.new_tag("style", id="elysia-yuc-local-fonts")
    style["data-render-version"] = RENDER_CACHE_VERSION
    style.string = f"""
@font-face {{
  font-family: "{FONT_FAMILY}";
  src: url("{REGULAR_FONT.resolve().as_uri()}") format("opentype");
  font-style: normal;
  font-weight: 400;
  font-display: block;
}}
@font-face {{
  font-family: "{FONT_FAMILY}";
  src: url("{BOLD_FONT.resolve().as_uri()}") format("opentype");
  font-style: normal;
  font-weight: 700;
  font-display: block;
}}
html,
body,
body * {{
  font-family: "{FONT_FAMILY}", sans-serif !important;
}}
"""
    head.append(style)


async def dispose_html(response: requests.Response) -> BeautifulSoup:
    """Trim the upstream page and make its resources deterministic."""
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser", from_encoding="utf-8")

    first_table = soup.select_one("table")
    if first_table:
        first_table.decompose()

    for selector in ("header", "aside", "script", ".toggle", "#sidebar-dimmer", ".fa"):
        for tag in soup.select(selector):
            tag.decompose()

    hr_tags = soup.find_all("hr")
    if len(hr_tags) >= 2:
        next_element = hr_tags[1].next_sibling
        while next_element:
            next_sibling = next_element.next_sibling
            next_element.extract()
            next_element = next_sibling

    for tag in soup.find_all(["a", "link", "img", "source"]):
        if tag.name == "img" and tag.get("data-src"):
            tag["src"] = tag["data-src"]
            del tag["data-src"]

        attr = "href" if tag.name in {"a", "link"} else "src"
        if tag.has_attr(attr):
            tag[attr] = _absolute_resource_url(tag[attr])

    for link in soup.select('link[rel~="stylesheet"][href]'):
        parsed = urlsplit(link["href"])
        if (
            parsed.hostname == "fonts.loli.net"
            or "/font-awesome/" in parsed.path
        ):
            link.decompose()

    _inject_local_fonts(soup)
    return soup


def _html_file(template_name: str) -> Path:
    return Path(yuc_wiki_path) / f"{template_name}.html"


def _image_file(template_name: str) -> Path:
    return Path(yuc_wiki_path) / f"{template_name}.{RENDER_CACHE_VERSION}.jpeg"


async def get_yuc_wiki_image(
    template_name: str,
    width: int,
    height: int,
) -> bytes:
    """Render the sanitized page after all local fonts are ready."""
    image_file = _image_file(template_name)
    if image_file.exists():
        return image_file.read_bytes()

    async with get_new_page(
        device_scale_factor=2,
        viewport={"width": width, "height": height},
    ) as page:
        await page.goto(
            _html_file(template_name).resolve().as_uri(),
            wait_until="networkidle",
        )
        await page.evaluate("document.fonts.ready")
        image_bytes = await page.screenshot(
            full_page=True,
            type="jpeg",
            quality=40,
        )

    await save_img(image_bytes, template_name)
    return image_bytes


async def save_img(data: bytes, template_name: str) -> None:
    _image_file(template_name).write_bytes(data)
    print("保存图片完成")
