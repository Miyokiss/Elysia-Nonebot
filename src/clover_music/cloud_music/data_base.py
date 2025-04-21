import os
from os import getcwd
from nonebot.log import logger
from nonebot_plugin_htmlrender import template_to_pic
from playwright.async_api import async_playwright
from src.clover_music.cloud_music.cloud_music import netease_music_search,netease_music_info


__name__ = "cloud_music | data_base"

async def save_img(data: bytes ,temp_file: str) -> None:

    """
     保存图片到指定文件
     :param data:
     :return:
     """
    with open(temp_file, "wb") as file:
        file.write(data)
async def netease_music_search_info_img(keyword,session,temp_file) -> bytes:
        """获取数据"""
        if os.path.exists(temp_file):
            with open(temp_file,"rb") as image_file:
                return image_file.read()
        song_lists = await netease_music_search(keyword, session)
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
                "viewport": {"width": 580, "height": 530},
                "base_url": f"file://{getcwd()}",
            },
            wait=2,
        )
        await save_img(image_bytes,temp_file)
        await browser.close()
        return image_bytes

async def netease_music_info_img(keyword,session,idx,temp_file: str):
        """
        获取数据\n
        :param keyword: 搜索关键字
        :param session: requests会话对象
        :param idx: 歌曲索引
        :param temp_file: 临时文件路径
        :return: {\n
            song_id,
            song_name,
            singer
        }
        :return: None 如果没有找到或其他返回None
        """
        song_lists = await netease_music_search(keyword, session)
        song_id = None
        for i in range(len(song_lists)):
            s_list = song_lists[i]
            if isinstance(s_list, dict) and 'index' in s_list:
                logger.debug(f"s_list['index']: {s_list['index']}, index: {idx}")
                if str(s_list['index']) == str(idx):
                    song_id = s_list["song_id"]
                    break
        if song_id is None:
            return None
        song_info = await netease_music_info(song_id)
        if song_info is None:
            return None
        artists = song_info[0]['artists']
        artists_name = []
        for i in range(len(artists)):
            artist = artists[i]
            if isinstance(artist, dict) and 'name' in artist:
                artists_name.append(artist['name'])
        playTime = song_info[0]['hMusic']['playTime']
        seconds = playTime // 1000
        minutes = seconds // 60
        hours = minutes // 60
        playTime_str = f"{hours}:{minutes % 60}:{seconds % 60}"

        song_name = song_info[0]['name']
        song_artists = "、".join(artists_name)

        data = {
             "song_name" : song_name,
             "song_alias" : " - "+song_info[0]['alias'][0] if len(song_info[0]['alias']) > 0 else "",
             "song_artists" : song_artists,
             "song_imgurl" : song_info[0]['album']['blurPicUrl'],
             "song_playTime" : playTime_str
        }
        logger.debug(f"data：{data}")
        async with async_playwright() as p:
            browser = await p.chromium.launch()

        image_bytes = await template_to_pic(
            template_path=getcwd() + "/src/clover_html/cloud_music",
            template_name="info.html",
            templates={"data": data},
            pages={
                "viewport": {"width": 580, "height": 530},
                "base_url": f"file://{getcwd()}",
            },
            wait=2,
        )
        await save_img(image_bytes, temp_file)
        await browser.close()
        return song_id,song_name,song_artists
