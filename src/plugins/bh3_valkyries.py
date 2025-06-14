import json
import uuid
import random
from pathlib import Path
from nonebot import logger
from datetime import datetime
from nonebot.rule import to_me
from nonebot.plugin import on_command
from src.configs.path_config import temp_path
from nonebot.exception import FinishedException
from src.clover_image.delete_file import delete_file
from nonebot.adapters.qq import   MessageSegment,MessageEvent, Message
from src.bh3_valkyries.data_base import (get_all_valkyrie_json, get_valkyrie_info,
                                         get_audio_links, get_valkyrie_img, download_audio)
from src.bh3_valkyries.base import all_valkyrie_info_img

bh3_valkyries = on_command("今日助理",aliases={"我的助理"},rule=to_me(),priority=1,block=True)
@bh3_valkyries.handle()
async def handle_function(message: MessageEvent):
    cmd = message.get_plaintext().split()
    user_id = message.get_user_id()

    temp_valkyries = Path(temp_path) / f"{datetime.now().date()}_bh3_valkyries.json"

    if not temp_valkyries.exists():
            await bh3_valkyries.send("助理信息正在获取中，请稍等...")
            try:
                await get_all_valkyrie_json(temp_valkyries)
            except Exception as e:
                logger.error(f"获取数据失败: {e}")
                await bh3_valkyries.finish("获取助理信息失败，请稍后再试...")

    with open(temp_valkyries, "r", encoding="utf-8") as f:
            data = json.load(f)
    
    if cmd[0] == "/今日助理":
        if data and isinstance(data, list):
            # 随机选择一名女武神
            valkyrie = random.choice(data)
            logger.debug(f"valkyrie:{valkyrie}")
            content_id = valkyrie["content_id"]
            # 获取助理信息
            temp_valkyrie = Path(temp_path) / f"bh3_valkyrie_{datetime.now().date()}_{content_id}.json"
            if not temp_valkyrie.exists():
                await get_valkyrie_info(content_id, temp_valkyrie)
            with open(temp_valkyrie, "r", encoding="utf-8") as f:
                valkyrie_info = json.load(f)
            # 获取图片/音频
            img_content = valkyrie_info['contents'][0]['text']
            audio_content = valkyrie_info['contents'][2]['text']

            img_link = await get_valkyrie_img(img_content)
            logger.debug(f"提取到的立绘链接: {img_link}")

            audio_links = await get_audio_links("舰桥互动", audio_content)
            logger.debug(f"提取到的舰桥互动音频链接: {audio_links}")

            r_data = random.choice(audio_links)
            output_silk_path = await download_audio(r_data['url'])
            r_msg = Message([
                 MessageSegment.image(img_link),
                 MessageSegment.text(r_data['text'])
            ])
            await bh3_valkyries.send(r_msg)

            if output_silk_path is None:
                logger.error("下载音频失败")
                await bh3_valkyries.finish("下载音频失败，请稍后再试...")
            await bh3_valkyries.send(MessageSegment.file_audio(Path(output_silk_path)))
            await delete_file(output_silk_path)
            await bh3_valkyries.finish()

        else:
            logger.warning("数据格式不正确或为空")
            await bh3_valkyries.finish("获取今日助理数据格式不正确/为空，请稍后再试...")
    elif cmd[0] == "/我的助理":
        values = message.get_plaintext().replace("/我的助理", "").split()
        logger.debug(f"Received command: {cmd}\n values: {values}")
        temp_info_img_path = Path(temp_path) / f"bh3_valkyries_info_{user_id}_{datetime.now().date()}_{uuid.uuid4().hex}.png"
        if await all_valkyrie_info_img(data, temp_info_img_path):
             await bh3_valkyries.send(MessageSegment.file_image(temp_info_img_path))
             await delete_file(temp_info_img_path)
             await bh3_valkyries.finish()
        else:
            logger.error("生成助理列表信息图片失败")
            await bh3_valkyries.finish("生成助理列表信息图片失败，请稍后再试...")
