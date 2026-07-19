import logging
import re
from collections.abc import Callable


QQ_MEDIA_URL_PATTERN = re.compile(
    r"https://(?:multimedia\.nt\.qq\.com\.cn|qqbot\.ugcimg\.cn)/[^'\"\s)]+"
)
MESSAGE_EVENT_PREFIX = re.compile(
    r"^(QQ\b[^|\r\n]*\|\s*"
    r"\[EventType\.[A-Z0-9_]*MESSAGE_CREATE\]:)"
)
DISPATCH_TYPE_SUFFIX = re.compile(
    r",\s*type='([A-Z][A-Z0-9_]*)'"
    r"(?:,\s*id=(?:None|'[^'\r\n]*'))?\)\s*$"
)
OPENID_PATTERN = re.compile(r"(?<![A-Fa-f0-9])[A-Fa-f0-9]{32}(?![A-Fa-f0-9])")
LABELED_CONTENT_PATTERN = re.compile(
    r"((?:\b(?:keyword|content|input|output|text|prompt|query|messages?|"
    r"completion|reply|answer|values?|token|secret|password|error|response|"
    r"body|data)\b|\berror[_ -]?message\b|"
    r"\bapi[_ -]?key\b|\bkey\b|(?:密钥|用户回复|回复参数|文本|内容))"
    r"\s*[:：=]\s*).*$",
    flags=re.IGNORECASE | re.DOTALL,
)


def _safe_exception_summary(exception) -> str:
    value = getattr(exception, "value", exception)
    if value is None:
        return "unknown"

    name = type(value).__name__
    errors_method = getattr(value, "errors", None)
    if not callable(errors_method):
        return name

    try:
        errors = errors_method()
    except Exception:
        return name

    issues = []
    for error in errors[:5] if isinstance(errors, list) else []:
        if not isinstance(error, dict):
            continue
        location = error.get("loc", ())
        if not isinstance(location, (list, tuple)):
            location = (location,)
        safe_location = (
            ".".join(
                re.sub(r"[^A-Za-z0-9_-]", "?", str(part))[:40] for part in location
            )
            or "unknown"
        )
        error_type = re.sub(r"[^A-Za-z0-9_.-]", "?", str(error.get("type", "unknown")))[
            :60
        ]
        issues.append(f"{safe_location}:{error_type}")
    return f"{name}[{','.join(issues)}]" if issues else name


def _sanitize_record_exception(record) -> None:
    exception = record.get("exception")
    value = getattr(exception, "value", None)
    if value is None:
        return

    safe_value = RuntimeError(f"{type(value).__name__}: details omitted")
    replace = getattr(exception, "_replace", None)
    if callable(replace):
        record["exception"] = replace(value=safe_value)
    else:
        record["exception"] = safe_value


def sanitize_log_record(record) -> None:
    message = record["message"]
    message = QQ_MEDIA_URL_PATTERN.sub("<QQ media URL omitted>", message)
    if match := MESSAGE_EVENT_PREFIX.match(message):
        message = f"{message[: match.end()]} message content omitted"

    if "Failed to parse event Dispatch(" in message:
        event_type = DISPATCH_TYPE_SUFFIX.search(message)
        type_name = event_type.group(1) if event_type else "unknown"
        error_summary = _safe_exception_summary(record.get("exception"))
        record["message"] = (
            f"QQ event parse failed: type={type_name}; error={error_summary}; "
            "raw payload omitted"
        )
        record["exception"] = None
        return

    message = OPENID_PATTERN.sub("<openid omitted>", message)
    message = LABELED_CONTENT_PATTERN.sub(r"\1<text omitted>", message)
    record["message"] = message
    _sanitize_record_exception(record)


def get_log_record_patcher(debug: bool) -> Callable[[dict], None] | None:
    """Disable log sanitization in debug mode so diagnostics stay intact."""
    return None if debug else sanitize_log_record


def is_debug_mode(config: object) -> bool:
    """Read debug mode across NoneBot versions.

    NoneBot 2.5 removed ``Config.debug``; its replacement is ``log_level``.
    Keep the old field as a fallback so this remains compatible with earlier
    releases too.
    """
    debug = getattr(config, "debug", None)
    if debug is not None:
        if isinstance(debug, str):
            return debug.strip().lower() in {"1", "true", "yes", "on"}
        return bool(debug)

    log_level = getattr(config, "log_level", "INFO")
    if isinstance(log_level, int):
        return log_level <= logging.DEBUG
    return str(log_level).strip().upper() in {"DEBUG", "TRACE"}
