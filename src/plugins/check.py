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
from src.providers.llm.AliBL.AliBL import Ali_BL_Api
from nonebot.adapters.qq import Message, MessageEvent
from src.clover_sqlite.models.chat import GroupChatRole
from src.providers.tts.gpt_sovits_v2 import TTSProvider
from nonebot.adapters.qq import   MessageSegment,MessageEvent
from src.configs.path_config import AUDIO_TEMP_PATH

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
        "/奶龙","我喜欢你", "❤",
        "/重启","/repo", "/info", "/help", "/test"]

send_menu = ["/menu","/今日运势","/今日塔罗","/图","/随机图","搜番","/日报","/点歌","/摸摸头","/群老婆","/待办","/天气",
             "/待办查询", "/新建待办", "/删除待办" ,"/cf","/B站搜索", "/BV搜索", "/喜报", "/悲报","/鲁迅说",
             "/轻小说","/本季新番","/新番观察","/下季新番","/绝对色感","/jm"]

async def check_value_in_menu(message: MessageEvent) -> bool:
    value = message.get_plaintext().strip().split(" ")
    if hasattr(message, "group_openid"): # 是否有属性group_openid，即是否为群聊消息
        group_id = message.group_openid
    else:
        group_id = "C2C" # 非群聊消息，存为c2c
    #缓存用户id
    await UserList.insert_user(message.author.id,group_id)
    if value[0] in menu or value[0].isdigit() or value[0] == "#":
        return False
    else:
        return True


check = on_message(rule=to_me() & Rule(check_value_in_menu), priority=10)
@check.handle()
async def handle_function(message: MessageEvent):
    if hasattr(message, "group_openid"):
        group_openid = message.group_openid
    else:
        group_openid = "C2C"

    member_openid, content = message.author.id, message.get_plaintext()
    status = await GroupChatRole.is_on(group_openid)
    logger.debug(f"check | status ——————> {status}")
    # 这里配置 AI 调用
    if status==1:
        msg = await ai_chat.deepseek_chat(group_openid,content)
        await check.finish(msg)
    if status==2:
        text = await Ali_BL_Api(group_openid,content)
        # tts 调用 配置
        tts = TTSProvider()
        try:
            # 生成语音文件
            result = await asyncio.wait_for(tts.to_tts(text), timeout=10)
            if result is None:
                raise Exception("TTS 生成失败，结果为空")
            file_path = result["file_path"]
            file_name = result["file_name"]
            logger.debug(f"check:result | 生成语音文件：\n路径={file_path} \n文件名={file_name}")

            # 转码
            output_silk_path = await asyncio.wait_for(Transcoding(file_path, file_name), timeout=10)
            logger.debug(f"check:output_silk_path | output_silk_path：{output_silk_path}")

            # 发送语音文件
            await check.send(MessageSegment.file_audio(Path(output_silk_path)))

        except asyncio.TimeoutError:
            logger.error("check：asyncio.TimeoutError | TTS 生成/转换超时！")
        except Exception as e:
            logger.error(f"check：Exception | TTS 失败：{e}")
        try:
           if file_path:
               await delete_file(file_path)
           if output_silk_path:
               await delete_file(output_silk_path)
        except Exception as e:
           logger.error(f"check：Exception | 删除临时文件失败：{e}")
    else:
        await check.finish(message=Message(random.choice(text_list)))

text_list = [
    "【妖精爱莉回复】哎呀，亲爱的舰长♪ 没识别到什么呢？"+"\n"+"让我来猜猜看是不是你心中那点小秘密呀？",
    "【妖精爱莉回复】亲爱的舰长，别一头雾水啦♪" + "\n" + " 我这么可爱，怎么会让我猜不透呢？",
    "【妖精爱莉回复】亲爱的舰长，是啥意思呀？完全没搞懂呢♪ " + "\n" + "不过没关系，我们一起慢慢探索，总能找到答案的哦！",
    "【妖精爱莉回复】哎呀，亲爱的舰长，是特殊信号吗？我也听不懂呢♪ " + "\n" + "下个明确指令吧！♪ 我会像星辰一样指引你，让你的每一步都充满光彩和信心哦！",
    "【妖精爱莉回复】难道是新指令吗？哎呀，一脸茫然呢♪ " + "\n" + "哎呀，一脸茫然呢♪",
]

async def Transcoding(file_path : str ,output_filename : str):
    """
    转码处理语音文件
    :param file_path: 输入文件路径
    :param output_filename: 输出文件名
    :return: output_silk_path 转码后的文件路径
    """
    # 转码处理语音文件
    output_silk_path = os.path.join(AUDIO_TEMP_PATH, os.path.splitext(output_filename)[0] + ".silk")
    # 使用 graiax-silkcoder 进行转换
    silkcoder.encode(file_path, output_silk_path, rate=32000, tencent=True, ios_adaptive=True)
    return output_silk_path


get_menu = on_command("help", rule=to_me(), priority=10, block=True)
@get_menu.handle()
async def send_menu_list():
    content = "\n"
    for command in send_menu:
        content += command + "\n"
    await get_menu.finish(content)

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
