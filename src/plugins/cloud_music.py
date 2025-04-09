import asyncio
import pickle
import time
from pathlib import Path
from nonebot import on_command
from nonebot.rule import to_me
from nonebot.exception import FinishedException
from nonebot.adapters.qq import MessageSegment,MessageEvent
from src.clover_music.cloud_music.cloud_music import *
from src.clover_image.delete_file import delete_file
from nonebot import logger

unikey_cache = {'unikey': None, 'expires': 0}

music = on_command("点歌", rule=to_me(), priority=10, block=False)
async def login(session):
    """处理登录逻辑"""
    if not os.path.exists('cloud_music_cookies.cookie'):
        with open('cloud_music_cookies.cookie', 'wb') as f:
            pickle.dump(session.cookies, f)
    session.cookies = pickle.load(open('cloud_music_cookies.cookie', 'rb'))
    session, status, user_id = await netease_cloud_music_is_login(session)
    return session, status, user_id

async def handle_qr_login(session):
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
async def handle_function(msg: MessageEvent):
    try:
        keyword = msg.get_plaintext().replace("/点歌", "").strip(" ")
        if keyword == "":
            await music.finish("\n请输入“/点歌+歌曲名”喔🎶")

        session = requests.session()
        session, status, user_id = await login(session)
        if not status:
            await music.send("登录失效，请联系管理员进行登录")
            await handle_qr_login(session)

        song_id, song_name, singer, song_url = await netease_music_search(keyword, session)
        song_name = str(song_name).replace(".", "·").replace("/", "、")
        if song_id is None:
            await music.finish("\n没有找到歌曲，或检索到的歌曲均为付费喔qwq\n这绝对不是我的错，绝对不是！")

        await music.send(MessageSegment.text(f" 来源：网易云音乐\n歌曲：{song_name} - {singer}\n请稍等喔🎵"))
        output_silk_path = await netease_music_download(song_id, song_name, singer, session)

        if output_silk_path == -1:
            await music.send("歌曲音频获取失败：登录信息失效。")
        elif output_silk_path is None:
            await music.send("歌曲音频获取失败了Σヽ(ﾟД ﾟ; )ﾉ，请重试。")
        else:
            await music.send(MessageSegment.file_audio(Path(output_silk_path)))
        await delete_file(output_silk_path)
        await music.finish()

    except Exception as e:
        if isinstance(e, FinishedException):
            logger.error(f"处理点歌请求时发生错误: {e}")
            await music.finish("处理点歌请求时发生错误，请稍后重试。这绝对不是我的错，绝对不是！")