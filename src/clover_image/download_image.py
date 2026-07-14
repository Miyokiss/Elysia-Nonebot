import os
import asyncio
import aiohttp
from nonebot import logger

__name__ = 'download_image'

async def download_image(url,file_path):
    """
    下载图片
    :param url:
    :param file_path:
    :return:
    """
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        logger.warning(f"跳过无效图片地址: {url!r}")
        return False

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                if not os.path.exists(os.path.dirname(file_path)):
                    os.makedirs(os.path.dirname(file_path))
                with open(file_path, 'wb') as file:
                    while True:
                        chunk = await response.content.read(8192)
                        if not chunk:
                            break
                        file.write(chunk)
        return True
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
        logger.warning(f"下载图片时出错: {e}")
        return False
