from pathlib import Path
from nonebot.rule import to_me
from nonebot.plugin import on_command
from nonebot.exception import FinishedException
from src.clover_image.delete_file import delete_file
from src.clover_sqlite.models.chat import GroupChatRole
from src.clover_sqlite.models.chat import MODE_ELYSIA, MODE_OFF
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from src.providers.llm.elysiacmd  import has_elysia_command_regex,elysia_command
from src.providers.llm.AliBL.base import on_bl_new_session_id,on_bl_new_memory_id
from nonebot import logger

Elysia_super = on_command("爱莉希雅",aliases={"妖精爱莉"},rule=to_me(),priority=1,block=True)
@Elysia_super.handle()
async def handle_function(message: MessageEvent):
    if hasattr(message, "group_openid"):
        logger.debug("群聊环境")
        user_id, group_openid, content = message.get_user_id(), message.group_openid, message.get_plaintext().split()
        current_mode = await GroupChatRole.is_on(group_openid)
    else:
        logger.debug("私聊环境")
        user_id,content = message.get_user_id(), message.get_plaintext().split()

    logger.debug(f"\n{content}")
    if content[0] == "/爱莉希雅":
        values = message.get_plaintext().replace("/爱莉希雅", "").split()
        try:
            if len(values) == 0 or not all(values[1:len(values)]):
                if not hasattr(message, 'group_openid'):
                    await Elysia_super.finish("暂未在当前场景下开放开启功能。建议使用\n/爱莉希雅 新的对话 \n创建新的对话\n/爱莉希雅 新的记忆\n创建新的记忆")
                    # 判断是否为管理员
                if not await GroupChatRole.get_admin_list(group_openid, user_id):
                    await Elysia_super.finish("您没有权限使用此功能，你可以通过指令：\n/爱莉希雅 新的对话 \n创建新的对话\n/爱莉希雅 新的记忆\n创建新的记忆")
                else:
                    if current_mode != MODE_ELYSIA:
                        await GroupChatRole.ai_mode(group_openid, MODE_ELYSIA)
                        await Elysia_super.finish("成功开启爱莉希雅对话~")
                    else:
                        await Elysia_super.finish("当前群已是爱莉希雅对话~")
            elif len(values) == 1:
                if values[0] == "新的对话":
                    msg = await on_bl_new_session_id(user_id)
                    if msg["code"] is True:
                        if has_elysia_command_regex(msg["msg"]):
                            r_msg = await elysia_command(msg["msg"])
                            msg = Message([
                                MessageSegment.file_image(Path(r_msg['imgs'])),
                                MessageSegment.text(r_msg['txt'])
                            ])
                            await Elysia_super.send(msg)
                            await delete_file(r_msg['imgs'])
                            await Elysia_super.finish("开始新的对话啦！~")
                        else:
                            await Elysia_super.finish("未定义内容，建议 新的对话")
                    else:
                        await Elysia_super.finish(msg["msg"])
                if values[0] == "新的记忆":
                    msg =await on_bl_new_memory_id(user_id)
                    if msg is True:
                        await Elysia_super.finish("开始新的记忆啦！~")
                    else:
                        await Elysia_super.finish(msg)
                else:
                    await Elysia_super.finish("请输入正确的指令！\n指令格式：\n/爱莉希雅\n/爱莉希雅 <新的对话/新的记忆>")
        except Exception as e:
            if isinstance(e, FinishedException):
                return
            logger.error(f"处理请求时发生错误: {e}")
            await Elysia_super.finish("处理请求时发生错误，请稍后重试")
    elif content[0] == "/妖精爱莉":
        if not hasattr(message, 'group_openid'):
            await Elysia_super.finish("暂未在当前场景下开放此功能。")
            # 判断是否为管理员
        if not await GroupChatRole.get_admin_list(group_openid, user_id):
            await Elysia_super.finish("您没有权限使用此功能。")
        else:
            if current_mode == MODE_ELYSIA:
                await GroupChatRole.ai_mode(group_openid, MODE_OFF)
                await Elysia_super.finish("成功关闭爱莉希雅对话~")
            else:
                await Elysia_super.finish("当前群已开启妖精爱莉聊天~")

            
