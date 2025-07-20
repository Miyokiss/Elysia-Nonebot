import sys
from datetime import datetime
from typing import List, Dict, Any
from functools import partial
from nonebot import logger
import asyncio
from http import HTTPStatus
from dashscope import Application
from src.configs.api_config import (
    ALI_KEY,ALI_BLAPP_ID,
    ALIBABA_CLOUD_ACCESS_KEY_ID,ALIBABA_CLOUD_ACCESS_KEY_SECRET,
    workspaceId)
from alibabacloud_bailian20231229.client import Client as bailian20231229Client
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_bailian20231229 import models as bailian_20231229_models
from alibabacloud_tea_util import models as util_models
from alibabacloud_tea_util.client import Client as UtilClient
from src.utils.date_info import DateInfo

__name__ = "AliBL API"

class AliBLAPI:
    def __init__(self):
        pass

    @staticmethod
    def create_client() -> bailian20231229Client:
        """
        使用AK&SK初始化账号Client
        @return: Client
        @throws Exception
        """
        config = open_api_models.Config(
            access_key_id=ALIBABA_CLOUD_ACCESS_KEY_ID,
            access_key_secret=ALIBABA_CLOUD_ACCESS_KEY_SECRET
        )
        config.endpoint = f'bailian.cn-beijing.aliyuncs.com'
        return bailian20231229Client(config)

    @staticmethod
    async def Get_Ali_BL_Memory_Id(
        user_id : str,
        args: List[str]=sys.argv[1:],
    ) -> None:
        client = AliBLAPI.create_client()
        create_memory_request = bailian_20231229_models.CreateMemoryRequest(
            description="用户ID："+user_id,
        )
        runtime = util_models.RuntimeOptions()
        headers = {}
        try:
            msg = await client.create_memory_with_options_async(workspaceId, create_memory_request, headers, runtime)
            return msg.body.memory_id
        except Exception as error:
            logger.error(f"【阿里百练API服务】创建记忆失败: {error}")
            UtilClient.assert_as_string(error)
            return None
    
    @staticmethod
    async def Post_Ali_BL_chat_Api(
        session_id : str = None,
        content : str =  "空内容",
        memory_id : str = None,
        Like_value : int = 100) -> Dict[str, any]:
        """调用阿里百炼API进行聊天"""
        try:
            # 参数有效性校验
            if not memory_id:
                logger.error("【阿里百练API服务】memory_id不能为空")
                return {"session_id": session_id, "content": "", "error": "memory_id_required"}

            # 构造调用参数
            etime = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            date_info = DateInfo()
            week = date_info.get_weekday()
            is_holiday, holiday = date_info.check_holiday()

            call_params = {
                "api_key": ALI_KEY,
                "app_id": ALI_BLAPP_ID,
                "prompt": content,
                "memory_id" : memory_id,
                "workspace": workspaceId,
                "biz_params": {
                    "user_prompt_params":{
                        "Etime": etime,
                        "Weekday": week,
                        "Holiday": holiday,
                        "Like_value" : Like_value
                    }
                }
            }

            if session_id != None:
                call_params["session_id"] = session_id

            # 修复异步调用：将同步方法包装为异步执行
            loop = asyncio.get_event_loop()
            responses = await loop.run_in_executor(
                None,  # 使用默认的executor
                partial(Application.call, **call_params)  # 包装同步方法
            )

            # 响应处理
            if responses.status_code != HTTPStatus.OK:
                logger.error(
                    f"code={responses.status_code}, "
                    f"message={responses.message}, "
                    f"请参考文档：https://help.aliyun.com/zh/model-studio/developer-reference/error-code",
                    exc_info=True
                )
                logger.debug(f"【阿里百练API服务】构造参数: {call_params}")
                return {
                    "session_id": session_id,
                    "content": "",
                    "error": f"api_error_{responses.status_code}"
                }

            # 正常响应
            return {
                "session_id": responses.output.session_id,
                "content": responses.output.text or "",  # 防止None值
                "error": None
            }

        except Exception as error:
            # 链式异常处理
            logger.exception(
                f"【阿里百练API服务】调用异常: {error}", 
                exc_info=True
            )
            return {
                "session_id": session_id,
                "content": "",
                "error": str(error)
            }