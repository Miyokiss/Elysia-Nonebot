import re
import os
import uuid
import random
import asyncio
import subprocess
from pathlib import Path
from nonebot import logger
from graiax import silkcoder
from datetime import datetime
from nonebot import on_message
from nonebot.rule import Rule, to_me
from src.clover_openai import ai_chat
from src.utils.tts import MarkdownCleaner
from src.clover_html.help import help_info_img
from src.clover_sqlite.models.user import UserList
from src.providers.llm.AliBL.base import BLChatRole
from src.clover_image.delete_file import delete_file
from src.providers.llm.AliBL.base import on_bl_chat
from src.clover_sqlite.models.chat import GroupChatRole
from src.providers.tts.gpt_sovits_v2 import TTSProvider
from nonebot.plugin import on_command, on_keyword, on_fullmatch
from nonebot.exception import FinishedException, PausedException
from nonebot.adapters.qq import MessageSegment, MessageEvent, Message
from src.providers.llm.elysiacmd import has_elysia_command_regex, elysia_command
from src.configs.path_config import temp_path, image_local_qq_image_path, AUDIO_PATH
from src.providers.waf.llm_waf import LLMWAF

waf = LLMWAF()

menu = ["/今日运势","/今日塔罗","/今日助理","/我的助理"
        "/图","/随机图",
        "/搜番",
        "/日报",
        "/点歌",
        "/摸摸头",
        "/群老婆","/今日老婆",
        "/开启ai","/关闭ai","/角色列表","/添加人设", "/更新人设", "/删除人设", "/切换人设", "/管理员注册",
        "/天气",
        "/B站搜索","/BV搜索",
        "/待办","/待办查询", "/新建待办", "/删除待办",
        "/喜报", "/悲报",
        "/luxun","/鲁迅说",
        "/轻小说",
        "/本季新番","/下季新番","/新番观察",
        "/绝对色感",
        "/jm",
        "/爱莉希雅","/妖精爱莉",
        "/奶龙","我喜欢你", "❤","#joker","#小丑","#寂寞的人唱伤心的歌","#得吃",
        "/重启","/repo", "/info", "/help", "/test"]

send_menu = [
    {
        "command_type": "日常功能",
        "command_list": [
            {
                "command": "/今日运势",
                "description": "Tips:查询今日运势",
            },
            {
                "command": "/日报",
                "description": "Tips:综合讯息大全！",
            },
            {
                "command": "/摸摸头",
                "description": "Tips:摸摸爱莉的！！！",
            },
            {
                "command": "/点歌 歌名",
                "description": "Tips:搜索获取你指定歌名的音乐！",
            },
            {
                "command": "/天气 地名",
                "description": "Tips:查询指定地点的天气信息！",
            },
            {
                "command": "/轻小说",
                "description": "Tips:轻小说咨询！~"
            },
            {
                "command": "/搜番 图片",
                "description": "Tips:识图搜索番剧！~"
            }
        ]
    },
    {
        "command_type": "B站相关",
        "command_list": [
            {
                "command": "/BV搜索 BV号",
                "description": "Tips:获取BV号对应的视频/信息！",
            },
            {
                "command": "/B站搜索 关键词",
                "description": "Tips:搜索B站关键词的视频信息！",
            }
        ]
    },
    {
        "command_type": "番剧相关",
        "command_list": [
            {
                "command": "/本季新番",
                "description": "Tips:本季新番咨讯！",
            },
            {
                "command": "/下季新番",
                "description": "Tips:下季新番咨讯！",
            },
            {
                "command": "/新番观察",
                "description": "Tips:未来新番咨询！",
            }
        ]
    },
    {
        "command_type": "群老婆相关",
        "command_list": [
            {
                "command": "/群老婆",
                "description": "Tips:获取今日老婆！",
            },
            {
                "command": "/群老婆 换",
                "description": "Tips:重新获取今日老婆！",
            },
            {
                "command": "/群老婆 摸",
                "description": "Tips:摸摸今日群老婆！",
            }
        ]
    },
    {
        "command_type": "今日塔罗",
        "command_list": [
            {
                "command": "/今日塔罗",
                "description": "Tips:塔罗牌列表帮助",
            },
            {
                "command": "/今日塔罗 1",
                "description": "Tips:抽取大阿尔克纳牌",
            },
            {
                "command": "/今日塔罗 2",
                "description": "Tips:抽取小阿尔克纳牌",
            },
            {
                "command": "/今日塔罗 3",
                "description": "Tips:抽取混合牌组",
            },
            {
                "command": "/今日塔罗 4",
                "description": "Tips:抽取三角牌阵",
            },
            {
                "command": "/今日塔罗 5",
                "description": "Tips:抽取六芒星牌阵",
            }
        ]
    },
    {
        "command_type": "助理相关",
        "command_list": [
            {
                "command": "/今日助理",
                "description": "Tips:获取、查询今日助理",
            },
            {
                "command": "/今日助理 ID",
                "description": "Tips:设定你指定ID的助理为今日助理",
            },
            {
                "command": "/今日助理 名称",
                "description": "Tips:设定你指定名称的助理为今日助理",
            },
            {
                "command": "/我的助理",
                "description": "Tips:获取你的全部助理信息",
            },
            {
                "command": "/我的助理 名称",
                "description": "Tips:获取你指定名称的助理信息",
            },
            {
                "command": "/我的助理 ID",
                "description": "Tips:获取你指定ID的助理信息",
            }
        ]
    },
    {
        "command_type": "图片相关",
        "command_list": [
            {
                "command": "/图",
                "description": "Tips:获取一张随机爱莉图片！~",
            },
            {
                "command": "/随机图",
                "description": "Tips:获取一张随机图片！~",
            }
        ]
    },
    {
        "command_type": "整活功能",
        "command_list": [
            {
                "command": "/奶龙",
                "description": "",
            },
            {
                "command": "#joker",
                "description": "",
            },
            {
                "command": "#得吃",
                "description": "",
            },
            {
                "command": "/喜报 内容",
                "description": "tips:发送喜报内容",
            },
            {
                "command": "/悲报 内容",
                "description": "Tips:发送悲报内容",
            },
            {
                "command": "/鲁迅说 内容",
                "description": "Tips:你想让鲁迅说什么？",
            }
        ]
    }
]

async def check_value_in_menu(message: MessageEvent) -> bool:
    value = message.get_plaintext().strip().split(" ")
    group_id = message.group_openid if hasattr(message, "group_openid") else "C2C"
    await UserList.insert_user(message.author.id, group_id)
    return value[0] not in menu and not value[0].isdigit() and value[0] != "#"

check = on_message(rule=to_me() & Rule(check_value_in_menu), priority=20, block=True)

@check.handle()
async def handle_function(message: MessageEvent):
    status = 0
    group_openid = message.group_openid if hasattr(message, "group_openid") else "C2C"
    content = message.get_plaintext() or "空内容"
    
    if content.startswith("/"):
        r_msg = f"收到内容：{content}\n{random.choice(text_list)}"
        await check.finish(r_msg)
    
    # 临时关闭非私聊环境
    if group_openid != "C2C":
        await check.finish(random.choice(text_list))

    if len(content) > 30:
        await check.finish("请勿发送过长的内容")
    content = MarkdownCleaner.clean_markdown(content)
    
    if content.startswith("新的对话") or content.startswith("新的记忆"):
        await check.finish("请输入正确的指令！\n指令格式：\n/爱莉希雅\n/爱莉希雅 <新的对话/新的记忆>")
    elif status == 0 or status == 2:
        if status == 0:
            await asyncio.wait_for(handle_Elysia_response(message), timeout=250)
        elif status == 2:
            await asyncio.wait_for(handle_Elysia_response(message,on_tts = True), timeout=250)
    elif status == 1:
        msg = await ai_chat.deepseek_chat(group_openid, content)
        await check.finish(msg)
    else:
        await check.finish(random.choice(text_list))
text_list = [
    "【妖精爱莉回复】哎呀，亲爱的舰长♪ 没识别到什么呢？\n让我来猜猜看是不是你心中那点小秘密呀？",
    "【妖精爱莉回复】亲爱的舰长，别一头雾水啦♪\n 我这么可爱，怎么会让我猜不透呢？",
    "【妖精爱莉回复】亲爱的舰长，是啥意思呀？完全没搞懂呢♪ \n不过没关系，我们一起慢慢探索，总能找到答案的哦！",
    "【妖精爱莉回复】哎呀，亲爱的舰长，是特殊信号吗？我也听不懂呢♪ \n下个明确指令吧！♪ 我会像星辰一样指引你，让你的每一步都充满光彩和信心哦！",
    "【妖精爱莉回复】难道是新指令吗？哎呀，一脸茫然呢♪ \n哎呀，一脸茫然呢♪",
]

async def handle_Elysia_response(message: MessageEvent, on_tts: bool = False):
    """Elysia Chat 响应"""
    user_id = message.get_user_id()
    content = message.get_plaintext() or "空内容"
    user_msg = await BLChatRole.get_chat_role_by_user_id(user_id)
    if user_msg is None:
        # 发送等待回复
        r_msg = Message([
            MessageSegment.file_image((Path(image_local_qq_image_path) / "AIchat.png")),
            MessageSegment.text("请认真阅读并同意《AI服务使用协议与安全规范》相关内容后"
                                +"\n回答此问题：本爱莉希雅出自那款游戏？"
                                +"\n回复游戏名称！要求使用中文，不得使用其他语言符号或外号"
                                +"\n回答正确即视为已阅读并同意遵守相关协议！")
        ])
        try:
            await check.send(r_msg)
            
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
                    await check.finish("回答错误，请重新开始对话。")
                else:
                    await check.send("回答正确，欢迎您！舰长~"
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
            await check.finish("发生错误，请稍后再试。")
    else:
        ban_info = await waf.get_ban_reason(user_id)
        if ban_info:
            await check.finish(f"您的AI Chat已被封禁：{ban_info}\n请联使用 /help 指令咨询管理员了解详情")
        is_k, is_i = await waf.process(user_id, content)
        if is_k:
            logger.info(f"用户：{user_id} {is_i} content：{content}")
            return

    async def _Elysia_Chat_task():
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, 
                lambda: asyncio.run(on_bl_chat(user_id, content))
            )
            if not result:
                raise Exception("生成失败")
            if has_elysia_command_regex(result):
                r_msg = await elysia_command(result)
                logger.debug(f"Elysia Chat R Data：{r_msg}")
                txt = r_msg.get("txt") or None
                imgs = r_msg.get("imgs") or None
                audios = r_msg.get("audios") or None
                is_voice = r_msg.get("is_voice") if r_msg.get("is_voice") == "True" else on_tts
                tone = r_msg.get("tone") or None
                if txt is not None:
                    logger.debug(f"Elysia txt：{txt}")
                    if imgs is not None:
                        # 如果imgs是str
                        if isinstance(imgs, str):
                            msg = Message([
                                MessageSegment.file_image(Path(imgs)),
                                MessageSegment.text(txt)
                            ])
                            await check.send(msg)
                            await delete_file(imgs)
                        elif len(imgs) == 2:
                            logger.debug(f"Elysia 处理发送图片数量为2")
                            msg = Message([
                            MessageSegment.file_image(Path(imgs['info_img'])),
                            MessageSegment.text(txt)
                            ])
                            await check.send(msg)
                            await check.send(MessageSegment.file_image(Path(imgs['music_img'])))
                            await delete_file(imgs['info_img'])
                            await delete_file(imgs['music_img'])
                    else:
                        await check.send(txt)
                if audios is not None:
                    await check.send(MessageSegment.file_audio(Path(audios)))
                    await delete_file(audios)
                if is_voice == "True" or on_tts: 
                    if tone is None:
                        raise ValueError('tone is None')
                    tts = TTSProvider()
                    # 移除（）和()和括号内文本
                    text = re.sub(r'[\(\（][^()（）]*[\)\）]', '', txt)
                    result = await tts.to_tts(text ,tone)
                    if not result:
                        raise Exception("TTS 生成失败，结果为空")
                    file_path = result["file_path"]
                    file_name = result["file_name"]
                    logger.debug(f"生成语音文件：{file_path}")

                    # 转码使用异步等待
                    output_silk_path = await Transcoding(file_path, file_name)
                    await check.send(MessageSegment.file_audio(Path(output_silk_path)))
                    await delete_file(output_silk_path)
                    await delete_file(file_path)
            else:
                await check.send("未定义内容/超出最大回复token，建议开启 新的对话")
            await check.finish()
            
        except Exception as e:
            if isinstance(e, FinishedException):
                return
            r_msg = "未知错误，请稍后再试"
            if hasattr(e, 'message'):
                r_msg = e.message
            logger.error(f"Elysia Chat 处理失败：{str(e)}")
            await check.finish(f"Elysia Chat 处理失败：{r_msg}")

    # 创建后台任务不阻塞当前处理
    asyncio.create_task(_Elysia_Chat_task())

async def Transcoding(file_path: str, output_filename: str) -> str:
    """
    将文件转换为silk格式
    :param file_path: 文件路径
    :param output_filename: 输出文件名
    :return: 输出文件路径
    """
    loop = asyncio.get_running_loop()
    output_silk_path = Path(temp_path) / f"{Path(output_filename).stem}.silk"
    await loop.run_in_executor(
        None, 
        lambda: silkcoder.encode(file_path, output_silk_path, rate=32000, tencent=True)
    )
    return str(output_silk_path)


get_help = on_command("help", rule=to_me(), priority=10, block=True)
@get_help.handle()
async def send_help_list():
    temp_file = os.path.join(temp_path, f"{datetime.now().date()}_{uuid.uuid4().hex}.png")
    if await help_info_img(send_menu, temp_file):
        await get_help.finish(MessageSegment.file_image(Path(temp_file)))
    else:
        await get_help.finish("获取帮助失败")

restart = on_command("重启", rule=to_me(), priority=10, block=True)
@restart.handle()
async def handle_function(message: MessageEvent):
    if not hasattr(message, 'group_openid'):
        await restart.finish("暂未在当前场景下开放此功能。")

    member_openid, group_openid = message.author.id, message.group_openid
    if not await GroupChatRole.get_admin_list(group_openid, member_openid):
        await restart.finish("您没有权限使用此功能。")
    subprocess.Popen(["runtime/python", "Reboot.py"]) # 如果你使用了集成环境，请将python路径替换为集成环境路径
    await restart.finish("重启成功，请10秒后再试。")

love = on_keyword({"我喜欢你", "❤"}, rule=to_me(), priority=2, block=False)
@love.handle()
async def spread_love():
    await love.finish("我也喜欢你。")

test = on_command("test", rule=to_me(), priority=10, block=True)
@test.handle()
async def bot_on_ready():
    await test.finish("\n 测测你的")

joker = on_fullmatch({"#joker", "#小丑"}, rule=to_me(), priority=2, block=True)
@joker.handle()
async def bot_on_joker():
    await joker.finish(MessageSegment.file_audio(Path(AUDIO_PATH, "joker.silk")))

dechi = on_fullmatch({"#寂寞的人唱伤心的歌", "#得吃"}, rule=to_me(), priority=2, block=True)
@dechi.handle()
async def bot_on_dechi():
    await dechi.finish(MessageSegment.file_audio(Path(AUDIO_PATH, "寂寞的人伤心的歌.silk")))