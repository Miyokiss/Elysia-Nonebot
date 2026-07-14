import asyncio
import uuid
from pathlib import Path
from nonebot import logger
from nonebot.rule import to_me
from src.clover_image.rua import rua
from nonebot.plugin import on_command
from src.utils.Message import delete_msg
from nonebot.adapters.qq import  MessageSegment
from src.clover_image.delete_file import delete_file
from src.clover_image.qq_image import  download_qq_image
from nonebot.adapters.qq.message import MessageMarkdown
from src.clover_sqlite.models.user import UserList, Wife
from nonebot.adapters.qq import Message, MessageEvent, Bot
from nonebot.adapters.qq.exception import ActionFailed
from src.clover_providers.cloud_file_api.rustfs import rustfs_api
from src.configs.Keyboard_config import Keyboard_fortune, Keyboard_mate

today_group_wife = on_command("群老婆", rule=to_me(), priority=10)
@today_group_wife.handle()
async def handle_group_wife(message: MessageEvent, bot: Bot):
    if not hasattr(message, 'group_openid'):
        await today_group_wife.finish("暂未在当前场景下开放此功能。")

    member_openid = message.get_user_id()
    group_id = message.group_openid
    # 检查用户是否已有伴侣
    has_wife = await Wife.has_wife(user_id=member_openid, group_id=group_id)

    values = message.get_plaintext().removeprefix("/群老婆").strip().split()
    if len(values) == 0:
        if has_wife is None:
            wife_id = await UserList.get_user_id(member_openid, group_id)
            if not wife_id:
                await today_group_wife.finish("本群群友使用BOT的用户不足，无法分配老婆！")
            await Wife.save_wife(user_id=member_openid, group_id=group_id, wife_id=wife_id)
            await post_wife_function(member_openid=member_openid, wife_id=wife_id, bot=bot, message=message)
            return
        await post_wife_function(member_openid=member_openid, wife_id=has_wife, bot=bot, message=message)
        return
    elif len(values) == 1:
        if has_wife is None:
            await today_group_wife.finish("你还没有获取群老婆哦\n请先获取群老婆：/群老婆")
        
        if values[0] == "换":
            logger.debug(f"用户 {member_openid} 换")
            user_info = await Wife.get_user_today_info(user_id=member_openid, group_id=group_id)
            if user_info and user_info.change_idx < 3:
                wife_id = await UserList.get_user_id(member_openid, group_id)
                if not wife_id:
                    await today_group_wife.finish("没有其他群友可以换啦！")
                await Wife.update_wife(
                    member_openid,
                    group_id,
                    user_info.change_idx + 1,
                    wife_id)
                await post_wife_function(member_openid=member_openid, wife_id=wife_id, bot=bot, message=message)
                return
            else:
                await today_group_wife.finish("今日已经换过很多次老婆啦！不可以太花心哦！")
        elif values[0] == "摸":
            logger.debug(f"用户 {member_openid} 摸")
            local_image_path = await download_qq_image(has_wife)
            if local_image_path:
                local_gif = None
                try:
                    local_gif = rua(local_image_path).add_gif()
                    r_msg = Message([
                        MessageSegment.file_image(Path(local_gif))
                    ])
                    sent_msg = await today_group_wife.send(r_msg)
                    asyncio.create_task(delete_msg(bot, message, sent_msg))
                except Exception as exc:
                    logger.opt(exception=exc).warning("摸头动图生成失败")
                    await today_group_wife.send("摸头动图生成失败，请稍后重试。")
                finally:
                    await delete_file(local_image_path)
                    if local_gif:
                        await delete_file(local_gif)
            else:
                await today_group_wife.send("获取老婆头像失败...")
            await today_group_wife.finish()
        else:
            await today_group_wife.finish("请输入正确的指令")
    else:
        await today_group_wife.finish("请输入正确的指令")

async def post_wife_function(member_openid, wife_id, bot, message) -> None:
    size = 640
    img_name = f"{member_openid}_{wife_id}.jpg"

    if wife_id is None:
        await today_group_wife.finish("潜在老婆太少了，快请群友多多使用吧")
    
    local_image_path = await download_qq_image(wife_id, size=size)
    if not local_image_path:
        await today_group_wife.finish("获取图片失败")

    try:
        sent_msg = await send_avatar_card(
            matcher=today_group_wife,
            local_image_path=local_image_path,
            object_key=img_name,
            content=f"<@{member_openid}> 你抽到了 <@{wife_id}>",
            keyboard=Keyboard_mate,
            size=size,
        )
        asyncio.create_task(delete_msg(bot, message, sent_msg))
        await today_group_wife.finish()
    finally:
        await delete_file(local_image_path)


async def send_avatar_card(matcher, local_image_path, object_key, content, keyboard, size):
    uploaded = await rustfs_api.upload_file(
        local_path=str(local_image_path), object_key=object_key
    )
    if uploaded:
        image_url = await rustfs_api.get_download_url(object_key=object_key)
        if image_url:
            params = [
                {"key": "width", "values": [str(size)]},
                {"key": "height", "values": [str(size)]},
                {"key": "url", "values": [image_url]},
                {"key": "content", "values": [content]},
            ]
            markdown_image = MessageMarkdown(
                custom_template_id="102735560_1771313464", params=params
            )
            try:
                return await matcher.send(Message([
                    MessageSegment.markdown(markdown_image),
                    MessageSegment.keyboard(keyboard),
                ]))
            except ActionFailed as exc:
                logger.warning(
                    f"Markdown 卡片发送失败，降级为普通图片: "
                    f"code={exc.code}, message={exc.message}"
                )

    return await matcher.send(MessageSegment.file_image(Path(local_image_path)))

today_wife = on_command("今日老婆", rule=to_me(), priority=10)
@today_wife.handle()
async def handle_today_wife(bot: Bot, message: MessageEvent):
      member_openid = message.get_user_id()
      index_uuid = uuid.uuid4()
      img_name = f"{member_openid}_{index_uuid}.jpg"
      size = 640

      qq_user_img_path = await download_qq_image(member_openid, size=size)
      if not qq_user_img_path:
          await today_wife.finish("获取头像失败，请稍后重试。")
      try:
          sent_msg = await send_avatar_card(
              matcher=today_wife,
              local_image_path=qq_user_img_path,
              object_key=img_name,
              content=f"<@{member_openid}>",
              keyboard=Keyboard_fortune,
              size=size,
          )
          asyncio.create_task(delete_msg(bot, message, sent_msg))
          await today_wife.finish()
      finally:
          await delete_file(qq_user_img_path)
