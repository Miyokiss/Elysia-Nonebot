import re
import json
import requests
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
from nonebot.log import logger
from src.utils.tts import MarkdownCleaner
from src.configs.path_config import temp_path

__name__ = "bh3_valkyries | data_base"

async def get_all_valkyrie_json(temp_file):
    """
    获取所有女武神数据
    """
    headers = {
     'pragma':'no-cache',
     'cache-control':'no-cache',
     'sec-ch-ua-platform':'"Windows"',
     'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0',
     'accept':'application/json, text/plain, */*',
     'sec-ch-ua':'"Microsoft Edge";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
     'sec-ch-ua-mobile':'?0',
     'origin':'https://baike.mihoyo.com',
     'sec-fetch-site':'same-site',
     'sec-fetch-mode':'cors',
     'sec-fetch-dest':'empty',
     'referer':'https://baike.mihoyo.com/',
     'accept-encoding':'gzip, deflate, br, zstd',
     'accept-language':'zh-CN,zh;q=0.9,en;q=0.8,mt;q=0.7,zh-TW;q=0.6,zh-HK;q=0.5,en-US;q=0.4',
     'priority':'u=1, i'}
    payload=None
    response = requests.request("GET", "https://act-api-takumi-static.mihoyo.com/common/blackboard/bh3_wiki/v1/home/content/list?app_sn=bh3_wiki&channel_id=18", headers=headers, data=payload)
    if response.status_code == 200:
        data = response.json()
        if 'data' in data and 'list' in data['data']:
            valkyries = data['data']['list'][0]['list']
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(valkyries, f, ensure_ascii=False, indent=4)
            return True
        else:
            raise ValueError("数据格式不正确，未找到 'data' 或 'list' 键")
    else:
        raise Exception(f"请求失败，状态码: {response.status_code}, 原因: {response.text}")

async def get_valkyrie_info(content_id, temp_file):
    """
    获取单个女武神数据
    """
    headers = {
     'pragma':'no-cache',
     'cache-control':'no-cache',
     'sec-ch-ua-platform':'"Windows"',
     'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0',
     'accept':'application/json, text/plain, */*',
     'sec-ch-ua':'"Microsoft Edge";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
     'sec-ch-ua-mobile':'?0',
     'origin':'https://baike.mihoyo.com',
     'sec-fetch-site':'same-site',
     'sec-fetch-mode':'cors',
     'sec-fetch-dest':'empty',
     'referer':'https://baike.mihoyo.com/',
     'accept-encoding':'gzip, deflate, br, zstd',
     'accept-language':'zh-CN,zh;q=0.9,en;q=0.8,mt;q=0.7,zh-TW;q=0.6,zh-HK;q=0.5,en-US;q=0.4',
     'priority':'u=1, i'}
    payload=None

    response = requests.request("GET", f"https://act-api-takumi-static.mihoyo.com/common/blackboard/bh3_wiki/v1/content/info?app_sn=bh3_wiki&content_id={content_id}", headers=headers, data=payload)
    if response.status_code == 200:
        data = response.json()
        if 'data' in data and 'content' in data['data']:
            valkyrie_info = data['data']['content']
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(valkyrie_info, f, ensure_ascii=False, indent=4)
            return True
        else:
            raise ValueError("数据格式不正确，未找到 'data' 或 'content' 键")
    else:
        raise Exception(f"请求失败，状态码: {response.status_code}, 原因: {response.text}")



async def get_audio_links(Keywords, html_content):
    """
    提取舰桥互动对应的音频链接
    
    参数:
        Keywords (str): 要查找的关键词，例如"舰桥互动"
        html_content (str): 包含舰桥互动音频信息的HTML内容
    
    返回:
        list: 符合条件的音频链接列表
    """
    audio_links = []
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 查找所有包含舰桥互动的表格行
    rows = soup.find_all('tr')
    
    for row in rows:
        # 检查是否包含目标关键词
        header = row.find('td', class_='h3')
        if header and Keywords in header.text:
            # 查找当前行内的所有音频元素
            audio_sources = row.find_all('source', {'src': re.compile(r'^https?://')})
            # 查找当前行内的音频文本标签
            audio_text = row.find('span', class_='obc-tmpl-character__voice-content')
            # 首层tr跳过
            if audio_text and Keywords in audio_text.text: continue
            
            for source in audio_sources:
                audio_url = source.get('src')
                # 验证URL格式, 格式化文本
                if re.match(r'^https?://', audio_url):
                    audio_links.append({
                        'text': MarkdownCleaner.clean_markdown(audio_text.text) if audio_text else '',
                        'url': audio_url
                        })
    
    logger.debug(f"提取到 {len(audio_links)} 个有效音频链接")
    return audio_links


async def get_valkyrie_img(html_content):
    """
    提取女武神立绘图片链接
    参数:
        html_content (str): 包含女武神立绘信息的HTML内容
    返回:
        str: 提取到的图片链接，如果未找到则返回None
"""
    soup = BeautifulSoup(html_content, 'html.parser')
    container = soup.find('div', class_='obc-tmpl-valkyrie--mobile')
    if not container:
        logger.warning("未找到目标容器，HTML结构可能变更")
        return None
    img_tag = container.find('img')
    if not (img_tag and img_tag.has_attr('src')):
        logger.warning("容器内未找到有效图片标签")
        return None
    if img_tag:
        image_url = img_tag.get('src')
        logger.debug(f"成功提取图片URL: {image_url}")
        return image_url
    else:
        logger.warning("未在HTML内容中找到图片标签")
    return None

async def get_valkyries_data():
    temp_valkyries = Path(temp_path) / f"{datetime.now().date()}_bh3_valkyries.json"

    if not temp_valkyries.exists():
            try:
                await get_all_valkyrie_json(temp_valkyries)
            except Exception as e:
                logger.error(f"获取数据失败: {e}")
                return None

    with open(temp_valkyries, "r", encoding="utf-8") as f:
            data = json.load(f)
    return data