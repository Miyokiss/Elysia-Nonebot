import os
import uuid
from os import getcwd
from pathlib import Path
from datetime import datetime
from nonebot.log import logger
from nonebot.rule import to_me
from nonebot.adapters import Message
from nonebot.plugin import on_command
from nonebot.params import CommandArg
from src.configs.path_config import temp_path
from nonebot.adapters.qq import MessageSegment
from playwright.async_api import async_playwright
from src.clover_image.delete_file import delete_file
from nonebot_plugin_htmlrender import template_to_pic

weather = on_command("天气", rule=to_me(), aliases={"weather", "查天气"}, priority=10)

@weather.handle()
async def handle_function(args: Message = CommandArg()):

    # 提取参数纯文本作为地名，并判断是否有效
    if city_encoded := args.extract_plain_text():
        temp_file = os.path.join(temp_path, f"weather_{datetime.now().date()}_{uuid.uuid4().hex}.png")
        r_weather = await weather_info_img(city_encoded, temp_file)
        if r_weather is True:
            await weather.send(MessageSegment.file_image(Path(temp_file)))
            await delete_file(temp_file)
            await weather.finish()
        else:
            await weather.finish(f"获取天气信息失败：{r_weather}")
    else:
        await weather.finish("请输入地名")


import requests

def get_weather(location):
    # 设置请求的URL和参数
    url = f'https://apis.juhe.cn/simpleWeather/query?key=50a3bd415158e186903d6e6994157589&city={location.rstrip("市").rstrip("县").rstrip("区")}'
    # 发送GET请求
    response = requests.get(url)
    # 检查请求是否成功
    if response.status_code == 200:
        # 解析返回的JSON数据
        data = response.json()

        # 检查是否查询成功
        if data['reason'] == '查询成功!' or data['reason'] == '查询成功':
            # 返回天气数据
            return data['result']
        else:
            return {"error": "查询失败: " + data['reason']}
    else:
        return {"error": "请求失败，状态码: " + str(response.status_code)}

async def weather_info_img(city_encoded,temp_file):
        """获取数据
        :param keyword: 搜索关键字
        :param session: requests会话对象
        :param temp_file: 临时文件路径
        :return: True 如果没有找到或其他返回None"""
        
        if os.path.exists(temp_file):
            with open(temp_file,"rb") as image_file:
                return image_file.read()
        weather_data = get_weather(city_encoded)
        if 'error' in weather_data:
            return weather_data['error']
        else:
            if weather_data is None:
                return None
            data = {
                 "weather_data": weather_data,
            }
            logger.debug(f"data：{data}")
            async with async_playwright() as p:
                browser = await p.chromium.launch()

            image_bytes = await template_to_pic(
                template_path=getcwd() + "/src/clover_html/weather",
                template_name="main.html",
                templates={"data": data},
                pages={
                    "viewport": {"width": 1346, "height": 1},
                    "base_url": f"file://{getcwd()}",
                },
                wait=2,
            )
            with open(temp_file, "wb") as file:
                file.write(image_bytes)
            await browser.close()
            return True