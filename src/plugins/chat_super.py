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
    else:
        logger.debug("私聊环境")
        user_id,content = message.get_user_id(), message.get_plaintext().split()

    logger.debug(f"{content}")
    user_msg = await DifyChatRole.get_chat_role_by_user_id(user_id)
    if user_msg is None:
        # 发送等待回复
        r_msg = Message([
            MessageSegment.file_image((Path(image_local_qq_image_path) / "AIchat.png")),
            MessageSegment.text("请认真阅读并同意《AI服务使用协议与安全规范》相关内容后"
                                +"\n回答此问题：本爱莉希雅出自那款游戏？"
                                +"\n回复要求使用中文，不得使用其他语言符号或外号"
                                +"\n回答正确即视为已阅读并同意遵守相关协议！")
        ])
        try:
            await Elysia_super.send(r_msg)
            
            # 创建异步消息接收器
            future = asyncio.get_event_loop().create_future()
            
            # 定义临时 matcher 处理用户回复
            from nonebot.matcher import Matcher
            protocol_matcher = Matcher.new(
                rule=Rule(lambda event: event.get_user_id() == user_id),
                handlers=[lambda bot, event: future.set_result(event)],
                priority=0,
                block=True
            )
            
            try:
                # 等待用户回复（超时240秒）
                r_content = await asyncio.wait_for(future, timeout=240)
                # 显式获取消息内容
                answer = r_content.get_plaintext().strip() if hasattr(r_content, 'get_plaintext') else str(r_content).strip()
                if answer.lower() not in {"崩坏三", "崩坏3"}:
                    await Elysia_super.finish("回答错误，请重新开始对话。")
                else:
                    await Elysia_super.send("回答正确，欢迎您！舰长~"
                                     +"\nTips：如果在对话中遇到问题/错误/不想聊的话题/遇到胡言乱语，请尝试使用：/爱莉希雅 新的对话。"
                                     +"\n如果爱莉记住了些奇怪的东西可以使用：/爱莉新希雅 新的记忆")
                    content = "你好呀"
            except asyncio.TimeoutError:
                logger.info(f"check | 回复等待超时 User: {user_id} Content: {content}")
                return
            finally:
                # 清理临时 matcher
                protocol_matcher.destroy()
            
        except Exception as e:
            if isinstance(e, (FinishedException, PausedException)):
                return
            logger.error(f"处理用户协议交互时发生错误: {e}", exc_info=True)
            await Elysia_super.finish("发生错误，请稍后再试。")
    
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

            if cmd == "新的对话":
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
            
            elif cmd == "新的记忆":
                msg = await on_new_memory_id(user_id)
                if msg is True:
                    await Elysia_super.finish("开始新的记忆啦！~")
                else:
                    await Elysia_super.finish(msg)
            
            elif cmd in ["ban", "deban"]:
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

# Memo Base 相关操作指令
Elysia_super_memobase = on_command("爱莉记忆",rule=to_me(),priority=1,block=True)
@Elysia_super_memobase.handle()
async def handle_function(message: MessageEvent):
    user_id, group_openid, content = message.get_user_id(), message.group_openid, message.get_plaintext().split()
    if hasattr(message, 'group_openid'):
        logger.debug("群聊环境")
    else:
        logger.debug("私聊环境")
        group_openid = "C2C"

    # 处理指令逻辑
    if content[0] == "/爱莉记忆":
        values = message.get_plaintext().replace("/爱莉记忆", "").split()
        try:
            if len(values) == 0 or not all(values[1:len(values)]):
                await Elysia_super_memobase.finish("指令格式错误！")

            logger.debug(f"MemoBase Command Values: {values}")
            if values[0] == "查询所有用户":
                logger.debug("查询所有用户指令触发")
                if group_openid != "C2C":
                    logger.debug("群聊环境")
                    # 判断是否为管理员
                    if not await GroupChatRole.get_admin_list(group_openid, user_id):
                        await Elysia_super_memobase.finish("您没有权限使用此功能。")
                    results = await MemoBaseHandler.get_all_users()
                    if results:
                        response = "查询结果：\n" + "\n".join([f"- {res['text']}" for res in results])
                        await Elysia_super_memobase.finish(response)
                else:
                    await Elysia_super_memobase.finish("暂未在当前场景下开放此功能。")
            else:
                await Elysia_super_memobase.finish("请输入正确的指令！")
        except Exception as e:
            if isinstance(e, FinishedException):
                return
            logger.error(f"处理请求时发生错误: {e}")
            await Elysia_super_memobase.finish("处理请求时发生错误，请稍后重试")    