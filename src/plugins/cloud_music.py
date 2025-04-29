import asyncio
import pickle
import os
import time
import uuid
import requests
from pathlib import Path
from datetime import datetime
from typing import Tuple, Optional
from src.clover_music.cloud_music.data_base import netease_music_search_info_img,netease_music_info_img
from src.configs.path_config import temp_path
from nonebot import on_command
from nonebot.rule import to_me
from nonebot.exception import FinishedException
from nonebot.adapters.qq import MessageSegment,MessageEvent
from src.clover_music.cloud_music.cloud_music import *
from src.clover_image.delete_file import delete_file
from nonebot import logger

__name__ = "plugins | cloud_music"

unikey_cache = {'unikey': None, 'expires': 0}

music = on_command("点歌", rule=to_me(), priority=10, block=False)

async def login(session: requests.Session) -> Tuple[requests.Session, bool, Optional[str]]:
    """处理登录逻辑"""
    cookie_file = 'cloud_music_cookies.cookie'
    if not os.path.exists(cookie_file):
        with open(cookie_file, 'wb') as f:
            pickle.dump(session.cookies, f)
    session.cookies = pickle.load(open(cookie_file, 'rb'))
    return await netease_cloud_music_is_login(session)

async def handle_qr_login(session: requests.Session) -> None:
    """处理二维码登录逻辑"""
    if unikey_cache['unikey'] and time.time() < unikey_cache['expires']:
        unikey = unikey_cache['unikey']
    else:
        unikey = await get_qr_key(session)
        unikey_cache.update({
            'unikey': unikey,
            'expires': time.time() + 300
        })
        qr_path = await create_qr_code(unikey)
        """是否要发送到QQ上面登录 """
        # await clover_music.send(MessageSegment.file_image(Path(qr_path)))
        """是否要发送到QQ上面登录 """
        for _ in range(60):
            code = await check_qr_code(unikey, session)
            if code in (803,): break
            if code not in (801, 802):
                logger.error('二维码失效' if code == 800 else f'异常状态码：{code}')
                break
            await asyncio.sleep(5)
    with open('cloud_music_cookies.cookie', 'wb') as f:
        pickle.dump(session.cookies, f)

@music.handle()
async def handle_function(msg: MessageEvent) -> None:
    try:
        values = msg.get_plaintext().removeprefix("/点歌").strip().split()
        session = requests.session()
        # session, status, user_id = await login(session)
        
        # if not status:
        #     await music.send("登录失效，请联系管理员进行登录")
        #     await handle_qr_login(session)

        if not values or not all(values):
            await music.finish("\n请输入“/点歌+歌曲名”喔🎶")

        keyword = values[0]
        temp_file = os.path.join(temp_path, f"{datetime.now().date()}_{keyword}_{uuid.uuid4().hex}.png")

        if len(values) == 1:
            r_search_info_img = await netease_music_search_info_img(keyword, session, temp_file)
            if r_search_info_img is None:
                await music.finish("\n没有找到歌曲，或检索到的歌曲为付费/无版权喔qwq\n这绝对不是我的错，绝对不是！")
            await music.send(MessageSegment.file_image(Path(temp_file)))
        elif len(values) == 2:
            idx = values[1]
            if not idx.isdigit() or int(idx) < 1 or int(idx) > 10:
                await music.finish("\n序号必须是数字且在1-10范围内喔qwq")
            music_info = await netease_music_info_img(keyword, session, idx, temp_file)
            if music_info is None:
                await music.finish("\n没有找到歌曲，或检索到的歌曲为付费/无版权喔qwq\n这绝对不是我的错，绝对不是！")
            song_id = music_info['song_id']
            song_name = music_info['song_name']
            singer = music_info['song_artists']
            await music.send(MessageSegment.file_image(Path(temp_file)))
            output_silk_path = await netease_music_download(song_id, song_name, singer, session)
            if output_silk_path == -1:
                await music.send("歌曲音频获取失败：检索到的歌曲为付费（在努力恢复，待后续更新）")
            elif output_silk_path is None:
                await music.send("歌曲音频获取失败了Σヽ(ﾟД ﾟ; )ﾉ，请重试。")
            else:
                await music.send(MessageSegment.file_audio(Path(output_silk_path)))
                await delete_file(output_silk_path)
        else:
            await music.finish("\n输入有误，请检查格式或歌曲名称里是否有空格喔qwq")

        await delete_file(temp_file)
        await music.finish()
    except Exception as e:
        if isinstance(e, FinishedException):
            return
        logger.error(f"处理点歌请求时发生错误: {e}")
        r_msg = "未知错误，请稍后再试。"
        if hasattr(e, 'message'):
            r_msg = e.message
        await music.finish(f"处理点歌请求时发生错误：{r_msg}。这绝对不是我的错，绝对不是！")