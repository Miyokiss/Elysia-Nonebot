import uuid
from pathlib import Path
from nonebot.rule import to_me
from nonebot.plugin import on_command
from nonebot.exception import FinishedException
from nonebot.adapters.qq import  MessageSegment,MessageEvent,Message
from nonebot.adapters.qq.exception import ActionFailed
from src.clover_image.get_image import get_image_names, get_xjh_image
from src.clover_image.image_response import ImageServiceError
from src.clover_image.download_image import download_image
from src.clover_image.animetrace import animetrace_search_by_url
from src.clover_image.delete_file import delete_file
from src.configs.path_config import temp_path
from nonebot import logger

__name__ = "plugins_image"


image = on_command("图", rule=to_me(), priority=10,block=True)
@image.handle()
async def handle_image():

    local_image_path = await get_image_names()
    await image.finish(MessageSegment.file_image(Path(local_image_path)))



random_keyword_image = on_command("随机图", rule=to_me(), priority=10, block=True)


async def _finish_random_image_safely(message) -> None:
    try:
        await random_keyword_image.finish(message)
    except FinishedException:
        raise
    except ActionFailed as exc:
        logger.warning(
            f"随机图提示发送失败: code={exc.code}, message={exc.message}"
        )
    except Exception as exc:
        logger.warning(f"随机图提示发送失败: {type(exc).__name__}")


@random_keyword_image.handle()
async def handle_random_image(message: MessageEvent):

    # values = message.get_plaintext().replace("/随机图", "").split(" ")
    # keyword,is_r18,num = "",0,1

    # for value in values:
    #     if value.isdigit():
    #         num = int(value)
    #     elif value.lower() == "r18":
    #         is_r18 = 1
    #     else:
    #         keyword = value
    # urls = await get_anosu_image(keyword=keyword,is_r18=is_r18,num=num)
    # file_paths = []
    # for url in urls:
    #     filename = f"{message.get_user_id()}{random.randint(0, 10000)}.jpg"
    #     image_path = temp_path + filename
    #     file_paths.append(image_path)
    #     await download_image(url,image_path)
    # try:
    #     for file_path in file_paths:
    #         try:
    #             await random_keyword_image.send(MessageSegment.file_image(Path(file_path)))
    #         except Exception as e:
    #             logger.error(f"发送文件 {file_path} 时出错: {e}")
    #             await random_keyword_image.send("某个图被外星人抢走啦，请重试")
    # finally:
    #     # 删除所有临时文件
    #     for file_path in file_paths:
    #         await delete_file(file_path)
    filename = f"{message.get_user_id()}_{uuid.uuid4().hex}.jpg"
    image_path = Path(temp_path) / filename
    try:
        url = await get_xjh_image()
        if not await download_image(
            url, image_path, allowed_hosts={"img.xjh.me"}
        ):
            await random_keyword_image.finish("图片服务暂时不可用，请稍后重试。")
        await random_keyword_image.finish(MessageSegment.file_image(Path(image_path)))
    except FinishedException:
        raise
    except ImageServiceError as exc:
        logger.warning(f"随机图服务响应异常: {exc}")
        await _finish_random_image_safely("图片服务暂时不可用，请稍后重试。")
    except ActionFailed as exc:
        logger.warning(
            f"随机图消息发送失败: code={exc.code}, message={exc.message}"
        )
    except Exception as exc:
        logger.opt(exception=exc).error("随机图处理失败")
        await _finish_random_image_safely("图片处理失败，请稍后重试。")
    finally:
        # 删除所有临时文件
        await delete_file(image_path)


search_image = on_command("搜番", rule=to_me(), priority=10, block=True)
@search_image.handle()
async def handle_search_image(message: MessageEvent):
    if not message.attachments:
        await search_image.finish("没有图片诶？你想让我搜什么呀~♪")
    fig_url = message.attachments[0].url

    logger.debug("接收到url：" + fig_url)
    # API识图
    result = await animetrace_search_by_url(fig_url)
    if result is None:
        await search_image.finish("未找到结果")
    msg = Message([
            #MessageSegment.image(fig_url),   
            MessageSegment.text('\n 搜索结果\n'+result)
        ])
    await search_image.finish(msg)

