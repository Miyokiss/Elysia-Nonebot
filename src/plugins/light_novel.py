from datetime import datetime, time
from pathlib import Path
import requests.exceptions
from nonebot import logger
from nonebot.rule import to_me
from nonebot.plugin import on_command
from nonebot.adapters.qq import  MessageSegment
from src.clover_lightnovel.html_to_img import get_ln_image
from src.configs.path_config import temp_path
import os

__name__ = "light_novel"


light_novel = on_command("轻小说", rule=to_me(), priority=10, block=True)
@light_novel.handle()
async def get_ln():
    now = datetime.now()
    file = Path() / temp_path / f"{now.date()}轻小说.png"
    if not os.path.exists(file):
        await light_novel.send("正在为您整理最新轻小说咨询哦，请稍等🥳")
    try:
        await get_ln_image()
    except requests.exceptions.InvalidURL as e:
        logger.error(f"requests.exceptions.InvalidURL{e}")
        await light_novel.finish("获取信息失败了，请重试。")
    now = datetime.now().date()
    await light_novel.finish(MessageSegment.file_image(Path(temp_path+f"{now}轻小说.png")))