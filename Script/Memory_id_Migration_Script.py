import uuid
from nonebot import logger
from src.providers.llm.Dify import DifyChatRole
from src.providers.memory.memobase.base import MemoBaseHandler

__name__ = "Memory_id_Migration_Script"


async def Memory_id_Migration_Script():
    logger.info("开始执行Memory_id_Migration_Script...")

    try:
        # 查询所有 memory_id 为 "Memory" 的记录
        users = await DifyChatRole.filter(memory_id="Memory").all()
        count = len(users)
        logger.info(f"共发现 {count} 个用户需要迁移")

        if count == 0:
            logger.info("没有需要迁移的数据")
            return

        success_count = 0
        fail_count = 0

        for user in users:
            try:
                # 生成新的 UUID
                new_memory_id = str(uuid.uuid4())
                logger.info(f"正在处理用户 {user.user_id} | 原 memory_id: {user.memory_id} -> 新 memory_id: {new_memory_id}")

                # 在 MemoBase 中创建用户
                # 为了保证数据一致性，先在 MemoBase 创建用户
                mb_success = await MemoBaseHandler.create_user(uuid=new_memory_id)
                
                if mb_success:
                    # 更新数据库
                    user.memory_id = new_memory_id
                    await user.save()
                    logger.info(f"用户 {user.user_id} 迁移成功")
                    success_count += 1
                else:
                    logger.error(f"用户 {user.user_id} 在 MemoBase 创建失败，跳过数据库更新")
                    fail_count += 1
                    
            except Exception as e:
                logger.error(f"处理用户 {user.user_id} 时发生异常: {e}")
                fail_count += 1
        
        logger.info(f"迁移完成。成功: {success_count}, 失败: {fail_count}")

    except Exception as e:
        logger.error(f"脚本执行过程中发生全局异常: {e}")
