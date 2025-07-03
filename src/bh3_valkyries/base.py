import json
import uuid
from os import getcwd
from pathlib import Path
from datetime import datetime
from src.configs.path_config import temp_path
from playwright.async_api import async_playwright
from nonebot_plugin_htmlrender import template_to_pic
from src.clover_music.cloud_music.data_base import save_img
from src.bh3_valkyries.data_base import BH3_Data_base, get_valkyrie_info, get_valkyries_data_ext

__name__ = "bh3_valkyries | base"

async def valkyries_info_img(data, temp_file, title):
    """
    获取角色列表信息图片
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch()
    image_bytes = await template_to_pic(
        template_path=getcwd() + "/src/clover_html/BH3",
        template_name="VALKYRIES.html",
        templates={"data": data,
                   "title": title},
        pages={
            "viewport": {"width": 580, "height": 1},
            "base_url": f"file://{getcwd()}",
        },
        wait=2,
    )
    await save_img(image_bytes,temp_file)
    await browser.close()
    return True

async def valkyrie_info_img(valkyrie_info, temp_file, text):
    """
    获取角色信息图片
    """
    # 获取图片
    img_content = valkyrie_info['contents'][0]['text']
    img_link = await BH3_Data_base.get_valkyrie_img(img_content)

    ext_str = valkyrie_info['ext']
    ext_data = json.loads(ext_str)
    text_array = json.loads(ext_data['c_18']['filter']['text'])
    # 定义需要过滤的属性前缀
    property_filters = ["角色/", "初始阶级/"]
    # 过滤并转换文本属性
    text_array = [
        item.replace("/", "：") 
        for item in text_array 
        if not any(prop in item for prop in property_filters)
    ]
    data = {
        "title": valkyrie_info['title'],
        "name": await get_valkyries_data_ext(ext_str, "角色/"),
        "text_array": text_array,
        "summary": valkyrie_info['summary'],
        "text": text,
    }
    async with async_playwright() as p:
        browser = await p.chromium.launch()
    image_bytes = await template_to_pic(
        template_path=getcwd() + "/src/clover_html/BH3",
        template_name="valkyrie.html",
        templates={"data": data,
                   "img_link": img_link},
        pages={
            "viewport": {"width": 1185, "height": 1},
            "base_url": f"file://{getcwd()}",
        },
        wait=2,
    )
    await save_img(image_bytes,temp_file)
    await browser.close()
    return True

async def user_valkyrie_info_img(temp_file, valkyrie_info, user_valkyrie_info, text):
    """
    获取用户角色信息图片
    :param temp_file: 临时文件路径
    :param valkyrie_info: 角色信息
    :param user_valkyrie_info: 用户角色信息
    :param text: 文本信息
    :return: 是否成功
    """
    # 获取图片
    img_content = valkyrie_info['contents'][0]['text']
    img_link = await BH3_Data_base.get_valkyrie_img(img_content)
    
    ext_str = valkyrie_info['ext']
    ext_data = json.loads(ext_str)
    text_array = json.loads(ext_data['c_18']['filter']['text'])
    summary = valkyrie_info['summary']
    # 获取初始等级
    initial_level = await get_valkyries_data_ext(ext_str, "初始阶级/")
    # 定义需要过滤的属性前缀
    property_filters = ["角色/", "初始阶级/"]
    # 过滤并转换文本属性
    text_array = [
        item.replace("/", "：") 
        for item in text_array 
        if not any(prop in item for prop in property_filters)
    ]
    ramks = {
        "S": "https://uploadstatic.mihoyo.com/bh3-wiki/2021/09/04/75216984/f241781995cfa42230ce03da6d6d18fc_7542548367973996987.png",
        "SP": "https://uploadstatic.mihoyo.com/bh3-wiki/2021/09/04/75216984/992c35eb753699fbd82aaec12d9f9827_1119293747778788135.png",
        "A": "https://uploadstatic.mihoyo.com/bh3-wiki/2021/09/04/75216984/992c35eb753699fbd82aaec12d9f9827_1119293747778788135.png",
        "B": "https://uploadstatic.mihoyo.com/bh3-wiki/2021/09/03/50494840/62f86400f9a8c589cbac62ec6abda6d7_1075943272726867218.png"
    }
    # 安全获取等级图标（默认返回B级图标）
    icon_url = ramks.get(initial_level, ramks["B"])
    get_first_obtained = datetime.fromtimestamp(user_valkyrie_info.first_obtained).strftime("%Y-%m-%d %H:%M:%S")
    img_data = {
        "img_link": img_link,
        "title": valkyrie_info['title'],
        "name": await get_valkyries_data_ext(ext_str, "角色/"),
        "text_array": text_array,
        "summary": summary,
        "text": text,
        "get_first_obtained": get_first_obtained,
        "favorability": user_valkyrie_info.favorability,
        "count": user_valkyrie_info.count,
        "rank": icon_url
    }
    async with async_playwright() as p:
        browser = await p.chromium.launch()
    image_bytes = await template_to_pic(
        template_path=getcwd() + "/src/clover_html/BH3",
        template_name="user_valkyrie.html",
        templates={"data": img_data},
        pages={
            "viewport": {"width": 1185, "height": 1},
            "base_url": f"file://{getcwd()}",
        },
        wait=2,
    )
    await save_img(image_bytes,temp_file)
    await browser.close()
    return True

async def get_valkyrie_audio_info(valkyrie_info, Keywords = "舰桥互动"):
    """
    获取角色音频信息

    Arguments:
        valkyrie_info (dict): 角色信息
        Keywords (str): 音频关键词，默认为"舰桥互动"
    Returns:
        list: 角色音频关键词列表
        None: 如果没有找到关键词，则返回None
    """
    # 获取助理信息
    audio_content = valkyrie_info['contents'][2]['text'] if valkyrie_info['contents'][2]['text'] else None
    if audio_content is None:
        return None
    audio_links = await BH3_Data_base.get_audio_links(Keywords, audio_content)
    return audio_links

async def get_today_valkyrie_file(today, content_id):
    """
    获取今日角色信息
    """
    temp_valkyrie = Path(temp_path) / f"bh3_valkyrie_{today}_{content_id}.json"
    if not temp_valkyrie.exists():
        await get_valkyrie_info(content_id, temp_valkyrie)
    with open(temp_valkyrie, "r", encoding="utf-8") as f:
        valkyrie_info = json.load(f)
    return valkyrie_info