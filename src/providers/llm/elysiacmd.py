import re
import os
import json
import uuid
import requests
from os import getcwd
from datetime import datetime
from nonebot import logger
from typing import List, Optional
from src.configs.path_config import temp_path
from playwright.async_api import async_playwright
from nonebot_plugin_htmlrender import template_to_pic
from src.clover_music.cloud_music.cloud_music import music_download, netease_music_download, netease_music_search
from src.clover_music.cloud_music.data_base import netease_music_info_img
from src.utils.date_info import DateInfo

__name__ = "Elysia_cmd"

COMMAND_PATTERN = re.compile(
    r"<Elysia Command invocation>\s*(.+?)\s*</Elysia Command invocation>",
    re.DOTALL | re.IGNORECASE
)

def has_elysia_command_regex(content: str) -> bool:
    """检查是否存在 Elysia 命令"""
    match = COMMAND_PATTERN.search(content)
    logger.debug(f"Command match: {match}")
    return bool(match)

def get_elysia_commands(content: str) -> Optional[str]:
    """提取并返回第一个 Elysia 命令内容"""
    match = COMMAND_PATTERN.search(content)
    if match and (cmd := match.group(1).strip()):
        return cmd
    return None

def parse_elysia(Edata: Optional[str],field: str) -> Optional[str]:
    """解析并返回第一个有效指定字段"""
    data = json.loads(Edata.strip())
    if cmd := data.get(field):
        return cmd  # 找到第一个有效项立即返回
    return None  # 未找到返回None

async def save_img(data: bytes ,temp_file: str) -> None:

    """
     保存图片到指定文件
     :param data:
     :return:
     """
    with open(temp_file, "wb") as file:
        file.write(data)

async def elysia_command(result)-> list:
    """处理 Elysia 命令的异步函数
    
    Args:
        result: 包含命令的原始字符串
        
    Returns:
        包含响应内容的字典
    """
    Edata = get_elysia_commands(result)
    logger.debug(f"Elysia Chat CMD Data：{Edata}")

    cmd = parse_elysia(Edata,field = "cmd")
    logger.debug(f"Elysia Chat CMD：{cmd}")

    if cmd == "elysia_info":
        info_data = await _elysia_info_(Edata=Edata)
        info_img = await _elysia_info_img(info_data)

        return{
            "txt": info_data['txt'],
            "is_voice": info_data['is_voice'],
            "tone": info_data['tone'],
            "like_value": info_data['like_value'],
            "imgs": info_img
        }
    elif cmd == "cloud_music":
        session = requests.session()
        info_data = await _elysia_info_(Edata=Edata)
        info_img = await _elysia_info_img(info_data)

        song,singer,keyword = await _elysia_cloud_music_info_(Edata=Edata)

        logger.debug(f"cloud_music:song:{song} singer:{singer}")
        
        session = requests.session()
        temp_file = os.path.join(temp_path, f"{datetime.now().date()}_{uuid.uuid4().hex}.png")
        song_lists = await netease_music_search(keyword, session)
        song_id=song_lists[0]["song_id"]
        music_info = await netease_music_info_img(song_id=song_id, temp_file=temp_file)
        if music_info is None:
            return{
                "txt": "\n没有找到歌曲，或检索到的歌曲为付费/无版权喔qwq\n这绝对不是我的错，绝对不是！",
            }
        output_silk_path = await music_download(song_id)
        if output_silk_path is None:
            # 降级下载
            output_silk_path = await netease_music_download(song_id, session=session)
            if output_silk_path is None or output_silk_path == -1:
                return{
                    "txt": "歌曲音频获取失败了Σヽ(ﾟД ﾟ; )ﾉ，可能歌曲为付费歌曲请换首重试吧！"
                }
        return{
            "txt": info_data['txt'],
            "is_voice": info_data['is_voice'],
            "tone": info_data['tone'],
            "like_value": info_data['like_value'],
            "imgs": {
                "info_img": info_img,
                "music_img": temp_file
            },
            "audios": output_silk_path
        }
    else:
        return{
            "txt": "未定义命令，建议开启 新的对话"
        }

async def _elysia_info_(Edata: json) -> json:
    """处理 Elysia 信息
    Args:
        Edata: 包含命令的原始字符串"""
    time = parse_elysia(Edata,field = "time")
    mood = parse_elysia(Edata,field = "mood")
    is_voice = parse_elysia(Edata,field = "is_voice")
    tone = parse_elysia(Edata,field = "tone")
    like_value = parse_elysia(Edata,field = "like_value")
    supplement = parse_elysia(Edata,field = "supplement")
    txt = parse_elysia(Edata,field = "txt")
    return{
        "time": time,
        "mood": mood,
        "tone": tone,
        "is_voice": is_voice,
        "like_value": like_value,
        "supplement": supplement,
        "txt": txt
    }

async def _elysia_info_img(info_data: json) -> str:
    """生成 Elysia 信息图片
    Args:
        info_data: 包含命令的原始字符串
    Returns:
        图片路径
    """
    temp_file = os.path.join(temp_path, f"{datetime.now().date()}_{uuid.uuid4().hex}.png")
    if os.path.exists(temp_file):
        with open(temp_file,"rb") as image_file:
            return image_file.read()
    date_info = DateInfo()
    week = date_info.get_weekday()
    is_holiday, holiday = date_info.check_holiday()
    like_value = int(info_data.get("like_value"))
    like_percentage = int(like_value / 200 * 100)
    data = {
         "info_data": info_data,
         "week": week,
         "is_holiday": is_holiday,
         "holiday": holiday,
         "like_value": like_value,
         "like_percentage": like_percentage
    }
    logger.debug(f"data：{data}")
    async with async_playwright() as p:
        browser = await p.chromium.launch()
    image_bytes = await template_to_pic(
        template_path=getcwd() + "/src/clover_html/Elysia_html",
        template_name="chat.html",
        templates={"data": data},
        pages={
            "viewport": {"width": 580, "height": 1},
            "base_url": f"file://{getcwd()}",
        },
        wait=2,
    )
    await save_img(image_bytes,temp_file)
    await browser.close()
    return temp_file

async def _elysia_cloud_music_info_(Edata: json) -> tuple:
    """处理 Elysia cloud_music 信息
    Args:
        Edata: 包含命令的原始字符串
    Returns:
    song: 歌曲名
    singer: 歌手名
    keyword: 关键词
    """
    song = parse_elysia(Edata,field = "song")
    singer = parse_elysia(Edata,field = "singer")
    keyword = song+"-"+singer if singer!=None else song
    return song,singer,keyword