import re


def sanitize_log_record(record) -> None:
    message = record["message"]
    if "Failed to parse event Dispatch(" not in message:
        return

    event_type = re.search(r"type='([^']+)'", message)
    type_name = event_type.group(1) if event_type else "unknown"
    record["message"] = (
        f"QQ event parse failed: type={type_name}; raw payload omitted"
    )
    record["exception"] = None
