from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from threading import Lock

from nonebot import logger
from nonebot.adapters.qq import Message, MessageEvent, MessageSegment
from nonebot.adapters.qq.exception import ActionFailed
from nonebot.exception import FinishedException
from nonebot.params import CommandArg
from nonebot.plugin import on_command
from nonebot.rule import to_me

from src.clover_image.delete_file import delete_file
from src.clover_image.image_generation import (
    ImageDimensions,
    ImageGenerationConfigurationError,
    ImageGenerationError,
    ImageGenerationQuotaExhaustedError,
    InvalidImageSizeError,
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
    classify_prompt_assistant_request,
    contains_prompt_injection,
    image_prompt_assistant_client,
)
from src.clover_image.qq_image import download_qq_image
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
    "/生图 参考图 [分辨率] 提示词（请附图或引用图片）\n"
    "/生图 自拍 [分辨率] [提示词]\n"
    "分辨率示例：1920x1088、横向4K、竖向4K"
)
SELFIE_PROMPT_PREFIX = (
    "以参考图中的人物为主体，保留其可辨识的面部特征和发型，"
    "生成一张自然、真实的自拍照。"
)
DEFAULT_SELFIE_PROMPT = "自然光线，正对镜头，构图舒适。"
_MODE_PATTERN = re.compile(r"^(参考图|图生图|自拍)(?:\s+|[：:，,]\s*|$)")
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
PROMPT_ASSISTANT_REFUSAL = "生图助手仅支持将文字或参考图整理为生图提示词。"


class ImageGenerationMode(str, Enum):
    NATURAL = "natural"
    REFERENCE = "reference"
    SELFIE = "selfie"


@dataclass(frozen=True)
class ImageGenerationRequest:
    mode: ImageGenerationMode
    prompt: str
    dimensions: ImageDimensions | None = None


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


def _first_image_url(attachments) -> str | None:
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
        ):
            return url
    return None


def find_reference_image_url(event: MessageEvent) -> str | None:
    current_url = _first_image_url(getattr(event, "attachments", None))
    if current_url:
        return current_url

    reply = getattr(event, "reply", None)
    reply_url = _first_image_url(getattr(reply, "attachments", None))
    if reply_url:
        return reply_url

    for reply_element in getattr(event, "msg_elements", None) or ():
        reply_url = _first_image_url(getattr(reply_element, "attachments", None))
        if reply_url:
            return reply_url
    return None


async def _send_progress_safely() -> None:
    try:
        await generate_image.send("正在生成图片，请稍候。")
    except ActionFailed as exc:
        logger.warning(
            f"生图进度提示发送失败: code={exc.code}, message={exc.message}"
        )


async def _finish_send_failure_notice_safely() -> None:
    try:
        await generate_image.finish(
            "图片已经生成，但发送失败，请勿立即重复提交。"
        )
    except FinishedException:
        raise
    except ActionFailed as exc:
        logger.warning(
            f"生图失败提示发送失败: code={exc.code}, message={exc.message}"
        )


async def _send_prompt_assistant_progress_safely() -> None:
    try:
        await image_prompt_helper.send("正在分析画面与提示词，请稍候。")
    except ActionFailed as exc:
        logger.warning(
            f"生图助手进度提示发送失败: code={exc.code}, message={exc.message}"
        )


async def _finish_prompt_assistant_send_failure_notice_safely() -> None:
    try:
        await image_prompt_helper.finish(
            "提示词已经生成，但发送失败，请稍后重试。"
        )
    except FinishedException:
        raise
    except ActionFailed as exc:
        logger.warning(
            f"生图助手失败提示发送失败: code={exc.code}, message={exc.message}"
        )


generate_image = on_command("生图", rule=to_me(), priority=10, block=True)


@generate_image.handle()
async def handle_generate_image(
    event: MessageEvent,
    args: Message = CommandArg(),
):
    reference_url = find_reference_image_url(event)
    try:
        request = parse_generation_request(
            args.extract_plain_text(),
            has_reference_image=reference_url is not None,
        )
        image_generation_client.validate_request(request.dimensions)
    except InvalidImageSizeError as exc:
        await generate_image.finish(str(exc))
        return
    except ImageGenerationConfigurationError:
        logger.error("生图服务配置无效")
        await generate_image.finish("生图服务尚未正确配置，请联系管理员。")
        return
    if not request.prompt and request.mode is not ImageGenerationMode.SELFIE:
        await generate_image.finish(USAGE)
    if request.mode is ImageGenerationMode.REFERENCE and reference_url is None:
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
            reference = await download_reference_image(reference_url)
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
        result = await image_generation_client.generate(
            prompt,
            reference=reference,
            dimensions=request.dimensions,
        )
        await generate_image.finish(
            MessageSegment.file_image(result.content, file_name=result.filename)
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
    except ActionFailed as exc:
        logger.warning(
            f"生成图片发送失败: code={exc.code}, message={exc.message}"
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
        await image_prompt_helper.finish(f"反推提示词：\n{result.prompt}")
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
    except ActionFailed as exc:
        logger.warning(
            f"生图助手消息发送失败: request_id={request_id}, "
            f"code={exc.code}, message={exc.message}"
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
