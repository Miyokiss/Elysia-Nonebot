from nonebot import logger
from datetime import datetime
from tortoise import Model, fields
from tortoise.exceptions import DoesNotExist
from typing_extensions import Self, Optional, List, Dict
from src.clover_sqlite.data_init.db_connect import Model

class BH3_User_Valkyries(Model):
    """
    BH3_User_Valkyries
    """
    id = fields.IntField(pk=True)
    user_id = fields.CharField(max_length=128, index=True)  # 用户ID
    valkyrie_id = fields.IntField(index=True)  # 女武神ID
    count = fields.IntField(default=1)  # 解锁次数
    first_obtained = fields.IntField()  # 首次获得时间
    promotion_level = fields.IntField(default=0)  # 晋升等级
    favorability = fields.IntField(default=0)  # 好感值

    class Meta:
        # 指定表名
        table = "bh3_user_valkyries"
        table_description = "崩坏3用户女武神表"
    @classmethod
    # 获取用户所有女武神数据
    async def get_user_all_valkyries(cls, user_id: str) -> List[Self]:
        """
        获取用户所有女武神数据
        :param user_id: 用户ID
        :return: 用户女武神数据列表/None
        """
        try:
            return await cls.filter(user_id=user_id).all()
        except Exception as e:
            logger.error(f"获取用户 {user_id} 的所有女武神数据失败: {e}")
            return None
    @classmethod
    # 获取用户指定女武神数据
    async def get_user_valkyrie_data(cls, user_id: str, valkyrie_id: int) -> Optional[Self]:
        """
        获取用户指定女武神数据
        :param user_id: 用户ID
        :param valkyrie_id: 女武神ID
        :return: 用户女武神数据对象或None
        """
        try:
            return await cls.get(user_id=user_id, valkyrie_id=valkyrie_id)
        except DoesNotExist:
            logger.info(f"用户 {user_id} 的女武神 {valkyrie_id} 数据不存在，返回 None")
            return None
        except Exception as e:
            logger.error(f"获取用户女武神数据失败: {e}")
            return None

    @classmethod
    # 根据用户ID和女武神ID创建女武神数据
    async def create_user_valkyrie_data(cls, user_id: str, valkyrie_id: int, time: int) -> Self:
        """
        根据用户ID和女武神ID创建用户女武神数据
        :param user_id: 用户ID
        :param valkyrie_id: 女武神ID
        :param time: 首次获得时间戳
        :return: 创建的用户女武神数据对象
        """
        try:
            await cls.create(
                user_id=user_id,
                valkyrie_id=valkyrie_id,
                first_obtained=time
            )
            logger.info(f"成功创建用户 {user_id} 的女武神 {valkyrie_id} 数据")
            return True
        except Exception as e:
            logger.error(f"创建用户女武神数据失败: {e}")
            return None
        
    # 根据用户ID和女武神ID更新女武神数据
    async def update_user_valkyrie_data(self, user_id: str, valkyrie_id: int, **kwargs) -> bool:
        """
        根据用户ID和女武神ID更新用户女武神数据
        :param user_id: 用户ID
        :param valkyrie_id: 女武神ID
        :param kwargs: 要更新的字段和值
        :return: 是否成功
        """
        try:
            user_valkyrie = await self.get_user_valkyrie_data(user_id, valkyrie_id)
            if user_valkyrie:
                await user_valkyrie.update_from_dict(kwargs)
                await user_valkyrie.save()
                logger.info(f"成功更新用户 {user_id} 的女武神 {valkyrie_id} 数据")
                return True
            else:
                logger.warning(f"用户 {user_id} 的女武神 {valkyrie_id} 数据不存在，无法更新")
                return False
        except Exception as e:
            logger.error(f"更新用户女武神数据失败: {e}")
            return False



class BH3_User_Assistant(Model):
    """
    BH3_User_Assistant
    """
    id = fields.IntField(pk=True)
    user_id = fields.CharField(max_length=128, unique=True, index=True)  # 用户ID
    assistant_id = fields.IntField(default=0)  # 当前助理ID
    last_set_time = fields.IntField(default=0)  # 最后设置时间
    last_get_time = fields.IntField(default=0)  # 最后获取时间
    get_valkyrie_log = fields.JSONField(default=[])  # 获取女武神日志
    
    class Meta:
        table = "bh3_user_assistant"
        table_description = "崩坏3用户助理表"

    @classmethod
    # 获取用户数据
    async def get_user_data(cls, user_id: str) -> Optional[Self]:
        """
        获取用户数据
        :param user_id: 用户ID
        :return: 用户数据对象或None
        """
        try:
            return await cls.get(user_id=user_id)
        except DoesNotExist:
            logger.warning(f"用户 {user_id} 的数据不存在，返回 None")
            return None
        except Exception as e:
            logger.error(f"获取用户数据失败: {e}")
            return None
    
    @classmethod
    # 根据用户ID创建或更新指定字段
    async def create_or_update_field(cls, user_id: str, **kwargs) -> bool:
        """
        创建或更新指定字段
        :param user_id: 用户ID
        :param kwargs: 字段名和值
        :return: 是否成功
        """
        try:
            user_record = await cls.get_user_data(user_id)
            if user_record:
                await user_record.update_from_dict(kwargs)
                await user_record.save()
                return True
            else:
                await cls.create(user_id=user_id, **kwargs)
                return True
        except Exception as e:
            logger.error(f"创建或更新用户字段失败: {e}")
            return False
    @classmethod
    # 根据用户ID记录女武神日志
    async def record_get_valkyrie_log(cls, user_id: str, valkyrie_id: int, time: int) -> bool:
        """
        记录获取女武神日志
        :param user_id: 用户ID
        :param valkyrie_id: 女武神ID
        :return: 是否成功
        """
        try:
            user_record = await cls.get_user_data(user_id)
            if user_record:
                log_entry = {
                    "valkyrie_id": valkyrie_id,
                    "timestamp": time
                }
                user_record.get_valkyrie_log.append(log_entry)
                await user_record.save()
                return True
            else:
                logger.info(f"用户 {user_id} 的数据不存在，无法记录日志")
                return False
        except Exception as e:
            logger.error(f"记录获取女武神日志失败: {e}")
            return False

