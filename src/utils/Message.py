import asyncio
from nonebot import logger
from nonebot.adapters.qq import GroupAtMessageCreateEvent, C2CMessageCreateEvent, GuildMessageEvent

__name__ = "MessageUtils"

async def delete_msg(bot, message, sent_msg):
    # 等待110秒后撤回消息
    await asyncio.sleep(110)
    try:
          if isinstance(message, GroupAtMessageCreateEvent):
                await bot.delete_group_message(group_openid=message.group_openid, message_id=sent_msg.id)
          elif isinstance(message, C2CMessageCreateEvent):
                await bot.delete_c2c_message(openid=message.author.id, message_id=sent_msg.id)
          elif isinstance(message, GuildMessageEvent):
                await bot.delete_message(channel_id=message.channel_id, message_id=sent_msg.id)
    except Exception as e:
          logger.error(f"撤回消息失败: {e}")