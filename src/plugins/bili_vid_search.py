# https://api.bilibili.com/x/web-interface/search/type?keyword=av28465342&search_type=video&page=1

import nonebot.adapters.qq.exception
import src.clover_videos.billibili.biliVideos as biliVideos
import uuid
import requests
from pathlib import Path
from src.clover_image.download_image import download_image
from src.clover_image.delete_file import delete_file
from nonebot import on_command
from nonebot.rule import to_me
from nonebot.adapters.qq import   MessageSegment,MessageEvent, Message
from src.configs.path_config import video_path, temp_path
from src.clover_providers.cloud_file_api.kukufile import Kukufile
from src.configs.api_config import qrserver_url,qrserver_size
from src.utils.async_utils import run_sync
from nonebot import logger
from nonebot.exception import FinishedException
import asyncio

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

    i = 0
    for vid_info in search_result:
        i += 1
        if i >= 4:
            break
        pic = "https:" + str(vid_info['pic'])
        # print(pic)
        description = ("\n标题: " + str(vid_info['title']).replace('<em class="keyword">', "").replace('</em>', "") +
                       "\nup主: " + vid_info['author'] +
                       "\n" + vid_info['bvid'])
        msg = Message([
            MessageSegment.image(pic),
            MessageSegment.text(description),
        ])
        await bili_vid.send(msg)
        await asyncio.sleep(0.5)

    await bili_vid.finish(f"展示{len(search_result)}条结果中的前3条。")


bili_bv_search = on_command("BV搜索", rule=to_me(), priority=10)
@bili_bv_search.handle()
async def get_video_file(message: MessageEvent):
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
                video_url = await run_sync(
                    biliVideos.get_video_file_url, keyword[0], cid
                )
            except requests.RequestException as exc:
                logger.warning(f"B站播放地址接口请求失败: {exc}")
                await bili_bv_search.finish("B站接口暂时不可用，请稍后重试。")
            if not video_url:
                await bili_bv_search.finish("获取视频播放地址失败，请稍后重试。")

            try:
                await bili_bv_search.send(MessageSegment.video(video_url))
            except nonebot.adapters.qq.exception.ActionFailed:
                qr_url = await post_video_kuku_file(vid_title, video_url, cid)
                if not qr_url:
                    await bili_bv_search.finish("发送失败了，视频下载或上传服务异常")
                qr_path = Path(temp_path) / f"qr_{cid}_{uuid.uuid4().hex}.png"
                try:
                    if not await download_image(qr_url, qr_path):
                        await bili_bv_search.finish("二维码生成失败，请稍后重试")
                    r_msg = Message([
                        MessageSegment.file_image(qr_path),
                        MessageSegment.text("由于QQ的限制，官方bot无法发送文件大于10M（实际更低）。"
                                            +"\n此二维码有效时间为10分钟。"
                                            +"\n可尝试扫码下载或在线观看视频哦~!")
                    ])
                    await bili_bv_search.send(r_msg)
                finally:
                    await delete_file(qr_path)
            except FinishedException:
                raise
            except Exception as e:
                logger.error(f'{e}')
                await bili_bv_search.finish("发送失败了，请稍后再试")
    elif len(keyword) >= 2:

        try:
            page_num = int(keyword[1])
        except:
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
            video_url = await run_sync(
                biliVideos.get_video_file_url, keyword[0], cid
            )
        except requests.RequestException as exc:
            logger.warning(f"B站播放地址接口请求失败: {exc}")
            await bili_bv_search.finish("B站接口暂时不可用，请稍后重试。")
        if not video_url:
            await bili_bv_search.finish("获取视频播放地址失败，请稍后重试。")

        try:
            await bili_bv_search.send(MessageSegment.video(video_url))
        except nonebot.adapters.qq.exception.ActionFailed:
            qr_url = await post_video_kuku_file(vid_title, video_url, cid)
            if not qr_url:
                await bili_bv_search.finish("发送失败了，视频下载或上传服务异常")
            qr_path = Path(temp_path) / f"qr_{cid}_{uuid.uuid4().hex}.png"
            try:
                if not await download_image(qr_url, qr_path):
                    await bili_bv_search.finish("二维码生成失败，请稍后重试")
                r_msg = Message([
                    MessageSegment.file_image(qr_path),
                    MessageSegment.text("由于QQ的限制，官方bot无法发送文件大于10M（实际更低）。"
                                        +"\n此二维码有效时间为10分钟。"
                                        +"\n可尝试扫码下载或在线观看视频哦~!")
                ])
                await bili_bv_search.send(r_msg)
            finally:
                await delete_file(qr_path)
        except FinishedException:
            raise
        except Exception as e:
            logger.error(f'{e}')
            await bili_bv_search.finish("发送失败了，请稍后再试")
    await bili_bv_search.finish()

async def post_video_kuku_file(vid_title, video_url, cid):
    """
    上传视频（异步处理）
    :param vid_title: 视频标题
    :param video_url: 视频URL
    :param cid: 视频CID
    :return: 上传成功返回二维码URL，上传失败返回False
    """
    temp_file = Path(video_path) / f"{cid}_{uuid.uuid4().hex}.mp4"
    try:
        downloaded = await run_sync(
            biliVideos.video_download, video_url, temp_file
        )
        if not downloaded or not temp_file.is_file():
            logger.warning(f"视频下载失败或文件不存在: {temp_file}")
            return False

        post_msg = await Kukufile.upload_file(temp_file, file_name=vid_title)

        if isinstance(post_msg, (list, tuple)) and len(post_msg) > 1 and post_msg[0] == "OK":
            video_page_url = post_msg[1].strip()
            logger.debug("视频临时链接生成成功")
            try:
                await Kukufile.auto_delete_kukufile(["OK", video_page_url], 600)
            except Exception as exc:
                logger.error(f"设置 Kukufile 自动删除失败，拒绝发布无过期链接: {exc}")
                return False
            return f"{qrserver_url}?size={qrserver_size}&data={video_page_url}"
        else:
            logger.error("Kukufile 上传接口返回失败状态")
            return False
    except Exception as e:
        logger.error(f"后台任务异常: {str(e)}")
        return False
    finally:
        if temp_file.is_file():
            await delete_file(temp_file)
