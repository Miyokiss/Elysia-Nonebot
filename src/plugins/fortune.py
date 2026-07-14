import os
import time
import asyncio
from os import getcwd
from pathlib import Path
from nonebot import logger
from nonebot.rule import to_me
from nonebot.plugin import on_command
from nonebot.utils import logger_wrapper
from nonebot.exception import FinishedException
from nonebot_plugin_htmlrender import template_to_pic
from nonebot.adapters.qq import Message, MessageEvent, MessageSegment, Bot
from nonebot.adapters.qq.exception import ActionFailed
from src.clover_sqlite.models.fortune import QrFortune
from src.clover_sqlite.models.tarot import TarotExtractLog
from src.clover_sqlite.tarot_resources import resolve_tarot_image_path
from src.clover_music.cloud_music.data_base import save_img
from src.configs.Keyboard_config import Keyboard_fortune
from src.clover_image.delete_file import delete_file
from src.configs.path_config import temp_path
from src.clover_providers.cloud_file_api.rustfs import rustfs_api
from nonebot.adapters.qq.message import MessageMarkdown
from src.utils.Message import delete_msg

logger_wrapper("fortune")

fortune_by_sqlite = on_command("今日运势", rule=to_me(), priority=10)
@fortune_by_sqlite.handle()
async def get_today_fortune(bot: Bot, message: MessageEvent):
    try:
        user_id = message.get_user_id()
        result = await QrFortune.get_fortune(user_id)
        temp_file_name = f"{user_id}_{time.time()}.png"
        if result is None:
            logger.error("今日运势获取失败")
            await fortune_by_sqlite.finish("今日运势获取失败")
        temp_file = os.path.join(temp_path, temp_file_name)
        data = {
             "fortune_summary": result.fortune_summary,
             "lucky_star": result.lucky_star,
             "sign_text": result.sign_text,
             "un_sign_text": result.un_sign_text
        }
        logger.debug(f"data：{data}")
        image_bytes = await template_to_pic(
            template_path=getcwd() + "/src/clover_html/fortune",
            template_name="main.html",
            templates={"data": data},
            pages={
                "viewport": {"width": 540, "height": 1},
                "base_url": f"file://{getcwd()}",
            },
            wait=2,
        )
        await save_img(image_bytes,temp_file)
        try:
            sent_msg = await send_fortune_image(
                matcher=fortune_by_sqlite,
                image_path=Path(temp_file),
                object_key=temp_file_name,
                content=f"<@{user_id}>",
                width=1080,
                height=1920,
            )
            asyncio.create_task(delete_msg(bot, message, sent_msg))
            await fortune_by_sqlite.finish()
        finally:
            await delete_file(temp_file)
    except Exception as e:
        if isinstance(e, FinishedException):
            return
        logger.error(f"获取运势失败：{e}")
        await fortune_by_sqlite.finish("获取运势失败")


tarot = on_command("今日塔罗", rule=to_me(), priority=10)
@tarot.handle()
async def get_tarot(bot: Bot, message: MessageEvent):
    #extract_type : 1大阿尔克纳牌 2小阿尔克纳牌 3 混合牌组 4三角牌阵 5六芒星牌阵 6凯尔特十字牌阵 7恋人牌阵
    value = message.get_plaintext().strip().split(" ")
    if len(value) < 2 or len(value) > 2 or value[1] == "" or value[1] not in ["1","2","3","4","5"]:
        await tarot.finish("请输入正确的指令格式：/今日塔罗 + 数字(1-5) \n"
                           "1   大阿尔克纳牌 \n"
                           "2   小阿尔克纳牌 \n"
                           "3   混合牌组 \n"
                           "4   三角牌阵 \n"
                           "5   六芒星牌阵 "
                           )
    result = await TarotExtractLog.tarotChoice(int(value[1]),message.get_user_id())
    if result.extract_type in [1,2,3]:
        card_image = Path(resolve_tarot_image_path(result.image))
        if not card_image.is_file():
            logger.error(f"塔罗牌静态资源缺失: {card_image}")
            await tarot.finish("塔罗牌图片资源缺失，请联系管理员重新部署资源文件。")
        content = ("\n" + result.orientation + "\n" +
                   result.name + "\n" +
                   "含义：" + result.meaning)

        msg = Message([
            MessageSegment.file_image(card_image),
            MessageSegment.text(content),
        ])
        try:
            sent_msg = await tarot.send(msg)
            asyncio.create_task(delete_msg(bot, message, sent_msg))
            await tarot.finish()
        except Exception as e:
            if isinstance(e, FinishedException):
                return
            logger.error(f"获取塔罗牌失败：{e}")
            await tarot.finish("您的塔罗牌被未来人抢走啦，请重试。这绝对不是咱的错，绝对不是！")
    else:
        img_path = Path(result.image)
        if not img_path.is_file():
            logger.error(f"塔罗牌阵图片不存在: {img_path}")
            await tarot.finish("塔罗牌阵生成失败，请稍后重试。")
        sent_msg = await send_fortune_image(
            matcher=tarot,
            image_path=img_path,
            object_key=img_path.name,
            content=f"<@{message.get_user_id()}>",
            width=180,
            height=230,
        )
        asyncio.create_task(delete_msg(bot, message, sent_msg))
        await tarot.finish()


async def send_fortune_image(
    matcher, image_path: Path, object_key: str, content: str, width: int, height: int
):
    uploaded = await rustfs_api.upload_file(
        local_path=str(image_path), object_key=object_key
    )
    if uploaded:
        image_url = await rustfs_api.get_download_url(object_key=object_key)
        if image_url:
            params = [
                {"key": "width", "values": [str(width)]},
                {"key": "height", "values": [str(height)]},
                {"key": "url", "values": [image_url]},
                {"key": "content", "values": [content]},
            ]
            markdown_image = MessageMarkdown(
                custom_template_id="102735560_1771313464", params=params
            )
            try:
                return await matcher.send(Message([
                    MessageSegment.markdown(markdown_image),
                    MessageSegment.keyboard(Keyboard_fortune),
                ]))
            except ActionFailed as exc:
                logger.warning(
                    f"运势 Markdown 发送失败，降级为普通图片: "
                    f"code={exc.code}, message={exc.message}"
                )

    return await matcher.send(MessageSegment.file_image(image_path))

