from http import HTTPStatus
from dashscope import Application
from src.clover_sqlite.models.chat import GroupChatRole
from nonebot import logger
from src.configs.api_config import ALI_KEY,ALI_BLAPP_ID

__name__ = "AliBL API"

async def Ali_BL_Api(group_openid, content):
    await GroupChatRole.save_super_chat_history(group_openid, {"role": "user", "content": content})
    messages = await GroupChatRole.get_super_chat_history(group_openid)
    # 构造调用参数
    call_params = {
        "api_key": ALI_KEY,
        "app_id": ALI_BLAPP_ID,
        #"session_id": session_id,
        "messages": messages
    }
    
    #call_params["memory_id"] = 
    #call_params["prompt"] = content
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
        reply_content = responses.output.text
        logger.debug(f"【阿里百练API服务】响应结果: {reply_content}")
        await GroupChatRole.save_super_chat_history(group_openid, {"role": "assistant", "content": reply_content})
        return reply_content