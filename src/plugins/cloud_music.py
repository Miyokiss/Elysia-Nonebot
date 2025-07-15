import os
import uuid
import asyncio
import requests
from pathlib import Path
from datetime import datetime
from src.clover_music.cloud_music.data_base import netease_music_search_info_img,netease_music_info_img
from src.clover_music.cloud_music.cloud_music import music_download, netease_music_download, netease_music_search
from src.configs.path_config import temp_path
from nonebot import on_command
from nonebot.rule import Rule, to_me
from nonebot.exception import FinishedException, PausedException
from nonebot.adapters.qq import MessageSegment, MessageEvent, Message
from src.clover_image.delete_file import delete_file
from nonebot import logger

__name__ = "plugins | cloud_music"

unikey_cache = {'unikey': None, 'expires': 0}

music = on_command("点歌", rule=to_me(), priority=10, block=False)
@music.handle()
async def handle_function(msg: MessageEvent) -> None:
    try:
        keyword = msg.get_plaintext().removeprefix("/点歌").strip()
        session = requests.session()

        if not keyword or not all(keyword):
            await music.finish("\n请输入“/点歌+歌曲名”喔")

        temp_file = os.path.join(temp_path, f"{datetime.now().date()}_{uuid.uuid4().hex}.png")
        logger.debug(f"开始搜索歌曲: {keyword}")
        song_lists = await netease_music_search(keyword, session)
        if song_lists is None:
            await music.finish("\n没有找到歌曲，或检索到的歌曲为付费或者无版权喔qwq")
        if len(song_lists) > 1:
            r_search_info_img = await netease_music_search_info_img(song_lists, temp_file)
            if r_search_info_img is not True:
                logger.error(f"歌曲信息图片生成失败 User: {msg.get_user_id()} Keyword: {keyword}")
                await music.finish("\n歌曲信息图片生成失败")

            # 发送搜索结果并等待用户选择
            r_msg = Message([
                MessageSegment.file_image(Path(temp_file)),
                MessageSegment.text("\n请直接回复要听的歌曲序号哦！(1-10)")
            ])
            try:
                await music.send(r_msg)
                # 创建异步等待
                future = asyncio.get_event_loop().create_future()

                # 定义临时 matcher 处理用户回复
                from nonebot.matcher import Matcher
                choice_matcher = Matcher.new(
                    rule=Rule(lambda event: event.get_user_id() == msg.get_user_id()),
                    handlers=[lambda bot, event: future.set_result(event)],
                    priority=0,
                    block=True
                )
                # 等待用户回复（超时30秒）
                reply_event = await asyncio.wait_for(future, timeout=30)
                choice = reply_event.get_plaintext().strip()

                if not choice.isdigit() or int(choice) < 1 or int(choice) > len(song_lists):
                    await music.finish(f"请输入1-{len(song_lists)}之间的数字")
                idx = choice
                song_id = None
                for i in range(len(song_lists)):
                    s_list = song_lists[i]
                    if isinstance(s_list, dict) and 'index' in s_list:
                        logger.debug(f"s_list['index']: {s_list['index']}, index: {idx}")
                        if str(s_list['index']) == str(idx):
                            song_id = s_list["song_id"]
                            break
                if song_id is None:
                    await music.finish("\n未获取到歌曲信息可能是序号有误！")
            finally:
                choice_matcher.destroy()
        else:
            song_id = song_lists[0]["song_id"]
        logger.debug(f"歌曲ID获取成功: {song_id}")
        img_task = post_netease_music_info_img(song_id, temp_file)
        music_task = post_music_download(song_id, session)
        await asyncio.gather(img_task, music_task)
    except asyncio.TimeoutError:
        logger.info(f"点歌选择超时 User: {msg.get_user_id()} Keyword: {keyword}")
    except Exception as e:
        if isinstance(e, (FinishedException, PausedException)):
            return
        logger.error(f"处理点歌请求时发生错误: {e}")
        r_msg = "未知错误，请稍后再试"
        if hasattr(e, 'message'):
            r_msg = e.message
        await music.finish(f"处理点歌请求时发生错误：{r_msg}。这绝对不是我的错，绝对不是！")

async def post_netease_music_info_img(song_id, temp_file):
    music_info = await netease_music_info_img(song_id, temp_file)
    if not music_info:
        logger.error(f"歌曲信息图片生成失败 Song ID: {song_id}")
        await music.finish("\n图片生成失败或未获取到歌曲信息")
        return False
    await music.send(MessageSegment.file_image(Path(temp_file)))
    await delete_file(temp_file)

async def post_music_download(song_id, session):
    output_silk_path = await music_download(song_id)
    if output_silk_path is None:
        logger.warning(f"主下载失败，触发降级下载")
        output_silk_path = await netease_music_download(song_id, session=session)
        
    if output_silk_path is None or output_silk_path == -1:
        await music.send("歌曲音频获取失败了Σヽ(ﾟД ﾟ; )ﾉ，可能歌曲为付费歌曲请换首重试吧！")
    await music.send(MessageSegment.file_audio(Path(output_silk_path)))
    await delete_file(output_silk_path)