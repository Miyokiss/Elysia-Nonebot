import os
import random
import asyncio
import subprocess
from pathlib import Path
from nonebot import logger
from graiax import silkcoder
from nonebot import  on_message
from nonebot.rule import Rule, to_me
from src.clover_openai import ai_chat
from nonebot.plugin import on_command, on_keyword
from src.clover_sqlite.models.user import UserList
from src.clover_image.delete_file import delete_file
from src.providers.llm.AliBL.base import on_bl_chat
from nonebot.adapters.qq import Message, MessageEvent
from src.clover_sqlite.models.chat import GroupChatRole
from src.providers.tts.gpt_sovits_v2 import TTSProvider
from nonebot.adapters.qq import   MessageSegment,MessageEvent
from src.configs.path_config import AUDIO_PATH

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

    if status == 1:
        msg = await ai_chat.deepseek_chat(group_openid, message.get_plaintext())
        await check.finish(msg)
    elif status == 2:
        await handle_tts_response(message)
    else:
        await check.finish(message=Message(random.choice(text_list)))

async def handle_tts_response(message: MessageEvent):
    """AI Chat TTS 响应"""
    user_id = message.get_user_id()
    content = message.get_plaintext()
    if not content:
        await check.finish(message=Message(random.choice(text_list)))

    text = await on_bl_chat(user_id, content)
    tts = TTSProvider()
    
    try:
        result = await asyncio.wait_for(tts.to_tts(text), timeout=10)
        if not result:
            raise Exception("TTS 生成失败，结果为空")

        file_path = result["file_path"]
        file_name = result["file_name"]
        logger.debug(f"check:result | 生成语音文件：\n路径={file_path} \n文件名={file_name}")

        output_silk_path = await asyncio.wait_for(Transcoding(file_path, file_name), timeout=10)
        logger.debug(f"check:output_silk_path | output_silk_path：{output_silk_path}")

        await check.send(MessageSegment.file_audio(Path(output_silk_path)))
        await cleanup_files(file_path, output_silk_path)
    except asyncio.TimeoutError:
        logger.error("check：asyncio.TimeoutError | TTS 生成/转换超时！")
    except Exception as e:
        logger.error(f"check：Exception | TTS 失败：{e}")

async def cleanup_files(*files):
    for file in files:
        if file:
            try:
                await delete_file(file)
            except Exception as e:
                logger.error(f"check：Exception | 删除临时文件失败：{e}")

text_list = [
    "【妖精爱莉回复】哎呀，亲爱的舰长♪ 没识别到什么呢？\n让我来猜猜看是不是你心中那点小秘密呀？",
    "【妖精爱莉回复】亲爱的舰长，别一头雾水啦♪\n 我这么可爱，怎么会让我猜不透呢？",
    "【妖精爱莉回复】亲爱的舰长，是啥意思呀？完全没搞懂呢♪ \n不过没关系，我们一起慢慢探索，总能找到答案的哦！",
    "【妖精爱莉回复】哎呀，亲爱的舰长，是特殊信号吗？我也听不懂呢♪ \n下个明确指令吧！♪ 我会像星辰一样指引你，让你的每一步都充满光彩和信心哦！",
    "【妖精爱莉回复】难道是新指令吗？哎呀，一脸茫然呢♪ \n哎呀，一脸茫然呢♪",
]

async def Transcoding(file_path : str ,output_filename : str)->str:
    """
    ### 转码处理语音文件 \n
    :param output_filename: 输出文件名
    :param file_path: 输入文件路径
    :return: output_silk_path 转码后的文件路径
    """
    # 转码处理语音文件
    output_silk_path = os.path.join(AUDIO_PATH, os.path.splitext(output_filename)[0] + ".silk")
    # 使用 graiax-silkcoder 进行转换
    silkcoder.encode(file_path, output_silk_path, rate=32000, tencent=True, ios_adaptive=True)
    return output_silk_path


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
A：联系开发者QQ或邮箱：3522766049
"""
    await get_help.finish(MessageSegment.text(text))

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
