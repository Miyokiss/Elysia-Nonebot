import time
import os
import signal
import subprocess
from nonebot import logger

__name__ = "Reboot"
def main():
    try:
        # 等待足够时间让原进程发送消息
        time.sleep(4)
        
        # 读取原进程 PID
        with open("bot.pid", "r") as f:
            pid = int(f.read().strip())
        
        # 终止原进程
        os.kill(pid, signal.SIGTERM)
        logger.info(f"已终止原进程 {pid}")
        
        # 确保进程结束
        time.sleep(5)
    except FileNotFoundError:
        logger.error("错误：未找到 bot.pid 文件")
        return 1
    except ProcessLookupError:
        logger.error("错误：原进程已终止")
    except Exception as e:
        logger.error(f"终止进程时出错: {e}")
        return 1

    # 启动
    proc = subprocess.Popen(["runtime/python", "bot.py"]) # 如使用集成环境在此修改
    
    # 记录新 PID
    with open("bot.pid", "w") as f:
        f.write(str(proc.pid))
    logger.info(f"已启动新进程 {proc.pid}")
    return 0

if __name__ == "Reboot":
    exit_code = main()
    exit(exit_code)