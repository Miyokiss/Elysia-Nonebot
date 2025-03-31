import random
from pathlib import Path
from nonebot.rule import to_me
from nonebot.plugin import on_command
from nonebot.adapters.qq import  MessageSegment,MessageEvent,Message
from src.clover_image.get_image import get_image_names,get_anosu_image
from src.clover_image.download_image import download_image
from src.clover_image.animetrace import animetrace_search_by_url
from src.clover_image.delete_file import delete_file
from src.configs.path_config import temp_path
from nonebot import logger

__name__ = "plugins_image"


image = on_command("图", rule=to_me(), priority=10,block=False)
@image.handle()
async def handle_function():

    local_image_path = await get_image_names()
    await image.finish(MessageSegment.file_image(Path(local_image_path)))



random_keyword_image = on_command("随机图", rule=to_me(), priority=10, block=False)
@random_keyword_image.handle()
async def handle_function(message: MessageEvent):

    values = message.get_plaintext().replace("/随机图", "").split(" ")
    keyword,is_r18,num = "",0,1

    for value in values:
        if value.isdigit():
            num = int(value)
        elif value.lower() == "r18":
            is_r18 = 1
        else:
            keyword = value
    urls = await get_anosu_image(keyword=keyword,is_r18=is_r18,num=num)
    file_paths = []
    for url in urls:
        filename = f"{message.get_user_id()}{random.randint(0, 10000)}.jpg"
        image_path = temp_path + filename
        file_paths.append(image_path)
        await download_image(url,image_path)

    try:
        for file_path in file_paths:
            try:
                await random_keyword_image.send(MessageSegment.file_image(Path(file_path)))
            except Exception as e:
                logger.error(f"发送文件 {file_path} 时出错: {e}")
                await random_keyword_image.send("某个图被外星人抢走啦，请重试")
    finally:
        # 删除所有临时文件
        for file_path in file_paths:
            await delete_file(file_path)



search_image = on_command("搜番", rule=to_me(), priority=10, block=False)
@search_image.handle()
async def handle_function(message: MessageEvent):
    if not message.attachments:
        msg = Message([
            MessageSegment.image(),   
            MessageSegment.text("没有图片诶？你想让我搜什么呀~♪")
        ])
        await search_image.send(msg)
    fig_url = message.attachments[0].url

    logger.debug(f"接收到url："+fig_url)
    # API识图
    result = await animetrace_search_by_url(fig_url)
    if result is None:
        msg = Message([
            #MessageSegment.image(fig_url),
            MessageSegment.text("未找到结果")
        ])
        await search_image.send(msg)
    msg = Message([
            #MessageSegment.image(fig_url),   
            MessageSegment.text('\n 搜索结果\n'+result)
        ])
    await search_image.send(msg)

