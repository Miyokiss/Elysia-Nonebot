from __future__ import annotations

import asyncio
import math
import re
from collections import deque
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import httpx

from src.configs.api_config import (
    video_generation_api_key,
    video_generation_base_url,
    video_generation_duration,
    video_generation_model,
    video_generation_poll_interval,
    video_generation_timeout,
)


MAX_PROMPT_LENGTH = 4000
MAX_REFERENCE_IMAGE_COUNT = 4
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_TASK_ID_LENGTH = 512

_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_API_KEY_PATTERN = re.compile(
    r"(?i)\b(?:bearer\s+)?sk-[a-z0-9_-]{8,}\b"
)
_REQUEST_ID_PATTERN = re.compile(
    r"(?i)\b(?:request|trace)[ _-]*id\s*[:=]\s*"
    r"(?P<request_id>[A-Za-z0-9][A-Za-z0-9._:-]{2,127})"
)
_REQUEST_ID_CLAUSE_PATTERN = re.compile(
    r"(?i)\s*\(?\b(?:request|trace)[ _-]*id\s*[:=]\s*"
    r"[A-Za-z0-9][A-Za-z0-9._:-]{2,127}\)?"
)
_QUOTA_MESSAGE_PATTERN = re.compile(
    r"(?:insufficient[_\s-]*(?:quota|balance|credits?)|"
    r"(?:quota|credits?)[_\s-]*(?:exceeded|exhausted|failed)|"
    r"balance[_\s-]*(?:not[_\s-]*enough|too[_\s-]*low)|"
    r"额度不足|余额不足)",
    re.IGNORECASE,
)
_QUOTA_CODES = {
    "account_overdue",
    "balance_not_enough",
    "billing_hard_limit_reached",
    "credit_balance_too_low",
    "insufficient_balance",
    "insufficient_credits",
    "insufficient_quota",
    "insufficient_user_quota",
    "no_quota",
    "pre_consume_token_quota_failed",
    "quota_exceeded",
    "quota_exhausted",
    "usage_limit_reached",
}
_AUTHENTICATION_CODES = {
    "authentication_error",
    "invalid_api_key",
    "invalid_authentication",
    "invalid_token",
    "unauthorized",
}
_QUEUED_STATUSES = {"created", "pending", "queued", "submitted", "waiting"}
_IN_PROGRESS_STATUSES = {
    "generating",
    "in-progress",
    "in_progress",
    "processing",
    "running",
}
_COMPLETED_STATUSES = {
    "complete",
    "completed",
    "done",
    "finished",
    "succeed",
    "succeeded",
    "success",
}
_FAILED_STATUSES = {
    "cancelled",
    "canceled",
    "error",
    "failed",
    "rejected",
}
_SKIPPED_RESULT_PATH_PARTS = {
    "content",
    "image_url",
    "input",
    "inputs",
    "request",
}


class VideoGenerationError(RuntimeError):
    """A video generation failure whose message is safe to show or log."""


class VideoGenerationConfigurationError(VideoGenerationError):
    """The configured video provider cannot be used."""


class VideoGenerationValidationError(VideoGenerationError, ValueError):
    """A video generation request is invalid."""


class VideoGenerationResponseError(VideoGenerationError):
    """The provider returned a successful but unusable response."""


class VideoGenerationHTTPError(VideoGenerationError):
    """The provider returned an HTTP error without exposing its response."""

    def __init__(
        self,
        status_code: int,
        *,
        code: str | None = None,
        error_type: str | None = None,
        detail: str | None = None,
        request_id: str | None = None,
    ):
        self.status_code = status_code
        self.code = code
        self.error_type = error_type
        self.detail = detail
        self.request_id = request_id
        self.authentication_failed = status_code == 401 or (
            bool(code) and code.lower() in _AUTHENTICATION_CODES
        )
        parts = [f"视频生成接口返回 HTTP {status_code}"]
        if code:
            parts.append(f"code={code}")
        if error_type:
            parts.append(f"type={error_type}")
        if detail:
            parts.append(f"detail={detail}")
        if request_id:
            parts.append(f"request_id={request_id}")
        self.diagnostic_message = " | ".join(parts)
        super().__init__(self.diagnostic_message)


class VideoGenerationQuotaExhaustedError(VideoGenerationHTTPError):
    """The provider rejected the request because its quota is exhausted."""

    def __init__(
        self,
        status_code: int,
        *,
        code: str | None = None,
        error_type: str | None = None,
        detail: str | None = None,
        request_id: str | None = None,
    ):
        VideoGenerationHTTPError.__init__(
            self,
            status_code,
            code=code,
            error_type=error_type,
            detail=detail,
            request_id=request_id,
        )
        VideoGenerationError.__init__(self, "视频生成额度不足")


class VideoGenerationTaskFailedError(VideoGenerationError):
    """The asynchronous provider task reached a failed state."""

    def __init__(self, *, task_id: str, detail: str | None = None):
        self.task_id = task_id
        self.detail = detail
        message = "视频生成任务失败"
        if detail:
            message = f"{message}：{detail}"
        super().__init__(message)


class VideoGenerationTimeoutError(VideoGenerationError, TimeoutError):
    """The total create-and-poll time budget was exhausted."""


class VideoGenerationMode(str, Enum):
    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"
    REFERENCE_VIDEO = "reference_video"
    TEXT = "text_to_video"
    IMAGE = "image_to_video"


class VideoTaskStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class VideoGenerationRequest:
    prompt: str
    mode: VideoGenerationMode = VideoGenerationMode.TEXT_TO_VIDEO
    image_urls: tuple[str, ...] = ()
    video_url: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.prompt, str):
            raise VideoGenerationValidationError("视频提示词必须是字符串")
        prompt = self.prompt.strip()
        if not prompt:
            raise VideoGenerationValidationError("视频提示词不能为空")
        if len(prompt) > MAX_PROMPT_LENGTH:
            raise VideoGenerationValidationError(
                f"视频提示词不能超过 {MAX_PROMPT_LENGTH} 个字符"
            )

        try:
            mode = (
                self.mode
                if isinstance(self.mode, VideoGenerationMode)
                else VideoGenerationMode(self.mode)
            )
        except (TypeError, ValueError) as exc:
            raise VideoGenerationValidationError("不支持的视频生成模式") from exc

        if isinstance(self.image_urls, (str, bytes)) or not isinstance(
            self.image_urls, Sequence
        ):
            raise VideoGenerationValidationError("参考图片 URL 必须是列表")
        image_urls = tuple(self.image_urls)
        if len(image_urls) > MAX_REFERENCE_IMAGE_COUNT:
            raise VideoGenerationValidationError(
                f"单次最多支持 {MAX_REFERENCE_IMAGE_COUNT} 张参考图片"
            )
        for index, image_url in enumerate(image_urls, start=1):
            _validate_media_url(image_url, label=f"第 {index} 张参考图片")

        if self.video_url is not None:
            _validate_media_url(self.video_url, label="参考视频")

        if mode is VideoGenerationMode.TEXT_TO_VIDEO:
            if image_urls or self.video_url is not None:
                raise VideoGenerationValidationError("文生视频模式不能包含参考媒体")
        elif mode is VideoGenerationMode.IMAGE_TO_VIDEO:
            if not image_urls:
                raise VideoGenerationValidationError("图生视频模式至少需要一张参考图片")
            if self.video_url is not None:
                raise VideoGenerationValidationError("图生视频模式不能包含参考视频")
        elif self.video_url is None:
            raise VideoGenerationValidationError("参考视频模式需要一个参考视频 URL")

        object.__setattr__(self, "prompt", prompt)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "image_urls", image_urls)

    def to_api_payload(self, model: str, duration: int) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": self.prompt,
            "duration": duration,
            "seconds": str(duration),
        }
        content: list[dict[str, Any]] = []
        for index, image_url in enumerate(self.image_urls):
            role = "reference_image"
            if self.mode is VideoGenerationMode.IMAGE_TO_VIDEO and index == 0:
                role = "first_frame"
            content.append(
                {
                    "type": "image_url",
                    "role": role,
                    "image_url": {"url": image_url},
                }
            )
        if self.video_url is not None:
            content.append(
                {
                    "type": "video_url",
                    "role": "reference_video",
                    "video_url": {"url": self.video_url},
                }
            )
        if content:
            payload["metadata"] = {"content": content}
        return payload


@dataclass(frozen=True)
class GeneratedVideo:
    url: str = field(repr=False)
    task_id: str
    model: str


@dataclass(frozen=True)
class VideoTaskResult:
    task_id: str
    status: VideoTaskStatus
    video_url: str | None = field(default=None, repr=False)
    error: str | None = field(default=None, repr=False)

    def as_generated_video(self, model: str) -> GeneratedVideo:
        if self.status is not VideoTaskStatus.COMPLETED or self.video_url is None:
            raise VideoGenerationResponseError("视频生成任务尚未返回可用结果")
        return GeneratedVideo(url=self.video_url, task_id=self.task_id, model=model)


@dataclass(frozen=True)
class _HTTPErrorMetadata:
    code: str | None = None
    error_type: str | None = None
    detail: str | None = None
    request_id: str | None = None

    def as_kwargs(self) -> dict[str, str | None]:
        return {
            "code": self.code,
            "error_type": self.error_type,
            "detail": self.detail,
            "request_id": self.request_id,
        }


def _validate_media_url(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise VideoGenerationValidationError(f"{label} URL 无效")
    if any(character in value for character in "\r\n\x00"):
        raise VideoGenerationValidationError(f"{label} URL 无效")
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
    except ValueError:
        raise VideoGenerationValidationError(f"{label} URL 无效") from None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise VideoGenerationValidationError(f"{label} URL 必须是 HTTP(S) 地址")


def _validate_base_url(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise VideoGenerationConfigurationError("视频生成 API 地址未正确配置")
    if any(character in value for character in "\r\n\x00"):
        raise VideoGenerationConfigurationError("视频生成 API 地址未正确配置")
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
    except ValueError:
        raise VideoGenerationConfigurationError(
            "视频生成 API 地址未正确配置"
        ) from None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise VideoGenerationConfigurationError("视频生成 API 地址未正确配置")
    return value.rstrip("/")


def _validate_secret(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or "\r" in value
        or "\n" in value
        or value.strip().upper() in {"<KEY>", "CHANGE_ME", "YOUR_API_KEY"}
    ):
        raise VideoGenerationConfigurationError("视频生成 API Key 未正确配置")
    return value


def _validate_model(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or any(character in value for character in "\r\n\x00")
        or value.strip().upper() in {"<MODEL>", "CHANGE_ME", "YOUR_MODEL"}
    ):
        raise VideoGenerationConfigurationError("视频生成模型未正确配置")
    return value


def _validate_positive_number(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VideoGenerationConfigurationError(f"{label}必须是正数")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0:
        raise VideoGenerationConfigurationError(f"{label}必须是正数")
    return normalized


def _validate_task_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > MAX_TASK_ID_LENGTH
        or any(character in value for character in "\r\n\x00")
    ):
        raise VideoGenerationResponseError("视频生成接口未返回有效的任务 ID")
    return value


def _iter_mappings(payload: object) -> Iterator[tuple[tuple[str, ...], Mapping[str, Any]]]:
    queue: deque[tuple[tuple[str, ...], object]] = deque([((), payload)])
    visited = 0
    while queue and visited < 2048:
        path, value = queue.popleft()
        visited += 1
        if isinstance(value, Mapping):
            yield path, value
            for key, child in value.items():
                if isinstance(child, (Mapping, list, tuple)):
                    queue.append((path + (str(key).lower(),), child))
        elif isinstance(value, (list, tuple)):
            for child in value:
                if isinstance(child, (Mapping, list, tuple)):
                    queue.append((path, child))


def _path_is_input(path: tuple[str, ...]) -> bool:
    return bool(set(path) & _SKIPPED_RESULT_PATH_PARTS)


def _string_value(mapping: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            normalized = str(value).strip()
            if normalized:
                return normalized
    return None


def _extract_task_id(payload: Mapping[str, Any], default: str | None) -> str:
    for path, mapping in _iter_mappings(payload):
        if _path_is_input(path):
            continue
        value = _string_value(mapping, ("task_id", "taskId", "taskID"))
        if value is not None:
            return _validate_task_id(value)
    for path, mapping in _iter_mappings(payload):
        if _path_is_input(path):
            continue
        value = _string_value(mapping, ("id",))
        if value is not None:
            return _validate_task_id(value)
    if default is not None:
        return _validate_task_id(default)
    raise VideoGenerationResponseError("视频生成接口未返回任务 ID")


def _extract_status(payload: Mapping[str, Any]) -> VideoTaskStatus | None:
    for path, mapping in _iter_mappings(payload):
        if _path_is_input(path):
            continue
        raw_status = _string_value(
            mapping,
            ("status", "state", "task_status", "taskStatus"),
        )
        if raw_status is None:
            continue
        status = raw_status.lower().replace(" ", "_")
        if status in _QUEUED_STATUSES:
            return VideoTaskStatus.QUEUED
        if status in _IN_PROGRESS_STATUSES:
            return VideoTaskStatus.IN_PROGRESS
        if status in _COMPLETED_STATUSES:
            return VideoTaskStatus.COMPLETED
        if status in _FAILED_STATUSES:
            return VideoTaskStatus.FAILED
        raise VideoGenerationResponseError("视频生成接口返回了未知任务状态")
    return None


def _extract_result_url(payload: Mapping[str, Any]) -> str | None:
    strong_keys = (
        "video_url",
        "videoUrl",
        "output_url",
        "outputUrl",
        "result_url",
        "resultUrl",
        "download_url",
        "downloadUrl",
    )
    for path, mapping in _iter_mappings(payload):
        if _path_is_input(path):
            continue
        value = _string_value(mapping, strong_keys)
        if value is not None:
            return value

    result_containers = {
        "data",
        "metadata",
        "output",
        "result",
        "video",
        "video_url",
    }
    for path, mapping in _iter_mappings(payload):
        if _path_is_input(path):
            continue
        if not path or set(path) & result_containers:
            value = _string_value(mapping, ("url",))
            if value is not None:
                return value
    return None


def _extract_remote_error(payload: Mapping[str, Any]) -> str | None:
    for path, mapping in _iter_mappings(payload):
        if _path_is_input(path):
            continue
        for key in ("failure_reason", "error_message", "reason"):
            value = mapping.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        error = mapping.get("error")
        if isinstance(error, str) and error.strip():
            return error.strip()
        if isinstance(error, Mapping):
            value = _string_value(error, ("message", "detail", "reason", "code"))
            if value is not None:
                return value

        raw_status = _string_value(
            mapping,
            ("status", "state", "task_status", "taskStatus"),
        )
        if (
            raw_status is not None
            and raw_status.lower().replace(" ", "_") in _FAILED_STATUSES
        ) or set(path) & {"error", "errors", "failure"}:
            value = _string_value(mapping, ("message", "detail"))
            if value is not None:
                return value

    root_message = payload.get("message") or payload.get("detail")
    if isinstance(root_message, str) and root_message.strip():
        return root_message.strip()
    return None


def _sanitize_remote_error(
    value: str | None,
    *,
    api_key: str,
    sensitive_values: Sequence[str] = (),
) -> str | None:
    if not value:
        return None
    sanitized = value.replace(api_key, "[已隐藏]")
    for sensitive in sorted(set(sensitive_values), key=len, reverse=True):
        if not sensitive:
            continue
        if len(sensitive) >= 6 or sanitized.strip() == sensitive.strip():
            sanitized = sanitized.replace(sensitive, "[已隐藏内容]")
    sanitized = _API_KEY_PATTERN.sub("[已隐藏]", sanitized)
    sanitized = _URL_PATTERN.sub("[已隐藏地址]", sanitized)
    sanitized = " ".join(sanitized.split())
    if not sanitized:
        return None
    return sanitized[:300]


def _sanitize_diagnostic_identifier(
    value: object,
    *,
    api_key: str,
) -> str | None:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return None
    normalized = " ".join(str(value).split())
    if not normalized:
        return None
    if (
        api_key in normalized
        or _API_KEY_PATTERN.search(normalized)
        or _URL_PATTERN.search(normalized)
    ):
        return None
    if (
        len(normalized) > 128
        or re.fullmatch(r"[A-Za-z0-9._:-]+", normalized) is None
    ):
        return None
    return normalized


def _ordered_error_mappings(payload: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(payload, Mapping):
        return ()
    mappings: list[Mapping[str, Any]] = []
    nested_error = payload.get("error")
    if isinstance(nested_error, Mapping):
        mappings.append(nested_error)
    mappings.append(payload)
    data = payload.get("data")
    if isinstance(data, Mapping):
        data_error = data.get("error")
        if isinstance(data_error, Mapping):
            mappings.append(data_error)
        if set(data) & {
            "code",
            "detail",
            "error_code",
            "errorCode",
            "error_message",
            "errorMessage",
            "message",
            "reason",
        }:
            mappings.append(data)
    return tuple(mappings)


def _extract_diagnostic_field(
    payload: object,
    keys: Sequence[str],
) -> str | None:
    for mapping in _ordered_error_mappings(payload):
        value = _string_value(mapping, keys)
        if value is not None:
            return value
    return None


def _extract_http_error_message(payload: object) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    nested_error = payload.get("error")
    if isinstance(nested_error, str) and nested_error.strip():
        return nested_error.strip()
    return _extract_diagnostic_field(
        payload,
        (
            "message",
            "detail",
            "reason",
            "error_message",
            "errorMessage",
            "failure_reason",
        ),
    )


def _request_sensitive_values(
    request_json: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    if request_json is None:
        return ()
    values: list[str] = []
    prompt = request_json.get("prompt")
    if isinstance(prompt, str) and prompt:
        values.append(prompt)
    for _, mapping in _iter_mappings(request_json):
        url = mapping.get("url")
        if isinstance(url, str) and url:
            values.append(url)
    return tuple(values)


def _extract_request_id(
    response: httpx.Response,
    payload: object,
    message: str | None,
    *,
    api_key: str,
) -> str | None:
    for header_name in (
        "x-request-id",
        "request-id",
        "x-requestid",
        "x-oneapi-request-id",
        "x-new-api-request-id",
        "x-trace-id",
        "trace-id",
    ):
        request_id = _sanitize_diagnostic_identifier(
            response.headers.get(header_name),
            api_key=api_key,
        )
        if request_id:
            return request_id
    payload_request_id = _extract_diagnostic_field(
        payload,
        ("request_id", "requestId", "requestID", "trace_id", "traceId"),
    )
    request_id = _sanitize_diagnostic_identifier(
        payload_request_id,
        api_key=api_key,
    )
    if request_id:
        return request_id
    if message and (match := _REQUEST_ID_PATTERN.search(message)):
        return _sanitize_diagnostic_identifier(
            match.group("request_id"),
            api_key=api_key,
        )
    return None


def _http_error_metadata(
    response: httpx.Response,
    payload: object,
    *,
    api_key: str,
    request_json: Mapping[str, Any] | None,
) -> _HTTPErrorMetadata:
    raw_message = _extract_http_error_message(payload)
    request_id = _extract_request_id(
        response,
        payload,
        raw_message,
        api_key=api_key,
    )
    detail = _sanitize_remote_error(
        raw_message,
        api_key=api_key,
        sensitive_values=_request_sensitive_values(request_json),
    )
    if detail and request_id:
        detail = _REQUEST_ID_CLAUSE_PATTERN.sub("", detail).strip(" ,;|-") or None
    return _HTTPErrorMetadata(
        code=_sanitize_diagnostic_identifier(
            _extract_diagnostic_field(
                payload,
                ("code", "error_code", "errorCode"),
            ),
            api_key=api_key,
        ),
        error_type=_sanitize_diagnostic_identifier(
            _extract_diagnostic_field(
                payload,
                ("type", "error_type", "errorType"),
            ),
            api_key=api_key,
        ),
        detail=detail,
        request_id=request_id,
    )


def _extract_error_codes(payload: object) -> set[str]:
    codes: set[str] = set()
    for mapping in _ordered_error_mappings(payload):
        for key in ("code", "error_code", "errorCode", "type"):
            value = mapping.get(key)
            if isinstance(value, str) and value.strip():
                codes.add(value.strip().lower().replace("-", "_"))
    return codes


def _is_quota_error(status_code: int, payload: object) -> bool:
    if status_code == 402:
        return True
    for code in _extract_error_codes(payload):
        if code in _QUOTA_CODES:
            return True
        if "quota" in code and any(
            marker in code
            for marker in ("exceed", "exhaust", "fail", "insufficient", "limit")
        ):
            return True
        if "balance" in code and any(
            marker in code for marker in ("insufficient", "low", "not_enough", "overdue")
        ):
            return True
        if "credit" in code and any(
            marker in code for marker in ("exceed", "exhaust", "insufficient", "low")
        ):
            return True
    if isinstance(payload, Mapping):
        message = _extract_http_error_message(payload)
        if message is not None and _QUOTA_MESSAGE_PATTERN.search(message):
            return True
    return False


class VideoGenerationClient:
    def __init__(
        self,
        *,
        base_url: str = video_generation_base_url,
        api_key: str = video_generation_api_key,
        model: str = video_generation_model,
        duration_seconds: int = video_generation_duration,
        timeout_seconds: float = video_generation_timeout,
        poll_interval_seconds: float = video_generation_poll_interval,
    ):
        self.base_url = _validate_base_url(base_url)
        self._api_key = _validate_secret(api_key)
        self.model = _validate_model(model)
        if (
            isinstance(duration_seconds, bool)
            or not isinstance(duration_seconds, int)
            or not 4 <= duration_seconds <= 15
        ):
            raise VideoGenerationConfigurationError(
                "视频生成时长必须是 4 到 15 秒的整数"
            )
        self.duration_seconds = duration_seconds
        self.timeout_seconds = _validate_positive_number(
            timeout_seconds,
            label="视频生成总超时",
        )
        self.poll_interval_seconds = _validate_positive_number(
            poll_interval_seconds,
            label="视频生成轮询间隔",
        )
        if self.poll_interval_seconds > self.timeout_seconds:
            raise VideoGenerationConfigurationError(
                "视频生成轮询间隔不能大于总超时"
            )

    def _new_http_client(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(
            self.timeout_seconds,
            connect=min(10.0, self.timeout_seconds),
        )
        return httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "application/json",
            },
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        )

    def _deadline(self) -> float:
        return asyncio.get_running_loop().time() + self.timeout_seconds

    def _remaining(self, deadline: float) -> float:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise VideoGenerationTimeoutError("视频生成等待超时")
        return remaining

    async def _request_json(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        deadline: float,
        json: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        remaining = self._remaining(deadline)
        try:
            if method == "POST":
                request = client.post(url, json=json)
            else:
                request = client.get(url)
            response = await asyncio.wait_for(request, timeout=remaining)
        except (asyncio.TimeoutError, httpx.TimeoutException):
            raise VideoGenerationTimeoutError("视频生成等待超时") from None
        except httpx.RequestError:
            raise VideoGenerationError("视频生成接口网络请求失败") from None

        response_too_large = len(response.content) > MAX_RESPONSE_BYTES
        payload = None
        if not response_too_large:
            try:
                payload = response.json()
            except ValueError:
                pass

        if response.status_code >= 400:
            metadata = _http_error_metadata(
                response,
                payload,
                api_key=self._api_key,
                request_json=json,
            )
            if response_too_large:
                metadata = _HTTPErrorMetadata(
                    code=metadata.code,
                    error_type=metadata.error_type,
                    detail="错误响应体超过大小限制，已省略",
                    request_id=metadata.request_id,
                )
            if _is_quota_error(response.status_code, payload):
                raise VideoGenerationQuotaExhaustedError(
                    response.status_code,
                    **metadata.as_kwargs(),
                )
            raise VideoGenerationHTTPError(
                response.status_code,
                **metadata.as_kwargs(),
            )
        if response_too_large:
            raise VideoGenerationResponseError("视频生成接口响应超过大小限制")
        if not isinstance(payload, Mapping):
            raise VideoGenerationResponseError("视频生成接口返回了无法解析的响应")
        return payload

    def _normalize_result_url(self, value: str) -> str:
        absolute = urljoin(f"{self.base_url}/", value)
        try:
            _validate_media_url(absolute, label="生成视频")
        except VideoGenerationValidationError:
            raise VideoGenerationResponseError(
                "视频生成接口未返回有效的视频地址"
            ) from None
        return absolute

    def _parse_task_result(
        self,
        payload: Mapping[str, Any],
        *,
        default_task_id: str | None = None,
        default_status: VideoTaskStatus | None = None,
    ) -> VideoTaskResult:
        task_id = _extract_task_id(payload, default_task_id)
        raw_url = _extract_result_url(payload)
        status = _extract_status(payload)
        error = _sanitize_remote_error(
            _extract_remote_error(payload),
            api_key=self._api_key,
        )
        if status is None:
            if raw_url is not None:
                status = VideoTaskStatus.COMPLETED
            elif error is not None:
                status = VideoTaskStatus.FAILED
            elif default_status is not None:
                status = default_status
            else:
                raise VideoGenerationResponseError(
                    "视频生成接口未返回任务状态"
                )

        video_url = None
        if raw_url is not None:
            video_url = self._normalize_result_url(raw_url)
        if status is VideoTaskStatus.COMPLETED and video_url is None:
            video_url = (
                f"{self.base_url}/v1/videos/"
                f"{quote(task_id, safe='')}/content"
            )

        return VideoTaskResult(
            task_id=task_id,
            status=status,
            video_url=video_url,
            error=error,
        )

    async def _create_task_with_client(
        self,
        client: httpx.AsyncClient,
        request: VideoGenerationRequest,
        *,
        deadline: float,
    ) -> VideoTaskResult:
        if not isinstance(request, VideoGenerationRequest):
            raise VideoGenerationValidationError(
                "request 必须是 VideoGenerationRequest"
            )
        payload = await self._request_json(
            client,
            "POST",
            f"{self.base_url}/v1/videos",
            deadline=deadline,
            json=request.to_api_payload(self.model, self.duration_seconds),
        )
        return self._parse_task_result(
            payload,
            default_status=VideoTaskStatus.QUEUED,
        )

    async def _get_task_with_client(
        self,
        client: httpx.AsyncClient,
        task_id: str,
        *,
        deadline: float,
    ) -> VideoTaskResult:
        validated_task_id = _validate_task_id(task_id)
        payload = await self._request_json(
            client,
            "GET",
            f"{self.base_url}/v1/videos/{quote(validated_task_id, safe='')}",
            deadline=deadline,
        )
        return self._parse_task_result(
            payload,
            default_task_id=validated_task_id,
        )

    async def _wait_for_task_with_client(
        self,
        client: httpx.AsyncClient,
        task_id: str,
        *,
        deadline: float,
    ) -> GeneratedVideo:
        while True:
            remaining = self._remaining(deadline)
            await asyncio.sleep(min(self.poll_interval_seconds, remaining))
            result = await self._get_task_with_client(
                client,
                task_id,
                deadline=deadline,
            )
            if result.status is VideoTaskStatus.COMPLETED:
                return result.as_generated_video(self.model)
            if result.status is VideoTaskStatus.FAILED:
                raise VideoGenerationTaskFailedError(
                    task_id=result.task_id,
                    detail=result.error,
                )

    async def create_task(
        self,
        request: VideoGenerationRequest,
    ) -> VideoTaskResult:
        deadline = self._deadline()
        async with self._new_http_client() as client:
            return await self._create_task_with_client(
                client,
                request,
                deadline=deadline,
            )

    async def get_task(self, task_id: str) -> VideoTaskResult:
        deadline = self._deadline()
        async with self._new_http_client() as client:
            return await self._get_task_with_client(
                client,
                task_id,
                deadline=deadline,
            )

    async def wait_for_task(self, task_id: str) -> GeneratedVideo:
        deadline = self._deadline()
        async with self._new_http_client() as client:
            return await self._wait_for_task_with_client(
                client,
                task_id,
                deadline=deadline,
            )

    async def generate(self, request: VideoGenerationRequest) -> GeneratedVideo:
        deadline = self._deadline()
        async with self._new_http_client() as client:
            result = await self._create_task_with_client(
                client,
                request,
                deadline=deadline,
            )
            if result.status is VideoTaskStatus.COMPLETED:
                return result.as_generated_video(self.model)
            if result.status is VideoTaskStatus.FAILED:
                raise VideoGenerationTaskFailedError(
                    task_id=result.task_id,
                    detail=result.error,
                )
            return await self._wait_for_task_with_client(
                client,
                result.task_id,
                deadline=deadline,
            )


class _UnavailableVideoGenerationClient:
    async def _raise_configuration_error(self, *args, **kwargs):
        raise VideoGenerationConfigurationError("视频生成服务尚未正确配置")

    create_task = _raise_configuration_error
    generate = _raise_configuration_error
    get_task = _raise_configuration_error
    wait_for_task = _raise_configuration_error


try:
    video_generation_client = VideoGenerationClient()
except VideoGenerationConfigurationError:
    # Keep the rest of the bot loadable when this optional feature is unset.
    video_generation_client = _UnavailableVideoGenerationClient()


__all__ = [
    "GeneratedVideo",
    "MAX_PROMPT_LENGTH",
    "MAX_REFERENCE_IMAGE_COUNT",
    "VideoGenerationClient",
    "VideoGenerationConfigurationError",
    "VideoGenerationError",
    "VideoGenerationHTTPError",
    "VideoGenerationMode",
    "VideoGenerationQuotaExhaustedError",
    "VideoGenerationRequest",
    "VideoGenerationResponseError",
    "VideoGenerationTaskFailedError",
    "VideoGenerationTimeoutError",
    "VideoGenerationValidationError",
    "VideoTaskResult",
    "VideoTaskStatus",
    "video_generation_client",
]
