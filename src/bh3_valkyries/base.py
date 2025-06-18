from os import getcwd
from nonebot.log import logger
from playwright.async_api import async_playwright
from nonebot_plugin_htmlrender import template_to_pic
from src.clover_music.cloud_music.data_base import save_img

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

async def valkyrie_info_img(data, temp_file):
    """
    获取角色信息图片
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch()
    image_bytes = await template_to_pic(
        template_path=getcwd() + "/src/clover_html/BH3",
        template_name="valkyrie.html",
        templates={"data": data},
        pages={
            "viewport": {"width": 1185, "height": 1},
            "base_url": f"file://{getcwd()}",
        },
        wait=2,
    )
    await save_img(image_bytes,temp_file)
    await browser.close()
    return True