from typing import Any
from nonebot import logger
from tortoise import fields
from tortoise.fields import JSONField
from typing_extensions import Self, Optional, List, Dict
from src.clover_sqlite.data_init.db_connect import Model
from tortoise.exceptions import DoesNotExist, IntegrityError

class BLChatRole(Model):
    """
    BL聊天表
    """
    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    user_id = fields.CharField(max_length=128,description="user_id")
    is_session_id = fields.CharField(max_length=128, description="session_ID")
    memory_id = fields.CharField(max_length=128, description="memory_id")
    chat_logs = fields.JSONField(description="chat_logs", null=True)

    class Meta:
        # 指定表名
        table = "bl_chat_role"
        table_description = "百炼聊天表"

    @classmethod
    async def create_chat_role(cls, user_id: List[str], is_session_id: str, memory_id: str, chat_logs: Optional[Dict] = None) -> Self:
        """
        创建新的聊天角色记录\n
        :param user_id: 用户ID列表
        :param is_session_id: 会话ID
        :param memory_id: 记忆ID
        :param chat_logs: 聊天记录
        :return: 创建的记录对象

        示例:
        await BLChatRole.create_chat_role(user_id=["12345"], is_session_id="session_123", memory_id="memory_123", chat_logs={"message": "Hello"})
        """
        try:
            logger.info(f"Creating chat role for user_id: {user_id}, session_id: {is_session_id}, memory_id: {memory_id}")
            return await cls.create(user_id=user_id, is_session_id=is_session_id, memory_id=memory_id, chat_logs=chat_logs)
        except IntegrityError as e:
            logger.error(f"Failed to create chat role due to integrity error: {e}")
            raise ValueError("Failed to create chat role due to integrity error") from e
        except Exception as e:
            logger.error(f"Unexpected error occurred while creating chat role: {e}")
            raise

    @classmethod
    async def get_chat_role_by_user_id(cls, user_id: List[str]) -> Optional[Self]:
        """
        根据用户ID获取记录\n
        :param user_id: 用户ID
        :return: 查询到的记录对象

        示例:
        chat_role = await BLChatRole.get_chat_role_by_user_id(user_id=["12345"])
        """
        try:
            logger.info(f"Fetching chat role for user_id: {user_id}")
            return await cls.get(user_id=user_id)
        except DoesNotExist:
            logger.info(f"No chat role found for user_id: {user_id}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error occurred while fetching chat role: {e}")
            raise

    @classmethod
    async def update_chat_role_by_user_id(cls, user_id: List[str], **kwargs) -> bool:
        """
        更新字段\n
        :param user_id: 用户ID列表
        :param kwargs: 需要更新的字段
        :return: 是否更新成功

        示例:
        success = await BLChatRole.update_chat_role_by_user_id(user_id=["12345"], is_session_id="new_session_id")
        """
        try:
            logger.info(f"Updating chat role for user_id: {user_id} with data: {kwargs}")
            await cls.filter(user_id=user_id).update(**kwargs)
            return True
        except Exception as e:
            logger.error(f"Failed to update chat role: {e}")
            return False
    @classmethod
    async def save_chat_logs_role_by_user_id(cls, user_id: str | None,content: dict[str, str | Any] | None):
        """
        保存聊天上下文

        :param group_id: 群聊的ID。
        :param content: 要保存的内容。
        """
        history = await cls.filter(user_id=user_id).first()
        if history.chat_logs is None:
            history.chat_logs = [content]
            await history.save()
        else:
            history.chat_logs.append(content)
            await history.save()

    @classmethod
    async def delete_chat_role_by_user_id(cls, user_id: List[str]) -> bool:
        """
        删除用户表\n
        :param user_id: 用户ID列表
        :return: 是否删除成功

        示例:
        success = await BLChatRole.delete_chat_role_by_user_id(user_id=["12345"])
        """
        try:
            logger.info(f"Deleting chat role for user_id: {user_id}")
            await cls.filter(user_id=user_id).delete()
            return True
        except Exception as e:
            logger.error(f"Failed to delete chat role: {e}")
            return False