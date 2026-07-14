import os
import asyncio
import uuid
import aiohttp
from pathlib import Path
from nonebot import logger

from src.configs.path_config import image_local_qq_image_path
from src.configs.api_config import app_id,bot_account



async def _download_avatar(url: str, save_path: str):
    timeout = aiohttp.ClientTimeout(total=20)
    for attempt in range(3):
        part_path = f"{save_path}.{uuid.uuid4().hex}.part"
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("Content-Type", "")
                    if content_type and not content_type.startswith("image/"):
                        raise ValueError(f"头像接口返回了非图片内容: {content_type}")
                    with open(part_path, 'wb') as file:
                        async for chunk in response.content.iter_chunked(8192):
                            file.write(chunk)
            os.replace(part_path, save_path)
            return save_path
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError) as exc:
            if attempt == 2:
                logger.warning(f"QQ 头像下载失败: {exc}")
                return None
            await asyncio.sleep(0.5 * (2 ** attempt))
        finally:
            try:
                Path(part_path).unlink(missing_ok=True)
            except OSError as exc:
                logger.warning(f"清理头像下载临时文件失败 {part_path}: {exc}")


"""获取QQ头像"""
async def download_qq_image(member_open_id, size = 140):
    """
    获取QQ头像
    :param member_open_id: QQ加密后的openid
    :param size: 头像尺寸，默认为140，支持40、100、140、640
    :return: 本地保存的头像路径
    """
    os.makedirs(image_local_qq_image_path, exist_ok=True)

    save_path = str(
        Path(image_local_qq_image_path)
        / f"avatar_{uuid.uuid4().hex}.jpg"
    )
    url = f"https://q.qlogo.cn/qqapp/{app_id}/{member_open_id}/{size}"
    return await _download_avatar(url, save_path)

"""获取QQ头像"""
async def download_qq_image_by_account(account):
    os.makedirs(image_local_qq_image_path, exist_ok=True)
    if account is None:
        account = bot_account
    save_path = str(
        Path(image_local_qq_image_path) / f"avatar_{uuid.uuid4().hex}.jpg"
    )
    size = 640  # 尺寸 40、100、140、640
    url = f"https://q2.qlogo.cn/headimg_dl?dst_uin={account}&spec={size}"
    return await _download_avatar(url, save_path)

