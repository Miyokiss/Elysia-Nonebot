import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from httpx import HTTPError, Response
from tenacity import RetryError


logger = logging.getLogger(__name__)

BILI_HOTWORD_URLS = (
    "https://api.bilibili.com/x/web-interface/wbi/search/square?limit=10",
    "https://s.search.bilibili.com/main/hotword",
)
BILI_HOTWORD_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.bilibili.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
    ),
}
MAX_BILI_HOTWORDS = 10
BILI_FETCH_TIMEOUT = 30
BILI_SOURCE_TIMEOUT = 12

HttpGet = Callable[..., Awaitable[Response]]


class BiliHotwordResponseError(ValueError):
    """Raised when a Bilibili hotword response violates the expected contract."""


class BiliHotwordFetchError(RuntimeError):
    """Raised when all configured Bilibili hotword sources fail."""


def _get_hotword_items(payload: Mapping[str, Any]) -> object:
    if "list" in payload:
        return payload["list"]

    data = payload.get("data")
    if not isinstance(data, Mapping):
        return None
    trending = data.get("trending")
    if not isinstance(trending, Mapping):
        return None
    return trending.get("list")


def parse_bili_hotwords(payload: object) -> list[str]:
    """Parse both the current and legacy Bilibili hotword responses."""
    if not isinstance(payload, Mapping):
        raise BiliHotwordResponseError("B站热点响应不是 JSON 对象")
    if payload.get("code") != 0:
        raise BiliHotwordResponseError("B站热点接口返回非成功状态")

    items = _get_hotword_items(payload)
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        raise BiliHotwordResponseError("B站热点响应缺少列表")

    hotwords: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        value = ""
        for field in ("show_name", "keyword"):
            candidate = item.get(field)
            if isinstance(candidate, str) and candidate.strip():
                value = candidate.strip()
                break
        if not value or value in seen:
            continue
        seen.add(value)
        hotwords.append(value)
        if len(hotwords) == MAX_BILI_HOTWORDS:
            break

    if not hotwords:
        raise BiliHotwordResponseError("B站热点响应没有有效条目")
    return hotwords


async def _fetch_bili_hotwords(
    request_get: HttpGet,
    urls: Sequence[str],
    source_timeout: float,
) -> list[str]:
    last_error: BaseException | None = None
    for index, url in enumerate(urls):
        try:
            response = await asyncio.wait_for(
                request_get(
                    url,
                    headers=BILI_HOTWORD_HEADERS.copy(),
                ),
                timeout=source_timeout,
            )
            return parse_bili_hotwords(response.json())
        except (HTTPError, RetryError, ValueError, asyncio.TimeoutError) as exc:
            last_error = exc
            if index + 1 < len(urls):
                logger.warning(
                    "B站热点源请求失败（%s），尝试备用接口",
                    type(exc).__name__,
                )

    raise BiliHotwordFetchError("所有B站热点接口均不可用") from last_error


async def fetch_bili_hotwords(
    request_get: HttpGet,
    urls: Sequence[str] = BILI_HOTWORD_URLS,
    timeout: float = BILI_FETCH_TIMEOUT,
    source_timeout: float = BILI_SOURCE_TIMEOUT,
) -> list[str]:
    """Fetch hotwords, falling back within a bounded total deadline."""
    try:
        return await asyncio.wait_for(
            _fetch_bili_hotwords(request_get, urls, source_timeout),
            timeout=timeout,
        )
    except asyncio.TimeoutError as exc:
        raise BiliHotwordFetchError("B站热点接口请求超时") from exc
