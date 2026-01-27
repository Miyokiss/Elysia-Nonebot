import httpx
from datetime import datetime
from typing import List, Dict, Any
from nonebot import logger
from http import HTTPStatus
from src.configs.api_config import (dify_api_key, dify_base_url)
from src.utils.date_info import DateInfo

__name__ = "Dify_API"

class DifyAPI:
    def __init__(self):
        pass

    @staticmethod
    async def Get_Memory_Id() -> None:
        # 记忆功能暂未实现
        return None
    
    @staticmethod
    async def Post_chat_api(
        user_id: str,
        session_id : str = None,
        content : str =  "空内容",
        memory_id : str = None,
        Like_value : int = 100) -> Dict[str, any]:
        """调用Dify API进行聊天"""
        if user_id is None or content is None:
            logger.error("用户ID或内容为空，无法调用Dify API")
            return
        try:
            # 构造调用参数
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
                    "Etime": etime,
                    "Weekday": week,
                    "Holiday": holiday,
                    "Like_value": str(Like_value)
                },
                "query": content,
                "response_mode": "blocking",
                "conversation_id": session_id if session_id else "",
                "user": user_id
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{dify_base_url}/chat-messages",
                    headers=headers,
                    json=payload,
                    timeout=30.0
                )

            # 响应处理
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

            # 正常响应
            return {
                "session_id": resp_data.get("conversation_id"),
                "content": resp_data.get("answer", ""),
                "error": None
            }

        except Exception as error:
            # 链式异常处理
            logger.exception(
                f"调用异常: {error}", 
                exc_info=True
            )
            return {
                "session_id": session_id,
                "content": "",
                "error": str(error)
            }