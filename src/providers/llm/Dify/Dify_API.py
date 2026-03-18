import json
import httpx
from datetime import datetime
from typing import Dict, Any
from nonebot import logger
from http import HTTPStatus
from src.configs.api_config import (dify_api_key, dify_base_url)
from src.utils.date_info import DateInfo

__name__ = "Dify_API"


class DifyAPI:
    def __init__(self):
        pass

    @staticmethod
    async def Post_chat_api(
        user_id: str,
        session_id: str = None,
        content: str = "空内容",
        memory_id: str = None,
        Like_value: int = 100,
        response_mode: str = "streaming"
    ) -> Dict[str, Any]:
        """调用Dify API进行聊天"""
        if user_id is None or content is None or memory_id is None:
            logger.error("用户ID、内容或记忆UUID为空，无法调用Dify API")
            return None
        try:
            etime = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            date_info = DateInfo()
            week = date_info.get_weekday()
            is_holiday, holiday = date_info.check_holiday()

            headers = {
                "Authorization": f"Bearer {dify_api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "inputs": {
                    "Memory_id": memory_id,
                    "Etime": etime,
                    "Weekday": week,
                    "Holiday": holiday,
                    "Like_value": str(Like_value)
                },
                "query": content,
                "response_mode": response_mode,
                "conversation_id": session_id if session_id else "",
                "user": user_id
            }

            async with httpx.AsyncClient() as client:
                if response_mode == "streaming":
                    return await DifyAPI._handle_streaming_response(
                        client=client,
                        headers=headers,
                        payload=payload,
                        session_id=session_id
                    )

                response = await client.post(
                    f"{dify_base_url}/chat-messages",
                    headers=headers,
                    json=payload,
                    timeout=30.0
                )
                return DifyAPI._handle_blocking_response(response, session_id)

        except Exception as error:
            logger.exception(
                f"调用异常: {error}",
                exc_info=True
            )
            return {
                "session_id": session_id,
                "content": "",
                "error": str(error)
            }

    @staticmethod
    def _handle_blocking_response(response: httpx.Response, session_id: str) -> Dict[str, Any]:
        """处理阻塞式响应"""
        if response.status_code != HTTPStatus.OK:
            logger.error(
                f"code={response.status_code}, "
                f"message={response.text}"
            )
            return {
                "session_id": session_id,
                "content": "",
                "error": f"api_error_{response.status_code}"
            }

        resp_data = response.json()
        return {
            "session_id": resp_data.get("conversation_id"),
            "content": resp_data.get("answer", ""),
            "error": None
        }

    @staticmethod
    async def _handle_streaming_response(
        client: httpx.AsyncClient,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        session_id: str
    ) -> Dict[str, Any]:
        """处理流式响应"""
        answer_parts = []
        conversation_id = session_id

        async with client.stream(
            "POST",
            f"{dify_base_url}/chat-messages",
            headers=headers,
            json=payload,
            timeout=30.0
        ) as response:
            if response.status_code != HTTPStatus.OK:
                error_bytes = await response.aread()
                error_message = error_bytes.decode("utf-8", errors="ignore")
                logger.error(
                    f"code={response.status_code}, "
                    f"message={error_message}"
                )
                return {
                    "session_id": session_id,
                    "content": "",
                    "error": f"api_error_{response.status_code}"
                }

            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue

                data = line.removeprefix("data:").strip()
                if not data:
                    continue

                try:
                    event_data = json.loads(data)
                except json.JSONDecodeError:
                    logger.warning(f"无法解析Dify流式响应片段: {data}")
                    continue

                event = event_data.get("event")
                if event in {"message", "agent_message"}:
                    answer_parts.append(event_data.get("answer", ""))
                    conversation_id = event_data.get("conversation_id", conversation_id)
                elif event == "message_end":
                    conversation_id = event_data.get("conversation_id", conversation_id)
                elif event == "error":
                    error_message = event_data.get("message", "unknown_error")
                    logger.error(f"Dify流式响应报错: {error_message}")
                    return {
                        "session_id": conversation_id,
                        "content": "".join(answer_parts),
                        "error": error_message
                    }

        return {
            "session_id": conversation_id,
            "content": "".join(answer_parts),
            "error": None
        }
