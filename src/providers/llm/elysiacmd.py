import re
import os
import json
import uuid
import requests
from datetime import datetime
from nonebot import logger
from typing import List, Optional
from src.configs.path_config import temp_path
from src.clover_music.cloud_music.cloud_music import music_download, netease_music_download
from src.clover_music.cloud_music.data_base import netease_music_info_img

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

def get_all_elysia_commands(content: str) -> List[str]:
    """提取并返回所有 Elysia 命令内容列表"""
    return [
        match.group(1).strip()
        for match in COMMAND_PATTERN.finditer(content)
        if match.group(1).strip()
    ]

def parse_elysia(Edata: List[str],field: str) -> List[Optional[str]]:
    """解析并返回所有有效指定字段"""
    results = []
    for json_str in Edata:
        try:
            data = json.loads(json_str.strip())
            if cmd := data.get(field):
                results.append(cmd)
        except (json.JSONDecodeError, AttributeError):
            continue
    return results


async def elysia_command(result)-> list:
    """处理 Elysia 命令的异步函数
    
    Args:
        result: 包含命令的原始字符串
        
    Returns:
        包含响应内容的字典
    """
    Edata = get_all_elysia_commands(result)
    logger.debug(f"Elysia Chat CMD Data：{Edata}")

    r_result = re.sub(COMMAND_PATTERN, "", result).strip()
    logger.debug(f"Elysia Chat Result：{r_result}")

    cmd = parse_elysia(Edata,field = "cmd")
    logger.debug(f"Elysia Chat CMD：{cmd}")

    if cmd[0] == "cloud_music":
        session = requests.session()
        song = parse_elysia(Edata,field = "song")[0]
        singer = parse_elysia(Edata,field = "singer")[0]
        logger.debug(f"cloud_music:song:{song} singer:{singer}")
        keyword = song+"-"+singer if singer!=None else song
        temp_file = os.path.join(temp_path, f"{datetime.now().date()}_{uuid.uuid4().hex}.png")
        music_info = await netease_music_info_img(keyword, session, idx=1, temp_file=temp_file)
        if music_info is None:
            return{
                "txt": "\n没有找到歌曲，或检索到的歌曲为付费/无版权喔qwq\n这绝对不是我的错，绝对不是！",
            }
        song_id = music_info['song_id']
        output_silk_path = await music_download(song_id)
        if output_silk_path is None:
            # 降级下载
            output_silk_path = await netease_music_download(song_id, session=session)
            if output_silk_path is None:
                return{
                    "txt": "歌曲音频获取失败了Σヽ(ﾟД ﾟ; )ﾉ，可能歌曲为付费歌曲请换首重试吧！"
                }
        return{
            "txt": r_result,
            "img": temp_file,
            "audio": output_silk_path
        }
    else:
        return{
            "txt": "命令未定义"
        }
        