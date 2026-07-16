import os
from os import getcwd
from nonebot.log import logger
from nonebot_plugin_htmlrender import template_to_pic
from playwright.async_api import async_playwright
from src.clover_music.cloud_music.cloud_music import netease_music_info
from src.clover_music.cloud_music.data_comments import DataGet
from src.clover_music.cloud_music.song_info import build_music_card_data


__name__ = "cloud_music | data_base"

async def save_img(data: bytes ,temp_file: str) -> None:

    """
     保存图片到指定文件
     :param data:
     :return:
     """
    with open(temp_file, "wb") as file:
        file.write(data)
async def netease_music_search_info_img(song_lists, temp_file):
        """获取数据
        :param keyword: 搜索关键字
        :param session: requests会话对象
        :param temp_file: 临时文件路径
        :return: True 如果没有找到或其他返回None"""
        if os.path.exists(temp_file):
            with open(temp_file,"rb") as image_file:
                return image_file.read()
        data = {
             "song_lists": song_lists,
        }
        logger.debug(f"data：{data}")
        async with async_playwright() as p:
            browser = await p.chromium.launch()

        image_bytes = await template_to_pic(
            template_path=getcwd() + "/src/clover_html/cloud_music",
            template_name="main.html",
            templates={"data": data},
            pages={
                "viewport": {"width": 580, "height": 1},
                "base_url": f"file://{getcwd()}",
            },
            wait=2,
        )
        await save_img(image_bytes,temp_file)
        await browser.close()
        return True

async def netease_music_info_img(song_id, temp_file: str):
        """
        获取数据\n
        :param keyword: 搜索关键字
        :param session: requests会话对象
        :param idx: 歌曲索引
        :param temp_file: 临时文件路径
        :return: True 如果没有找到或其他返回None
        """
        Data_get = DataGet()
        song_info = await netease_music_info(song_id)
        try:
            song_comments = await Data_get.song_comments(song_id)
        except Exception as exc:
            logger.warning(
                f"歌曲热评获取失败，继续生成基础信息卡片: {type(exc).__name__}"
            )
            song_comments = []
        data = build_music_card_data(song_info, song_comments)
        if data is None:
            return None
        logger.debug(f"data：{data}")
        async with async_playwright() as p:
            browser = await p.chromium.launch()

        image_bytes = await template_to_pic(
            template_path=getcwd() + "/src/clover_html/cloud_music",
            template_name="info.html",
            templates={"data": data},
            pages={
                "viewport": {"width": 580, "height": 1},
                "base_url": f"file://{getcwd()}",
            },
            wait=2,
        )
        await save_img(image_bytes, temp_file)
        await browser.close()
        return True
