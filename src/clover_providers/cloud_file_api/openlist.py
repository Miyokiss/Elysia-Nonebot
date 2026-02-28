# openlist API
import asyncio
import aiohttp
import os
from nonebot import logger
from urllib.parse import quote
from src.configs.api_config import url, openlist_storage_file_path, username, password

__name__ = "openlist_api"

class OpenlistAPI:
    def __init__(self, url: str = url, storage_file_path: str = openlist_storage_file_path, username: str = username, password: str = password):
        self.url = url.rstrip("/")
        self.storage_file_path = storage_file_path if storage_file_path.endswith("/") else f"{storage_file_path}/"
        self.username = username
        self.password = password
        self.Authorization = None

    async def _ensure_auth(self):
        """确保已有 Token，否则尝试获取"""
        if not self.Authorization:
            await self.get_Authorization()

    # 获取下载链接
    async def get_download_url(self, openlist_file_path: str, password: str = "") -> str:
        """
        :param openlist_file_path: openlist 文件路径
        :param password: 文件密码（可选）
        :return: 下载链接
        """
        await self._ensure_auth()
        data = {
            "password": f"{password}",
            "path": f"{self.storage_file_path}{openlist_file_path}"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.url}/api/fs/get", json=data, headers={"Authorization": self.Authorization}) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("code") == 200:
                        return result.get("data").get("raw_url")
                    else:
                        raise ValueError(f"API Error: {result.get('message')}")
                else:
                    raise ValueError(f"Failed to get download URL: {response.status}")

    # 上传文件
    async def upload_file(self, file_path: str , overwrite: bool = False , file_name: str = None) -> dict:
        """
        :param file_path: 本地文件路径
        :param overwrite: 是否覆盖已存在的文件
        :return: 服务器响应
        """
        await self._ensure_auth()
        file_name = file_name or os.path.basename(file_path)
        
        # 处理中文文件名，建议进行 URL 编码，防止 header 乱码问题
        remote_path = f"{self.storage_file_path}{file_name}"
        encoded_path = quote(remote_path)

        # 构造请求数据
        headers = {
            "Authorization": self.Authorization,
            "File-Path": encoded_path,
            "overwrite": "true" if overwrite else "false",
        }
        # 上传文件
        async with aiohttp.ClientSession() as session:
            with open(file_path, 'rb') as file_data:
                async with session.put(f"{self.url}/api/fs/put", data=file_data, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("code") == 200:
                            return result
                        else:
                            raise ValueError(f"API Error: {result.get('message')}")
                    else:
                        raise ValueError(f"Failed to upload file: {response.status}")

    async def delete_file(self, files: str) -> dict:
        """
        :param files: 要删除的文件名、列表以,分隔
        :param openlist_storage_file_path: openlist 文件路径
        :return: 服务器响应
        """
        await self._ensure_auth()
        data = {
            "dir": f"{self.storage_file_path}",
            "names": files.split(",")
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.url}/api/fs/remove", json=data, headers={"Authorization": self.Authorization}) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("code") == 200:
                        return result
                    else:
                        raise ValueError(f"API Error: {result.get('message')}")
                else:
                    raise ValueError(f"Failed to delete file: {response.status}")

    # 获取Authorization
    async def get_Authorization(self, otp_code: str = "") -> dict:
        """
        :return: 服务器响应
        """
        async with aiohttp.ClientSession() as session:
            data = {
                "otp_code": otp_code,
                "username": self.username,
                "password": self.password
            }
            async with session.post(f"{self.url}/api/auth/login/hash", json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("code") == 200:
                        self.Authorization = result.get("data").get("token")
                        return result
                    else:
                        raise ValueError(f"Login Failed: {result.get('message')}")
                else:
                    raise ValueError(f"Failed to get Authorization: {response.status}")

    # 检测登录状态
    async def check_login_status(self) -> dict:
        """
        :return: 服务器响应
        """
        await self._ensure_auth()
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.url}/api/me", headers={"Authorization": self.Authorization}) as response:
                if response.status == 200:
                    result = await response.json()
                    return result
                else:
                    raise ValueError(f"Failed to check login status: {response.status}")
                
    # 延迟删除文件
    async def delayed_delete_file(self, file_name: str, delay: int = 60):
        await asyncio.sleep(delay)
        try:
            await self.delete_file(file_name)
        except Exception as e:
            logger.warning(f"Failed to delete remote file {file_name}: {e}")


openlist_api = OpenlistAPI()