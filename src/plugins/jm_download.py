import re
import uuid
from pathlib import Path
from nonebot import logger
from nonebot.rule import to_me
from nonebot.plugin import on_command
from nonebot.adapters.qq import MessageEvent, MessageSegment,Message
from src.clover_image.download_image import download_image
from src.clover_image.delete_file import delete_file
from src.configs.path_config import temp_path
from src.clover_jm.jm_comic import jm_qr, jm_email
from nonebot.exception import FinishedException

__name__ = "JM_Download"

jm = on_command("jm", rule=to_me(), priority=10, block=False)

async def handle_email_download(album_id: str, email: str):
    """处理邮箱发送逻辑"""
    if not validate_email(email):
        await jm.finish("邮箱格式不正确！")
    await jm.send("正在发送中，请稍等~")
    msg = await jm_email(album_id=album_id, receiver_email=email)
    await jm.finish(msg)

async def handle_qrcode_download(album_id: str):
    """处理二维码发送载逻辑"""
    await jm.send("正在下载中，请稍等~")
    msgs = await jm_qr(album_id=album_id)
    if not isinstance(msgs, dict):
        await jm.finish("生成下载链接失败，请稍后重试。")
    qr_url = msgs.get("qr_code")
    if not qr_url:
        await jm.finish(msgs.get("msg", "生成下载链接失败，请稍后重试。"))

    qr_path = Path(temp_path) / f"qr_{album_id}_{uuid.uuid4().hex}.png"
    try:
        if not await download_image(qr_url, qr_path):
            await jm.finish("二维码生成失败，请稍后重试。")
        msg = Message([
            MessageSegment.text(msgs.get("msg", "获取成功")),
            MessageSegment.file_image(qr_path),
        ])
        await jm.finish(msg)
    finally:
        if qr_path.is_file():
            await delete_file(qr_path)

@jm.handle()
async def handle_function(message: MessageEvent):
    values = message.get_plaintext().replace("/jm", "").split()
    try:
        if len(values) == 0 or not all(values[1:len(values)]):
            await jm.finish("请输入正确的格式 /jm+id 或 /jm+id+邮箱号")
        elif len(values) == 1:
            await handle_qrcode_download(values[0])
        elif len(values) == 2:
            await handle_email_download(values[0], values[1])
    except Exception as e:
        if isinstance(e, FinishedException):
            return
        logger.error(f"处理请求时发生错误: {e}")
        await jm.finish("处理请求时发生错误，请稍后重试")

def validate_email(email: str) -> bool:
    """验证邮箱格式是否合法"""
    EMAIL_REGEX = r"^[a-zA-Z0-9._%+-]+@([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$"
    return re.fullmatch(EMAIL_REGEX, email) is not None
