import os
import random
import asyncio
import subprocess
from pathlib import Path
from nonebot import logger
from graiax import silkcoder
from nonebot import  on_message
from nonebot.rule import Rule, to_me
from nonebot.exception import FinishedException
from src.clover_openai import ai_chat
from nonebot.plugin import on_command, on_keyword
from src.clover_sqlite.models.user import UserList
from src.clover_image.delete_file import delete_file
from src.providers.llm.AliBL.base import on_bl_chat
from nonebot.adapters.qq import Message, MessageEvent
from src.clover_sqlite.models.chat import GroupChatRole
from src.providers.tts.gpt_sovits_v2 import TTSProvider
from nonebot.adapters.qq import   MessageSegment,MessageEvent
from src.configs.path_config import temp_path,image_local_qq_image_path

menu = ["/今日运势","/今日塔罗",
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
        "/爱莉希雅","妖精爱莉",
        "/奶龙","我喜欢你", "❤","/joker",
        "/重启","/repo", "/info", "/help", "/test"]

send_menu = ["/help","/今日运势","/今日塔罗","/图","/随机图","搜番","/日报","/点歌","/摸摸头","/群老婆","/待办","/天气",
             "/待办查询", "/新建待办", "/删除待办" ,"/B站搜索", "/BV搜索", "/喜报", "/悲报","/鲁迅说",
             "/轻小说","/本季新番","/新番观察","/下季新番","/绝对色感"]

async def check_value_in_menu(message: MessageEvent) -> bool:
    value = message.get_plaintext().strip().split(" ")
    group_id = message.group_openid if hasattr(message, "group_openid") else "C2C"
    await UserList.insert_user(message.author.id, group_id)
    return value[0] not in menu and not value[0].isdigit() and value[0] != "#"

check = on_message(rule=to_me() & Rule(check_value_in_menu), priority=10)

@check.handle()
async def handle_function(message: MessageEvent):
    group_openid = message.group_openid if hasattr(message, "group_openid") else "C2C"
    status = await GroupChatRole.is_on(group_openid)
    logger.debug(f"check | status ——————> {status}")
    if status == 0:
        await handle_Elysia_response(message)
    elif status == 1:
        msg = await ai_chat.deepseek_chat(group_openid, message.get_plaintext())
        await check.finish(msg)
    elif status == 2:
        await handle_tts_response(message)
    else:
        await check.finish(random.choice(text_list))
text_list = [
    "【妖精爱莉回复】哎呀，亲爱的舰长♪ 没识别到什么呢？\n让我来猜猜看是不是你心中那点小秘密呀？",
    "【妖精爱莉回复】亲爱的舰长，别一头雾水啦♪\n 我这么可爱，怎么会让我猜不透呢？",
    "【妖精爱莉回复】亲爱的舰长，是啥意思呀？完全没搞懂呢♪ \n不过没关系，我们一起慢慢探索，总能找到答案的哦！",
    "【妖精爱莉回复】哎呀，亲爱的舰长，是特殊信号吗？我也听不懂呢♪ \n下个明确指令吧！♪ 我会像星辰一样指引你，让你的每一步都充满光彩和信心哦！",
    "【妖精爱莉回复】难道是新指令吗？哎呀，一脸茫然呢♪ \n哎呀，一脸茫然呢♪",
]

async def handle_Elysia_response(message: MessageEvent):
    """Elysia Chat 响应"""
    user_id = message.get_user_id()
    content = message.get_plaintext() or "空内容"

    async def _Elysia_Chat_task():
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, 
                lambda: asyncio.run(on_bl_chat(user_id, content))
            )
            if not result:
                raise Exception("生成失败，结果为空")
            result = result + "\n\n" + "以上内容由AI生成-该功能正在测试中：\n你可以通过指令：\n/爱莉希雅 新的对话 \n创建新的对话\n/爱莉希雅 新的记忆\n创建新的记忆"
            await check.finish(result)
            
        except Exception as e:
            if isinstance(e, FinishedException):
                return
            logger.error(f"Elysia Chat 处理失败：{str(e)}")

    # 创建后台任务不阻塞当前处理
    asyncio.create_task(_Elysia_Chat_task())
async def handle_tts_response(message: MessageEvent):
    """AI Chat TTS 响应"""
    user_id = message.get_user_id()
    content = message.get_plaintext() or "空内容"

    async def _tts_task():
        text = await on_bl_chat(user_id, content)
        tts = TTSProvider()
        
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, 
                lambda: asyncio.run(tts.to_tts(text))
            )
            if not result:
                raise Exception("TTS 生成失败，结果为空")

            file_path = result["file_path"]
            file_name = result["file_name"]
            logger.debug(f"生成语音文件：{file_path}")

            # 转码使用异步等待
            output_silk_path = await Transcoding(file_path, file_name)
            await check.send(MessageSegment.file_audio(Path(output_silk_path)))
            await cleanup_files(file_path, output_silk_path)
            await check.finish()
            
        except Exception as e:
            if isinstance(e, FinishedException):
                return
            logger.error(f"TTS处理失败：{str(e)}")

    # 创建后台任务不阻塞当前处理
    asyncio.create_task(_tts_task())

async def cleanup_files(*files):
    for file in files:
        if file:
            try:
                await delete_file(file)
            except Exception as e:
                logger.error(f"check：Exception | 删除临时文件失败：{e}")

async def Transcoding(file_path: str, output_filename: str) -> str:
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
    text = """
嗨~想我了吗？不论何时何地，爱莉希雅都会回应你的期待！
我可以做什么？
1、想要点歌给群友吗？快来点一首你喜欢的歌，和大家一起分享音乐的快乐吧♪
2、每日运势仅供娱乐，记得相信科学哦，不过偶尔看看也无妨，对吧？
3、想知道天气吗？随时可以和我说，我会回应你的期待♪

Q：遇到BUG/问题/提建议？
A：欢迎加入群聊反馈还能体验新内容！"""
    msg = Message([
        MessageSegment.text(text),
        MessageSegment.file_image(Path(image_local_qq_image_path+f"/QQ.jpg"))
    ])
    await get_help.finish(msg)

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

joker = on_command("joker", rule=to_me(), priority=2, block=True)
@joker.handle()
async def bot_on_joker():
    await joker.finish(MessageSegment.file_audio(Path(AUDIO_PATH, "joker.silk")))
