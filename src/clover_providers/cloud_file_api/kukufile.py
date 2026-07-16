import asyncio
import json
import mimetypes
import os
import re
import uuid
from pathlib import Path
from urllib.parse import urlparse

import requests
from nonebot import logger

from src.utils.async_utils import run_sync


BASE_URL = "https://d.kuku.lu"
SERVER_ENDPOINT = f"{BASE_URL}/_server.php"
REQUEST_TIMEOUT = (10, 30)
# urllib3 uses the connect timeout while it is still writing the request body.
# Keep the legacy 120-second budget so large multipart uploads are not cut off.
UPLOAD_TIMEOUT = (120, 300)
MAX_UPLOAD_SIZE = 512 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 64 * 1024
USER_KEY_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")
DOWNLOAD_HASH_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
    ),
}
POST_UPLOAD_HOST_SUFFIXES = (".kuku.lu",)
PUT_UPLOAD_HOST_SUFFIXES = (
    ".kuku.lu",
    ".amazonaws.com",
    ".r2.cloudflarestorage.com",
)
UPLOAD_SEMAPHORE = asyncio.Semaphore(2)


class KukufileProtocolError(RuntimeError):
    pass


class MultipartUploadStream:
    def __init__(
        self,
        file_path: Path,
        file_name: str,
        mime_type: str,
        fields: dict[str, object],
    ):
        self.file_path = file_path
        self.boundary = f"----Elysia{uuid.uuid4().hex}"
        parts = []
        for name, value in fields.items():
            parts.append(
                f"--{self.boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            )
        safe_name = file_name.replace("\\", "_").replace('"', "_")
        parts.append(
            f"--{self.boundary}\r\n"
            f'Content-Disposition: form-data; name="file_1"; '
            f'filename="{safe_name}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        )
        self.prefix = "".join(parts).encode("utf-8")
        self.suffix = f"\r\n--{self.boundary}--\r\n".encode("ascii")
        self.file_size = file_path.stat().st_size

    @property
    def content_type(self) -> str:
        return f"multipart/form-data; boundary={self.boundary}"

    def __len__(self) -> int:
        return len(self.prefix) + self.file_size + len(self.suffix)

    def __iter__(self):
        yield self.prefix
        with self.file_path.open("rb") as file_data:
            while chunk := file_data.read(UPLOAD_CHUNK_SIZE):
                yield chunk
        yield self.suffix


def _load_user_key() -> str:
    configured = os.getenv("KUKUFILE_USER_KEY", "").strip()
    if not configured:
        try:
            from nonebot import get_driver

            configured = str(
                getattr(get_driver().config, "kukufile_user_key", "") or ""
            ).strip()
        except Exception:
            configured = ""
    if configured and USER_KEY_PATTERN.fullmatch(configured):
        return configured.lower()
    if configured:
        logger.warning("KUKUFILE_USER_KEY 格式无效，将使用临时用户键")
    return uuid.uuid4().hex


USER_KEY = _load_user_key()


def _new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    session.cookies.set("cookie_uid", USER_KEY, domain="d.kuku.lu", path="/")
    return session


def _validate_download_url(value: str) -> str:
    if not isinstance(value, str):
        raise KukufileProtocolError("上传响应缺少下载链接")
    value = value.strip()
    parsed = urlparse(value)
    download_hash = parsed.path.strip("/")
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "d.kuku.lu"
        or not DOWNLOAD_HASH_PATTERN.fullmatch(download_hash)
    ):
        raise KukufileProtocolError("上传响应包含无效下载链接")
    return value


def _parse_post_upload_response(body: str) -> list[str]:
    body = body.strip()
    if not body.startswith("OK:"):
        raise KukufileProtocolError("上传节点返回失败状态")
    return ["OK", _validate_download_url(body.removeprefix("OK:"))]


def _is_allowed_upload_url(value: str, method: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
        port = parsed.port
    except (TypeError, ValueError):
        return False
    hostname = (parsed.hostname or "").lower()
    suffixes = POST_UPLOAD_HOST_SUFFIXES if method == "post" else PUT_UPLOAD_HOST_SUFFIXES
    return (
        parsed.scheme == "https"
        and port in {None, 443}
        and parsed.username is None
        and parsed.password is None
        and any(hostname.endswith(suffix) for suffix in suffixes)
    )


def _reject_redirect(response: requests.Response, context: str) -> None:
    if 300 <= response.status_code < 400:
        raise KukufileProtocolError(f"{context}返回了不受信任的重定向")


def _request_upload_server(
    session: requests.Session, file_name: str, file_size: int
) -> dict:
    upload_files = json.dumps(
        {"0": {"filename": file_name, "size": file_size}},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    response = session.post(
        SERVER_ENDPOINT,
        data={"action": "getUploadURL", "upload_files": upload_files},
        timeout=REQUEST_TIMEOUT,
        allow_redirects=False,
    )
    _reject_redirect(response, "上传节点协商")
    response.raise_for_status()
    try:
        data = response.json()
    except requests.JSONDecodeError as exc:
        raise KukufileProtocolError("上传节点协商返回了无效 JSON") from exc

    if not isinstance(data, dict):
        raise KukufileProtocolError("上传节点协商响应格式无效")
    servers = data.get("servers")
    if data.get("result") != "OK" or not isinstance(servers, list) or not servers:
        raise KukufileProtocolError("服务未提供可用上传节点")
    server = servers[0]
    if not isinstance(server, dict):
        raise KukufileProtocolError("上传节点格式无效")

    method = str(server.get("method", "")).lower()
    server_url = server.get("url")
    if method not in {"post", "put"} or not _is_allowed_upload_url(
        server_url, method
    ):
        raise KukufileProtocolError("上传节点配置无效")
    return server


def _register_put_upload(session: requests.Session, file_key: str) -> list[str]:
    if not file_key:
        raise KukufileProtocolError("PUT 上传响应缺少文件键")
    response = session.post(
        SERVER_ENDPOINT,
        data={
            "action": "registerFileByUser",
            "uuid": USER_KEY,
            "file_key": file_key,
            "thumimg": "",
        },
        timeout=REQUEST_TIMEOUT,
        allow_redirects=False,
    )
    _reject_redirect(response, "PUT 文件注册")
    response.raise_for_status()
    try:
        data = response.json()
    except requests.JSONDecodeError as exc:
        raise KukufileProtocolError("PUT 文件注册返回了无效 JSON") from exc
    if not isinstance(data, dict) or data.get("result") != "OK":
        raise KukufileProtocolError("PUT 文件注册失败")
    return ["OK", _validate_download_url(data.get("url"))]


def _upload_file(file_path: Path, file_name: str) -> list[str]:
    with _new_session() as session:
        server = _request_upload_server(session, file_name, file_path.stat().st_size)
        method = str(server["method"]).lower()
        server_url = server["url"]
        mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"

        if method == "post":
            data = {
                "ajax": "1",
                "uuid": USER_KEY,
                "country": "HK",
                "filecnt": 1,
                "file_1_name": file_name,
                "file_1_type": mime_type,
            }
            stream = MultipartUploadStream(file_path, file_name, mime_type, data)
            response = session.post(
                server_url,
                data=stream,
                headers={
                    "Content-Type": stream.content_type,
                    "Content-Length": str(len(stream)),
                },
                timeout=UPLOAD_TIMEOUT,
                allow_redirects=False,
            )
            _reject_redirect(response, "POST 文件上传")
            response.raise_for_status()
            return _parse_post_upload_response(response.text)

        with file_path.open("rb") as file_data:
            response = session.put(
                server_url,
                data=file_data,
                headers={"Content-Type": mime_type},
                timeout=UPLOAD_TIMEOUT,
                allow_redirects=False,
            )
        _reject_redirect(response, "PUT 文件上传")
        response.raise_for_status()
        return _register_put_upload(session, str(server.get("file_key", "")))


def _describe_request_error(exc: BaseException) -> str:
    if isinstance(exc, requests.Timeout):
        return "请求超时"
    pending = [exc]
    seen = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if current is not exc and isinstance(current, TimeoutError):
            return "上传连接写入超时"
        if isinstance(current, BaseException):
            pending.extend(
                item for item in current.args if isinstance(item, BaseException)
            )
            if current.__cause__ is not None:
                pending.append(current.__cause__)
            if current.__context__ is not None:
                pending.append(current.__context__)
    if isinstance(exc, requests.exceptions.SSLError):
        return "TLS 连接失败"
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, requests.ConnectionError):
        return "连接失败"
    return type(exc).__name__


def _extract_download_hash(status: list | tuple) -> str:
    if len(status) < 2 or status[0] != "OK":
        raise ValueError("无效的 Kukufile 上传状态")
    download_url = _validate_download_url(status[1])
    return urlparse(download_url).path.strip("/")


def _auto_delete_succeeded(body: str, content_type: str) -> bool:
    body = body.strip()
    if not body:
        return False
    if body.upper() == "OK":
        return True
    if re.fullmatch(r"result\s*=\s*OK\s*;?", body, re.IGNORECASE):
        return True
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    return (
        data.get("success") is True
        or str(data.get("result", "")).lower() == "ok"
        or str(data.get("status", "")).lower() in {"ok", "success"}
    )


def _response_kind(body: str, content_type: str) -> str:
    lowered = body.lower()
    if "cdn-cgi/challenge" in lowered or "just a moment" in lowered:
        return "Cloudflare challenge"
    if "text/html" in content_type.lower() or "<html" in lowered:
        return "unexpected HTML"
    return "unrecognized response"


def _set_expiration(status: list | tuple, time: int) -> str:
    if isinstance(time, bool) or not isinstance(time, int) or time <= 0:
        raise ValueError("Kukufile 删除时间必须为正整数秒")
    download_hash = _extract_download_hash(status)
    download_url = _validate_download_url(status[1])
    with _new_session() as session:
        headers = {
            "Referer": download_url,
            "X-Requested-With": "XMLHttpRequest",
        }
        response = session.post(
            f"{BASE_URL}/view.php",
            params={"hash": download_hash},
            headers=headers,
            data={
                "action": "addTimelimit",
                "set_timelimit": time,
            },
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )

    body = response.text.strip()
    content_type = response.headers.get("Content-Type", "unknown")
    if response.status_code == 200 and _auto_delete_succeeded(body, content_type):
        logger.debug("Kukufile 自动删除设置成功")
        return body
    raise RuntimeError(
        f"文件设定删除失败，状态码：{response.status_code}，"
        f"响应类型：{content_type}，响应摘要：{_response_kind(body, content_type)}"
    )


class Kukufile:
    @staticmethod
    async def upload_file(file_path, file_name: str | None = None):
        path = Path(file_path)
        try:
            if not path.is_file():
                logger.warning("Kukufile 上传文件不存在")
                return None
            file_size = path.stat().st_size
        except OSError as exc:
            logger.warning(
                f"Kukufile 上传文件无法读取: {_describe_request_error(exc)}"
            )
            return None
        if file_size > MAX_UPLOAD_SIZE:
            logger.warning("Kukufile 上传文件超过 512 MiB 限制")
            return None
        display_name = re.sub(
            r"[\r\n]+", " ", str(file_name or path.name)
        ).strip() or path.name

        def expire_cancelled_upload(status):
            if not isinstance(status, (list, tuple)):
                return
            try:
                _set_expiration(status, 600)
            except Exception as exc:
                logger.warning(
                    f"取消后的 Kukufile 上传未能设置过期时间: {type(exc).__name__}"
                )

        try:
            async with UPLOAD_SEMAPHORE:
                return await run_sync(
                    _upload_file,
                    path,
                    display_name,
                    _cancel_cleanup=expire_cancelled_upload,
                )
        except (OSError, requests.RequestException, KukufileProtocolError) as exc:
            detail = (
                str(exc)
                if isinstance(exc, KukufileProtocolError)
                else _describe_request_error(exc)
            )
            logger.warning(f"Kukufile 上传失败: {detail}")
            return None

    @staticmethod
    async def auto_delete_kukufile(status: list | tuple, time: int):
        try:
            return await run_sync(_set_expiration, status, time)
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Kukufile 自动删除请求失败: {_describe_request_error(exc)}"
            ) from exc
