import asyncio
import boto3
from nonebot import logger
from src.configs.api_config import endpoint_url, aws_access_key_id, aws_secret_access_key, bucket_name, signature_version
from botocore.client import Config

__name__ = "rustfs_api"

class RustFSAPI:
    def __init__(self):
        self.bucket_name = bucket_name
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
                    retries={'max_attempts': 1} # 失败重试次数
                ),
                region_name='qq-bot'
            )
            logger.debug("RustFS (S3) client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize RustFS (S3) client: {e}")

    async def upload_file(self, local_path: str, object_key: str, bucket: str = None) -> bool:
        bucket = bucket or self.bucket_name
        try:
            await asyncio.to_thread(self.s3.upload_file, local_path, bucket, object_key)
            logger.debug(f"Uploaded {local_path} to s3://{bucket}/{object_key}")
            return True
        except Exception as e:
            logger.error(f"RustFS Upload Error: {e}")
            return False

    async def download_file(self, object_key: str, local_path: str, bucket: str = None) -> bool:
        bucket = bucket or self.bucket_name
        try:
            await asyncio.to_thread(self.s3.download_file, bucket, object_key, local_path)
            logger.debug(f"Downloaded s3://{bucket}/{object_key} to {local_path}")
            return True
        except Exception as e:
            logger.error(f"RustFS Download Error: {e}")
            return False

    async def delete_file(self, object_key: str, bucket: str = None) -> bool:
        bucket = bucket or self.bucket_name
        try:
            await asyncio.to_thread(self.s3.delete_object, Bucket=bucket, Key=object_key)
            logger.debug(f"Deleted s3://{bucket}/{object_key}")
            return True
        except Exception as e:
            logger.error(f"RustFS Delete Error: {e}")
            return False

    async def get_download_url(self, object_key: str, bucket: str = None, expires_in: int = 3600) -> str:
        bucket = bucket or self.bucket_name
        try:
            url = await asyncio.to_thread(
                self.s3.generate_presigned_url,
                'get_object',
                Params={'Bucket': bucket, 'Key': object_key},
                ExpiresIn=expires_in
            )
            return url
        except Exception as e:
            logger.error(f"RustFS Generate URL Error: {e}")
            return ""

rustfs_api = RustFSAPI()
