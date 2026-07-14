import asyncio
from nonebot import logger
from nonebot.adapters.qq import (
    C2CMessageCreateEvent,
    DirectMessageCreateEvent,
    GroupMessageCreateEvent,
    GuildMessageEvent,
)
from nonebot.adapters.qq.exception import ActionFailed

__name__ = "MessageUtils"

async def delete_msg(bot, message, sent_msg, delay: int = 90):
    """
    尝试撤回机器人消息。撤回属于尽力而为，平台拒绝不应影响主流程。
    """
    message_id = getattr(sent_msg, "id", None)
    if not message_id:
        logger.debug("跳过撤回：发送结果中没有消息 ID")
        return

    if delay > 0:
        await asyncio.sleep(delay)

    try:
        if isinstance(message, GroupMessageCreateEvent):
            await bot.delete_group_message(
                group_openid=message.group_openid, message_id=message_id
            )
        elif isinstance(message, C2CMessageCreateEvent):
            await bot.delete_c2c_message(
                openid=message.author.id, message_id=message_id
            )
        elif isinstance(message, DirectMessageCreateEvent):
            await bot.delete_dms_message(
                guild_id=message.guild_id, message_id=message_id
            )
        elif isinstance(message, GuildMessageEvent):
            await bot.delete_message(
                channel_id=message.channel_id, message_id=message_id
            )
    except ActionFailed as exc:
        logger.debug(f"撤回消息被平台拒绝: code={exc.code}, message={exc.message}")
    except Exception as e:
        logger.warning(f"撤回消息失败: {e}")
