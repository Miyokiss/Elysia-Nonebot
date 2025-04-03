import re
from nonebot import logger
from nonebot.rule import to_me
from nonebot.plugin import on_command
from nonebot.adapters.qq import MessageEvent, MessageSegment,Message
from src.clover_jm.jm_comic import download_jm_qr, download_jm_Pemail
from nonebot.exception import FinishedException

__name__ = "JM_Download"

jm = on_command("jm", rule=to_me(), priority=10, block=False)

async def handle_email_download(album_id: str, email: str):
    """处理邮箱发送逻辑"""
    if not validate_email(email):
        await jm.finish("邮箱格式不正确！")
    await jm.send("正在发送中，请稍等~")
    msg = await download_jm_Pemail(album_id=album_id, receiver_email=email)
    await jm.finish(msg)

async def handle_qrcode_download(album_id: str):
    """处理二维码发送载逻辑"""
    await jm.send("正在下载中，请稍等~")
    msgs = await download_jm_qr(album_id=album_id)
    if "qr_code" not in msgs:
        await jm.finish(msgs["msg"])
    msg = Message([
        MessageSegment.text(msgs["msg"]),
        MessageSegment.image(msgs["qr_code"])
    ])
    await jm.finish(msg)

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