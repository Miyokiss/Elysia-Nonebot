import os
import aiohttp

from src.configs.path_config import image_local_qq_image_path
from src.configs.api_config import app_id,bot_account



"""获取QQ头像"""
async def download_qq_image(member_open_id, size = 140):
    """
    获取QQ头像
    :param member_open_id: QQ加密后的openid
    :param size: 头像尺寸，默认为140，支持40、100、140、640
    :return: 本地保存的头像路径
    """
    if not os.path.exists(image_local_qq_image_path):
        os.makedirs(image_local_qq_image_path)

    save_path = image_local_qq_image_path + '/' + member_open_id + '.jpg'
    url = f"https://q.qlogo.cn/qqapp/{app_id}/{member_open_id}/{size}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            with open(save_path, 'wb') as file:
                while True:
                    chunk = await response.content.read(8192)
                    if not chunk:
                        break
                    file.write(chunk)
                return save_path

"""获取QQ头像"""
async def download_qq_image_by_account(account):
    if not os.path.exists(image_local_qq_image_path):
        os.makedirs(image_local_qq_image_path)
    if account is None:
        account = bot_account
    save_path = image_local_qq_image_path + '/' + account + '.jpg'
    size = 640  # 尺寸 40、100、140、640
    url = f"https://q2.qlogo.cn/headimg_dl?dst_uin={account}&spec={size}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            with open(save_path, 'wb') as file:
                while True:
                    chunk = await response.content.read(8192)
                    if not chunk:
                        break
                    file.write(chunk)
        return save_path

