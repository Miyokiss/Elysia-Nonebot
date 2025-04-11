from datetime import datetime
from pathlib import Path
from nonebot.rule import to_me
from nonebot.plugin import on_command
from nonebot.adapters.qq import  MessageSegment
from src.clover_report.data_source import Report
from src.configs.path_config import temp_path
from nonebot import logger
import os


daily_report = on_command("日报", rule=to_me(), priority=10)
@daily_report.handle()
async def handle_function():
    now = datetime.now()
    file = Path() / temp_path / f"{now.date()}日报.png"
    if not os.path.exists(file):
        await daily_report.send("您是今天第一个查看日报的哦，来看看世界上都发生了些什么吧💫\nCrunching the latest news, just for you. Hang tight…")
    try:
        await Report.get_report_image()
    except Exception as e:
        logger.error(f"日报获取失败：{e}")
        await daily_report.finish("出错啦，请重试。")
    await daily_report.finish(MessageSegment.file_image(Path(temp_path+f"{now.date()}日报.png")))
