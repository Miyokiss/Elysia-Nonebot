import os
import uuid
import httpx
from typing import Optional
from graiax import silkcoder
from datetime import datetime
from nonebot import get_driver
from nonebot.log import logger
from src.configs.path_config import temp_path
from src.clover_image.delete_file import delete_file

async_client: Optional[httpx.AsyncClient] = None

@get_driver().on_startup
async def init_netease_client():
    global async_client
    async_client = httpx.AsyncClient(
        verify=False,
        timeout=30.0,
        limits=httpx.Limits(max_connections=100)
    )

async def download_audio(audio_link, file_postfix="mp3"):
    """
    下载音频文件并转换为silk格式
    参数:
        audio_link (str): 音频文件的URL链接
        file_postfix (str): 音频文件的后缀名，默认为"mp3"
    返回:
        str: 转换后的silk文件路径，如果下载或转换失败则返回None
    """

    try:
        async with async_client.stream("GET",audio_link,follow_redirects=True) as response:
            response.raise_for_status()
            if response.status_code == 200:
                logger.debug(f"URL:{audio_link}\n开始下载中...")
                file_name = os.path.basename(f"{datetime.now().date()}-{uuid.uuid4().hex}")
                file_path = os.path.join(temp_path, f"{file_name}.{file_postfix}")
                with open(file_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
                output_silk_path = os.path.join(temp_path, os.path.splitext(file_name)[0] + ".silk")
                # 使用 graiax-silkcoder 进行转换
                silkcoder.encode(file_path, output_silk_path, rate=32000, tencent=True, ios_adaptive=True)
                # 删除临时文件
                await delete_file(file_path)
                return output_silk_path
            else:
                logger.error(f"获取音频链接失败，状态码：{response.status_code}, 原因：{response.text}")
                return None
    except Exception as e:
        logger.error(e)
        return None