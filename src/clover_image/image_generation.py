from __future__ import annotations

import asyncio
import base64
import binascii
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from threading import Lock
from urllib.parse import urlparse

import httpx

from src.configs.api_config import (
    image_generation_gpt_api_key,
    image_generation_gpt_base_url,
    image_generation_gpt_model,
    image_generation_seedream_api_key,
    image_generation_seedream_base_url,
    image_generation_seedream_model,
    image_generation_seedream_size,
    image_generation_size,
    image_generation_timeout,
)


MAX_REFERENCE_IMAGE_BYTES = 10 * 1024 * 1024
MAX_GENERATED_IMAGE_BYTES = 18 * 1024 * 1024
MAX_RESPONSE_BYTES = 30 * 1024 * 1024
MAX_PROMPT_LENGTH = 4000
DOWNLOAD_TIMEOUT_SECONDS = 45.0
GPT_IMAGE_MAX_EDGE = 3840
GPT_IMAGE_EDGE_MULTIPLE = 16
GPT_IMAGE_MAX_ASPECT_RATIO = 3
GPT_IMAGE_MIN_PIXELS = 655_360
GPT_IMAGE_MAX_PIXELS = 8_294_400
SEEDREAM_IMAGE_MAX_EDGE = 4096

_EXACT_IMAGE_SIZE_PATTERN = re.compile(
    r"^\s*(?P<width>[+-]?\d+)\s*[xX×*＊]\s*"
    r"(?P<height>[+-]?\d+)\s*$"
)

_QUOTA_ERROR_CODES = {
    "account_overdue",
    "arrearage",
    "billing_hard_limit_reached",
    "billing_not_active",
    "credit_balance_too_low",
    "insufficient_balance",
    "insufficient_credits",
    "insufficient_quota",
    "insufficient_user_quota",
    "balance_not_enough",
    "no_quota",
    "quota_exceeded",
    "quota_exhausted",
    "user_quota_exceeded",
    "usage_limit_reached",
}
_MODEL_UNAVAILABLE_CODES = {
    "invalid_model",
    "model_not_found",
    "model_not_supported",
    "no_available_channel",
    "unsupported_endpoint",
    "unsupported_model",
}
_QUOTA_MESSAGE_PATTERN = re.compile(
    r"(?:insufficient\s+(?:quota|credits?|balance)|"
    r"(?:quota|credits?)\s+(?:exhausted|exceeded)|"
    r"credit\s+balance\s+too\s+low|"
    r"额度(?:不足|已用完|用尽|已?耗尽|已达上限)|余额不足|欠费|请充值)",
    re.IGNORECASE,
)
_RATE_LIMIT_MESSAGE_PATTERN = re.compile(
    r"(?:rate\s*limit|too\s+many\s+requests|\b(?:rpm|tpm)\b|"
    r"请求过于频繁|上游负载已饱和)",
    re.IGNORECASE,
)


class ImageGenerationError(RuntimeError):
    """A safe-to-log image generation failure."""


class ImageGenerationConfigurationError(ImageGenerationError):
    """Image generation configuration is missing or invalid."""


class ImageGenerationQuotaExhaustedError(ImageGenerationError):
    """All providers eligible for the request explicitly exhausted quota."""


class InvalidImageSizeError(ImageGenerationError):
    """The requested dimensions are unsupported by every eligible provider."""


class UnsupportedReferenceImageError(ImageGenerationError):
    """The reference image format cannot be sent to either provider."""


class ImageGenerationHTTPError(ImageGenerationError):
    def __init__(
        self,
        status_code: int,
        *,
        error_codes: frozenset[str] = frozenset(),
        error_param: str | None = None,
        quota_exhausted: bool = False,
        authentication_failed: bool = False,
    ):
        self.status_code = status_code
        self.error_codes = error_codes
        self.error_param = error_param
        self.quota_exhausted = quota_exhausted
        self.authentication_failed = authentication_failed
        self.retryable = status_code in {404, 429}
        self.retryable = self.retryable or quota_exhausted or authentication_failed
        self.retryable = self.retryable or bool(
            error_codes & _MODEL_UNAVAILABLE_CODES
        )
        self.retryable = self.retryable or (
            status_code == 400 and error_param == "model"
        )
        super().__init__(f"生图接口返回 HTTP {status_code}")


class ImageGenerationProviderKind(str, Enum):
    GPT = "gpt"
    SEEDREAM = "seedream"


@dataclass(frozen=True)
class ImageDimensions:
    width: int
    height: int

    @property
    def api_value(self) -> str:
        return f"{self.width}x{self.height}"

    def __str__(self) -> str:
        return self.api_value


@dataclass(frozen=True)
class ImageGenerationProvider:
    model: str
    kind: ImageGenerationProviderKind
    base_url: str
    api_key: str = field(repr=False)


@dataclass(frozen=True)
class _ResponseErrorMetadata:
    codes: frozenset[str] = frozenset()
    error_param: str | None = None
    quota_exhausted: bool = False


@dataclass(frozen=True)
class ReferenceImage:
    content: bytes
    media_type: str
    filename: str


@dataclass(frozen=True)
class GeneratedImage:
    content: bytes
    media_type: str
    filename: str
    model: str
    revised_prompt: str | None = None


@dataclass(frozen=True)
class _GenerationPayload:
    content: bytes | None = None
    media_type: str | None = None
    url: str | None = None
    revised_prompt: str | None = None


class RoundRobinModelBalancer:
    def __init__(self, models: tuple[str, ...] | list[str]):
        normalized = tuple(model.strip() for model in models if model.strip())
        if not normalized:
            raise ImageGenerationConfigurationError("未配置可用的生图模型")
        self.models = normalized
        self._index = 0
        self._lock = Lock()

    def next_order(self) -> tuple[str, ...]:
        with self._lock:
            start = self._index
            self._index = (self._index + 1) % len(self.models)
        return self.models[start:] + self.models[:start]


def parse_exact_image_dimensions(value: str) -> ImageDimensions | None:
    match = _EXACT_IMAGE_SIZE_PATTERN.fullmatch(value)
    if match is None:
        return None
    try:
        width = int(match.group("width"))
        height = int(match.group("height"))
    except ValueError as exc:
        raise InvalidImageSizeError("分辨率数值无效") from exc
    return ImageDimensions(width=width, height=height)


def image_size_validation_error(
    dimensions: ImageDimensions,
    provider_kind: ImageGenerationProviderKind,
) -> str | None:
    if (
        type(dimensions.width) is not int
        or type(dimensions.height) is not int
    ):
        return "宽高必须是整数"
    if dimensions.width <= 0 or dimensions.height <= 0:
        return "宽高必须大于 0"

    if provider_kind is ImageGenerationProviderKind.SEEDREAM:
        if (
            dimensions.width > SEEDREAM_IMAGE_MAX_EDGE
            or dimensions.height > SEEDREAM_IMAGE_MAX_EDGE
        ):
            return f"宽高均不能超过 {SEEDREAM_IMAGE_MAX_EDGE}px"
        return None

    long_edge = max(dimensions.width, dimensions.height)
    short_edge = min(dimensions.width, dimensions.height)
    total_pixels = dimensions.width * dimensions.height
    if long_edge > GPT_IMAGE_MAX_EDGE:
        return f"长边不能超过 {GPT_IMAGE_MAX_EDGE}px"
    if (
        dimensions.width % GPT_IMAGE_EDGE_MULTIPLE != 0
        or dimensions.height % GPT_IMAGE_EDGE_MULTIPLE != 0
    ):
        return f"宽高必须是 {GPT_IMAGE_EDGE_MULTIPLE}px 的倍数"
    if long_edge > short_edge * GPT_IMAGE_MAX_ASPECT_RATIO:
        return f"长短边比例不能超过 {GPT_IMAGE_MAX_ASPECT_RATIO}:1"
    if total_pixels < GPT_IMAGE_MIN_PIXELS:
        return f"总像素不能少于 {GPT_IMAGE_MIN_PIXELS:,}"
    if total_pixels > GPT_IMAGE_MAX_PIXELS:
        return f"总像素不能超过 {GPT_IMAGE_MAX_PIXELS:,}"
    return None


def validate_requested_dimensions(
    dimensions: ImageDimensions | None,
    provider_kinds: tuple[ImageGenerationProviderKind, ...]
    | list[ImageGenerationProviderKind] = (
        ImageGenerationProviderKind.GPT,
        ImageGenerationProviderKind.SEEDREAM,
    ),
) -> None:
    if dimensions is None:
        return
    if not isinstance(dimensions, ImageDimensions):
        raise InvalidImageSizeError("分辨率参数无效")

    errors: list[str] = []
    checked_kinds: set[ImageGenerationProviderKind] = set()
    for provider_kind in provider_kinds:
        if provider_kind in checked_kinds:
            continue
        checked_kinds.add(provider_kind)
        reason = image_size_validation_error(dimensions, provider_kind)
        if reason is None:
            return
        provider_name = (
            "Seedream"
            if provider_kind is ImageGenerationProviderKind.SEEDREAM
            else "GPT"
        )
        errors.append(f"{provider_name}：{reason}")

    detail = f"（{'；'.join(errors)}）" if errors else ""
    raise InvalidImageSizeError(
        f"分辨率 {dimensions} 不受当前可用模型支持{detail}"
    )


def _detect_media_type(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith(b"BM"):
        return "image/bmp"
    return None


def _extension_for_media_type(media_type: str) -> str:
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/gif": "gif",
        "image/webp": "webp",
        "image/bmp": "bmp",
    }.get(media_type, "png")


def _validated_image(
    content: bytes,
    *,
    max_bytes: int,
    error_label: str,
) -> tuple[bytes, str]:
    if not content:
        raise ImageGenerationError(f"{error_label}为空")
    if len(content) > max_bytes:
        raise ImageGenerationError(f"{error_label}超过大小限制")
    media_type = _detect_media_type(content)
    if media_type is None:
        raise ImageGenerationError(f"{error_label}不是受支持的图片格式")
    return content, media_type


def reference_image_from_bytes(content: bytes) -> ReferenceImage:
    content, media_type = _validated_image(
        content,
        max_bytes=MAX_REFERENCE_IMAGE_BYTES,
        error_label="参考图",
    )
    if media_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise UnsupportedReferenceImageError(
            "参考图仅支持 PNG、JPEG 或 WebP 格式"
        )
    extension = _extension_for_media_type(media_type)
    return ReferenceImage(content, media_type, f"reference.{extension}")


async def read_reference_image(path: str | Path) -> ReferenceImage:
    try:
        content = await asyncio.to_thread(Path(path).read_bytes)
    except OSError as exc:
        raise ImageGenerationError("读取参考图失败") from exc
    return reference_image_from_bytes(content)


def _validate_http_url(url: str, *, error_label: str) -> str:
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise ImageGenerationError(f"{error_label}地址无效") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ImageGenerationError(f"{error_label}地址无效")
    return url


async def _download_image(
    url: str,
    *,
    max_bytes: int,
    error_label: str,
    headers: dict[str, str] | None = None,
) -> tuple[bytes, str]:
    _validate_http_url(url, error_label=error_label)
    timeout = httpx.Timeout(DOWNLOAD_TIMEOUT_SECONDS, connect=10.0)
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=headers,
        ) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > max_bytes:
                    raise ImageGenerationError(f"{error_label}超过大小限制")

                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > max_bytes:
                        raise ImageGenerationError(f"{error_label}超过大小限制")
    except ImageGenerationError:
        raise
    except httpx.TimeoutException as exc:
        raise ImageGenerationError(f"{error_label}下载超时") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise ImageGenerationError(f"{error_label}下载失败") from exc

    return _validated_image(bytes(content), max_bytes=max_bytes, error_label=error_label)


async def download_reference_image(url: str) -> ReferenceImage:
    content, _ = await _download_image(
        url,
        max_bytes=MAX_REFERENCE_IMAGE_BYTES,
        error_label="参考图",
    )
    return reference_image_from_bytes(content)


async def _bounded_post(
    client: httpx.AsyncClient,
    url: str,
    **kwargs,
) -> httpx.Response:
    async with client.stream("POST", url, **kwargs) as response:
        content_length = response.headers.get("Content-Length")
        try:
            declared_length = int(content_length) if content_length else None
        except ValueError:
            declared_length = None
        if declared_length is not None and declared_length > MAX_RESPONSE_BYTES:
            raise ImageGenerationError("生图接口响应超过大小限制")

        content = bytearray()
        async for chunk in response.aiter_bytes():
            content.extend(chunk)
            if len(content) > MAX_RESPONSE_BYTES:
                raise ImageGenerationError("生图接口响应超过大小限制")

        headers = httpx.Headers(response.headers)
        headers.pop("Content-Encoding", None)
        headers.pop("Content-Length", None)
        return httpx.Response(
            response.status_code,
            headers=headers,
            content=bytes(content),
            request=response.request,
        )


def _decode_base64_image(value: str) -> tuple[bytes, str]:
    encoded = value
    if value.startswith("data:"):
        try:
            header, encoded = value.split(",", 1)
        except ValueError as exc:
            raise ImageGenerationError("生图接口返回了无效的图片数据") from exc
        if ";base64" not in header.lower():
            raise ImageGenerationError("生图接口返回了无效的图片数据")

    encoded = "".join(encoded.split())
    encoded += "=" * (-len(encoded) % 4)
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ImageGenerationError("生图接口返回了无效的图片数据") from exc
    return _validated_image(
        content,
        max_bytes=MAX_GENERATED_IMAGE_BYTES,
        error_label="生成图片",
    )


def _extract_generation_payload(response: httpx.Response) -> _GenerationPayload:
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise ImageGenerationError("生图接口响应超过大小限制")

    content_type = response.headers.get("Content-Type", "").lower()
    if content_type.startswith("image/"):
        content, media_type = _validated_image(
            response.content,
            max_bytes=MAX_GENERATED_IMAGE_BYTES,
            error_label="生成图片",
        )
        return _GenerationPayload(content=content, media_type=media_type)

    try:
        payload = response.json()
    except ValueError as exc:
        raise ImageGenerationError("生图接口返回了无法解析的响应") from exc
    if not isinstance(payload, dict):
        raise ImageGenerationError("生图接口响应格式不正确")

    data = payload.get("data") or payload.get("images") or payload.get("output")
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        raise ImageGenerationError("生图接口未返回图片")

    item = data[0]
    if isinstance(item, str):
        return _GenerationPayload(url=item)
    if not isinstance(item, dict):
        raise ImageGenerationError("生图接口响应格式不正确")

    revised_prompt = item.get("revised_prompt")
    if not isinstance(revised_prompt, str):
        revised_prompt = None

    encoded = item.get("b64_json") or item.get("b64") or item.get("base64")
    if isinstance(encoded, str) and encoded:
        content, media_type = _decode_base64_image(encoded)
        return _GenerationPayload(
            content=content,
            media_type=media_type,
            revised_prompt=revised_prompt,
        )

    url = item.get("url") or item.get("image_url")
    if not isinstance(url, str) or not url:
        raise ImageGenerationError("生图接口未返回图片")
    if url.startswith("data:"):
        content, media_type = _decode_base64_image(url)
        return _GenerationPayload(
            content=content,
            media_type=media_type,
            revised_prompt=revised_prompt,
        )
    return _GenerationPayload(url=url, revised_prompt=revised_prompt)


def _same_origin(first: str, second: str) -> bool:
    first_url = urlparse(first)
    second_url = urlparse(second)
    return (
        first_url.scheme.lower(),
        first_url.hostname,
        first_url.port,
    ) == (
        second_url.scheme.lower(),
        second_url.hostname,
        second_url.port,
    )


def _normalize_error_code(value: str) -> str:
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value.strip())
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def _response_error_metadata(response: httpx.Response) -> _ResponseErrorMetadata:
    quota_exhausted = response.status_code == 402
    if len(response.content) > 1024 * 1024:
        return _ResponseErrorMetadata(quota_exhausted=quota_exhausted)
    try:
        payload = response.json()
    except ValueError:
        return _ResponseErrorMetadata(quota_exhausted=quota_exhausted)
    if not isinstance(payload, dict):
        return _ResponseErrorMetadata(quota_exhausted=quota_exhausted)

    error = payload.get("error")
    code_candidates = []
    message_candidates = []
    error_param = None
    if isinstance(error, dict):
        code_candidates.extend((error.get("code"), error.get("type")))
        message_candidates.append(error.get("message"))
        if isinstance(error.get("param"), str):
            error_param = _normalize_error_code(error["param"])
    elif isinstance(error, str):
        message_candidates.append(error)
    code_candidates.extend((payload.get("code"), payload.get("type")))
    message_candidates.extend((payload.get("message"), payload.get("detail")))

    codes = frozenset(
        normalized
        for candidate in code_candidates
        if isinstance(candidate, str) and candidate.strip()
        if (normalized := _normalize_error_code(candidate))
    )
    compact_quota_codes = {code.replace("_", "") for code in _QUOTA_ERROR_CODES}
    quota_exhausted = quota_exhausted or any(
        code in _QUOTA_ERROR_CODES or code.replace("_", "") in compact_quota_codes
        for code in codes
    )

    messages = " ".join(
        candidate[:512]
        for candidate in message_candidates
        if isinstance(candidate, str)
    )
    if messages and not _RATE_LIMIT_MESSAGE_PATTERN.search(messages):
        quota_exhausted = quota_exhausted or bool(
            _QUOTA_MESSAGE_PATTERN.search(messages)
        )
    return _ResponseErrorMetadata(
        codes=codes,
        error_param=error_param,
        quota_exhausted=quota_exhausted,
    )


class ImageGenerationClient:
    def __init__(
        self,
        *,
        providers: tuple[ImageGenerationProvider, ...]
        | list[ImageGenerationProvider]
        | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        models: tuple[str, ...] | list[str] | None = None,
        size: str = "1024x1024",
        seedream_size: str = "2K",
        timeout_seconds: float = 300.0,
    ):
        if providers is None:
            if base_url is None or api_key is None or models is None:
                raise ImageGenerationConfigurationError("生图 provider 配置不完整")
            providers = [
                ImageGenerationProvider(
                    model=model,
                    kind=(
                        ImageGenerationProviderKind.SEEDREAM
                        if model.lower().startswith("doubao-seedream")
                        else ImageGenerationProviderKind.GPT
                    ),
                    base_url=base_url,
                    api_key=api_key,
                )
                for model in models
            ]
        elif base_url is not None or api_key is not None or models is not None:
            raise ImageGenerationConfigurationError(
                "不能混用独立 provider 与旧版共享生图配置"
            )

        normalized_providers = tuple(
            ImageGenerationProvider(
                model=provider.model.strip(),
                kind=provider.kind,
                base_url=provider.base_url.rstrip("/"),
                api_key=provider.api_key.strip(),
            )
            for provider in providers
        )
        if not normalized_providers:
            raise ImageGenerationConfigurationError("未配置可用的生图 provider")
        self.providers = normalized_providers
        self.providers_by_model = {
            provider.model: provider for provider in normalized_providers
        }
        if len(self.providers_by_model) != len(normalized_providers):
            raise ImageGenerationConfigurationError("生图 provider 模型名称不能重复")
        self.size = size.strip()
        self.seedream_size = seedream_size.strip()
        self.timeout_seconds = float(timeout_seconds)
        self.balancer = RoundRobinModelBalancer(
            tuple(provider.model for provider in normalized_providers)
        )

    def _default_size_for_provider(
        self,
        provider: ImageGenerationProvider,
    ) -> str:
        configured_size = (
            self.seedream_size
            if provider.kind is ImageGenerationProviderKind.SEEDREAM
            else self.size
        )
        dimensions = parse_exact_image_dimensions(configured_size)
        if dimensions is not None:
            return dimensions.api_value
        if configured_size.casefold() == "auto":
            return "auto"
        if (
            provider.kind is ImageGenerationProviderKind.SEEDREAM
            and configured_size.casefold() in {"1k", "2k", "4k"}
        ):
            return configured_size.upper()
        return configured_size

    def _request_size_for_provider(
        self,
        provider: ImageGenerationProvider,
        dimensions: ImageDimensions | None,
    ) -> str:
        if dimensions is None:
            return self._default_size_for_provider(provider)
        reason = image_size_validation_error(dimensions, provider.kind)
        if reason is not None:
            provider_name = (
                "Seedream"
                if provider.kind is ImageGenerationProviderKind.SEEDREAM
                else "GPT"
            )
            raise InvalidImageSizeError(
                f"{provider_name} 不支持分辨率 {dimensions}：{reason}"
            )
        return dimensions.api_value

    def validate_requested_dimensions(
        self,
        dimensions: ImageDimensions | None,
    ) -> None:
        validate_requested_dimensions(
            dimensions,
            [provider.kind for provider in self.providers],
        )

    def validate_request(
        self,
        dimensions: ImageDimensions | None = None,
    ) -> None:
        self._validate_configuration()
        self.validate_requested_dimensions(dimensions)

    def _validate_configuration(self) -> None:
        if not self.size:
            raise ImageGenerationConfigurationError("未配置生图尺寸")
        if not self.seedream_size:
            raise ImageGenerationConfigurationError("未配置 Seedream 生图尺寸")
        for provider in self.providers:
            if not provider.model:
                raise ImageGenerationConfigurationError("未配置生图模型")
            _validate_http_url(
                provider.base_url,
                error_label=f"{provider.kind.value} 生图 API",
            )
            if not provider.api_key or provider.api_key in {"<KEY>", "<API_KEY>"}:
                raise ImageGenerationConfigurationError(
                    f"未配置 {provider.kind.value} 生图 API 密钥"
                )
            configured_size = self._default_size_for_provider(provider)
            configured_dimensions = parse_exact_image_dimensions(configured_size)
            if configured_dimensions is not None:
                reason = image_size_validation_error(
                    configured_dimensions,
                    provider.kind,
                )
                if reason is not None:
                    raise ImageGenerationConfigurationError(
                        f"{provider.kind.value} 默认生图尺寸无效：{reason}"
                    )
            elif provider.kind is ImageGenerationProviderKind.GPT:
                if configured_size != "auto":
                    raise ImageGenerationConfigurationError(
                        "gpt 默认生图尺寸必须为 auto 或有效的宽x高"
                    )
            elif configured_size not in {"auto", "1K", "2K", "4K"}:
                raise ImageGenerationConfigurationError(
                    "seedream 默认生图尺寸必须为 auto、1K、2K、4K 或有效的宽x高"
                )
        if self.timeout_seconds <= 0:
            raise ImageGenerationConfigurationError("生图超时配置无效")

    async def _request_model(
        self,
        client: httpx.AsyncClient,
        *,
        provider: ImageGenerationProvider,
        prompt: str,
        reference: ReferenceImage | None,
        dimensions: ImageDimensions | None = None,
    ) -> _GenerationPayload:
        model = provider.model
        request_size = self._request_size_for_provider(provider, dimensions)
        headers = {
            "Authorization": f"Bearer {provider.api_key}",
            "Accept": "application/json, image/*",
        }
        if reference is None:
            response = await _bounded_post(
                client,
                f"{provider.base_url}/v1/images/generations",
                headers=headers,
                json={"model": model, "prompt": prompt, "size": request_size},
            )
        elif provider.kind is ImageGenerationProviderKind.SEEDREAM:
            encoded = base64.b64encode(reference.content).decode("ascii")
            response = await _bounded_post(
                client,
                f"{provider.base_url}/v1/images/generations",
                headers=headers,
                json={
                    "model": model,
                    "prompt": prompt,
                    "image": f"data:{reference.media_type};base64,{encoded}",
                    "size": request_size,
                },
            )
        else:
            response = await _bounded_post(
                client,
                f"{provider.base_url}/v1/images/edits",
                headers=headers,
                data={"model": model, "prompt": prompt, "size": request_size},
                files={
                    "image": (
                        reference.filename,
                        reference.content,
                        reference.media_type,
                    )
                },
            )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            metadata = _response_error_metadata(response)
            raise ImageGenerationHTTPError(
                response.status_code,
                error_codes=metadata.codes,
                error_param=metadata.error_param,
                quota_exhausted=metadata.quota_exhausted,
                authentication_failed=(
                    response.status_code in {401, 403}
                    and not metadata.quota_exhausted
                ),
            ) from exc
        return _extract_generation_payload(response)

    async def _download_generated_image(
        self,
        url: str,
        *,
        provider: ImageGenerationProvider | None = None,
    ) -> tuple[bytes, str]:
        provider = provider or self.providers[0]
        headers = None
        if _same_origin(url, provider.base_url):
            headers = {"Authorization": f"Bearer {provider.api_key}"}
        return await _download_image(
            url,
            max_bytes=MAX_GENERATED_IMAGE_BYTES,
            error_label="生成图片",
            headers=headers,
        )

    async def _generate_remote(
        self,
        prompt: str,
        *,
        reference: ReferenceImage | None,
        dimensions: ImageDimensions | None,
    ) -> GeneratedImage:
        ordered_providers = tuple(
            self.providers_by_model[model]
            for model in self.balancer.next_order()
        )
        compatible_providers = tuple(
            provider
            for provider in ordered_providers
            if dimensions is None
            or image_size_validation_error(dimensions, provider.kind) is None
        )
        if not compatible_providers:
            self.validate_requested_dimensions(dimensions)
            raise InvalidImageSizeError("分辨率参数无效")
        provider_scope = (
            "所有"
            if len(compatible_providers) == len(ordered_providers)
            else "支持当前分辨率的"
        )

        timeout = httpx.Timeout(self.timeout_seconds, connect=10.0)
        failures: list[str] = []
        failure_kinds: list[str] = []
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            for provider in compatible_providers:
                model = provider.model
                try:
                    payload = await self._request_model(
                        client,
                        provider=provider,
                        prompt=prompt,
                        reference=reference,
                        dimensions=dimensions,
                    )
                except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
                    failures.append(f"{model}: 连接失败")
                    failure_kinds.append("connection")
                except httpx.TimeoutException as exc:
                    raise ImageGenerationError(
                        "生图请求结果未知，已停止自动切换模型"
                    ) from exc
                except httpx.HTTPError as exc:
                    raise ImageGenerationError(
                        "生图请求结果未知，已停止自动切换模型"
                    ) from exc
                except ImageGenerationHTTPError as exc:
                    if not exc.retryable:
                        raise
                    failures.append(f"{model}: {exc}")
                    if exc.quota_exhausted:
                        failure_kinds.append("quota")
                    elif exc.authentication_failed:
                        failure_kinds.append("authentication")
                    else:
                        failure_kinds.append("provider")
                else:
                    if payload.content is not None and payload.media_type is not None:
                        content, media_type = payload.content, payload.media_type
                    elif payload.url is not None:
                        content, media_type = await self._download_generated_image(
                            payload.url,
                            provider=provider,
                        )
                    else:
                        raise ImageGenerationError("生图接口未返回图片")

                    extension = _extension_for_media_type(media_type)
                    return GeneratedImage(
                        content=content,
                        media_type=media_type,
                        filename=f"generated.{extension}",
                        model=model,
                        revised_prompt=payload.revised_prompt,
                    )

        if failure_kinds and all(kind == "quota" for kind in failure_kinds):
            raise ImageGenerationQuotaExhaustedError(
                f"{provider_scope}生图渠道额度均已用完"
            )
        if failure_kinds and all(
            kind == "authentication" for kind in failure_kinds
        ):
            raise ImageGenerationConfigurationError(
                f"{provider_scope}生图渠道鉴权失败"
            )
        failure_summary = "; ".join(failures)
        raise ImageGenerationError(
            f"当前请求可用的生图模型均不可用 ({failure_summary})"
        )

    async def generate(
        self,
        prompt: str,
        *,
        reference: ReferenceImage | None = None,
        dimensions: ImageDimensions | None = None,
    ) -> GeneratedImage:
        self.validate_request(dimensions)
        prompt = prompt.strip()
        if not prompt:
            raise ImageGenerationError("提示词不能为空")
        if len(prompt) > MAX_PROMPT_LENGTH:
            raise ImageGenerationError("提示词过长")
        if reference is not None:
            reference = reference_image_from_bytes(reference.content)

        try:
            return await asyncio.wait_for(
                self._generate_remote(
                    prompt,
                    reference=reference,
                    dimensions=dimensions,
                ),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise ImageGenerationError(
                "生图请求结果未知，已停止自动切换模型"
            ) from exc


image_generation_client = ImageGenerationClient(
    providers=(
        ImageGenerationProvider(
            model=image_generation_gpt_model,
            kind=ImageGenerationProviderKind.GPT,
            base_url=image_generation_gpt_base_url,
            api_key=image_generation_gpt_api_key,
        ),
        ImageGenerationProvider(
            model=image_generation_seedream_model,
            kind=ImageGenerationProviderKind.SEEDREAM,
            base_url=image_generation_seedream_base_url,
            api_key=image_generation_seedream_api_key,
        ),
    ),
    size=image_generation_size,
    seedream_size=image_generation_seedream_size,
    timeout_seconds=image_generation_timeout,
)
