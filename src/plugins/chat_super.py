import asyncio
from pathlib import Path
from nonebot.rule import Rule, to_me
from nonebot.plugin import on_command
from src.providers.llm.Dify import DifyChatRole
from src.clover_image.delete_file import delete_file
from src.clover_sqlite.models.chat import GroupChatRole
from src.configs.path_config import image_local_qq_image_path
from src.clover_sqlite.models.chat import MODE_ELYSIA, MODE_OFF
from src.providers.memory.memobase.base import MemoBaseHandler
from nonebot.exception import FinishedException, PausedException
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from src.providers.llm.elysiacmd  import has_elysia_command_regex,elysia_command
from src.providers.llm.Dify.base import on_new_session_id,on_new_memory_id
from nonebot import logger

Elysia_super = on_command("爱莉希雅",aliases={"妖精爱莉"},rule=to_me(),priority=1,block=True)
@Elysia_super.handle()
async def handle_function(message: MessageEvent):
    if hasattr(message, "group_openid"):
        logger.debug("群聊环境")
        user_id, group_openid, content = message.get_user_id(), message.group_openid, message.get_plaintext().split()
        current_mode = await GroupChatRole.is_on(group_openid)
        if current_mode == MODE_ELYSIA:
            pass
        elif current_mode == MODE_OFF:
             await Elysia_super.finish("未开放此功能。")
        elif not await GroupChatRole.get_admin_list(group_openid, user_id):
            await Elysia_super.finish("未开放此功能。")
        else:
            pass
    else:
        logger.debug("私聊环境")
        user_id,content = message.get_user_id(), message.get_plaintext().split()
        await Elysia_super.finish("未开放此功能。")

    logger.debug(f"{content}")
    user_msg = await DifyChatRole.get_chat_role_by_user_id(user_id)
    if user_msg is None:
        await Elysia_super.finish("你还没有聊过诶，请先发送任意消息与爱莉希雅对话一次哦~")
    
    if content[0] == "/爱莉希雅":
        raw_text = message.get_plaintext().strip()
        if raw_text.startswith("/爱莉希雅"):
            args_text = raw_text[len("/爱莉希雅"):].strip()
        else:
            args_text = raw_text.replace("/爱莉希雅", "", 1).strip()
        values = args_text.split()

        try:
            # Case 1: 无参数 (开启/关闭/状态)
            if not values:
                if not hasattr(message, 'group_openid'):
                    await Elysia_super.finish("暂未在当前场景下开放开启功能。建议使用\n/爱莉希雅 新的对话 \n创建新的对话\n/爱莉希雅 新的记忆\n创建新的记忆")
                
                if not await GroupChatRole.get_admin_list(group_openid, user_id):
                    await Elysia_super.finish("您没有权限使用此功能，你可以通过指令：\n/爱莉希雅 新的对话 \n创建新的对话\n/爱莉希雅 新的记忆\n创建新的记忆")
                
                if current_mode != MODE_ELYSIA:
                    await GroupChatRole.ai_mode(group_openid, MODE_ELYSIA)
                    await Elysia_super.finish("成功开启爱莉希雅对话~")
                else:
                    await Elysia_super.finish("当前群已是爱莉希雅对话~")

            # Case 2: 子命令
            cmd = values[0]

            if cmd == "新的对话" and user_msg.is_banned is not True:
                msg = await on_new_session_id(user_id)
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
            
            if cmd == "新的记忆" and user_msg.is_banned is not True:
                msg = await on_new_memory_id(user_id)
                if msg is True:
                    await Elysia_super.finish("开始新的记忆啦！~")
                else:
                    await Elysia_super.finish(msg)
            
            if cmd in ["ban", "deban"]:
                # 管理员且是群聊环境
                if not hasattr(message, 'group_openid'):
                    await Elysia_super.finish("此功能仅限群聊使用")
                
                if not await GroupChatRole.get_admin_list(group_openid, user_id):
                    await Elysia_super.finish("您没有权限使用该类功能。")

                if len(values) < 2:
                    await Elysia_super.finish("请输入UserID")

                target_uid = values[1]
                if await DifyChatRole.get_chat_role_by_user_id(target_uid) is None:
                    await Elysia_super.finish("用户不存在")

                try:
                    if cmd == "ban":
                        if len(values) < 3:
                            await Elysia_super.finish("请输入封禁原因")
                        # 支持带空格的原因
                        reason = " ".join(values[2:])
                        reason += f"--管理员操作 by {user_id}"
                        await DifyChatRole.filter(user_id=target_uid).update(is_banned=True, ban_reason=reason)
                        await Elysia_super.finish("封禁成功")
                    elif cmd == "deban":
                        await DifyChatRole.filter(user_id=target_uid).update(is_banned=False)
                        await Elysia_super.finish("解封成功")
                except Exception as e:
                    if isinstance(e, FinishedException):
                        return
                    logger.error(f"Elysia_super_{cmd} Error: {e}", exc_info=True)
                    await Elysia_super.finish("操作失败")
            
            elif user_msg.is_banned is True:
                await Elysia_super.finish("您已被封禁，无法使用此功能。")
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

# Memo Base 相关操作指令 测试
Elysia_super_memobase = on_command("爱莉记忆",rule=to_me(),priority=1,block=True)
@Elysia_super_memobase.handle()
async def handle_function(message: MessageEvent):
    user_id, group_openid, content = message.get_user_id(), message.group_openid, message.get_plaintext().split()
    if hasattr(message, 'group_openid'):
        logger.debug("群聊环境")
    else:
        logger.debug("私聊环境")
        group_openid = "C2C"
        await Elysia_super_memobase.finish("暂未在当前场景下开放此功能。")
    # 判断是否为管理员
    if not await GroupChatRole.get_admin_list(group_openid, user_id):
        await Elysia_super_memobase.finish("您没有权限使用此功能。")

    # 处理指令逻辑
    if content[0] == "/爱莉记忆":
        values = message.get_plaintext().replace("/爱莉记忆", "").split()
        try:
            if len(values) == 0 or not all(values[1:len(values)]):
                await Elysia_super_memobase.finish("指令格式错误！")

            logger.debug(f"MemoBase Command Values: {values}")
            if values[0] == "查询所有用户":
                logger.debug("查询所有用户指令触发")
                if len(values) >= 2 and values[1].isdigit():
                    limit = int(values[1])
                else:
                    limit = 10
                results = await MemoBaseHandler.get_all_users(limit=limit)
                if results:
                    count = len(results)
                    if count <= 1000:
                        response = f"当前获取到 {count} 位最近用户"
                        values_indx = 0
                        for user in results:
                            values_indx += 1
                            response += f"{values_indx}、用户ID: {user['id']}\n创建时间: {user['created_at']}\n更新时间: {user['updated_at']}\n资料数: {user['profile_count']}\n事件数: {user['event_count']}\n"
                        await Elysia_super_memobase.finish(response)
                    else:
                        await Elysia_super_memobase.finish(f"用户数量过多，当前获取到 {count} 位用户，请使用参数限制数量。")
                else:
                    await Elysia_super_memobase.finish(f"获取用户列表失败:{results}")
            elif values[0] == "查询用户":
                logger.debug("查询用户记忆指令触发")
                if len(values) < 2:
                    await Elysia_super_memobase.finish("请提供用户ID，指令格式：/爱莉记忆 查询用户 <用户ID>")
                target_user_id = values[1]
                user_info = await MemoBaseHandler.get_user_memory_info(target_user_id)
                if user_info:
                    # response = f"用户ID: {user_info['id']}\n创建时间: {user_info['created_at']}\n更新时间: {user_info['updated_at']}\n资料数: {user_info['profile_count']}\n事件数: {user_info['event_count']}\n"
                    await Elysia_super_memobase.finish(user_info)
                else:
                    await Elysia_super_memobase.finish(f"获取用户 {target_user_id} 记忆信息失败或用户不存在。")
            else:
                await Elysia_super_memobase.finish("请输入正确的指令！")
        except Exception as e:
            if isinstance(e, FinishedException):
                return
            logger.error(f"处理请求时发生错误: {e}")
            await Elysia_super_memobase.finish("处理请求时发生错误，请稍后重试")    