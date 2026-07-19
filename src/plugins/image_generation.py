from __future__ import annotations

import asyncio
import re
import time
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import date
from enum import Enum
from io import BytesIO
from threading import Lock

from nonebot import logger
from nonebot.adapters.qq import Message, MessageEvent, MessageSegment
from nonebot.adapters.qq.exception import ActionFailed, NetworkError
from nonebot.adapters.qq.models import (
    Action,
    Button,
    InlineKeyboard,
    InlineKeyboardRow,
    MessageKeyboard,
    MessageMarkdown,
    Permission,
    RenderData,
)
from nonebot.exception import FinishedException
from nonebot.params import CommandArg
from nonebot.plugin import on_command
from nonebot.rule import to_me
from PIL import Image, UnidentifiedImageError

from src.clover_image.delete_file import delete_file
from src.clover_image.image_generation import (
    GeneratedImage,
    ImageDimensions,
    ImageGenerationConfigurationError,
    ImageGenerationError,
    ImageGenerationQuotaExhaustedError,
    InvalidImageSizeError,
    MAX_PROMPT_LENGTH,
    MAX_REFERENCE_IMAGE_COUNT,
    MAX_TOTAL_REFERENCE_IMAGE_BYTES,
    ReferenceImage,
    UnsupportedReferenceImageError,
    download_reference_image,
    image_generation_client,
    read_reference_image,
)
from src.clover_image.image_prompt_assistant import (
    MAX_ASSISTANT_TEXT_LENGTH,
    PromptAssistantConfigurationError,
    PromptAssistantError,
    PromptAssistantInputError,
    PromptAssistantRequestType,
    classify_prompt_assistant_request,
    contains_prompt_injection,
    image_prompt_assistant_client,
)
from src.clover_image.qq_image import download_qq_image
from src.clover_providers.cloud_file_api.rustfs import rustfs_api
from src.configs.api_config import (
    image_generation_daily_user_limit,
    image_generation_max_concurrency,
    image_generation_user_cooldown,
    image_prompt_assistant_daily_user_limit,
    image_prompt_assistant_max_concurrency,
    image_prompt_assistant_user_cooldown,
)
from src.clover_sqlite.models.image_generation import (
    DailyQuotaStatus,
    ImageGenerationUsage,
)


USAGE = (
    "用法：\n"
    "/生图 [分辨率] 提示词\n"
    "/生图 参考图 [分辨率] 提示词（可附 1-4 张图或引用含图消息）\n"
    "/生图 自拍 [分辨率] [提示词]\n"
    "分辨率示例：1920x1088、横向4K、竖向4K"
)
SELFIE_PROMPT_PREFIX = (
    "以参考图中的人物为主体，保留其可辨识的面部特征和发型，"
    "生成一张自然、真实的自拍照。"
)
DEFAULT_SELFIE_PROMPT = "自然光线，正对镜头，构图舒适。"
_MODE_PATTERN = re.compile(r"^(参考图|图生图|自拍)(?:\s+|[：:，,]\s*|$)")
_ACTION_REFERENCE_INTENT_PATTERN = re.compile(
    r"动作|姿势|姿态|体态|站姿|坐姿|pose|posture|action",
    re.IGNORECASE,
)
_SIZE_VALUE_PATTERN = (
    r"(?P<width>[+-]?\d+)\s*[xX×*＊]\s*(?P<height>[+-]?\d+)"
)
_OUTPUT_SIZE_LABEL_PATTERN = (
    r"(?:(?:输出|图片|图像|画布)(?:的)?(?:分辨率|尺寸)|"
    r"output\s+(?:resolution|size))"
)
_LEADING_SIZE_LABEL_PATTERN = r"(?:分辨率|尺寸|resolution|size)"
_QUALIFIED_SIZE_PATTERN = re.compile(
    r"(?<![A-Za-z])"
    + _OUTPUT_SIZE_LABEL_PATTERN
    + r"(?![A-Za-z])\s*(?:为|是|[:：=])?\s*"
    + _SIZE_VALUE_PATTERN
    + r"(?:\s*(?:px|像素))?(?:\s*的)?",
    re.IGNORECASE,
)
_LEADING_MARKED_SIZE_PATTERN = re.compile(
    r"^\s*"
    + _LEADING_SIZE_LABEL_PATTERN
    + r"(?![A-Za-z])\s*(?:为|是|[:：=])?\s*"
    + _SIZE_VALUE_PATTERN
    + r"(?:\s*(?:px|像素))?(?:\s*的)?",
    re.IGNORECASE,
)
_ANY_PLAIN_MARKED_SIZE_PATTERN = re.compile(
    r"(?<![A-Za-z])"
    + _LEADING_SIZE_LABEL_PATTERN
    + r"(?![A-Za-z])\s*(?:为|是|[:：=])?\s*"
    + _SIZE_VALUE_PATTERN
    + r"(?:\s*(?:px|像素))?(?:\s*的)?",
    re.IGNORECASE,
)
_LEADING_SIZE_PATTERN = re.compile(
    r"^\s*"
    + _SIZE_VALUE_PATTERN
    + r"(?:\s*(?:px|像素))?(?=$|[\s,，;；:：])",
    re.IGNORECASE,
)
_ORIENTATION_TERMS = (
    r"横向|横版|横屏|横图|landscape|"
    r"竖向|竖版|竖屏|竖图|portrait"
)
_ORIENTED_4K_VALUE_PATTERN = (
    rf"(?:(?P<before>{_ORIENTATION_TERMS})\s*4\s*k|"
    rf"4\s*k\s*(?P<after>{_ORIENTATION_TERMS}))"
)
_LEADING_ORIENTED_4K_PATTERN = re.compile(
    r"^\s*"
    + _ORIENTED_4K_VALUE_PATTERN
    + r"(?=$|[\s,，;；:：])",
    re.IGNORECASE,
)
_ANY_ORIENTED_4K_PATTERN = re.compile(
    _ORIENTED_4K_VALUE_PATTERN + r"(?=$|[\s,，;；:：])",
    re.IGNORECASE,
)
_QUALIFIED_ORIENTED_4K_PATTERN = re.compile(
    r"(?<![A-Za-z])"
    + _OUTPUT_SIZE_LABEL_PATTERN
    + r"(?![A-Za-z])\s*(?:为|是|[:：=])?\s*"
    + _ORIENTED_4K_VALUE_PATTERN
    + r"(?=$|[\s,，;；:：])",
    re.IGNORECASE,
)
PROMPT_ASSISTANT_USAGE = (
    "用法：/生图助手 画面描述；也可附图或引用图片，"
    "并附加画面调整要求。"
)
PROMPT_ASSISTANT_REFUSAL = "您的请求存在问题！生图助手仅支持将文字或参考图整理为生图提示词。"
_MARKDOWN_ESCAPE_PATTERN = re.compile(r"([\\`*_{}\[\]()<>#+.!|~-])")
_GPT_IMAGE_VERSION_PATTERN = re.compile(
    r"^gpt-image-(?P<version>\d+(?:\.\d+)?)(?:-[a-z0-9._-]+)?$",
    re.IGNORECASE,
)
_SEEDREAM_VERSION_PATTERN = re.compile(
    r"^doubao-seedream-(?P<major>\d+)-(?P<minor>\d+)(?:-\d+)?$",
    re.IGNORECASE,
)
_GPT_VERSION_PATTERN = re.compile(
    r"^gpt-(?P<major>\d+)(?:\.(?P<minor>\d+))?(?:-[a-z0-9._-]+)?$",
    re.IGNORECASE,
)
_GENERATED_IMAGE_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/bmp": "bmp",
}
_DEFAULT_MARKDOWN_IMAGE_DIMENSIONS = ImageDimensions(1024, 1024)
_RUSTFS_IMAGE_URL_EXPIRES_SECONDS = 3600
_RUSTFS_IMAGE_DELETE_DELAY_SECONDS = _RUSTFS_IMAGE_URL_EXPIRES_SECONDS + 60

def _build_image_generation_keyboard(
    generation_prompt: str | None = None,
) -> MessageKeyboard:
    prompt = (
        re.sub(
            r"\s+",
            " ",
            unicodedata.normalize("NFC", generation_prompt),
        ).strip()
        if generation_prompt
        else ""
    )
    generation_command = f"/生图 {prompt}" if prompt else "/生图 "
    return MessageKeyboard(
        content=InlineKeyboard(
            rows=[
                InlineKeyboardRow(
                    buttons=[
                        Button(
                            id="image_generation",
                            render_data=RenderData(
                                label="生图",
                                visited_label="生图",
                                style=1,
                            ),
                            action=Action(
                                type=2,
                                permission=Permission(type=2),
                                data=generation_command,
                                reply=False,
                                enter=False,
                                unsupport_tips="请手动输入 /生图",
                            ),
                        ),
                        Button(
                            id="image_prompt_assistant",
                            render_data=RenderData(
                                label="生图助手",
                                visited_label="生图助手",
                                style=0,
                            ),
                            action=Action(
                                type=2,
                                permission=Permission(type=2),
                                data="/生图助手 ",
                                reply=False,
                                enter=False,
                                unsupport_tips="请手动输入 /生图助手",
                            ),
                        ),
                    ]
                )
            ]
        )
    )


IMAGE_GENERATION_KEYBOARD = _build_image_generation_keyboard()


class ImageGenerationMode(str, Enum):
    NATURAL = "natural"
    REFERENCE = "reference"
    SELFIE = "selfie"


_IMAGE_GENERATION_MODE_LABELS = {
    ImageGenerationMode.NATURAL: "文生图",
    ImageGenerationMode.REFERENCE: "参考图",
    ImageGenerationMode.SELFIE: "自拍",
}
_PROMPT_ASSISTANT_TYPE_LABELS = {
    PromptAssistantRequestType.TEXT_TO_PROMPT: "文字转提示词",
    PromptAssistantRequestType.IMAGE_TO_PROMPT: "图片反推",
    PromptAssistantRequestType.IMAGE_TEXT_TO_PROMPT: "图文反推",
}


@dataclass(frozen=True)
class ImageGenerationRequest:
    mode: ImageGenerationMode
    prompt: str
    dimensions: ImageDimensions | None = None


@dataclass(frozen=True)
class HostedGeneratedImage:
    object_key: str
    url: str
    dimensions: ImageDimensions


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


_generation_capacity = GenerationCapacity(image_generation_max_concurrency)
_cooldown_lock = Lock()
_last_user_requests: dict[str, float] = {}
_prompt_assistant_capacity = GenerationCapacity(image_prompt_assistant_max_concurrency)
_prompt_assistant_cooldown_lock = Lock()
_prompt_assistant_last_requests: dict[str, float] = {}
_hosted_image_cleanup_tasks: set[asyncio.Task[bool]] = set()


def _reserve_with_cooldown(
    user_id: str,
    *,
    cooldown_seconds: float,
    requests: dict[str, float],
    lock: Lock,
    now: float | None = None,
) -> int:
    cooldown = max(0.0, float(cooldown_seconds))
    if cooldown == 0:
        return 0
    current = time.monotonic() if now is None else now
    with lock:
        previous = requests.get(user_id)
        if previous is not None:
            remaining = cooldown - (current - previous)
            if remaining > 0:
                return max(1, int(remaining + 0.999))
        requests[user_id] = current
        if len(requests) > 2048:
            cutoff = current - max(cooldown * 2, 300.0)
            stale_users = [
                key for key, requested_at in requests.items()
                if requested_at < cutoff
            ]
            for key in stale_users:
                requests.pop(key, None)
    return 0


def reserve_user_request(user_id: str, *, now: float | None = None) -> int:
    return _reserve_with_cooldown(
        user_id,
        cooldown_seconds=image_generation_user_cooldown,
        requests=_last_user_requests,
        lock=_cooldown_lock,
        now=now,
    )


def reserve_prompt_assistant_request(
    user_id: str,
    *,
    now: float | None = None,
) -> int:
    return _reserve_with_cooldown(
        user_id,
        cooldown_seconds=image_prompt_assistant_user_cooldown,
        requests=_prompt_assistant_last_requests,
        lock=_prompt_assistant_cooldown_lock,
        now=now,
    )


async def reserve_daily_generation_usage(user_id: str) -> DailyQuotaStatus:
    return await ImageGenerationUsage.reserve_daily_usage(
        user_id,
        user_limit=image_generation_daily_user_limit,
    )


async def reserve_daily_prompt_assistant_usage(user_id: str) -> DailyQuotaStatus:
    return await ImageGenerationUsage.reserve_daily_usage(
        user_id,
        user_limit=image_prompt_assistant_daily_user_limit,
        namespace="prompt_assistant",
    )


async def _remaining_daily_quota_text(
    user_id: str,
    *,
    user_limit: int,
    namespace: str = "",
) -> str:
    limit = max(0, int(user_limit))
    if limit == 0:
        return "不限"

    scope_prefix = f"{namespace}:" if namespace else ""
    try:
        usage = await ImageGenerationUsage.get_or_none(
            scope_id=f"{scope_prefix}user:{user_id}",
            request_date=date.today(),
        )
    except Exception as exc:
        logger.opt(exception=exc).warning("查询生图今日剩余额度失败")
        return "未知"

    used = int(usage.request_count) if usage is not None else 0
    return f"{max(0, limit - used)} 次"


def _escape_markdown_text(value: str) -> str:
    return _MARKDOWN_ESCAPE_PATTERN.sub(r"\\\1", value)


def _format_elapsed(elapsed_seconds: float) -> str:
    return f"{max(0.0, elapsed_seconds):.2f} 秒"


def _public_model_version(model: str) -> str:
    model_name = model.strip().rsplit("/", maxsplit=1)[-1]
    if match := _GPT_IMAGE_VERSION_PATTERN.fullmatch(model_name):
        return match.group("version")
    if match := _SEEDREAM_VERSION_PATTERN.fullmatch(model_name):
        return f"{match.group('major')}.{match.group('minor')}"
    if match := _GPT_VERSION_PATTERN.fullmatch(model_name):
        minor = match.group("minor")
        return (
            f"{match.group('major')}.{minor}"
            if minor is not None
            else match.group("major")
        )
    return "未知"


def _generated_image_dimensions(
    content: bytes,
    fallback: ImageDimensions | None = None,
) -> ImageDimensions:
    try:
        with Image.open(BytesIO(content)) as image:
            width, height = image.size
        if width > 0 and height > 0:
            return ImageDimensions(width, height)
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ):
        pass
    return fallback or _DEFAULT_MARKDOWN_IMAGE_DIMENSIONS


async def _host_generated_image(
    result: GeneratedImage,
    dimensions: ImageDimensions,
) -> HostedGeneratedImage | None:
    extension = _GENERATED_IMAGE_EXTENSIONS.get(result.media_type, "png")
    object_key = (
        f"image-generation/{date.today():%Y/%m/%d}/"
        f"{uuid.uuid4().hex}.{extension}"
    )
    uploaded = False
    try:
        uploaded = await rustfs_api.upload_bytes(
            result.content,
            object_key,
            content_type=result.media_type,
        )
        if not uploaded:
            logger.warning("生图结果上传 RustFS 失败，降级为 QQ 图片消息")
            return None
        image_url = await rustfs_api.get_download_url(
            object_key=object_key,
            expires_in=_RUSTFS_IMAGE_URL_EXPIRES_SECONDS,
        )
        if not image_url:
            logger.warning("生图结果获取 RustFS 下载链接失败，降级为 QQ 图片消息")
            await rustfs_api.delete_file(object_key=object_key)
            return None
    except asyncio.CancelledError:
        if uploaded:
            await rustfs_api.delete_file(object_key=object_key)
        raise
    except Exception as exc:
        if uploaded:
            await rustfs_api.delete_file(object_key=object_key)
        logger.opt(exception=exc).warning(
            "生图结果托管到 RustFS 时发生异常，降级为 QQ 图片消息"
        )
        return None
    return HostedGeneratedImage(object_key, image_url, dimensions)


def _schedule_hosted_image_cleanup(object_key: str) -> None:
    task = asyncio.create_task(
        rustfs_api.delayed_delete_file(
            object_key,
            delay=_RUSTFS_IMAGE_DELETE_DELAY_SECONDS,
        )
    )
    _hosted_image_cleanup_tasks.add(task)
    task.add_done_callback(_hosted_image_cleanup_tasks.discard)


def _native_markdown_message(
    content: str,
    *,
    generation_prompt: str | None = None,
    mention_user_id: str | None = None,
) -> Message:
    if mention_user_id is not None:
        content = f"<@{mention_user_id}>\n\n{content}"
    keyboard = (
        IMAGE_GENERATION_KEYBOARD
        if generation_prompt is None
        else _build_image_generation_keyboard(generation_prompt)
    )
    return Message(
        [
            MessageSegment.markdown(MessageMarkdown(content=content)),
            MessageSegment.keyboard(keyboard),
        ]
    )


def _generation_completion_text(
    *,
    model: str,
    mode: ImageGenerationMode,
    dimensions: ImageDimensions | None,
    elapsed_seconds: float,
    remaining_quota: str,
    markdown: bool,
    image_url: str | None = None,
    image_dimensions: ImageDimensions | None = None,
) -> str:
    resolution = str(dimensions) if dimensions is not None else "默认"
    details = (
        ("版本", _public_model_version(model)),
        ("模式", _IMAGE_GENERATION_MODE_LABELS[mode]),
        ("分辨率", resolution),
        ("用时", _format_elapsed(elapsed_seconds)),
        ("今日剩余", remaining_quota),
    )
    if not markdown:
        return "生图完成\n" + "\n".join(
            f"{label}：{value}" for label, value in details
        )

    lines = ["## 生图完成", ""]
    if image_url:
        display_dimensions = (
            image_dimensions
            or dimensions
            or _DEFAULT_MARKDOWN_IMAGE_DIMENSIONS
        )
        lines.extend(
            [
                "![生图 "
                f"#{display_dimensions.width}px "
                f"#{display_dimensions.height}px]({image_url})",
                "",
            ]
        )
    lines.extend(
        f"- **{label}**：{_escape_markdown_text(value)}"
        for label, value in details
    )
    return "\n".join(lines)


def _prompt_assistant_completion_text(
    *,
    prompt: str,
    model: str,
    request_type: PromptAssistantRequestType,
    elapsed_seconds: float,
    remaining_quota: str,
    markdown: bool,
) -> str:
    details = (
        ("版本", _public_model_version(model)),
        ("类型", _PROMPT_ASSISTANT_TYPE_LABELS[request_type]),
        ("用时", _format_elapsed(elapsed_seconds)),
        ("今日剩余", remaining_quota),
    )
    if not markdown:
        return (
            f"反推提示词：\n{prompt}\n\n"
            + "\n".join(f"{label}：{value}" for label, value in details)
        )

    lines = [
        "## 反推提示词",
        "",
        _escape_markdown_text(prompt),
        "",
        "---",
        "",
    ]
    lines.extend(
        f"- **{label}**：{_escape_markdown_text(value)}"
        for label, value in details
    )
    return "\n".join(lines)


def _qq_send_error_detail(exc: ActionFailed | NetworkError) -> str:
    if isinstance(exc, ActionFailed):
        return f"code={exc.code}, message={exc.message}"
    return f"error_type={type(exc).__name__}, message={exc}"


async def _finish_native_reply_with_fallback(
    matcher,
    message: Message,
    fallback_text: str,
    *,
    log_context: str,
    fallback_message: MessageSegment | None = None,
    mention_user_id: str | None = None,
) -> None:
    try:
        await matcher.finish(message)
    except FinishedException:
        raise
    except (ActionFailed, NetworkError) as exc:
        logger.warning(
            f"{log_context} Markdown/按钮发送失败，降级为普通文本: "
            f"{_qq_send_error_detail(exc)}"
        )
        if fallback_message is not None:
            await matcher.send(fallback_message)
        fallback_reply = (
            Message(
                [
                    MessageSegment.mention_user(mention_user_id),
                    MessageSegment.text(f"\n{fallback_text}"),
                ]
            )
            if mention_user_id is not None
            else fallback_text
        )
        await matcher.finish(fallback_reply)


def _parse_dimension_number(value: str) -> int:
    digits = value.lstrip("+-").lstrip("0") or "0"
    if len(digits) > 5:
        raise InvalidImageSizeError("分辨率数值过大")
    try:
        return int(value)
    except ValueError as exc:
        raise InvalidImageSizeError("分辨率数值无效") from exc


def _dimensions_from_match(match: re.Match[str]) -> ImageDimensions:
    return ImageDimensions(
        width=_parse_dimension_number(match.group("width")),
        height=_parse_dimension_number(match.group("height")),
    )


def _extract_requested_dimensions(
    value: str,
) -> tuple[str, ImageDimensions | None]:
    candidates: list[tuple[int, int, ImageDimensions]] = []

    for match in _QUALIFIED_SIZE_PATTERN.finditer(value):
        candidates.append((*match.span(), _dimensions_from_match(match)))

    leading_marked_match = _LEADING_MARKED_SIZE_PATTERN.match(value)
    if leading_marked_match is not None:
        candidates.append(
            (
                *leading_marked_match.span(),
                _dimensions_from_match(leading_marked_match),
            )
        )

    leading_match = _LEADING_SIZE_PATTERN.match(value)
    if leading_match is not None:
        candidates.append(
            (*leading_match.span(), _dimensions_from_match(leading_match))
        )

    oriented_matches = list(_QUALIFIED_ORIENTED_4K_PATTERN.finditer(value))
    leading_oriented_match = _LEADING_ORIENTED_4K_PATTERN.match(value)
    if leading_oriented_match is not None:
        oriented_matches.append(leading_oriented_match)
    for match in oriented_matches:
        orientation = (match.group("before") or match.group("after")).casefold()
        dimensions = (
            ImageDimensions(2160, 3840)
            if orientation.startswith("竖") or orientation == "portrait"
            else ImageDimensions(3840, 2160)
        )
        candidates.append((*match.span(), dimensions))

    prefix_candidates = [
        candidate
        for candidate in candidates
        if not value[: candidate[0]].strip(" \t\r\n,，;；:：")
    ]
    if prefix_candidates:
        cursor = max(candidate[1] for candidate in prefix_candidates)
        while cursor < len(value):
            while cursor < len(value) and value[cursor] in " \t\r\n,，;；:：":
                cursor += 1
            known_candidate_ends = [
                candidate_end
                for candidate_start, candidate_end, _ in candidates
                if candidate_start == cursor
            ]
            if known_candidate_ends:
                cursor = max(known_candidate_ends)
                continue
            plain_match = _ANY_PLAIN_MARKED_SIZE_PATTERN.match(value, cursor)
            oriented_match = _ANY_ORIENTED_4K_PATTERN.match(value, cursor)
            match = plain_match or oriented_match
            if match is None:
                break
            if plain_match is not None:
                dimensions = _dimensions_from_match(plain_match)
            else:
                orientation = (
                    oriented_match.group("before")
                    or oriented_match.group("after")
                ).casefold()
                dimensions = (
                    ImageDimensions(2160, 3840)
                    if orientation.startswith("竖")
                    or orientation == "portrait"
                    else ImageDimensions(3840, 2160)
                )
            candidates.append((*match.span(), dimensions))
            cursor = match.end()

    if not candidates:
        return value.strip(), None

    requested_dimensions = {candidate[2] for candidate in candidates}
    if len(requested_dimensions) > 1:
        raise InvalidImageSizeError(
            "提示词中包含多个不同的分辨率，请只保留一个"
        )

    for start, end, _ in sorted(candidates, reverse=True):
        left_start = start
        right_end = end
        line_start = value.rfind("\n", 0, start) + 1
        line_end = value.find("\n", end)
        content_end = len(value) if line_end == -1 else line_end
        if (
            not value[line_start:start].strip(" \t\r")
            and not value[end:content_end].strip(" \t\r")
        ):
            if line_end != -1:
                left_start = line_start
                right_end = line_end + 1
            elif line_start > 0:
                left_start = line_start - 1
                right_end = len(value)
        else:
            while left_start > 0 and value[left_start - 1] in " \t":
                left_start -= 1
            while right_end < len(value) and value[right_end] in " \t":
                right_end += 1
            bracket_pairs = {"(": ")", "（": "）", "[": "]", "【": "】"}
            if (
                left_start > 0
                and right_end < len(value)
                and value[left_start - 1] in bracket_pairs
                and bracket_pairs[value[left_start - 1]] == value[right_end]
            ):
                left_start -= 1
                right_end += 1
        left = value[:left_start]
        right = value[right_end:]
        separator = (
            " "
            if left
            and right
            and not left.endswith(("\r", "\n"))
            and not right.startswith(("\r", "\n"))
            else ""
        )
        value = f"{left}{separator}{right}"
    value = re.sub(r"([,，;；:：])[ \t]*[,，;；:：]+", r"\1", value)
    value = re.sub(r"[ \t]+([,，;；:：。.!?！？])", r"\1", value)
    value = value.strip(" \t\r\n,，;；:：")
    return value, next(iter(requested_dimensions))


def parse_generation_request(
    value: str,
    *,
    has_reference_image: bool = False,
) -> ImageGenerationRequest:
    value = value.strip()
    match = _MODE_PATTERN.match(value)
    if match:
        mode_name = match.group(1)
        mode = (
            ImageGenerationMode.SELFIE
            if mode_name == "自拍"
            else ImageGenerationMode.REFERENCE
        )
        value = value[match.end() :].strip()
    elif has_reference_image:
        mode = ImageGenerationMode.REFERENCE
    else:
        mode = ImageGenerationMode.NATURAL

    prompt, dimensions = _extract_requested_dimensions(value)
    return ImageGenerationRequest(mode, prompt, dimensions)


def _image_urls(attachments) -> tuple[str, ...]:
    urls: list[str] = []
    seen: set[str] = set()
    for attachment in attachments or ():
        content_type = getattr(attachment, "content_type", None)
        url = getattr(attachment, "url", None)
        if (
            (
                content_type is None
                or (
                    isinstance(content_type, str)
                    and content_type.lower().startswith("image/")
                )
            )
            and isinstance(url, str)
            and url
            and url not in seen
        ):
            seen.add(url)
            urls.append(url)
    return tuple(urls)


def _first_image_url(attachments) -> str | None:
    return next(iter(_image_urls(attachments)), None)


def find_reference_image_urls(event: MessageEvent) -> tuple[str, ...]:
    current_urls = _image_urls(getattr(event, "attachments", None))
    if current_urls:
        return current_urls

    referenced_urls = getattr(event, "_elysia_referenced_image_urls", ())
    if isinstance(referenced_urls, tuple) and referenced_urls:
        return referenced_urls

    reply = getattr(event, "reply", None)
    reply_urls = _image_urls(getattr(reply, "attachments", None))
    if reply_urls:
        return reply_urls

    forwarded_urls = getattr(event, "_elysia_forwarded_image_urls", ())
    if isinstance(forwarded_urls, tuple) and forwarded_urls:
        return forwarded_urls

    for reply_element in getattr(event, "msg_elements", None) or ():
        reply_urls = _image_urls(getattr(reply_element, "attachments", None))
        if reply_urls:
            return reply_urls
    return ()


def find_reference_image_url(event: MessageEvent) -> str | None:
    return next(iter(find_reference_image_urls(event)), None)


async def _download_reference_images(
    urls: tuple[str, ...],
) -> tuple[ReferenceImage, ...]:
    if len(urls) > MAX_REFERENCE_IMAGE_COUNT:
        raise UnsupportedReferenceImageError(
            f"单次最多支持 {MAX_REFERENCE_IMAGE_COUNT} 张参考图"
        )

    references: list[ReferenceImage] = []
    total_bytes = 0
    for index, url in enumerate(urls, start=1):
        try:
            reference = await download_reference_image(url)
        except ImageGenerationError as exc:
            raise UnsupportedReferenceImageError(
                f"第 {index} 张参考图处理失败：{exc}"
            ) from exc
        total_bytes += len(reference.content)
        if total_bytes > MAX_TOTAL_REFERENCE_IMAGE_BYTES:
            max_mebibytes = MAX_TOTAL_REFERENCE_IMAGE_BYTES // (1024 * 1024)
            raise UnsupportedReferenceImageError(
                f"参考图总大小不能超过 {max_mebibytes} MiB"
            )
        references.append(reference)
    return tuple(references)


def _prompt_with_ordered_reference_roles(
    prompt: str,
    count: int,
) -> str | None:
    if _ACTION_REFERENCE_INTENT_PATTERN.search(prompt):
        role_guidance = (
            "用户明确指定图片用途时，以用户要求为准；否则将参考图 1 "
            "作为主体、角色身份和外观参考，将参考图 2 "
            "作为动作、姿势和构图参考，第 3 张及后续图片作为补充参考。"
            "不要用后续参考图中的人物身份替换参考图 1 的主体。"
        )
    else:
        role_guidance = (
            "请根据用户文字判断每张图片的用途；用户未明确指定时，"
            "以参考图 1 为主要参考，其余图片按顺序作为补充参考，"
            "不要混淆不同图片中的主体身份。"
        )
    context = f"本次共有 {count} 张按发送顺序排列的参考图。{role_guidance}"
    combined = f"{context}\n用户要求：{prompt}"
    return combined if len(combined) <= MAX_PROMPT_LENGTH else None


async def _send_progress_safely() -> None:
    try:
        await generate_image.send("正在生成图片，请稍候。")
    except (ActionFailed, NetworkError) as exc:
        logger.warning(
            f"生图进度提示发送失败: {_qq_send_error_detail(exc)}"
        )


async def _finish_send_failure_notice_safely() -> None:
    try:
        await generate_image.finish(
            "图片已经生成，但发送失败，请勿立即重复提交。"
        )
    except FinishedException:
        raise
    except (ActionFailed, NetworkError) as exc:
        logger.warning(
            f"生图失败提示发送失败: {_qq_send_error_detail(exc)}"
        )


async def _send_prompt_assistant_progress_safely() -> None:
    try:
        await image_prompt_helper.send("正在分析画面与提示词，请稍候。")
    except (ActionFailed, NetworkError) as exc:
        logger.warning(
            f"生图助手进度提示发送失败: {_qq_send_error_detail(exc)}"
        )


async def _finish_prompt_assistant_send_failure_notice_safely() -> None:
    try:
        await image_prompt_helper.finish(
            "提示词已经生成，但发送失败，请稍后重试。"
        )
    except FinishedException:
        raise
    except (ActionFailed, NetworkError) as exc:
        logger.warning(
            f"生图助手失败提示发送失败: {_qq_send_error_detail(exc)}"
        )


generate_image = on_command("生图", rule=to_me(), priority=10, block=True)


@generate_image.handle()
async def handle_generate_image(
    event: MessageEvent,
    args: Message = CommandArg(),
):
    reference_urls = find_reference_image_urls(event)
    try:
        request = parse_generation_request(
            args.extract_plain_text(),
            has_reference_image=bool(reference_urls),
        )
        image_generation_client.validate_request(request.dimensions)
    except InvalidImageSizeError as exc:
        await generate_image.finish(str(exc))
        return
    except ImageGenerationConfigurationError:
        logger.error("生图服务配置无效")
        await generate_image.finish("生图服务尚未正确配置，请联系管理员。")
        return
    if (
        request.mode is ImageGenerationMode.REFERENCE
        and len(reference_urls) > MAX_REFERENCE_IMAGE_COUNT
    ):
        await generate_image.finish(
            f"单次最多支持 {MAX_REFERENCE_IMAGE_COUNT} 张参考图。"
        )
        return
    if not request.prompt and request.mode is not ImageGenerationMode.SELFIE:
        await generate_image.finish(USAGE)
    if request.mode is ImageGenerationMode.REFERENCE and not reference_urls:
        await generate_image.finish("参考图模式需要附带图片或引用一张图片。")

    user_id = event.get_user_id()
    if not _generation_capacity.try_acquire():
        await generate_image.finish("当前生图任务较多，请稍后再试。")

    avatar_path: str | None = None
    try:
        cooldown_remaining = reserve_user_request(user_id)
        if cooldown_remaining:
            await generate_image.finish(
                f"生图请求过于频繁，请在 {cooldown_remaining} 秒后再试。"
            )

        reference = None
        prompt = request.prompt or DEFAULT_SELFIE_PROMPT
        if request.mode is ImageGenerationMode.REFERENCE:
            references = await _download_reference_images(reference_urls)
            if len(references) > 1:
                ordered_prompt = _prompt_with_ordered_reference_roles(
                    prompt,
                    len(references),
                )
                if ordered_prompt is None:
                    await generate_image.finish(
                        "多图提示词过长，请精简后重试。"
                    )
                    return
                prompt = ordered_prompt
                reference = references
            else:
                reference = references[0]
        elif request.mode is ImageGenerationMode.SELFIE:
            avatar_path = await download_qq_image(user_id, size=640)
            if not avatar_path:
                await generate_image.finish("获取头像失败，请稍后重试。")
            reference = await read_reference_image(avatar_path)
            prompt = f"{SELFIE_PROMPT_PREFIX}\n{prompt}"

        quota_status = await reserve_daily_generation_usage(user_id)
        if quota_status is DailyQuotaStatus.USER_LIMIT_REACHED:
            await generate_image.finish("你今天的生图次数已用完，请明天再试。")

        await _send_progress_safely()
        generation_started_at = time.monotonic()
        result = await image_generation_client.generate(
            prompt,
            reference=reference,
            dimensions=request.dimensions,
        )
        elapsed_seconds = time.monotonic() - generation_started_at
        output_dimensions = _generated_image_dimensions(
            result.content,
            fallback=request.dimensions,
        )
        hosted_image = await _host_generated_image(result, output_dimensions)
        if hosted_image is not None:
            _schedule_hosted_image_cleanup(hosted_image.object_key)
        remaining_quota = await _remaining_daily_quota_text(
            user_id,
            user_limit=image_generation_daily_user_limit,
        )
        markdown_text = _generation_completion_text(
            model=result.model,
            mode=request.mode,
            dimensions=output_dimensions,
            elapsed_seconds=elapsed_seconds,
            remaining_quota=remaining_quota,
            markdown=True,
            image_url=hosted_image.url if hosted_image is not None else None,
            image_dimensions=output_dimensions,
        )
        fallback_text = _generation_completion_text(
            model=result.model,
            mode=request.mode,
            dimensions=output_dimensions,
            elapsed_seconds=elapsed_seconds,
            remaining_quota=remaining_quota,
            markdown=False,
        )
        fallback_image = MessageSegment.file_image(
            result.content,
            file_name=result.filename,
        )
        if hosted_image is None:
            await generate_image.send(fallback_image)
        await _finish_native_reply_with_fallback(
            generate_image,
            _native_markdown_message(
                markdown_text,
                mention_user_id=user_id,
            ),
            fallback_text,
            log_context="生图完成信息",
            fallback_message=(
                fallback_image if hosted_image is not None else None
            ),
            mention_user_id=user_id,
        )
    except FinishedException:
        raise
    except ImageGenerationConfigurationError:
        logger.error("生图服务配置无效")
        await generate_image.finish("生图服务尚未正确配置，请联系管理员。")
    except ImageGenerationQuotaExhaustedError:
        logger.warning("当前请求可用的生图渠道额度均已用完")
        await generate_image.finish(
            "当前请求可用的生图渠道额度均已用完，"
            "请联系管理员补充额度后再试。"
        )
    except (InvalidImageSizeError, UnsupportedReferenceImageError) as exc:
        await generate_image.finish(str(exc))
    except ImageGenerationError as exc:
        logger.warning(f"生图失败: {exc}")
        await generate_image.finish("生图服务暂时不可用，请稍后重试。")
    except (ActionFailed, NetworkError) as exc:
        logger.warning(
            f"生成图片发送失败: {_qq_send_error_detail(exc)}"
        )
        await _finish_send_failure_notice_safely()
    except Exception as exc:
        logger.opt(exception=exc).error("生图处理失败")
        await generate_image.finish("生图处理失败，请稍后重试。")
    finally:
        if avatar_path:
            await delete_file(avatar_path)
        _generation_capacity.release()


image_prompt_helper = on_command(
    "生图助手",
    rule=to_me(),
    priority=10,
    block=True,
)


@image_prompt_helper.handle()
async def handle_image_prompt_helper(
    event: MessageEvent,
    args: Message = CommandArg(),
):
    text = args.extract_plain_text().strip()
    reference_url = find_reference_image_url(event)
    user_id = event.get_user_id()
    cooldown_remaining = reserve_prompt_assistant_request(user_id)
    if cooldown_remaining:
        await image_prompt_helper.finish(
            f"请求过于频繁，请在 {cooldown_remaining} 秒后再试。"
        )

    request_type = classify_prompt_assistant_request(
        text,
        has_reference_image=reference_url is not None,
    )
    if request_type is None:
        await image_prompt_helper.finish(PROMPT_ASSISTANT_USAGE)
    if len(text) > MAX_ASSISTANT_TEXT_LENGTH:
        await image_prompt_helper.finish("输入文字过长，请精简后重试。")
    if text and contains_prompt_injection(text):
        await image_prompt_helper.finish(PROMPT_ASSISTANT_REFUSAL)

    if not _prompt_assistant_capacity.try_acquire():
        await image_prompt_helper.finish("当前生图助手任务较多，请稍后再试。")

    request_id = uuid.uuid4().hex[:12]
    request_started_at: float | None = None
    try:
        quota_status = await reserve_daily_prompt_assistant_usage(user_id)
        if quota_status is DailyQuotaStatus.USER_LIMIT_REACHED:
            await image_prompt_helper.finish("你今天的生图助手次数已用完，请明天再试。")

        reference = None
        if reference_url is not None:
            reference = await download_reference_image(reference_url)

        await _send_prompt_assistant_progress_safely()
        request_started_at = time.monotonic()
        logger.info(
            f"生图助手请求开始: request_id={request_id}, type={request_type.value}"
        )
        result = await image_prompt_assistant_client.reverse_prompt(
            text,
            reference=reference,
            request_id=request_id,
        )
        elapsed_ms = round((time.monotonic() - request_started_at) * 1000)
        if not result.allowed or not result.prompt:
            logger.info(
                f"生图助手已拒绝请求: request_id={request_id}, "
                f"type={request_type.value}, reason={result.reason_code.value}, "
                f"elapsed_ms={elapsed_ms}"
            )
            await image_prompt_helper.finish(PROMPT_ASSISTANT_REFUSAL)
        logger.info(
            f"生图助手请求完成: request_id={request_id}, "
            f"type={request_type.value}, elapsed_ms={elapsed_ms}"
        )
        remaining_quota = await _remaining_daily_quota_text(
            user_id,
            user_limit=image_prompt_assistant_daily_user_limit,
            namespace="prompt_assistant",
        )
        markdown_text = _prompt_assistant_completion_text(
            prompt=result.prompt,
            model=result.model,
            request_type=result.request_type,
            elapsed_seconds=elapsed_ms / 1000,
            remaining_quota=remaining_quota,
            markdown=True,
        )
        fallback_text = _prompt_assistant_completion_text(
            prompt=result.prompt,
            model=result.model,
            request_type=result.request_type,
            elapsed_seconds=elapsed_ms / 1000,
            remaining_quota=remaining_quota,
            markdown=False,
        )
        await _finish_native_reply_with_fallback(
            image_prompt_helper,
            _native_markdown_message(
                markdown_text,
                generation_prompt=result.prompt,
                mention_user_id=user_id,
            ),
            fallback_text,
            log_context="生图助手结果",
            mention_user_id=user_id,
        )
    except FinishedException:
        raise
    except PromptAssistantInputError:
        await image_prompt_helper.finish("生图助手输入无效，请检查后重试。")
    except PromptAssistantConfigurationError as exc:
        stage = exc.stage.value if exc.stage is not None else "unknown"
        elapsed_ms = (
            round((time.monotonic() - request_started_at) * 1000)
            if request_started_at is not None
            else 0
        )
        logger.error(
            f"生图助手配置无效: request_id={request_id}, stage={stage}, "
            f"error={exc}, elapsed_ms={elapsed_ms}"
        )
        await image_prompt_helper.finish("生图助手尚未正确配置，请联系管理员。")
    except UnsupportedReferenceImageError as exc:
        await image_prompt_helper.finish(str(exc))
    except (PromptAssistantError, ImageGenerationError) as exc:
        error_stage = getattr(exc, "stage", None)
        stage = error_stage.value if error_stage is not None else "unknown"
        elapsed_ms = (
            round((time.monotonic() - request_started_at) * 1000)
            if request_started_at is not None
            else 0
        )
        logger.warning(
            f"生图助手请求失败: request_id={request_id}, "
            f"error_type={type(exc).__name__}, stage={stage}, "
            f"error={exc}, elapsed_ms={elapsed_ms}"
        )
        await image_prompt_helper.finish("生图助手暂时不可用，请稍后再试。")
    except (ActionFailed, NetworkError) as exc:
        logger.warning(
            f"生图助手消息发送失败: request_id={request_id}, "
            f"{_qq_send_error_detail(exc)}"
        )
        await _finish_prompt_assistant_send_failure_notice_safely()
    except Exception as exc:
        logger.error(
            f"生图助手处理失败: request_id={request_id}, "
            f"error_type={type(exc).__name__}"
        )
        await image_prompt_helper.finish("生图助手暂时不可用，请稍后再试。")
    finally:
        _prompt_assistant_capacity.release()
