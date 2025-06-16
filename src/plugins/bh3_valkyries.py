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
from src.bh3_valkyries.data_base import (get_valkyries_data, get_valkyrie_info,
                                         get_audio_links, get_valkyrie_img, download_audio)
from src.bh3_valkyries.base import all_valkyrie_info_img
from src.bh3_valkyries import BH3_User_Assistant, BH3_User_Valkyries

bh3_valkyries = on_command("今日助理",aliases={"我的助理"},rule=to_me(),priority=1,block=True)
@bh3_valkyries.handle()
async def handle_function(message: MessageEvent):
    cmd = message.get_plaintext().split()
    user_id = message.get_user_id()
    
    if cmd[0] == "/今日助理":
        # 获取用户数据
        user_assistant = await BH3_User_Assistant.get_user_data(user_id)
        # 检查是否已获取过助理且最后获取时间是今天
        if user_assistant:
            today = datetime.now().date()
            date_str = datetime.fromtimestamp(user_assistant.last_get_time).date()
            logger.debug(f"用户 {user_id} 上次获取助理时间: {date_str}, 今天日期: {today}")

            if date_str == today:
                await bh3_valkyries.finish("您今天已经获取过助理了，请明天再来吧！~")

        # 获取女武神数据
        data = await get_valkyries_data()
        if data is None:
            await bh3_valkyries.finish("获取数据失败，请稍后再试...")

        if data and isinstance(data, list):
            # 随机选择一名女武神
            valkyrie = random.choice(data)
            time = int(datetime.now().timestamp())
            content_id = valkyrie["content_id"]
            logger.debug(f"获取的女武神ID: {content_id}, 时间戳: {time}")
            # 更新用户助理数据
            await BH3_User_Assistant.create_or_update_field(
                user_id=user_id,
                last_get_time=time
            )
            # 写入日志
            await BH3_User_Assistant.record_get_valkyrie_log(user_id, content_id, time)
            # 获取用户助理信息
            user_valkyrie = await BH3_User_Valkyries.get_user_valkyrie_data(user_id, content_id)
            # 如果用户没有该女武神数据，则创建
            if user_valkyrie is None:
                user_valkyrie = await BH3_User_Valkyries.create_user_valkyrie_data(
                    user_id=user_id,
                    valkyrie_id=content_id,
                    time=time
                )
            else:
                # 如果用户已有该女武神，则更新获取次数
                bh3_user_valkyries = BH3_User_Valkyries()
                await bh3_user_valkyries.update_user_valkyrie_data(
                    user_id=user_id,
                    valkyrie_id=content_id,
                    count=user_valkyrie.count + 1
                )

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
        data = await get_valkyries_data()
        if data is None:
            await bh3_valkyries.finish("获取数据失败，请稍后再试...")
        
        values = message.get_plaintext().replace("/我的助理", "").split()

        all_valkyries = await BH3_User_Valkyries.get_user_all_valkyries(user_id)
        if not all_valkyries:
            await bh3_valkyries.finish("您还没有任何女武神数据，请先获取今日助理！")
        
        valkyrie_map = {v.valkyrie_id: v for v in all_valkyries}  # 创建O(1)查询字典
        
        for item in data:
            valkyrie = valkyrie_map.get(item['content_id'])  # O(1)时间复杂度查找
            if valkyrie:
                item['obtain_time'] = datetime.fromtimestamp(valkyrie.first_obtained).strftime("%Y-%m-%d")

        # 生成助理列表信息图片
        temp_info_img_path = Path(temp_path) / f"bh3_valkyries_info_{user_id}_{datetime.now().date()}_{uuid.uuid4().hex}.png"
        if await all_valkyrie_info_img(data, temp_info_img_path):
             await bh3_valkyries.send(MessageSegment.file_image(temp_info_img_path))
             await delete_file(temp_info_img_path)
             await bh3_valkyries.finish()
        else:
            logger.error("生成助理列表信息图片失败")
            await bh3_valkyries.finish("生成助理列表信息图片失败，请稍后再试...")
