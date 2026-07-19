import os
import threading
import logging
import nonebot
from pathlib import Path
from nonebot import logger
from nonebot.log import default_format
from nonebot.adapters.qq import Adapter as QQAdapter
from apscheduler.schedulers.background import BackgroundScheduler
from src.configs.path_config import log_path,temp_path,video_path,yuc_wiki_path
from src.utils.cache_cleanup import get_stale_files
from src.utils.log_sanitizer import get_log_record_patcher, is_debug_mode
from src.utils.nonebot_compat import patch_empty_message_command_parsing
from src.utils.qq_event_compat import patch_qq_reply_message_parsing

# 禁用第三方库日志
for lib in ["websockets", "httpx", "httpcore", "hpack", "asyncio","aiosqlite","tortoise","urllib3","tzlocal"]:
    logging.getLogger(lib).setLevel(logging.WARNING)

__name__ = "Bot"

# NoneBot 2.5.0 and current main index message[0] without an empty-message guard.
patch_empty_message_command_parsing()
patch_qq_reply_message_parsing()

# 记录 PID 到文件
with open("bot.pid", "w") as f:
    f.write(str(os.getpid()))
# 初始化 NoneBot
nonebot.init()
from backend import start_flask
driver = nonebot.get_driver()
driver.register_adapter(QQAdapter)  # 注册QQ适配器
nonebot.load_from_toml("pyproject.toml")


logger.configure(patcher=get_log_record_patcher(is_debug_mode(driver.config)))


log_options = {
    "format": default_format,
    "rotation": "50 MB",
    "retention": "7 days",
    "compression": "zip",
    "encoding": "utf-8",
    "enqueue": True,
    "backtrace": False,
    "diagnose": False,
}
logger.add(Path(log_path) / "error.log", level="ERROR", **log_options)
logger.add(Path(log_path) / "log.log", level="INFO", **log_options)

from src.clover_sqlite.data_init.db_connect import disconnect, init
driver.on_startup(init)
driver.on_shutdown(disconnect)

def clean_temp_cache():
    """定时清理缓存文件"""
    path_list =  [Path(temp_path), Path(video_path),Path(yuc_wiki_path)]
    logger.info("开始清理文件")
    for folder_path in path_list:
        files = get_stale_files(folder_path, max_age_seconds=3600)
        for file in files:
            try:
                file.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning(f"清理缓存文件失败 {file}: {exc}")
    logger.info("清理完成")

scheduler = BackgroundScheduler()
scheduler.add_job(clean_temp_cache, 'cron', hour=0, minute=0)

if __name__ == "Bot":
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    scheduler.start()
    nonebot.run()
