import json
import uuid
import random
import asyncio
from pathlib import Path
from nonebot import logger
from datetime import datetime
from nonebot.rule import to_me
from nonebot.plugin import on_command
from src.utils.audio import download_audio
from src.configs.path_config import temp_path
from src.clover_image.delete_file import delete_file
from src.configs.Keyboard_config import Keyboard_valkyrie
from src.bh3_valkyries.base import valkyries_info_img, valkyrie_info_img
from src.bh3_valkyries import BH3_User_Assistant, BH3_User_Valkyries
from nonebot.adapters.qq import   MessageSegment,MessageEvent, Message
from src.bh3_valkyries.data_base import BH3_Data_base, get_valkyrie_info, get_valkyries_data_ext

bh3_valkyries = on_command("今日助理",aliases={"我的助理"},rule=to_me(),priority=1,block=True)
@bh3_valkyries.handle()
async def handle_function(message: MessageEvent):
    cmd = message.get_plaintext().split()
    user_id = message.get_user_id()
    # 获取当前时间戳
    current_time = datetime.now().timestamp()
    # 获取当前日期
    today = datetime.now().date()
    
    # 合并用户数据查询
    user_assistant, user_all_valkyries = await asyncio.gather(
        BH3_User_Assistant.get_user_data(user_id),
        BH3_User_Valkyries.get_user_all_valkyries(user_id)
    )
    
    if cmd[0] == "/今日助理":
        # 获取用户数据
        user_assistant = await BH3_User_Assistant.get_user_data(user_id)

        if len(cmd) >= 2:
            if cmd[1] == "<女武神名称/ID>" or len(cmd) > 2:
                await bh3_valkyries.send("指令有误 \nTips: 指令：/今日助理 <角色关键字/ID> \n例：/今日助理 979 来设定今日助理哦~!")
                await bh3_valkyries.finish(MessageSegment.keyboard(Keyboard_valkyrie))
            
            # 设定指定女武神为助理
            user_all_valkyries = await BH3_User_Valkyries.get_user_all_valkyries(user_id)
            if not user_all_valkyries:
                await bh3_valkyries.finish("您还没有任何女武神数据，请先获取今日助理！")
            
            data = await BH3_Data_base.get_valkyries_data()
            keywords = cmd[1]
            ids = await BH3_Data_base.search_valkyrie_to_id(data, keywords)

            if ids is None:
                await bh3_valkyries.finish("未找到指定女武神，请检查关键词/ID是否正确~")
            elif isinstance(ids, list):
                # 搜索结果为多个
                temp_info_img_path = Path(temp_path) / f"bh3_valkyries_info_{user_id}_{today}_{uuid.uuid4().hex}.png"
                result = await valkyries_info_img(
                    await BH3_Data_base.search_user_valkyries_by_id(
                        user_all_valkyries,
                        data, 
                        ids),
                    temp_info_img_path, "搜索结果")
                if result:
                     r_msg = Message([
                         MessageSegment.text("\n搜索到多个女武神，请选择其中一位你拥有的女武神作为今日助理!~" \
                         "\nTips: 指令：/今日助理 <角色关键字/ID>\n例：/今日助理 979 或 /今日助理 粉色妖精小姐"),
                         MessageSegment.file_image(temp_info_img_path)
                     ])
                     await bh3_valkyries.send(r_msg)
                     await delete_file(temp_info_img_path)
                     await bh3_valkyries.finish(MessageSegment.keyboard(Keyboard_valkyrie))
                else:
                    logger.error("生成助理列表信息图片失败")
                    await bh3_valkyries.finish("生成助理列表信息图片失败，请稍后再试...")
            else:
                # 搜索结果为单个 设定每日助理角色且增加好感
                logger.debug(f"用户 {user_id} 指定女武神ID: {ids}")

                last_set_time = datetime.fromtimestamp(user_assistant.last_set_time).date()
                logger.debug(f"用户 {user_id} 上次设置理时间: {last_set_time}, 今天日期: {today}")

                if last_set_time == today:
                    await bh3_valkyries.finish("今天已经设置助理角色了，请明天再来吧...")
                
                ids_valkyries = await BH3_User_Valkyries.get_user_valkyrie_data(user_id, ids)
                # 判断是否已经设置过的助理角色
                if user_assistant.assistant_id != ids:
                    # 设置新的助理
                    await BH3_User_Assistant.create_or_update_field(
                        user_id, 
                        assistant_id = ids, 
                        last_set_time = current_time, 
                        first_set_time = current_time
                    )
                    await BH3_User_Valkyries.update_user_valkyrie_data(
                        user_id, 
                        valkyrie_id = ids, 
                        favorability = ids_valkyries.favorability + 1
                    )
                    logger.debug(f"已设置女武神ID:{ids}，好感度+1")
                    await bh3_valkyries.finish(f"已设置女武神ID:{ids}，好感度+1")
                else:
                    # 多天连续设置
                    await BH3_User_Assistant.create_or_update_field(user_id, last_set_time=current_time)
                    # 好感度按天数递曾 超过5天则 减1
                    # 求天数差
                    first_set_time = datetime.fromtimestamp(user_assistant.first_set_time).date()
                    days_diff = (today - first_set_time).days + 1
                    if days_diff > 5:
                        await BH3_User_Valkyries.update_user_valkyrie_data(
                            user_id,
                            valkyrie_id = ids,
                            favorability = ids_valkyries.favorability - 1 if ids_valkyries.favorability > 0 else 0
                        )
                        logger.debug(f"已设置女武神ID:{ids}\n当前连续设置次数:{days_diff}")
                        await bh3_valkyries.finish(f"已设置女武神ID:{ids}\n当前连续设置次数:{days_diff} 好感度减少 \n女武神也需要休息哦~！")
                    else:
                        await BH3_User_Valkyries.update_user_valkyrie_data(
                            user_id,
                            valkyrie_id = ids,
                            favorability = ids_valkyries.favorability + days_diff
                        )
                        logger.debug(f"用户{user_id} 当前连续设置次数:{days_diff}好感+{days_diff}")
                        await bh3_valkyries.finish(f"已设置女武神ID:{ids}，\n当前连续设置次数:{days_diff}好感+{days_diff}")
        
        # 检查是否已获取过助理且最后获取时间是今天
        if user_assistant:
            last_get_time = datetime.fromtimestamp(user_assistant.last_get_time).date()
            logger.debug(f"用户 {user_id} 上次获取助理时间: {last_get_time}, 今天日期: {today}")

            if last_get_time == today:
                # 展示设定的助理角色信息
                last_set_time = datetime.fromtimestamp(user_assistant.last_set_time).date()
                if last_set_time == today:
                    # 获取用户设定的助理角色信息
                    assistant_id = user_assistant.assistant_id
                    await bh3_valkyries.finish(f"当前助理角色为: {assistant_id}")
                else:
                    await bh3_valkyries.finish(f"今日还未设置助理角色！~")

        # 获取女武神数据
        data = await BH3_Data_base.get_valkyries_data()
        if data is None:
            await bh3_valkyries.finish("获取数据失败，请稍后再试...")

        if data and isinstance(data, list):
            # 随机选择一名女武神
            valkyrie = random.choice(data)
            content_id = valkyrie["content_id"]
            logger.debug(f"获取的女武神ID: {content_id}, 时间戳: {current_time}")
            # 更新用户助理数据
            await BH3_User_Assistant.create_or_update_field(
                user_id=user_id,
                last_get_time=current_time
            )
            # 写入日志
            await BH3_User_Assistant.record_get_valkyrie_log(user_id, content_id, current_time)
            # 获取用户助理信息
            user_valkyrie = await BH3_User_Valkyries.get_user_valkyrie_data(user_id, content_id)
            # 如果用户没有该女武神数据，则创建
            if user_valkyrie is None:
                user_valkyrie = await BH3_User_Valkyries.create_user_valkyrie_data(
                    user_id=user_id,
                    valkyrie_id=content_id,
                    time=current_time
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
            temp_valkyrie = Path(temp_path) / f"bh3_valkyrie_{today}_{content_id}.json"
            if not temp_valkyrie.exists():
                await get_valkyrie_info(content_id, temp_valkyrie)
            with open(temp_valkyrie, "r", encoding="utf-8") as f:
                valkyrie_info = json.load(f)
            # 获取图片/音频
            img_content = valkyrie_info['contents'][0]['text']
            audio_content = valkyrie_info['contents'][2]['text']

            img_link, audio_links = await asyncio.gather(
                BH3_Data_base.get_valkyrie_img(img_content),
                BH3_Data_base.get_audio_links("舰桥互动", audio_content)
            )

            r_data = random.choice(audio_links)
            output_silk_path = await download_audio(r_data['url'])

            ext_str = valkyrie_info['ext']
            ext_data = json.loads(ext_str)
            text_array = json.loads(ext_data['c_18']['filter']['text'])
            summary = valkyrie_info['summary']
            no_property_list = ["角色/","初始阶级/"]
            text_array = [item for item in text_array if not any(prop in item for prop in no_property_list)]
            # 将/替换为：
            text_array = [item.replace("/", "：") for item in text_array]

            img_data = {
                "img_link": img_link,
                "title": valkyrie_info['title'],
                "name": await get_valkyries_data_ext(ext_str, "角色/"),
                "text_array": text_array,
                "summary": summary,
                "text": r_data['text']
            }
            valkyrie_info_img_path = Path(temp_path) / f"bh3_valkyrie_info_{user_id}_{today}_{uuid.uuid4().hex}.png"
            if await valkyrie_info_img(img_data, valkyrie_info_img_path):
                r_msg = Message([
                     MessageSegment.file_image(valkyrie_info_img_path),
                     MessageSegment.text(f"\n今日获得女武神！{summary}")
                ])
                await bh3_valkyries.send(r_msg)

                if output_silk_path is None:
                    logger.error("下载音频失败")
                    await bh3_valkyries.finish("下载音频失败，请稍后再试...")
                await bh3_valkyries.send(MessageSegment.file_audio(Path(output_silk_path)))
                await delete_file(valkyrie_info_img_path)
                await delete_file(output_silk_path)
                await bh3_valkyries.finish()
            else:
                await bh3_valkyries.finish("女武神信息生成失败，请稍后再试...")

        else:
            logger.error("数据格式不正确或为空")
            await bh3_valkyries.finish("错误：获取今日助理数据格式不正确/为空，请稍后再试...")

    elif cmd[0] == "/我的助理":
        if cmd[1] == "<女武神名称/ID>" or len(cmd) > 2:
                await bh3_valkyries.send("指令有误 \nTips: 指令：/我的助理 <角色关键字/ID> \n例：/我的助理 979 来获取助理信息哦~!")
                await bh3_valkyries.finish(MessageSegment.keyboard(Keyboard_valkyrie))
        
        user_all_valkyries = await BH3_User_Valkyries.get_user_all_valkyries(user_id)
        if not user_all_valkyries:
            await bh3_valkyries.finish("您还没有任何女武神数据，请先获取今日助理！")

        data = await BH3_Data_base.get_valkyries_data()
        if data is None:
            await bh3_valkyries.finish("获取数据失败，请稍后再试...")
        
        if len(cmd) == 2:
            keywords = cmd[1]
            ids = await BH3_Data_base.search_valkyrie_to_id(data, keywords)

            if ids is None:
                await bh3_valkyries.finish("未找到指定女武神，请检查关键词/ID是否正确~")
            elif isinstance(ids, list):
                # 搜索结果为多个
                temp_info_img_path = Path(temp_path) / f"bh3_valkyries_info_{user_id}_{today}_{uuid.uuid4().hex}.png"
                if await valkyries_info_img(
                    await BH3_Data_base.search_user_valkyries_by_id(
                        user_all_valkyries,
                        data, 
                        ids),
                    temp_info_img_path,
                    "搜索结果"
                    ):
                     r_msg = Message([
                         MessageSegment.text("\n搜索到多个女武神，请选择其中一位你拥有的女武神查看信息哦!~" \
                         "\nTips: 指令：/我的助理 <角色关键字/ID>\n例：/我的助理 979 或 /我的助理 粉色妖精小姐"),
                         MessageSegment.file_image(temp_info_img_path)
                     ])
                     await bh3_valkyries.send(r_msg)
                     await delete_file(temp_info_img_path)
                     await bh3_valkyries.finish(MessageSegment.keyboard(Keyboard_valkyrie))
                else:
                    logger.error("生成助理列表信息图片失败")
                    await bh3_valkyries.finish("生成助理列表信息图片失败，请稍后再试...")
            else:
                # 搜索结果为单个 查看角色信息
                # 判断是否拥有角色
                for item in user_all_valkyries:
                    if item.valkyrie_id == ids:
                        get_first_obtained = datetime.fromtimestamp(item.first_obtained).strftime("%Y-%m-%d %H:%M:%S")
                        r_msg = Message([
                            MessageSegment.text(f"\n角色ID：{item.valkyrie_id}"
                                                f"\n获取时间：{get_first_obtained}"
                                                f"\n角色好感：{item.favorability}"
                                                f"\n获取次数：{item.count}")
                        ])
                        await bh3_valkyries.finish(r_msg)
                await bh3_valkyries.finish("你还没有获取过这个助理哦!~")
        
        # 生成助理列表信息图片
        temp_info_img_path = Path(temp_path) / f"bh3_valkyries_info_{user_id}_{today}_{uuid.uuid4().hex}.png"
        if await valkyries_info_img(
            await BH3_Data_base.search_user_valkyries_by_id(
                user_all_valkyries, 
                data),
            temp_info_img_path, 
            "女武神图鉴"
            ):
             await bh3_valkyries.send(MessageSegment.file_image(temp_info_img_path))
             await delete_file(temp_info_img_path)
             await bh3_valkyries.finish()
        else:
            logger.error("生成助理列表信息图片失败")
            await bh3_valkyries.finish("生成助理列表信息图片失败，请稍后再试...")
