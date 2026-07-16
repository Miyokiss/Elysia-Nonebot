import os
import asyncio
import aiohttp
from urllib.parse import urlparse
from nonebot import logger

__name__ = 'download_image'

async def download_image(url, file_path, *, allowed_hosts=None):
    """
    下载图片
    :param url:
    :param file_path:
    :return:
    """
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        logger.warning(f"跳过无效图片地址: {url!r}")
        return False
    if allowed_hosts:
        try:
            hostname = urlparse(url).hostname
        except ValueError:
            hostname = None
        if hostname not in allowed_hosts:
            logger.warning("跳过不受信任的图片地址")
            return False

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                url, allow_redirects=not bool(allowed_hosts)
            ) as response:
                if 300 <= response.status < 400:
                    logger.warning("受信任图片地址返回了重定向，已拒绝")
                    return False
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
