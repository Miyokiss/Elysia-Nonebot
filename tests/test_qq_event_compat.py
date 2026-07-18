import unittest

from nonebot.adapters.qq import Adapter as QQAdapter
from nonebot.adapters.qq.models import Dispatch
from pydantic import ValidationError

from src.utils.qq_event_compat import patch_qq_reply_message_parsing


def build_payload(**data_updates):
    data = {
        "id": "message-id",
        "content": "reply text",
        "timestamp": "2026-07-18T10:00:00+08:00",
        "author": {
            "id": "author-id",
            "bot": False,
            "member_openid": "member-openid",
        },
        "group_id": "group-id",
        "group_openid": "group-openid",
        "msg_elements": [{"content": "quoted text"}],
    }
    data.update(data_updates)
    return Dispatch.model_validate(
        {
            "op": 0,
            "s": 1,
            "t": "GROUP_MESSAGE_CREATE",
            "id": "event-id",
            "d": data,
        }
    )


class QQEventCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        patch_qq_reply_message_parsing()

    def test_missing_reply_metadata_is_filled_without_mutating_payload(self):
        payload = build_payload(message_type=7, msg_idx="parent-index")

        event = QQAdapter.payload_to_event(payload)

        self.assertEqual(event.msg_elements[0].message_type, 7)
        self.assertEqual(event.msg_elements[0].msg_idx, "parent-index")
        self.assertNotIn("message_type", payload.data["msg_elements"][0])
        self.assertNotIn("msg_idx", payload.data["msg_elements"][0])

    def test_unrelated_validation_errors_are_not_hidden(self):
        payload = build_payload(author={})

        with self.assertRaises(ValidationError) as raised:
            QQAdapter.payload_to_event(payload)

        locations = {tuple(error["loc"]) for error in raised.exception.errors()}
        self.assertIn(("author", "id"), locations)

    def test_empty_resumed_payload_is_normalized(self):
        payload = Dispatch.model_validate(
            {"op": 0, "s": 2, "t": "RESUMED", "id": "event-id", "d": ""}
        )

        event = QQAdapter.payload_to_event(payload)

        self.assertEqual(event.get_event_name().value, "RESUMED")
        self.assertEqual(payload.data, "")

    def test_nonempty_string_payload_type_error_is_not_hidden(self):
        payload = Dispatch.model_validate(
            {"op": 0, "s": 2, "t": "RESUMED", "id": "event-id", "d": "bad"}
        )

        with self.assertRaises(TypeError):
            QQAdapter.payload_to_event(payload)

    def test_patch_is_idempotent(self):
        patched = QQAdapter.payload_to_event

        patch_qq_reply_message_parsing()

        self.assertIs(QQAdapter.payload_to_event, patched)


if __name__ == "__main__":
    unittest.main()
