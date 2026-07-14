import asyncio
import logging


logger = logging.getLogger(__name__)


async def run_sync(function, *args, _cancel_cleanup=None, **kwargs):
    """Run blocking work without abandoning its cleanup when cancelled."""
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        result = None
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if task.done() and not task.cancelled():
            try:
                result = task.result()
            except Exception:
                pass
        if _cancel_cleanup is not None:
            try:
                _cancel_cleanup(result)
            except Exception:
                logger.warning("取消任务后的文件清理失败", exc_info=True)
        raise
