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
from src.clover_providers.cloud_file_api.openlist import openlist_api
from src.configs.Keyboard_config import Keyboard_fortune, Keyboard_mate

today_group_wife = on_command("群老婆", rule=to_me(), priority=10)
@today_group_wife.handle()
async def handle_function(message: MessageEvent):
      if not hasattr(message, 'group_openid'):
        await today_group_wife.finish("暂未在当前场景下开放此功能。")

      member_openid = message.get_user_id()
      group_id = message.group_id
      # 检查用户是否已有伴侣
      has_wife = await Wife.has_wife(user_id = member_openid, group_id = group_id)

      values = message.get_plaintext().removeprefix("/群老婆").strip().split()
      if len(values) == 0:
            if has_wife is None:
                  wife_id = await UserList.get_user_id(member_openid, group_id)
                  await Wife.save_wife(user_id=member_openid, group_id=group_id, wife_id=wife_id)
                  await post_wife_function(wife_id)
                  return
            await post_wife_function(has_wife)
            return
      elif len(values) == 1:
            if has_wife is None:
                  await today_group_wife.finish("你还没有获取群老婆哦\n请先获取群老婆：/群老婆")
            if values[0] == "换":
                  logger.debug(f"用户 {member_openid} 换")
                  user_info = await Wife.get_user_today_info(user_id=member_openid, group_id=group_id)
                  if user_info.change_idx < 3:
                        wife_id = await UserList.get_user_id(member_openid, group_id)
                        await Wife.update_wife(
                              member_openid, 
                              group_id, 
                              user_info.change_idx + 1, 
                              wife_id)
                        await post_wife_function(wife_id)
                        return
                  else:
                        await today_group_wife.finish(f"今日已经换过很多次老婆啦！不可以太花心哦！")
            elif values[0] == "摸":
                  logger.debug(f"用户 {member_openid} 摸")
                  local_image_path = await download_qq_image(has_wife)
                  local_gif = rua(local_image_path).add_gif()
                  r_msg = Message([
                        MessageSegment.file_image(Path(local_gif))
                        ])
                  await today_group_wife.send(r_msg)
                  await delete_file(local_image_path)
                  await delete_file(local_gif)
                  await today_group_wife.finish()
            else:
                 await today_group_wife.finish("请输入正确的指令")
      else:
           await today_group_wife.finish("请输入正确的指令")

async def post_wife_function(user_id) -> None:
      if user_id is None:
           await today_group_wife.finish("潜在老婆太少了，快请群友多多使用吧")
      local_image_path = await download_qq_image(user_id)
      msg = Message([
            MessageSegment.text(f"您的今日群老婆"),
            MessageSegment.file_image(Path(local_image_path)),
        ])
      await today_group_wife.send(msg)
      await delete_file(local_image_path)
      await today_group_wife.finish(MessageSegment.keyboard(Keyboard_mate))

today_wife = on_command("今日老婆", rule=to_me(), priority=10)
@today_wife.handle()
async def handle_function(bot: Bot, message: MessageEvent):
      member_openid = message.get_user_id()
      index_uuid = uuid.uuid4()
      img_name = f"{member_openid}_{index_uuid}.jpg"
      size = 640

      qq_user_img_path = await download_qq_image(member_openid, size=size)
      await openlist_api.upload_file(qq_user_img_path, overwrite=True , file_name=img_name)
      await delete_file(qq_user_img_path)
      openlist_file_url = await openlist_api.get_download_url(img_name)
      params = [
            {
                  "key": "width",
                  "values": [f"{size}"]
            },
            {
                  "key": "height",
                  "values": [f"{size}"]
            },
            {
                  "key": "url",
                  "values": [f"{openlist_file_url}"]
            },
            {
                  "key": "content",
                  "values": [f"<@{member_openid}>"]
            }
      ]
      markdown_image = MessageMarkdown(custom_template_id="102735560_1771313464", params=params)

      rmsg = Message([
            MessageSegment.markdown(markdown_image),
            MessageSegment.keyboard(Keyboard_fortune)
        ])
      sent_msg = await today_wife.send(rmsg)
      asyncio.create_task(openlist_api.delayed_delete_file(img_name))
      asyncio.create_task(delete_msg(bot, message, sent_msg))
      await today_wife.finish()