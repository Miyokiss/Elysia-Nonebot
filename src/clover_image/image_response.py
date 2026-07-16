import json
from urllib.parse import urlparse


XJH_IMAGE_HOSTS = {"img.xjh.me"}


class ImageServiceError(RuntimeError):
    """Raised when a remote image service returns an unusable response."""


def parse_xjh_image_response(
    status: int, body: str, content_type: str = "unknown"
) -> str:
    if status != 200:
        raise ImageServiceError(f"random image API returned HTTP {status}")

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ImageServiceError(
            f"random image API returned invalid JSON ({content_type})"
        ) from exc

    image_url = data.get("img") if isinstance(data, dict) else None
    if not isinstance(image_url, str) or not image_url.strip():
        raise ImageServiceError("random image API response has no image URL")
    image_url = image_url.strip()
    if image_url.startswith("//"):
        image_url = f"https:{image_url}"
    try:
        parsed = urlparse(image_url)
        port = parsed.port
    except ValueError as exc:
        raise ImageServiceError("random image API returned an invalid image URL") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname not in XJH_IMAGE_HOSTS
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ImageServiceError("random image API returned an untrusted image URL")
    return image_url
