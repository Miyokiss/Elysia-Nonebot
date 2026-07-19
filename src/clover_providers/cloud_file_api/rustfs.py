import asyncio
from pathlib import Path
import boto3
from nonebot import logger
from src.configs.api_config import endpoint_url, aws_access_key_id, aws_secret_access_key, bucket_name, signature_version
from src.utils.async_utils import run_sync
from botocore.client import Config

__name__ = "rustfs_api"

class RustFSAPI:
    def __init__(self):
        self.bucket_name = bucket_name
        self.s3 = None
        try:
            # 创建链接
            self.s3 = boto3.client(
                's3',
                endpoint_url=endpoint_url,
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                config=Config(
                    signature_version=signature_version,
                    connect_timeout=5,     # 连接超时时间（秒）
                    read_timeout=10,       # 读取超时时间（秒）
                    retries={'max_attempts': 3, 'mode': 'standard'},
                    request_checksum_calculation='when_required',
                    response_checksum_validation='when_required',
                    s3={'addressing_style': 'path'},
                ),
                region_name='qq-bot'
            )
            logger.debug("RustFS (S3) client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize RustFS (S3) client: {e}")

    async def upload_file(self, local_path: str, object_key: str, bucket: str = None) -> bool:
        bucket = bucket or self.bucket_name
        if self.s3 is None:
            logger.error("RustFS client is not initialized")
            return False
        if not object_key or not Path(local_path).is_file():
            logger.warning(f"跳过 RustFS 上传，无效文件或对象名: {local_path}, {object_key}")
            return False
        try:
            await run_sync(self.s3.upload_file, local_path, bucket, object_key)
            logger.debug(f"Uploaded {local_path} to s3://{bucket}/{object_key}")
            return True
        except Exception as e:
            logger.error(f"RustFS Upload Error: {e}")
            return False

    async def upload_bytes(
        self,
        content: bytes,
        object_key: str,
        content_type: str | None = None,
        bucket: str = None,
    ) -> bool:
        bucket = bucket or self.bucket_name
        if self.s3 is None:
            logger.error("RustFS client is not initialized")
            return False
        if not isinstance(content, bytes) or not content or not object_key:
            logger.warning("跳过 RustFS 上传，无效字节内容或对象名")
            return False

        parameters = {
            "Bucket": bucket,
            "Key": object_key,
            "Body": content,
        }
        if content_type:
            parameters["ContentType"] = content_type
        try:
            await run_sync(
                self.s3.put_object,
                **parameters,
                _cancel_cleanup=lambda _: self.s3.delete_object(
                    Bucket=bucket,
                    Key=object_key,
                ),
            )
            logger.debug(f"Uploaded bytes to s3://{bucket}/{object_key}")
            return True
        except Exception as e:
            logger.error(f"RustFS Upload Error: {e}")
            return False

    async def download_file(self, object_key: str, local_path: str, bucket: str = None) -> bool:
        bucket = bucket or self.bucket_name
        if self.s3 is None:
            logger.error("RustFS client is not initialized")
            return False
        try:
            await run_sync(
                self.s3.download_file,
                bucket,
                object_key,
                local_path,
                _cancel_cleanup=lambda _: _remove_local_file(local_path),
            )
            logger.debug(f"Downloaded s3://{bucket}/{object_key} to {local_path}")
            return True
        except Exception as e:
            logger.error(f"RustFS Download Error: {e}")
            return False

    async def delete_file(self, object_key: str, bucket: str = None) -> bool:
        bucket = bucket or self.bucket_name
        if self.s3 is None:
            logger.error("RustFS client is not initialized")
            return False
        try:
            await run_sync(self.s3.delete_object, Bucket=bucket, Key=object_key)
            logger.debug(f"Deleted s3://{bucket}/{object_key}")
            return True
        except Exception as e:
            logger.error(f"RustFS Delete Error: {e}")
            return False

    async def delayed_delete_file(
        self,
        object_key: str,
        delay: int,
        bucket: str = None,
        attempts: int = 3,
        retry_delay: int = 30,
    ) -> bool:
        await asyncio.sleep(max(0, int(delay)))
        attempts = max(1, int(attempts))
        for attempt in range(attempts):
            if await self.delete_file(object_key, bucket=bucket):
                return True
            if attempt + 1 < attempts:
                await asyncio.sleep(max(0, int(retry_delay)))
        return False

    async def get_download_url(self, object_key: str, bucket: str = None, expires_in: int = 3600) -> str:
        bucket = bucket or self.bucket_name
        if self.s3 is None or not object_key:
            logger.error("RustFS client is not initialized or object key is empty")
            return ""
        try:
            url = await run_sync(
                self.s3.generate_presigned_url,
                'get_object',
                Params={'Bucket': bucket, 'Key': object_key},
                ExpiresIn=expires_in
            )
            return url
        except Exception as e:
            logger.error(f"RustFS Generate URL Error: {e}")
            return ""


def _remove_local_file(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError as exc:
        logger.warning(f"清理 RustFS 下载临时文件失败 {path}: {exc}")


rustfs_api = RustFSAPI()
