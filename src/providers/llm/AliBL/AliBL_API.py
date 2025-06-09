import sys
from datetime import datetime
from typing import List
from nonebot import logger
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
        memory_id : str = None) -> list:
        """调用阿里百炼API进行聊天"""
        # 构造调用参数
        etime = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        call_params = {
            "api_key": ALI_KEY,
            "app_id": ALI_BLAPP_ID,
            "prompt": content,
            "workspace": workspaceId,
            "biz_params": {
                "user_prompt_params":{
                    "Etime": etime
                }
            }
        }
        if session_id!=None:
            call_params["session_id"] = session_id
        if memory_id!=None:
            call_params["memory_id"] = memory_id
        # 调用API
        responses = Application.call(**call_params)
        if responses.status_code != HTTPStatus.OK:
            logger.error(
                f"code={responses.status_code}, "
                f"message={responses.message}, "
                f"请参考文档：https://help.aliyun.com/zh/model-studio/developer-reference/error-code"
            )
            logger.debug(f"【阿里百练API服务】构造参数: {call_params}")
            return "【阿里百练API服务响应异常】"
        else:
            reply_content = {
                "session_id": responses.output.session_id,
                "content": responses.output.text
            }
            logger.debug(f"【阿里百练API服务】响应结果: {reply_content}")
            return reply_content