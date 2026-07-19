from __future__ import annotations

import asyncio
import ipaddress
import math
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from urllib.parse import urlparse

import aiofiles
import httpx
from nonebot import logger
from nonebot.adapters.qq import Bot, Message, MessageEvent, MessageSegment
from nonebot.adapters.qq.exception import ActionFailed, NetworkError
from nonebot.exception import FinishedException
from nonebot.params import CommandArg
from nonebot.plugin import on_command
from nonebot.rule import to_me

from src.clover_image.delete_file import delete_file
from src.clover_sqlite.models.image_generation import (
    DailyQuotaStatus,
    ImageGenerationUsage,
)
from src.clover_videos.video_generation import (
    GeneratedVideo,
    VideoGenerationConfigurationError,
    VideoGenerationError,
    VideoGenerationHTTPError,
    VideoGenerationMode,
    VideoGenerationQuotaExhaustedError,
    VideoGenerationRequest,
    VideoGenerationTimeoutError,
    VideoGenerationValidationError,
    video_generation_client,
)
from src.configs.api_config import (
    video_generation_api_key,
    video_generation_base_url,
    video_generation_daily_user_limit,
    video_generation_max_concurrency,
    video_generation_user_cooldown,
)
from src.configs.path_config import video_path


USAGE = (
    "用法：\n"
    "/生视频 提示词\n"
    "/生视频 图生视频 提示词（附图或引用含图消息）\n"
    "/生视频 参考视频 提示词（附视频或引用含视频消息）"
)
MAX_REFERENCE_IMAGE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_REFERENCE_IMAGE_BYTES = 20 * 1024 * 1024
MAX_REFERENCE_VIDEO_BYTES = 50 * 1024 * 1024
MAX_GENERATED_VIDEO_BYTES = 40 * 1024 * 1024
OUTPUT_DOWNLOAD_TIMEOUT_SECONDS = 180.0
_MODE_PATTERN = re.compile(
    r"^(文生视频|图生视频|参考视频)(?:\s+|[：:，,]\s*|$)"
)
_IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
_VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}


class VideoGenerationInputError(ValueError):
    """The command or its QQ media attachments are not valid."""


class VideoDeliveryError(RuntimeError):
    """The generated video could not be downloaded or sent safely."""


@dataclass(frozen=True)
class InputMedia:
    kind: str
    url: str
    size: int | None = None
    filename: str | None = None


class GenerationCapacity:
    def __init__(self, limit: int):
        self.limit = max(1, int(limit))
        self._active = 0
        self._lock = Lock()

    def try_acquire(self) -> bool:
        with self._lock:
            if self._active >= self.limit:
                return False
            self._active += 1
            return True

    def release(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)


_generation_capacity = GenerationCapacity(video_generation_max_concurrency)
_cooldown_lock = Lock()
_last_user_requests: dict[str, float] = {}


def reserve_user_request(user_id: str, *, now: float | None = None) -> int:
    cooldown = max(0.0, float(video_generation_user_cooldown))
    if cooldown == 0:
        return 0
    current = time.monotonic() if now is None else now
    with _cooldown_lock:
        previous = _last_user_requests.get(user_id)
        if previous is not None:
            remaining = cooldown - (current - previous)
            if remaining > 0:
                return max(1, math.ceil(remaining))
        _last_user_requests[user_id] = current
        if len(_last_user_requests) > 2048:
            cutoff = current - cooldown
            stale = [
                key
                for key, requested_at in _last_user_requests.items()
                if requested_at < cutoff
            ]
            for key in stale:
                _last_user_requests.pop(key, None)
    return 0


def _attachment_kind(content_type: object, filename: object, url: str) -> str | None:
    if isinstance(content_type, str):
        normalized = content_type.lower().strip()
        if normalized.startswith("image/"):
            return "image"
        if normalized.startswith("video/"):
            return "video"
        if normalized:
            return None

    candidate = filename if isinstance(filename, str) and filename else urlparse(url).path
    suffix = Path(candidate).suffix.lower()
    if suffix in _IMAGE_EXTENSIONS:
        return "image"
    if suffix in _VIDEO_EXTENSIONS:
        return "video"
    return None


def _media_inputs(attachments) -> tuple[InputMedia, ...]:
    media: list[InputMedia] = []
    seen: set[str] = set()
    for attachment in attachments or ():
        url = getattr(attachment, "url", None)
        if not isinstance(url, str) or not url or url in seen:
            continue
        filename = getattr(attachment, "filename", None)
        kind = _attachment_kind(
            getattr(attachment, "content_type", None),
            filename,
            url,
        )
        if kind is None:
            continue
        raw_size = getattr(attachment, "size", None)
        size = (
            raw_size
            if isinstance(raw_size, int)
            and not isinstance(raw_size, bool)
            and raw_size >= 0
            else None
        )
        seen.add(url)
        media.append(
            InputMedia(
                kind=kind,
                url=url,
                size=size,
                filename=filename if isinstance(filename, str) else None,
            )
        )
    return tuple(media)


def find_reference_media(event: MessageEvent) -> tuple[InputMedia, ...]:
    current = _media_inputs(getattr(event, "attachments", None))
    if current:
        return current

    reply = getattr(event, "reply", None)
    replied = _media_inputs(getattr(reply, "attachments", None))
    if replied:
        return replied

    for reply_element in getattr(event, "msg_elements", None) or ():
        replied = _media_inputs(getattr(reply_element, "attachments", None))
        if replied:
            return replied
    return ()


def _validate_media(media: tuple[InputMedia, ...]) -> None:
    images = [item for item in media if item.kind == "image"]
    videos = [item for item in media if item.kind == "video"]
    if len(images) > 4:
        raise VideoGenerationInputError("单次最多支持 4 张参考图。")
    if len(videos) > 1:
        raise VideoGenerationInputError("单次只能附带 1 个参考视频。")
    if any(
        item.size is not None and item.size > MAX_REFERENCE_IMAGE_BYTES
        for item in images
    ):
        raise VideoGenerationInputError("单张参考图不能超过 10 MiB。")
    known_image_bytes = sum(item.size or 0 for item in images)
    if known_image_bytes > MAX_TOTAL_REFERENCE_IMAGE_BYTES:
        raise VideoGenerationInputError("参考图总大小不能超过 20 MiB。")
    if videos and videos[0].size is not None:
        if videos[0].size > MAX_REFERENCE_VIDEO_BYTES:
            raise VideoGenerationInputError("参考视频不能超过 50 MiB。")


def parse_generation_request(
    value: str,
    *,
    media: tuple[InputMedia, ...] = (),
) -> VideoGenerationRequest:
    value = value.strip()
    _validate_media(media)
    images = tuple(item.url for item in media if item.kind == "image")
    videos = tuple(item.url for item in media if item.kind == "video")

    explicit_mode = False
    match = _MODE_PATTERN.match(value)
    if match is not None:
        explicit_mode = True
        mode = {
            "文生视频": VideoGenerationMode.TEXT,
            "图生视频": VideoGenerationMode.IMAGE,
            "参考视频": VideoGenerationMode.REFERENCE_VIDEO,
        }[match.group(1)]
        value = value[match.end() :].strip()
    elif videos:
        mode = VideoGenerationMode.REFERENCE_VIDEO
    elif images:
        mode = VideoGenerationMode.IMAGE
    else:
        mode = VideoGenerationMode.TEXT

    if not value:
        raise VideoGenerationInputError(USAGE)
    if explicit_mode and mode is VideoGenerationMode.TEXT and media:
        raise VideoGenerationInputError("文生视频模式不能附带图片或视频。")
    if mode is VideoGenerationMode.IMAGE:
        if not images:
            raise VideoGenerationInputError("图生视频模式需要附带图片或引用含图消息。")
        if videos:
            raise VideoGenerationInputError("图生视频模式不能附带参考视频。")
    if mode is VideoGenerationMode.REFERENCE_VIDEO and not videos:
        raise VideoGenerationInputError(
            "参考视频模式需要附带视频或引用含视频消息。"
        )

    return VideoGenerationRequest(
        prompt=value,
        mode=mode,
        image_urls=images,
        video_url=videos[0] if videos else None,
    )


def _origin(url: str) -> tuple[str, str, int | None] | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is None:
        port = 443 if parsed.scheme.lower() == "https" else 80
    return parsed.scheme.lower(), parsed.hostname.lower(), port


def _same_origin(first: str, second: str) -> bool:
    return _origin(first) is not None and _origin(first) == _origin(second)


def _is_public_video_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if _same_origin(url, video_generation_base_url):
        return False
    hostname = parsed.hostname.lower()
    if hostname == "localhost" or hostname.endswith(".local"):
        return False
    try:
        return ipaddress.ip_address(hostname).is_global
    except ValueError:
        return True


def _download_headers(url: str) -> dict[str, str]:
    if _same_origin(url, video_generation_base_url):
        return {"Authorization": f"Bearer {video_generation_api_key}"}
    return {}


def _valid_video_prefix(content_type: str, prefix: bytes) -> bool:
    normalized = content_type.split(";", 1)[0].strip().lower()
    if normalized.startswith("video/"):
        return True
    if normalized not in {"", "application/octet-stream", "binary/octet-stream"}:
        return False
    return (
        len(prefix) >= 12 and prefix[4:8] == b"ftyp"
    ) or prefix.startswith(b"\x1aE\xdf\xa3")


async def download_generated_video(url: str, destination: Path) -> Path:
    if _origin(url) is None:
        raise VideoDeliveryError("生成结果地址无效")
    destination = Path(destination)
    part_path = destination.with_suffix(destination.suffix + ".part")
    timeout = httpx.Timeout(OUTPUT_DOWNLOAD_TIMEOUT_SECONDS, connect=10.0)
    downloaded = 0
    prefix = bytearray()
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            trust_env=False,
        ) as client:
            async with client.stream(
                "GET",
                url,
                headers=_download_headers(url),
            ) as response:
                response.raise_for_status()
                raw_length = response.headers.get("Content-Length")
                if raw_length:
                    try:
                        content_length = int(raw_length)
                    except ValueError:
                        content_length = None
                    if (
                        content_length is not None
                        and content_length > MAX_GENERATED_VIDEO_BYTES
                    ):
                        raise VideoDeliveryError("生成视频超过发送大小限制")

                content_type = response.headers.get("Content-Type", "")
                async with aiofiles.open(part_path, "wb") as output:
                    async for chunk in response.aiter_bytes(64 * 1024):
                        if not chunk:
                            continue
                        downloaded += len(chunk)
                        if downloaded > MAX_GENERATED_VIDEO_BYTES:
                            raise VideoDeliveryError("生成视频超过发送大小限制")
                        if len(prefix) < 16:
                            prefix.extend(chunk[: 16 - len(prefix)])
                        await output.write(chunk)
        if downloaded == 0 or not _valid_video_prefix(content_type, bytes(prefix)):
            raise VideoDeliveryError("生视频接口未返回有效的视频文件")
        await asyncio.to_thread(part_path.replace, destination)
        return destination
    except VideoDeliveryError:
        raise
    except httpx.TimeoutException as exc:
        raise VideoDeliveryError("生成视频下载超时") from exc
    except httpx.HTTPError as exc:
        raise VideoDeliveryError("生成视频下载失败") from exc
    except OSError as exc:
        raise VideoDeliveryError("生成视频暂存失败") from exc
    finally:
        if part_path.is_file():
            await delete_file(part_path)


async def _send_generated_video(
    bot: Bot,
    event: MessageEvent,
    result: GeneratedVideo,
) -> None:
    if _is_public_video_url(result.url):
        try:
            await bot.send(event=event, message=MessageSegment.video(result.url))
            return
        except (ActionFailed, NetworkError) as exc:
            logger.warning(
                "QQ 远程视频发送失败，改用本地上传: "
                f"{type(exc).__name__}"
            )

    safe_task_id = re.sub(r"[^A-Za-z0-9_-]", "_", result.task_id)[:64]
    local_path = Path(video_path) / (
        f"generated_{safe_task_id or 'task'}_{uuid.uuid4().hex}.mp4"
    )
    try:
        await download_generated_video(result.url, local_path)
        await bot.send(
            event=event,
            message=MessageSegment.file_video(local_path),
        )
    finally:
        if local_path.is_file():
            await delete_file(local_path)


generate_video = on_command("生视频", rule=to_me(), priority=10, block=True)


@generate_video.handle()
async def handle_generate_video(
    event: MessageEvent,
    bot: Bot,
    args: Message = CommandArg(),
):
    media = find_reference_media(event)
    try:
        request = parse_generation_request(
            args.extract_plain_text(),
            media=media,
        )
    except (VideoGenerationInputError, VideoGenerationValidationError) as exc:
        await generate_video.finish(str(exc))
        return

    if not _generation_capacity.try_acquire():
        await generate_video.finish("当前生视频任务较多，请稍后再试。")
        return

    try:
        user_id = event.get_user_id()
        cooldown_remaining = reserve_user_request(user_id)
        if cooldown_remaining:
            await generate_video.finish(
                f"生视频请求过于频繁，请在 {cooldown_remaining} 秒后再试。"
            )
            return

        quota_status = await ImageGenerationUsage.reserve_daily_usage(
            user_id,
            user_limit=video_generation_daily_user_limit,
            namespace="video_generation",
        )
        if quota_status is DailyQuotaStatus.USER_LIMIT_REACHED:
            await generate_video.finish("你今天的生视频次数已用完，请明天再试。")
            return

        await generate_video.send("正在生成视频，通常需要几分钟，请稍候。")
        started_at = time.monotonic()
        result = await video_generation_client.generate(request)
        await _send_generated_video(bot, event, result)
        elapsed = max(1, round(time.monotonic() - started_at))
        mode_label = {
            VideoGenerationMode.TEXT: "文生视频",
            VideoGenerationMode.IMAGE: "图生视频",
            VideoGenerationMode.REFERENCE_VIDEO: "参考视频",
        }[request.mode]
        await generate_video.finish(
            f"生视频完成｜{mode_label}｜{result.model}｜耗时 {elapsed} 秒"
        )
    except FinishedException:
        raise
    except VideoGenerationConfigurationError:
        logger.error("生视频服务配置无效")
        await generate_video.finish("生视频服务尚未正确配置，请联系管理员。")
    except VideoGenerationQuotaExhaustedError as exc:
        logger.warning(
            f"生视频接口额度不足: {exc.diagnostic_message}"
        )
        await generate_video.finish(
            "生视频额度不足，请联系管理员补充额度后再试。"
        )
    except VideoGenerationHTTPError as exc:
        logger.warning(f"生视频接口请求失败: {exc}")
        if exc.status_code in {401, 403}:
            await generate_video.finish(
                "生视频服务鉴权失败，请联系管理员检查 API Key。"
            )
        elif exc.status_code == 404:
            await generate_video.finish(
                "生视频接口或模型不可用，请联系管理员检查配置。"
            )
        else:
            await generate_video.finish("生视频服务暂时不可用，请稍后重试。")
    except VideoDeliveryError as exc:
        logger.warning(f"生成视频发送失败: {exc}")
        await generate_video.finish(
            "视频已经生成，但下载或发送失败，请勿立即重复提交。"
        )
    except VideoGenerationTimeoutError:
        logger.warning("生视频任务等待超时，提交结果可能仍在处理中")
        await generate_video.finish(
            "生视频等待超时，任务可能仍在处理中，请勿立即重复提交。"
        )
    except VideoGenerationError as exc:
        logger.warning(f"生视频失败: {exc}")
        await generate_video.finish("生视频服务暂时不可用，请稍后重试。")
    except (ActionFailed, NetworkError) as exc:
        logger.warning(f"生成视频发送失败: {type(exc).__name__}")
        await generate_video.finish(
            "视频已经生成，但 QQ 发送失败，请勿立即重复提交。"
        )
    except Exception as exc:
        logger.opt(exception=exc).error("生视频处理失败")
        await generate_video.finish("生视频处理失败，请稍后重试。")
    finally:
        _generation_capacity.release()
