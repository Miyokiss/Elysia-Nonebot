import asyncio
import functools
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
    async def get_all_users(cls,limit: int = 10) -> Optional[List[Dict[str, Any]]]:
        """
        获取所有用户
        :param limit: 获取用户的数量限制，默认为10
        :return: 用户列表或None
        """
        client = cls._get_client()
        if client is None:
            logger.error("MemoBase 客户端未初始化")
            return None

        try:
            # 使用 run_in_executor 避免阻塞事件循环
            loop = asyncio.get_running_loop()
            users = await loop.run_in_executor(None, functools.partial(client.get_all_users, limit=limit))
            logger.debug(f"获取到的用户数量: {len(users)}:{users}")
            return users
        except Exception as e:
            logger.error(f"获取所有用户失败: {e}")
            return None
        
    @classmethod
    async def create_user(cls, uuid: str) -> bool:
        """
        注册用户
        :param uuid: 创建的用户UUID
        :return: 是否创建成功
        """
        client = cls._get_client()
        if client is None:
            logger.error("MemoBase 客户端未初始化")
            return False
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, functools.partial(client.add_user, id=uuid))
            return True
        except Exception as e:
            logger.error(f"创建用户 {uuid} 失败: {e}")
            return False
        
    @classmethod
    async def get_user_memory_info(cls, user_id: str) -> Optional[Dict[str, Any]]:
        """
        获取指定用户的记忆信息
        """
        client = cls._get_client()
        if client is None:
            logger.error("MemoBase 客户端未初始化")
            return None

        try:
            loop = asyncio.get_running_loop()
            user = await loop.run_in_executor(None, client.get_usage, user_id)
            if user is None:
                logger.error(f"用户 {user_id} 不存在")
                return None
            return user
        except Exception as e:
            logger.error(f"获取用户 {user_id} 失败: {e}")
            return None