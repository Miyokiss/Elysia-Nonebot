import re


QQ_MEDIA_URL_PATTERN = re.compile(
    r"https://(?:multimedia\.nt\.qq\.com\.cn|qqbot\.ugcimg\.cn)/[^'\"\s)]+"
)
C2C_EVENT_PREFIX = re.compile(
    r"^QQ\b[^|\r\n]*\|\s*\[EventType\.C2C_MESSAGE_CREATE\]:"
)
DISPATCH_TYPE_SUFFIX = re.compile(r"\btype='([A-Z][A-Z0-9_]*)'\)\s*$")


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
        safe_location = ".".join(
            re.sub(r"[^A-Za-z0-9_-]", "?", str(part))[:40]
            for part in location
        ) or "unknown"
        error_type = re.sub(
            r"[^A-Za-z0-9_.-]", "?", str(error.get("type", "unknown"))
        )[:60]
        issues.append(f"{safe_location}:{error_type}")
    return f"{name}[{','.join(issues)}]" if issues else name


def sanitize_log_record(record) -> None:
    message = record["message"]
    message = QQ_MEDIA_URL_PATTERN.sub("<QQ media URL omitted>", message)
    if match := C2C_EVENT_PREFIX.match(message):
        message = f"{message[:match.end()]} message content omitted"
    record["message"] = message

    if "Failed to parse event Dispatch(" not in message:
        return

    event_type = DISPATCH_TYPE_SUFFIX.search(message)
    type_name = event_type.group(1) if event_type else "unknown"
    error_summary = _safe_exception_summary(record.get("exception"))
    record["message"] = (
        f"QQ event parse failed: type={type_name}; error={error_summary}; "
        "raw payload omitted"
    )
    record["exception"] = None
