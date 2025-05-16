# -*- coding: utf-8 -*-
import os
import uuid
import httpx
import qrcode
import base64
import codecs
import json
import requests
from io import BytesIO
from datetime import datetime
from Crypto.Cipher import AES
from graiax import silkcoder
from nonebot import get_driver
from typing import Optional
import src.clover_music.cloud_music.agent as agent
from src.clover_image.delete_file import delete_file
from nonebot import logger

__name__ = "clover_music | cloud_music | cloud_music"


requests.packages.urllib3.disable_warnings()
headers = {'User-Agent': agent.get_user_agents(), 'Referer': 'https://music.163.com/'}

# 在 cloud_music.py 文件顶部添加


# 全局异步客户端
async_client: Optional[httpx.AsyncClient] = None

# 机器人启动时初始化
@get_driver().on_startup
async def init_netease_client():
    global async_client
    async_client = httpx.AsyncClient(
        verify=False,
        timeout=30.0,
        limits=httpx.Limits(max_connections=100)
    )

# 机器人关闭时清理
@get_driver().on_shutdown
async def close_netease_client():
    if async_client:
        await async_client.aclose()

# 解密params和encSecKey值
def keys(key):
    while len(key) % 16 != 0:
        key += '\0'
    return str.encode(key)

#登录加密
def AES_aes(t, key, iv):
    def p(s): return s + (AES.block_size - len(s) %AES.block_size) * chr(AES.block_size - len(s) % AES.block_size)
    encrypt = str(base64.encodebytes(AES.new( keys(key), AES.MODE_CBC,keys(iv)).encrypt(str.encode(p(t)))),encoding='utf-8')
    return encrypt

def RSA_rsa(i, e, f):
    return format(int(codecs.encode(
        i[::-1].encode('utf-8'), 'hex_codec'), 16) ** int(e, 16) % int(f, 16), 'x').zfill(256)

# 获取的参数
key = agent.S()  # i6c的值
d = str({'key': key, 'type': "1", 'csrf_token': ""})
e = "010001"  # (["流泪", "强"])的值
f = "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7"
g = "0CoJUm6Qyw8W8jud"  # (["爱心", "女孩", "惊恐", "大笑"])的值
iv = "0102030405060708"  # 偏移量
i = agent.a()  # 随机生成长度为16的字符串


def login_params(u):
    if u is None:
        return AES_aes(AES_aes(d, g, iv), i, iv)  # g 和 i 都是key代替
    else:
        return AES_aes(AES_aes(u,g,iv),i,iv)  # g 和 i 都是key代替

def login_encSecKey():
    return RSA_rsa(i, e, f)

def get_music(id):
    return agent.get_params(id)




"""
使用二维码登录网易云音乐，需要先获取二维码的key，然后使用该key生成二维码，扫描二维码登录，最后通过登录接口 返回cookie 保存起来
"""
save_path = os.getcwd()+'/src/clover_music/netease_music'
os.makedirs(save_path, exist_ok=True)
qrcode_path = os.getcwd()+'/src/clover_music/'


# 判断cookie是否有效
async def netease_cloud_music_is_login(session):
    """
    验证登录状态
    Args:
        session:

    Returns:

    """
    try:
        session.cookies.load(ignore_discard=True)
    except Exception:
        pass
    csrf_token = session.cookies.get('__csrf')
    if csrf_token is None:
        return session, False,None
    else:
        try:
            loginurl = session.post(f'https://music.163.com/weapi/w/nuser/account/get?csrf_token={csrf_token}',data={'params': login_params(None), 'encSecKey': login_encSecKey()}, headers=headers).json()
            if loginurl['account'] is not None:
                return session, True,loginurl['account']['id']
            else:
                return session, False,None
        except BaseException:
            return session, False,None

# 获取二维码的key
async def get_qr_key(session):
    """
    获取unikey
    Args:
        session:

    Returns:

    """
    url = f"https://music.163.com/weapi/login/qrcode/unikey"
    data = {"params": login_params(None),"encSecKey": login_encSecKey()}
    response = session.post(url, headers=headers,params=data)
    result = json.loads(response.text)
    if result.get("code") == 200:
        unikey = result.get("unikey")
        return unikey
    else:
        return None

# 生成二维码
async def create_qr_code(unikey):
    """
    二维码生成
    Args:
        unikey:

    Returns:

    """
    qr = qrcode.QRCode(version=1,error_correction=qrcode.constants.ERROR_CORRECT_L,box_size=10,border=4)
    qr.add_data(f"https://music.163.com/login?codekey={unikey}")
    #保存二维码
    img_path = os.path.join(qrcode_path, 'qrcode.png')
    qr.make_image().save(img_path)
    return img_path

# 检查二维码状态是否被扫描
async def check_qr_code(unikey,session):
    token_url = f"https://music.163.com/weapi/login/qrcode/client/login?csrf_token="
    u = str({'key': unikey, 'type': "1", 'csrf_token': ""})
    qrcode_data = session.post( token_url,data={'params': login_params(u),'encSecKey': login_encSecKey()},headers=headers).json()
    return qrcode_data.get('code')

async def netease_music_search(keyword,session):
    """
    歌曲搜索
    Args:
        keyword: 搜索关键字
        session: requests会话对象
    Returns:
        song_lists: 搜索结果列表

    """
    url = "http://music.163.com/api/search/get"
    params = {
        "s": keyword,
        "type": 1,  # 1 表示搜索歌曲，2 表示搜索专辑，3 表示搜索歌手等
        "limit": 10,  # 限制搜索结果的数量
        "offset": 0,  # 搜索结果的偏移量，可用于分页
        "sub": "false",
    }
    response = session.get(url, headers=headers, params=params)
    data = response.json()
    if "result" in data and "songs" in data["result"]:
        songs = data["result"]["songs"]
        song_lists = [
            {
                "index": idx,
                "song_id": song["id"],
                "song_name": song['name'],
                "song_artists_name": song['artists'][0]['name'],
            } for idx, song in enumerate(songs, start=1)
            ]
        logger.debug(f"搜索结果：{song_lists}")
        return song_lists
    return None
async def netease_music_info(id: str):
    """
    获取歌曲信息
    Args:
        id: 歌曲id
    Returns: 歌曲信息
    returns: None 如果没有找到或其他返回None
    """
    headers = {
    'content-type':'application/x-www-form-urlencoded'
    }
    result = get_music(id)
    data = {'params': result['encText'], 'encSecKey': result['encSecKey']}

    response = requests.request("POST", "https://music.163.com/weapi/song/detail", headers=headers,data=data)
    if response.status_code == 200:
        response = response.json()
        if response['songs']:
            return response['songs']
    return None

#仅限于免费歌曲
# def netease_music_download(song_id,song_name,singer,session):
#     if not os.path.exists(save_path):
#         os.makedirs(save_path)
#     download_url = f"http://music.163.com/song/media/outer/url?br=999000&id={song_id}.mp3"
#     response = session.get(download_url, headers=headers)
#     if response.status_code == 200:
#         logger.info(f"正在下载 {song_name} - {singer} 歌曲...")
#         file_path = os.path.join(save_path, f"{song_name}-{singer}.mp3")
#         file_name = os.path.basename(f"{song_name}-{singer}.mp3")
#         with open(file_path, "wb") as f:
#             f.write(response.content)
#         output_silk_path = os.path.join(save_path, os.path.splitext(file_name)[0] + ".silk")
#         # 使用 graiax-silkcoder 进行转换
#         silkcoder.encode(file_path, output_silk_path)
#         return output_silk_path
#     else:
#         return None

#所有歌曲都可以下载
async def netease_music_download(song_id, session):
    """
    歌曲下载
    Args:
        song_id:
        song_name:
        singer:
        session:

    Returns:

    """
    if not os.path.exists(save_path):
        os.makedirs(save_path)

    # 获取加密后的歌曲id信息
    result = get_music(song_id)
    data = {'params': result['encText'], 'encSecKey': result['encSecKey']}
    download_url = 'https://music.163.com/weapi/song/enhance/player/url/v1?br=999000'
    response_data = session.post(download_url, headers=headers, data=data).json()
    url = response_data['data'][0]['url']
    if url is None:
        return -1
    # 下载歌曲
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            file_path = os.path.join(save_path, f"{song_id}.wav")
            file_name = os.path.basename(f"{song_id}.wav")

            with open(file_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)

            output_silk_path = os.path.join(save_path, os.path.splitext(file_name)[0] + ".silk")
            # 使用 graiax-silkcoder 进行转换
            silkcoder.encode(file_path, output_silk_path, rate=32000, tencent=True, ios_adaptive=True)
            # 删除临时文件
            await delete_file(file_path)
            return output_silk_path
        else:
            return None
    except requests.RequestException as e:
        return None


async def music_search(keyword):
    """
    第三方歌曲搜索
    Args:
        keyword:
    Returns:

    """
    url = "https://api.kxzjoker.cn/api/163_search"
    params = {
        "name": keyword,
        "limit": 10,
    }

    response = await async_client.get(url,params=params)
    result = response.json()
    song_id = result["data"][0]["id"]
    song_name = result["data"][0]["name"]
    singer = result["data"][0]["artists"][0]["name"]
    return song_id,song_name,singer

async def music_download(song_id):
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    try:
        headers = {
            "Referer": "https://kxzjoker.cn/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Origin": "https://kxzjoker.cn"
        }

        # 构造请求URL
        url = f'https://api.kxzjoker.cn/api/163_music?ids={song_id}&level=lossless&type=down'

        # 异步流式下载
        async with async_client.stream("GET",url,headers=headers,follow_redirects=True) as response:
            response.raise_for_status()

            file_path = os.path.join(save_path, f"{datetime.now().date()}-{uuid.uuid4().hex}-{song_id}.wav")
            file_name = os.path.basename(f"{datetime.now().date()}-{uuid.uuid4().hex}-{song_id}.wav")

            with open(file_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)

            output_silk_path = os.path.join(save_path, os.path.splitext(file_name)[0] + ".silk")
            # 使用 graiax-silkcoder 进行转换
            silkcoder.encode(file_path, output_silk_path, rate=32000, tencent=True, ios_adaptive=True)
            # 删除临时文件
            await delete_file(file_path)
            return output_silk_path

    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP错误 {e.response.status_code}")
    except Exception as e:
        print(f"❌ 下载失败：{str(e)}")
    return None
