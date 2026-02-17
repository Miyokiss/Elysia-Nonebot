import asyncio
import nonebot
# 初始化 NoneBot 以加载配置
nonebot.init()
from nonebot import logger
from Script.Memory_id_Migration_Script import Memory_id_Migration_Script
from src.clover_sqlite.data_init.db_connect import init, disconnect

async def main():
    logger.info("开始批执行数据库迁移脚本...")
    
    # 初始化数据库连接
    try:
        await init()
        logger.info("数据库连接成功")
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        return

    try:
        # 执行迁移的脚本
        await Memory_id_Migration_Script()
        logger.info("脚本执行完成")
    except Exception as e:
        logger.error(f"脚本执行过程中发生全局异常: {e}")
    finally:
        # 关闭数据库连接
        logger.info("正在关闭数据库连接...")
        await disconnect()
        logger.info("数据库连接已关闭")

if __name__ == "__main__":#
    asyncio.run(main())