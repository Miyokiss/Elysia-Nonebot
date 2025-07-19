from typing import Any
from nonebot import logger
from tortoise import fields
from tortoise.fields import JSONField
from datetime import datetime
from tortoise.exceptions import MultipleObjectsReturned
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
    like_value = fields.IntField(default=100, description="好感值、范围0-200")
    is_banned = fields.BooleanField(default=False, description="是否被封禁")
    ban_reason = fields.TextField(default="无", description="封禁原因")
    ban_time = fields.IntField(default=0, description="封禁时间")

    class Meta:
        # 指定表名
        table = "bl_chat_role"
        table_description = "百炼聊天表"

    @classmethod
    async def create_chat_role(cls, user_id: List[str], is_session_id: str, memory_id: str, like_value: int) -> Self:
        """
        创建新的聊天角色记录\n
        :param user_id: 用户ID列表
        :param is_session_id: 会话ID
        :param memory_id: 记忆ID
        :return: 创建的记录对象

        示例:
        await BLChatRole.create_chat_role(user_id=["12345"], is_session_id="session_123", memory_id="memory_123")
        """
        try:
            logger.info(f"Creating chat role for user_id: {user_id}, session_id: {is_session_id}, memory_id: {memory_id}, like_value: {like_value}")
            return await cls.create(user_id=user_id, is_session_id=is_session_id, memory_id=memory_id, like_value=like_value)
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
        except MultipleObjectsReturned as e:
            # 处理多对象返回异常
            logger.warning(f"获取 {user_id}  {e}")
            records = await cls.filter(
                user_id=user_id
            ).order_by("-id")
            if records:
                # 保留最新的一条记录
                keep_record = records[0]
                delete_ids = [r.id for r in records[1:]]
                await cls.filter(id__in=delete_ids).delete()
                logger.warning(f"检测到重复记录，已清理用户 {user_id} 的 {len(delete_ids)} 条重复数据")
                return keep_record
        except DoesNotExist:
            logger.info(f"No chat role found for user_id: {user_id}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error occurred while fetching chat role: {e}")
            raise

    @classmethod
    async def update_chat_role_by_user_id(cls, user_id: List[str], **kwargs) -> bool:
        """
        更新字段
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
    async def update_ban_status(cls, user_id: str, is_banned: bool, reason: str = None) -> bool:
        """
        更新用户封禁状态
        :param user_id: 用户ID列表
        :param is_banned: 是否封禁
        :param reason: 封禁原因（可选）
        :return: 是否更新成功
        """
        try:
            logger.info(f"Updating ban status for user_id: {user_id}, is_banned: {is_banned}")
            update_data = {
                'is_banned': is_banned,
                'ban_reason': reason,
                'ban_time': datetime.now().timestamp()
            }
            await cls.filter(user_id=user_id).update(**update_data)
            return True
        except Exception as e:
            logger.error(f"Failed to update ban status: {e}")
            return False

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


class BLChatRoleLog(Model):
    """
    聊天记录表
    """
    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    user_id = fields.CharField(max_length=128,description="user_id")
    user_content = fields.TextField(description="用户输入", null=True)
    assistant_content = fields.TextField(description="模型输出", null=True)
    save_time = fields.DateField(description="保存时间", null=True)
    class Meta:
        # 指定表名
        table = "bl_chat_role_log"
        table_description = "聊天记录表"

    @classmethod
    async def save_chat_log(cls, user_id: str, user_content: str, assistant_content: str):
        """
        保存聊天上下文
        :param user_id: 用户ID
        :param user_content: 用户输入
        :param assistant_content: 模型输出
        """
        await cls.create(user_id=user_id, 
                         user_content=user_content, 
                         assistant_content=assistant_content,
                         save_time=datetime.now())