import asyncio
import hashlib
import json
import time
from os import getcwd
from pathlib import Path

import httpx
from nonebot import logger
from nonebot_plugin_htmlrender import template_to_pic

from src.configs.api_config import afdian_token, afdian_user_id


AFDIAN_URL = "https://ifdian.net/api/open/query-sponsor"
AFDIAN_TIMEOUT = httpx.Timeout(5.0, connect=3.0)
AFDIAN_TOTAL_TIMEOUT_SECONDS = 8
HELP_IMAGE_CACHE_SECONDS = 300
HELP_RENDER_TIMEOUT_SECONDS = 30

_help_image_cache: tuple[float, bytes] | None = None
_help_render_lock = asyncio.Lock()


def _build_afdian_request() -> dict[str, object]:
    timestamp = int(time.time())
    params_json = json.dumps({"page": 1}, separators=(",", ":"))
    signature_source = f"params{params_json}ts{timestamp}user_id{afdian_user_id}"
    signature = hashlib.md5(
        (afdian_token + signature_source).encode("utf-8")
    ).hexdigest()
    return {
        "user_id": afdian_user_id,
        "params": params_json,
        "ts": timestamp,
        "sign": signature,
    }


def _parse_afdian_response(payload) -> dict[str, object]:
    if not isinstance(payload, dict) or payload.get("ec") != 200:
        raise ValueError("爱发电接口返回失败状态")
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("list"), list):
        raise ValueError("爱发电接口响应格式无效")

    top_list = []
    for sponsor in data["list"][:3]:
        user = sponsor.get("user") if isinstance(sponsor, dict) else None
        if not isinstance(user, dict):
            continue
        name = user.get("name")
        avatar = user.get("avatar")
        if isinstance(name, str) and isinstance(avatar, str):
            top_list.append({"name": name, "avatar": avatar})

    total_count = data.get("total_count", 0)
    if not isinstance(total_count, int) or isinstance(total_count, bool):
        total_count = 0
    return {"total_count": total_count, "top_list": top_list}


async def _fetch_afdian_data() -> dict[str, object]:
    async with httpx.AsyncClient(timeout=AFDIAN_TIMEOUT) as client:
        response = await client.post(AFDIAN_URL, json=_build_afdian_request())
        response.raise_for_status()
        return _parse_afdian_response(response.json())


async def get_afdian_data() -> dict[str, object]:
    try:
        result = await asyncio.wait_for(
            _fetch_afdian_data(), timeout=AFDIAN_TOTAL_TIMEOUT_SECONDS
        )
    except (asyncio.TimeoutError, httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning(f"获取爱发电赞助数据失败，使用空数据: {type(exc).__name__}")
        return {"total_count": 0, "top_list": []}

    logger.debug(f"查询赞助者成功，共 {result['total_count']} 条")
    return result


async def _render_help_image(data) -> bytes:
    afdian_data = await get_afdian_data()
    return await asyncio.wait_for(
        template_to_pic(
            template_path=getcwd() + "/src/clover_html/help",
            template_name="main.html",
            templates={"data": data, "afdian_data": afdian_data},
            pages={
                "viewport": {"width": 500, "height": 1},
                "base_url": f"file://{getcwd()}",
            },
            wait=2,
        ),
        timeout=HELP_RENDER_TIMEOUT_SECONDS,
    )


async def help_info_img(data, temp_file: str) -> bool:
    global _help_image_cache

    destination = Path(temp_file)
    if await asyncio.to_thread(destination.is_file):
        return True

    now = time.monotonic()
    cached = _help_image_cache
    if cached is None or cached[0] <= now:
        async with _help_render_lock:
            now = time.monotonic()
            cached = _help_image_cache
            if cached is None or cached[0] <= now:
                try:
                    image_bytes = await _render_help_image(data)
                except Exception as exc:
                    logger.warning(f"帮助图片生成失败: {type(exc).__name__}")
                    return False
                cached = (now + HELP_IMAGE_CACHE_SECONDS, image_bytes)
                _help_image_cache = cached

    try:
        await asyncio.to_thread(destination.write_bytes, cached[1])
    except OSError as exc:
        logger.warning(f"帮助图片写入失败: {type(exc).__name__}")
        return False
    return True
