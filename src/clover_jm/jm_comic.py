import asyncio
import yaml
import uuid
import jmcomic
from pathlib import Path
from datetime import datetime
from nonebot import logger
from src.configs.api_config import qrserver_url,qrserver_size
from src.clover_jm.disguise_pdf import folder_zip
from src.configs.path_config import jm_path,jm_config_path
from src.clover_providers.cloud_file_api.kukufile import Kukufile
from src.clover_image.delete_file import delete_folder,delete_file
from src.clover_email.send_email import send_email_by_qq
from src.utils.async_utils import run_sync

__name__ = "clover | jm_comic"

jm_config_lock = asyncio.Lock()

async def jm_email(album_id: str| None,receiver_email: str| None):
    file_name = f"JM-email-{uuid.uuid4().hex}"
    folder_path = Path(jm_path) / file_name
    zip_path = Path(jm_path) / f"{file_name}.zip"
    try:
        download_result = await download_jm(
            album_id=album_id, file_name=file_name, receiver_email=None
        )
        if not isinstance(download_result, tuple) or len(download_result) != 2:
            return "下载失败，请重试!"
        if not await folder_zip(folder_path, zip_path):
            return "压缩文件失败"
        if await send_email_by_qq(receiver_email, zip_path):
            return "发送成功,请注意查收\n如遇邮箱接收不到,请检查发送的邮箱是否正确,或者是否在垃圾箱"
        return "发送邮件失败，请重试!"
    finally:
        if folder_path.exists():
            await delete_folder(folder_path)
        if zip_path.is_file():
            await delete_file(zip_path)

async def jm_qr(album_id: str| None):

    file_name = f"JM-{album_id}-{datetime.now().date()}@{uuid.uuid4().hex}"
    folder_path = Path(jm_path) / file_name
    zip_path = Path(jm_path) / f"{file_name}.zip"
    try:
        download_result = await download_jm(
            album_id=album_id, file_name=file_name, receiver_email=None
        )
        if not isinstance(download_result, tuple) or len(download_result) != 2:
            return {"msg": "下载失败，请重试!"}
        album_detail, _ = download_result
        zip_name = f"{album_detail.title}.zip"
        if not await folder_zip(folder_path, zip_path):
            return {"msg": "压缩文件失败"}

        send_status = await Kukufile.upload_file(zip_path, zip_name)
        if not (
            isinstance(send_status, (list, tuple))
            and len(send_status) > 1
            and send_status[0] == "OK"
        ):
            logger.error("Kukufile 上传失败")
            return {"msg": "上传出错API,请重试!"}

        try:
            await Kukufile.auto_delete_kukufile(send_status, 600)
        except Exception as exc:
            logger.error(f"Kukufile 自动删除设置失败，拒绝发布链接: {exc}")
            return {"msg": "临时文件过期时间设置失败，请稍后重试。"}
        return {
            "msg": "获取成功~！码上下载！~\n有效期10分钟",
            "qr_code": f"{qrserver_url}?size={qrserver_size}&data={send_status[1]}",
        }
    finally:
        if folder_path.exists():
            await delete_folder(folder_path)
        if zip_path.is_file():
            await delete_file(zip_path)

async def download_jm(album_id: str| None,file_name :str | None,receiver_email: str| None):
    # 修改配置文件的下载路径
    async with jm_config_lock:
        target_name = file_name or receiver_email
        if not target_name:
            raise ValueError("JM 下载目录名不能为空")
        source_path = await get_jm_config(target_name)

        try:
            option = jmcomic.JmOption.from_file(jm_config_path)
        finally:
            await recover_jm_config(source_path)
    # 调用JM下载api
    try:
        return await run_sync(jmcomic.download_album, album_id, option)
    except Exception as e:
        logger.error(f"下载失败 :{e}")
        return "下载失败,请重试"

async def get_jm_config(file_name: str):

    with open(jm_config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
        source_path = config['dir_rule']['base_dir']
        new_base_dir = str(Path(jm_path) / file_name)
        config['dir_rule']['base_dir'] = new_base_dir
    with open(jm_config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, sort_keys=False, allow_unicode=True)
    return source_path

async def recover_jm_config(source_path : str):

    with open(jm_config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
        new_base_dir = str(Path(source_path))
        config['dir_rule']['base_dir'] = new_base_dir
    with open(jm_config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, sort_keys=False, allow_unicode=True)
