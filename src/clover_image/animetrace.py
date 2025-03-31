
import aiohttp
from nonebot import logger
from src.configs.api_config import animetrace_url

async def animetrace_search_by_url(search_url):
    data = {
        #'model': 'anime_model_lovelive',
        'model': 'pre_stable',
        'ai_detect':0,
        'is_multi':1,
        'url': search_url
    }
    logger.debug(f"animetrace_search_by_url: {data}")
    content = ""
    async with aiohttp.ClientSession() as session:
        async with session.post(animetrace_url, data=data) as response:
            logger.debug(f"animetrace_search_by_url 返回 Code: {response.status}")
            if response.status == 200:
                response = await response.json()
                logger.debug(f"animetrace_search_by_url 返回 Data: {response}")
                i = 0
                for item in response['data']:
                    for character in item['character']:
                        # 第n个、作品：角色
                        i += 1
                        content += f"{i}、作品：{character['work']}\n角色：{character['character']}\n"
                
                content += f"是否识别为AI生成图：\n"
                if response['ai']:
                    content += f"AI识别结果：疑似AI生成图"
                else:
                    content += f"AI识别结果：非AI生成图"
                return content
            else:
                return None


