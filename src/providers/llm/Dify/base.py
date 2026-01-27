from datetime import datetime
from typing import Dict, List, Optional
from src.providers.llm.Dify import DifyChatRoleLog, DifyChatRole
from src.providers.llm.Dify.Dify_API import DifyAPI
from src.providers.llm.elysiacmd import parse_elysia, get_elysia_commands
from nonebot import logger

__name__ = "Dify_Base"

async def _handle_new_user(user_id: str, content: str) -> str:
    """处理新用户"""
    # memory_id = await DifyAPI.Get_Memory_Id(user_id=user_id)
    # 暂时不启用记忆功能
    memory_id = "Memory"
    chat_msg = await DifyAPI.Post_chat_api(user_id=user_id, content=content, memory_id=memory_id)
    # 响应有效性校验
    if chat_msg.get("error") or not chat_msg.get("content"):
        error_msg = f"API调用失败: {chat_msg.get('error', '未知错误')}"
        logger.error(error_msg)
        return None
    is_session_id = chat_msg.get("session_id")
    r_msg = chat_msg.get("content")
    Edata = get_elysia_commands(r_msg)
    like_value = parse_elysia(Edata,field = "like_value")

    await DifyChatRoleLog.save_chat_log(
        user_id=user_id,
        user_content=content,
        assistant_content=r_msg
    )
    await DifyChatRole.create_chat_role(
        user_id=user_id,
        is_session_id=is_session_id,
        memory_id=memory_id,
        like_value=like_value
    )
    return r_msg

async def _handle_existing_user(user_id: str, content: str, user_msg) -> str:
    """处理已有用户"""
    try:
        memory_id = user_msg.memory_id
        is_session_id = user_msg.is_session_id
        Like_value = user_msg.like_value
        chat_msg = await DifyAPI.Post_chat_api(
            user_id=user_id,
            session_id=is_session_id,
            content=content,
            memory_id=memory_id,
            Like_value=Like_value
        )
        
        # 响应有效性校验
        if chat_msg.get("error") or not chat_msg.get("content"):
            error_msg = f"API调用失败: {chat_msg.get('error', '未知错误')}"
            logger.error(error_msg)
            return None
            
        # 正常处理流程
        r_msg = chat_msg.get("content")

        await DifyChatRoleLog.save_chat_log(
            user_id=user_id,
            user_content=content,
            assistant_content=r_msg
        )
        return r_msg
    except Exception as e:
        logger.exception(
            f"处理用户消息时发生异常: {str(e)}", 
            exc_info=True
        )
        return None

async def on_chat(user_id: str, content: str) -> Optional[str]:
    """处理用户聊天请求"""
    try:
        user_msg = await DifyChatRole.get_chat_role_by_user_id(user_id)
        
        if user_msg is None:
            r_msg = await _handle_new_user(user_id, content)
        else:
            r_msg = await _handle_existing_user(user_id, content, user_msg)
            
        logger.info(
            f"User {user_id} chat processed successfully. "
            f"Input: {content}, Output: {r_msg}"
        )
        return r_msg
        
    except Exception as e:
        logger.error(
            f"Error processing chat for user {user_id}. "
            f"Input: {content}, Error: {str(e)}"
        )
        return None
    
async def on_new_session_id(user_id: str) -> Optional[list[Dict[str, str]]]:
    """处理新建对话"""
    user_msg = await DifyChatRole.get_chat_role_by_user_id(user_id)
    if user_msg is None:
        return {"code":"None","msg":"你还没有聊过天哦~"}
    else:
        chat_msg = await DifyAPI.Post_chat_api(
            user_id=user_id,
            content="你好呀",
            memory_id=user_msg.memory_id,
            Like_value=user_msg.like_value) 
        is_session_id = chat_msg["session_id"]
        r_msg = chat_msg["content"]
        await DifyChatRole.update_chat_role_by_user_id(
            user_id=user_id,
            is_session_id=is_session_id
        )
        return {"code":True,"msg":r_msg}

async def on_new_memory_id(user_id: str) -> Optional[str]:
    """处理新记忆"""
    return "暂未启用记忆功能"
    
    # 暂未启用记忆功能
    user_msg = await DifyChatRole.get_chat_role_by_user_id(user_id)
    if user_msg is None:
        return "你还没有聊过天哦~"
    else:
        memory_id = await DifyAPI.Get_Memory_Id(user_id=user_id)
        await DifyChatRole.update_chat_role_by_user_id(
            user_id=user_id,
            memory_id=memory_id
        )
        return True