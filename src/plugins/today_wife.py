from pathlib import Path
from nonebot.adapters.qq import Message, MessageEvent
from nonebot.adapters.qq import  MessageSegment
from nonebot.plugin import on_command
from nonebot.rule import to_me
from src.configs.Keyboard_config import Keyboard_fortune
from src.clover_image.qq_image import  download_qq_image
from src.clover_image.delete_file import delete_file
from src.clover_sqlite.models.user import UserList

today_group_wife = on_command("群老婆", rule=to_me(), priority=10)
@today_group_wife.handle()
async def handle_function(message: MessageEvent):
      if not hasattr(message, 'group_openid'):
        await today_group_wife.finish("暂未在当前场景下开放此功能。")

      member_openid = message.get_user_id()

      user_id = await UserList.get_user_id(member_openid,message.group_id)
      if  user_id is None:
            await today_group_wife.finish("潜在老婆太少了，快请群友多多使用吧")
      local_image_path = await download_qq_image(user_id)
      msg = Message([
            MessageSegment.text(f"您的今日群老婆 <@{user_id}>"),
            MessageSegment.file_image(Path(local_image_path)),
        ])
      await delete_file(local_image_path)
      await today_group_wife.send(msg)
      await today_group_wife.finish(MessageSegment.keyboard(Keyboard_fortune))

today_wife = on_command("今日老婆", rule=to_me(), priority=10)
@today_wife.handle()
async def handle_function(message: MessageEvent):
      member_openid = message.get_user_id()

      local_image_path = await download_qq_image(member_openid)
      msg = Message([
            MessageSegment.file_image(Path(local_image_path)),
        ])

      await delete_file(local_image_path)
      await today_wife.send(msg)
      await today_wife.finish(MessageSegment.keyboard(Keyboard_fortune))


