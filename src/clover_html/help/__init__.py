import os
import json
import time
import hashlib
import requests
from os import getcwd
from playwright.async_api import async_playwright
from nonebot_plugin_htmlrender import template_to_pic
from src.clover_music.cloud_music.data_base import save_img
from src.configs.api_config import afdian_user_id, afdian_token
from nonebot import logger

async def get_afdian_data():
    """
    获取爱发电数据
    """

    ts = int(time.time())

    params = {
        "page": 1
    }
    params_json = json.dumps(params, separators=(',', ':'))
    # 计算签名
    kv_string = f"params{params_json}ts{ts}user_id{afdian_user_id}"
    sign = hashlib.md5((afdian_token + kv_string).encode('utf-8')).hexdigest()

    request_data = {
        "user_id": afdian_user_id,
        "params": params_json,
        "ts": ts,
        "sign": sign
    }

    url = "https://afdian.com/api/open/query-sponsor"
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.post(
        url, 
        data=json.dumps(request_data, separators=(',', ':')),
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        if data.get('ec') == 200:
            sponsors = data['data']['list']
            total_count = data['data']['total_count']
            # 获最新3个赞助者
            top_sponsors = sponsors[:3] if len(sponsors) >= 3 else sponsors
            top_list = []
            for sponsor in top_sponsors:
                user_info = sponsor['user']
                r_user = {
                    'name': user_info['name'],
                    'avatar': user_info['avatar'],
                }
                top_list.append(r_user)
            r_info = {
                'total_count': total_count,
                'top_list': top_list
            }
            logger.debug(f'查询赞助者成功: {r_info}')
            return r_info
        else:
            logger.error(f'查询赞助者失败: {data.get("em")}')
    else:
        logger.error(f'请求失败，状态码: {response.status_code}')


async def help_info_img(data, temp_file: str):
        if os.path.exists(temp_file):
            with open(temp_file,"rb") as image_file:
                return image_file.read()
        async with async_playwright() as p:
            browser = await p.chromium.launch()
        afdian_data = await get_afdian_data()
        image_bytes = await template_to_pic(
            template_path=getcwd() + "/src/clover_html/help",
            template_name="main.html",
            templates={"data": data,
                       "afdian_data": afdian_data
                       },
            pages={
                "viewport": {"width": 500, "height": 1},
                "base_url": f"file://{getcwd()}",
            },
            wait=2,
        )
        await save_img(image_bytes,temp_file)
        await browser.close()
        return True