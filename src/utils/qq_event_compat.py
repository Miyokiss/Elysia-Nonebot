from collections import defaultdict
from copy import deepcopy

from nonebot import logger
from nonebot.adapters.qq import Adapter as QQAdapter
from pydantic import ValidationError


QQ_MESSAGE_EVENT_TYPES = {
    "C2C_MESSAGE_CREATE",
    "GROUP_AT_MESSAGE_CREATE",
    "GROUP_MESSAGE_CREATE",
}
REPAIRABLE_REPLY_FIELDS = {"message_type", "msg_idx"}

_repair_counts: dict[str, int] = defaultdict(int)


def _event_type(payload) -> str:
    value = getattr(payload, "type", "")
    return str(getattr(value, "value", value) or "")


def _missing_reply_fields(exc: ValidationError) -> dict[int, set[str]] | None:
    missing: dict[int, set[str]] = defaultdict(set)
    errors = exc.errors()
    if not errors:
        return None

    for error in errors:
        location = error.get("loc")
        if (
            error.get("type") != "missing"
            or not isinstance(location, tuple)
            or len(location) != 3
            or location[0] != "msg_elements"
            or not isinstance(location[1], int)
            or location[1] < 0
            or location[2] not in REPAIRABLE_REPLY_FIELDS
        ):
            return None
        missing[location[1]].add(location[2])
    return dict(missing)


def _copy_payload_with_reply_defaults(payload, missing: dict[int, set[str]]):
    data = getattr(payload, "data", None)
    if not isinstance(data, dict):
        return None
    elements = data.get("msg_elements")
    if not isinstance(elements, list):
        return None

    normalized_data = deepcopy(data)
    normalized_elements = normalized_data["msg_elements"]
    parent_message_type = normalized_data.get("message_type")
    if not isinstance(parent_message_type, int) or isinstance(
        parent_message_type, bool
    ):
        parent_message_type = 0
    parent_msg_idx = normalized_data.get("msg_idx")
    if not isinstance(parent_msg_idx, str):
        parent_msg_idx = ""

    for index, fields in missing.items():
        if index >= len(normalized_elements):
            return None
        element = normalized_elements[index]
        if not isinstance(element, dict):
            return None
        if "message_type" in fields:
            element["message_type"] = parent_message_type
        if "msg_idx" in fields:
            element["msg_idx"] = parent_msg_idx

    if callable(model_copy := getattr(payload, "model_copy", None)):
        return model_copy(update={"data": normalized_data})
    if callable(copy := getattr(payload, "copy", None)):
        return copy(update={"data": normalized_data})
    return None


def _copy_payload_with_data(payload, data: dict):
    if callable(model_copy := getattr(payload, "model_copy", None)):
        return model_copy(update={"data": data})
    if callable(copy := getattr(payload, "copy", None)):
        return copy(update={"data": data})
    return None


def _log_repair(event_type: str, fields: set[str]) -> None:
    _repair_counts[event_type] += 1
    count = _repair_counts[event_type]
    if count not in {1, 10, 100} and count % 1000:
        return
    field_names = ",".join(sorted(fields))
    logger.warning(
        f"QQ 事件兼容字段已安全补全: "
        f"type={event_type}, fields={field_names}, count={count}"
    )


def patch_qq_reply_message_parsing(adapter_class=QQAdapter) -> None:
    if getattr(adapter_class, "_elysia_reply_compat_patched", False):
        return

    original = adapter_class.payload_to_event

    @staticmethod
    def payload_to_event(payload):
        try:
            return original(payload)
        except TypeError:
            event_type = _event_type(payload)
            data = getattr(payload, "data", None)
            if event_type != "RESUMED" or not isinstance(data, str) or data.strip():
                raise
            normalized = _copy_payload_with_data(payload, {})
            if normalized is None:
                raise
            event = original(normalized)
            _log_repair(event_type, {"data"})
            return event
        except ValidationError as exc:
            event_type = _event_type(payload)
            if event_type not in QQ_MESSAGE_EVENT_TYPES:
                raise
            missing = _missing_reply_fields(exc)
            if not missing:
                raise
            normalized = _copy_payload_with_reply_defaults(payload, missing)
            if normalized is None:
                raise
            event = original(normalized)
            _log_repair(
                event_type,
                {field for values in missing.values() for field in values},
            )
            return event

    adapter_class.payload_to_event = payload_to_event
    adapter_class._elysia_reply_compat_patched = True
