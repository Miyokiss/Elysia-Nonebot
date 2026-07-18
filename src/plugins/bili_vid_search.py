# https://api.bilibili.com/x/web-interface/search/type?keyword=av28465342&search_type=video&page=1

import src.clover_videos.billibili.biliVideos as biliVideos
import uuid
import requests
from pathlib import Path
from src.clover_image.download_image import download_image
from src.clover_image.delete_file import delete_file
from nonebot import on_command
from nonebot.rule import to_me
from nonebot.adapters.qq import (
    Bot,
    Message,
    MessageEvent,
    MessageSegment,
)
from src.configs.path_config import video_path, temp_path
from src.clover_providers.cloud_file_api.kukufile import Kukufile, MAX_UPLOAD_SIZE
from src.configs.api_config import qrserver_url,qrserver_size
from src.utils.async_utils import run_sync
from nonebot import logger
from nonebot.exception import FinishedException
from nonebot.adapters.qq.exception import ActionFailed
import asyncio


VIDEO_FALLBACK_BLOCKED_CODES = {
    304103,
    40034005,
    40034006,
    40054002,
    40054005,
}
QQ_REMOTE_VIDEO_LIMIT = 10 * 1024 * 1024
CLOUD_FALLBACK_TIMEOUT_SECONDS = 180
VIDEO_PIPELINE_SEMAPHORE = asyncio.Semaphore(2)
_background_uploads: set[asyncio.Task] = set()


def _can_use_video_fallback(exc: ActionFailed) -> bool:
    try:
        code = int(exc.code)
    except (TypeError, ValueError):
        return True
    return code not in VIDEO_FALLBACK_BLOCKED_CODES


async def _finish_bv_safely(message: str) -> None:
    try:
        await bili_bv_search.finish(message)
    except FinishedException:
        raise
    except ActionFailed as exc:
        logger.warning(
            f"BV 搜索提示发送失败: code={exc.code}, message={exc.message}"
        )
    except Exception as exc:
        logger.warning(f"BV 搜索提示发送失败: {type(exc).__name__}")


def _should_use_video_fallback(video_size) -> bool:
    return (
        isinstance(video_size, int)
        and not isinstance(video_size, bool)
        and video_size > QQ_REMOTE_VIDEO_LIMIT
    )


async def _send_search_result(message: Message, text_fallback: str) -> bool:
    try:
        await bili_vid.send(message)
        return True
    except ActionFailed as exc:
        logger.warning(
            f"B站搜索图片结果发送失败，尝试文本降级: "
            f"code={exc.code}, message={exc.message}"
        )
    except Exception as exc:
        logger.warning(f"B站搜索图片结果发送失败: {type(exc).__name__}")

    try:
        await bili_vid.send(text_fallback)
        return True
    except ActionFailed as exc:
        logger.warning(
            f"B站搜索文本结果发送失败: code={exc.code}, message={exc.message}"
        )
    except Exception as exc:
        logger.warning(f"B站搜索文本结果发送失败: {type(exc).__name__}")
    return False


async def _send_delayed_message(bot: Bot, event: MessageEvent, message) -> None:
    # Bot.send preserves msg_id/msg_seq from the original event, so QQ treats the
    # result as a passive reply instead of an unauthorized proactive message.
    await bot.send(event=event, message=message)


def _finish_background_upload(task: asyncio.Task) -> None:
    _background_uploads.discard(task)
    if task.cancelled():
        return
    try:
        task.result()
    except Exception as exc:
        logger.warning(f"超时后的云盘任务失败: {type(exc).__name__}")


def _track_background_upload(task: asyncio.Task) -> None:
    _background_uploads.add(task)
    task.add_done_callback(_finish_background_upload)


async def _post_video_with_deadline(*args, **kwargs) -> tuple[bool, str | bool | None]:
    task = asyncio.create_task(post_video_kuku_file(*args, **kwargs))
    try:
        done, _ = await asyncio.wait(
            {task}, timeout=CLOUD_FALLBACK_TIMEOUT_SECONDS
        )
    except asyncio.CancelledError:
        task.cancel()
        _track_background_upload(task)
        raise
    if not done:
        task.cancel()
        _track_background_upload(task)
        logger.warning(
            f"视频云盘降级超过 {CLOUD_FALLBACK_TIMEOUT_SECONDS} 秒，停止等待结果"
        )
        return False, None
    return True, task.result()


async def _send_delayed_safely(bot: Bot, event: MessageEvent, message) -> bool:
    try:
        await _send_delayed_message(bot, event, message)
        return True
    except ActionFailed as exc:
        logger.warning(
            f"BV 搜索延迟消息发送失败: code={exc.code}, message={exc.message}"
        )
    except Exception as exc:
        logger.warning(f"BV 搜索延迟消息发送失败: {type(exc).__name__}")
    return False

bili_vid = on_command("B站搜索",rule=to_me(), priority=10)
@bili_vid.handle()
async def get_bili_vid_info(message: MessageEvent):
    content = message.get_plaintext().replace("/B站搜索", "").strip()
    if content == "":
        await bili_vid.finish("请输入搜索内容\n指令格式：\n/B站搜索 搜索内容")
    try:
        response = await run_sync(biliVideos.get_video_info, content)
    except requests.RequestException as exc:
        logger.warning(f"B站搜索接口请求失败: {exc}")
        await bili_vid.finish("B站接口暂时不可用，请稍后重试。")
    if not isinstance(response, dict) or response.get('code') != 0:
        message = response.get('message', 'B站接口返回异常') if isinstance(response, dict) else 'B站接口返回异常'
        await bili_vid.finish(message)
    search_result = response.get('data', {}).get('result') or []

    sent_count = 0
    for vid_info in search_result[:3]:
        pic = "https:" + str(vid_info['pic'])
        description = ("\n标题: " + str(vid_info['title']).replace('<em class="keyword">', "").replace('</em>', "") +
                       "\nup主: " + vid_info['author'] +
                       "\n" + vid_info['bvid'])
        msg = Message([
            MessageSegment.image(pic),
            MessageSegment.text(description),
        ])
        if await _send_search_result(msg, description):
            sent_count += 1
            await asyncio.sleep(0.5)

    if sent_count:
        await bili_vid.finish(f"已展示 {sent_count} 条结果。")
    await bili_vid.finish("搜索结果发送失败，请稍后重试。")


bili_bv_search = on_command("BV搜索", rule=to_me(), priority=10)


async def _send_video_or_fallback(
    vid_title, video_url, cid, bot: Bot, event: MessageEvent, video_size=None
) -> None:
    if _should_use_video_fallback(video_size):
        logger.info(
            f"视频大小 {video_size} bytes 超过 QQ 直发阈值，直接使用云盘降级"
        )
    else:
        try:
            await bili_bv_search.send(MessageSegment.video(video_url))
            return
        except ActionFailed as exc:
            if not _can_use_video_fallback(exc):
                logger.warning(
                    f"QQ 视频发送失败，不启动云盘降级: "
                    f"code={exc.code}, message={exc.message}"
                )
                await _finish_bv_safely("QQ 视频服务暂时不可用，请稍后重试。")
                return
        except Exception as exc:
            logger.warning(f"QQ 视频发送失败: {type(exc).__name__}")
            await _finish_bv_safely("QQ 视频服务暂时不可用，请稍后重试。")
            return

    qr_path = None
    try:
        completed, qr_url = await _post_video_with_deadline(
            vid_title, video_url, cid, video_size=video_size
        )
        if not completed:
            await _send_delayed_safely(
                bot, event, "视频处理超时，请稍后重试"
            )
            return
        if not qr_url:
            await _send_delayed_safely(
                bot, event, "发送失败了，视频下载或上传服务异常"
            )
            return

        qr_path = Path(temp_path) / f"qr_{cid}_{uuid.uuid4().hex}.png"
        if not await download_image(qr_url, qr_path):
            await _send_delayed_safely(bot, event, "二维码生成失败，请稍后重试")
            return
        r_msg = Message([
            MessageSegment.file_image(qr_path),
            MessageSegment.text(
                "由于QQ的限制，官方bot无法发送文件大于10M（实际更低）。"
                "\n此二维码有效时间为10分钟。"
                "\n可尝试扫码下载或在线观看视频哦~!"
            ),
        ])
        await _send_delayed_message(bot, event, r_msg)
    except FinishedException:
        raise
    except ActionFailed as exc:
        logger.warning(
            f"BV 搜索消息发送失败: code={exc.code}, message={exc.message}"
        )
    except Exception as exc:
        logger.opt(exception=exc).error("BV 搜索降级处理失败")
        await _send_delayed_safely(bot, event, "发送失败了，请稍后再试")
    finally:
        if qr_path is not None:
            await delete_file(qr_path)


@bili_bv_search.handle()
async def get_video_file(message: MessageEvent, bot: Bot):
    keyword = message.get_plaintext().replace("/BV搜索", "").strip().split()
    if len(keyword) == 0:
        await bili_bv_search.finish("请输入BV号\n指令格式：\n/BV搜索 BV号\n/BV搜索 BV号 分P序号(数字)")
    try:
        P_num, pages, vid_title, vid_author, vid_pic = await run_sync(
            biliVideos.get_video_pages_info, keyword[0]
        )
    except requests.RequestException as exc:
        logger.warning(f"B站视频信息接口请求失败: {exc}")
        await bili_bv_search.finish("B站接口暂时不可用，请稍后重试。")
    if P_num is None:
        await bili_bv_search.finish("获取视频信息失败，请检查BV号是否正确。")
    if len(keyword) == 1:

        if P_num > 1:
            content = "\n标题:" + vid_title + "\nup主: " + vid_author + "\n该视频为多P播放：\n"
            for page in pages:
                content = content + "P" + str(page['page']) + ": " + page['part'] + "\n时长: " + str(page['duration']) + "s\n\n"

            content = content + "请选择您想播放的集数。\n决定好后麻烦回复 /BV搜索+BV号+序号 哦。\n"
            await bili_bv_search.finish(content)

        elif P_num == 1:

            content = ("\n标题: " + vid_title + "\nup主: " + vid_author + "\n视频加载中~请稍后~~~")
            msg = Message([
                MessageSegment.image(vid_pic),
                MessageSegment.text(content),
            ])
            await bili_bv_search.send(msg)

            cid = pages[0]['cid']
            try:
                video_info = await run_sync(
                    biliVideos.get_video_file_info, keyword[0], cid
                )
            except requests.RequestException as exc:
                logger.warning(f"B站播放地址接口请求失败: {exc}")
                await bili_bv_search.finish("B站接口暂时不可用，请稍后重试。")
            if not video_info:
                await bili_bv_search.finish("获取视频播放地址失败，请稍后重试。")

            await _send_video_or_fallback(
                vid_title,
                video_info["url"],
                cid,
                bot,
                message,
                video_size=video_info.get("size"),
            )
    elif len(keyword) >= 2:

        try:
            page_num = int(keyword[1])
        except (TypeError, ValueError):
            await bili_bv_search.finish("输入有误\n请确认是否为 /BV搜索+BV号+序号(数字) ")

        if page_num > len(pages):
            page_num = len(pages)
        elif page_num < 1:
            page_num = 1

        content = ("\n标题: " + vid_title + "\nup主: " + vid_author + "\n正在播放共" + str(P_num) + "P中的第" + str(page_num) + "P" + "\n视频加载中~请稍后~~~")
        msg = Message([
            MessageSegment.image(vid_pic),
            MessageSegment.text(content),
        ])
        await bili_bv_search.send(msg)

        cid = pages[page_num - 1]['cid']
        try:
            video_info = await run_sync(
                biliVideos.get_video_file_info, keyword[0], cid
            )
        except requests.RequestException as exc:
            logger.warning(f"B站播放地址接口请求失败: {exc}")
            await bili_bv_search.finish("B站接口暂时不可用，请稍后重试。")
        if not video_info:
            await bili_bv_search.finish("获取视频播放地址失败，请稍后重试。")

        await _send_video_or_fallback(
            vid_title,
            video_info["url"],
            cid,
            bot,
            message,
            video_size=video_info.get("size"),
        )
    await bili_bv_search.finish()

async def post_video_kuku_file(vid_title, video_url, cid, video_size=None):
    async with VIDEO_PIPELINE_SEMAPHORE:
        return await _post_video_kuku_file(vid_title, video_url, cid, video_size)


async def _post_video_kuku_file(vid_title, video_url, cid, video_size=None):
    """
    上传视频（异步处理）
    :param vid_title: 视频标题
    :param video_url: 视频URL
    :param cid: 视频CID
    :return: 上传成功返回二维码URL，上传失败返回False
    """
    temp_file = Path(video_path) / f"{cid}_{uuid.uuid4().hex}.mp4"
    try:
        if (
            isinstance(video_size, int)
            and not isinstance(video_size, bool)
            and video_size > MAX_UPLOAD_SIZE
        ):
            logger.warning(
                f"视频大小 {video_size} bytes 超过 Kukufile 上传限制"
            )
            return False

        downloaded = await biliVideos.video_download_async(
            video_url,
            temp_file,
            max_size=MAX_UPLOAD_SIZE,
            expected_size=video_size,
        )
        if not downloaded or not temp_file.is_file():
            logger.warning(f"视频下载失败或文件不存在: {temp_file}")
            return False

        display_name = str(vid_title).strip() or str(cid)
        if not display_name.lower().endswith(".mp4"):
            display_name += ".mp4"
        post_msg = await Kukufile.upload_temporary_file(
            temp_file,
            file_name=display_name,
            expiration_seconds=600,
        )

        if isinstance(post_msg, (list, tuple)) and len(post_msg) > 1 and post_msg[0] == "OK":
            video_page_url = post_msg[1].strip()
            logger.debug("视频临时链接生成成功")
            return f"{qrserver_url}?size={qrserver_size}&data={video_page_url}"
        else:
            logger.warning("Kukufile 上传接口未返回可用链接")
            return False
    except Exception as exc:
        logger.error(f"后台任务异常: {type(exc).__name__}")
        return False
    finally:
        if temp_file.is_file():
            await delete_file(temp_file)
