import asyncio
import memobase
from typing import List, Dict, Any, Optional
from nonebot import logger
from src.configs.api_config import Memobase_ACCESS_TOKEN, Memobase_API_Url

__name__ = "MemoBase"

class MemoBaseHandler:
    """
    MemoBase功能封装
    """
    _client: Optional[memobase.MemoBaseClient] = None

    @classmethod
    def _get_client(cls) -> Optional[memobase.MemoBaseClient]:
        """
        获取单例客户端实例
        """
        if cls._client is None:
            try:
                cls._client = memobase.MemoBaseClient(
                    api_key=Memobase_ACCESS_TOKEN, 
                    project_url=Memobase_API_Url
                )
                logger.debug("MemoBase 初始化成功")
            except Exception as e:
                logger.error(f"MemoBase 初始化失败: {e}")
                cls._client = None
        return cls._client

    @classmethod
    async def get_all_users(cls) -> Optional[List[Dict[str, Any]]]:
        """
        获取所有用户
        """
        client = cls._get_client()
        if client is None:
            logger.error("MemoBase 客户端未初始化")
            return None

        try:
            # 使用 run_in_executor 避免阻塞事件循环
            loop = asyncio.get_running_loop()
            users = await loop.run_in_executor(None, client.get_all_users)
            logger.debug(f"获取到的用户数量: {len(users)}:{users}")
            return users
        except Exception as e:
            logger.error(f"获取所有用户失败: {e}")
            return None