import random
from nonebot import logger
from datetime import datetime
from tortoise import Model, fields
from tortoise.exceptions import DoesNotExist, IntegrityError
from typing_extensions import Self, Optional, List, Dict
from src.clover_sqlite.data_init.db_connect import Model
from src.today_superpowers.data import SuperPowers_Data

class Today_superpowers(Model):
    """
    今日超能力表
    """
    id = fields.IntField(pk=True)
    time = fields.DateField(description="日期")
    superpowers = fields.TextField(description="今日超能力")
    but = fields.TextField(description="但是")
    press_count = fields.IntField(default=0, description="按下总次数")
    not_press_count = fields.IntField(default=0, description="不按总次数")

    class Meta:
        table = "today_superpowers"
        table_description = "今日超能力表"
    @classmethod
    async def get_today_superpowers(cls) -> Optional[Self]:
        today = datetime.now().date()
        try:
            instance, created = await cls.get_or_create(
                time=today,
                defaults={
                    'superpowers': random.choice(SuperPowers_Data.super_powers_lists),
                    'but': random.choice(SuperPowers_Data.but_lists)
                }
            )
            return instance
        except IntegrityError as e:  # 细化异常类型
            logger.error(f"数据库完整性约束失败: {str(e)}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"获取/创建今日超能力数据失败: {str(e)}", exc_info=True)
            return None
    @classmethod
    async def add_superpower_count(cls, is_on: bool) -> bool:
        """
        增加今日按下/不按超能力按钮的次数
        :param is_on: True: 按下超能力按钮 False: 不按超能力按钮
        :return: 是否成功
        """
        today = datetime.now().date()
        
        try:
            field = 'press_count' if is_on else 'not_press_count'
            result = await cls.filter(time=today).update(**{field: getattr(cls, field) + 1})
            
            if not result:
                logger.error(f"今日超能力数据不存在，请先 get_today_superpowers (time={today})")
                return False
            return True
        except Exception as e:
            logger.error(f"更新超能力计数失败: {str(e)}")
            return False



class Today_User_superpowers(Model):
    """
    今日超能力用户表
    """
    id = fields.IntField(pk=True)
    user_id = fields.CharField(max_length=128, index=True)
    time = fields.DateField(description="日期")
    is_button = fields.IntField(description="是否按下按钮")

    class Meta:
        table = "today_user_superpowers"
        table_description = "用户今日超能力表"

    @classmethod
    async def get_user_today_superpowers(cls, user_id: str) -> Optional[Self]:
        """
        获取用户今日超能力数据
        :param user_id: 用户ID
        :return: 用户今日超能力数据 或 None
        """
        today = datetime.now().date()
        try:
            return await cls.get_or_none(user_id=user_id, time=today)
        except DoesNotExist:
            logger.debug(f"用户今日超能力数据不存在 (user_id={user_id}, time={today})")
            return None
        except Exception as e:
            logger.error(f"获取用户今日超能力数据时出错 (user_id={user_id}, time={today}): {e}")
        
    @classmethod
    async def save_user_today_superpowers(cls, user_id: str, is_button: bool) -> bool:
        """
        保存用户今日超能力数据
        :param user_id: 用户ID
        :param is_button: 是否是按钮
        :return: 是否保存成功
        """
        today = datetime.now().date()
        try:
            await cls.create(
                user_id=user_id,
                time=today,
                is_button=is_button
            )
            return True
        except IntegrityError as e:  # 细化异常类型
            logger.error(f"数据库完整性约束失败: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"保存用户数据失败: {e} (user_id={user_id}, time={today})", exc_info=True)
            return False
