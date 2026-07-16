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
from nonebot.adapters.qq import MessageSegment, MessageEvent, Message, Bot
from nonebot.adapters.qq.exception import ActionFailed
from src.clover_image.delete_file import delete_file
from src.utils.Message import delete_msg
from nonebot import logger

__name__ = "plugins | cloud_music"

unikey_cache = {'unikey': None, 'expires': 0}
active_music_sessions = set()

music = on_command("点歌", rule=to_me(), priority=10, block=True)
@music.handle()
async def handle_function(bot: Bot, msg: MessageEvent) -> None:
    session = requests.Session()
    temp_file = None
    sent_msg = None
    choice_matcher = None
    future = None
    active_session = None
    owns_active_session = False
    try:
        active_session = msg.get_session_id()
        if active_session in active_music_sessions:
            await music.finish("当前会话已有点歌请求正在等待选择，请先完成或稍后再试。")
        active_music_sessions.add(active_session)
        owns_active_session = True

        keyword = msg.get_plaintext().removeprefix("/点歌").strip()

        if not keyword:
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
                future = asyncio.get_running_loop().create_future()
                session_id = active_session

                def is_choice_reply(event: MessageEvent) -> bool:
                    text = event.get_plaintext().lstrip()
                    return (
                        event.get_session_id() == session_id
                        and not text.startswith("/")
                    )

                async def capture_choice(event: MessageEvent) -> None:
                    if not future.done():
                        future.set_result(event)

                from nonebot.matcher import Matcher
                choice_matcher = Matcher.new(
                    type_="message",
                    rule=Rule(is_choice_reply),
                    handlers=[capture_choice],
                    priority=0,
                    block=True,
                )
                sent_msg = await music.send(r_msg)
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
                if choice_matcher is not None:
                    choice_matcher.destroy()
                if future is not None and not future.done():
                    future.cancel()
                if sent_msg is not None:
                    asyncio.create_task(
                        delete_msg(bot=bot, message=msg, sent_msg=sent_msg, delay=0)
                    )
        else:
            song_id = song_lists[0]["song_id"]
        logger.debug(f"歌曲ID获取成功: {song_id}")
        img_task = post_netease_music_info_img(song_id, temp_file)
        music_task = post_music_download(song_id, session)
        results = await asyncio.gather(img_task, music_task, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result
    except asyncio.TimeoutError:
        logger.info(f"点歌选择超时 User: {msg.get_user_id()} Keyword: {keyword}")
    except (FinishedException, PausedException):
        return
    except ActionFailed as exc:
        logger.warning(
            f"点歌消息发送失败，不再尝试发送错误提示: "
            f"code={exc.code}, message={exc.message}"
        )
        return
    except Exception as e:
        logger.opt(exception=e).error("处理点歌请求时发生错误")
        try:
            await music.finish("处理点歌请求时发生错误，请稍后重试。")
        except ActionFailed as send_exc:
            logger.warning(
                f"点歌错误提示发送失败: "
                f"code={send_exc.code}, message={send_exc.message}"
            )
    finally:
        if owns_active_session:
            active_music_sessions.discard(active_session)
        session.close()
        if temp_file and os.path.exists(temp_file):
            await delete_file(temp_file)

async def post_netease_music_info_img(song_id, temp_file):
    try:
        music_info = await netease_music_info_img(song_id, temp_file)
        if not music_info:
            logger.warning(f"歌曲信息图片生成失败 Song ID: {song_id}")
            return False
        await music.send(MessageSegment.file_image(Path(temp_file)))
        return True
    except Exception as exc:
        logger.warning(f"歌曲信息图片生成或发送失败，将继续发送音频: {exc}")
        return False
    finally:
        if temp_file and os.path.exists(temp_file):
            await delete_file(temp_file)

async def post_music_download(song_id, session):
    output_silk_path = await music_download(song_id)
    if output_silk_path is None:
        logger.warning("主下载失败，触发降级下载")
        output_silk_path = await netease_music_download(song_id, session=session)
        
    if output_silk_path is None or output_silk_path == -1:
        await music.send("歌曲音频获取失败了Σヽ(ﾟД ﾟ; )ﾉ，可能歌曲为付费歌曲请换首重试吧！")
        return False
    if not isinstance(output_silk_path, (str, os.PathLike)):
        logger.error(f"歌曲下载返回了无效路径: {output_silk_path!r}")
        await music.send("歌曲音频生成失败了，请稍后重试。")
        return False

    output_path = Path(output_silk_path)
    if not output_path.is_file():
        logger.error(f"歌曲音频文件不存在: {output_path}")
        await music.send("歌曲音频生成失败了，请稍后重试。")
        return False

    try:
        await music.send(MessageSegment.file_audio(output_path))
        return True
    finally:
        await delete_file(output_path)
