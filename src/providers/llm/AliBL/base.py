from datetime import datetime
from typing import Dict, List, Optional
from src.providers.llm.AliBL import BLChatRole
from src.providers.llm.AliBL.AliBL_API import AliBLAPI
from nonebot import logger

__name__ = "AliBL_Base"

async def _create_chat_log(user_content: str, assistant_content: str) -> List[Dict[str, str]]:
    """创建聊天记录"""
    return [
        {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "role": "user",
            "content": user_content
        },
        {
            "role": "assistant",
            "content": assistant_content
        }
    ]

async def _handle_new_user(user_id: str, content: str) -> str:
    """处理新用户"""
    content = ""
    memory_id = await AliBLAPI.Get_Ali_BL_Memory_Id(user_id=user_id)
    chat_msg = await AliBLAPI.Post_Ali_BL_chat_Api()
    is_session_id = chat_msg["session_id"]
    r_msg = chat_msg["content"]
    
    chat_logs_msg = await _create_chat_log(content, r_msg)
    await BLChatRole.create_chat_role(
        user_id=user_id,
        is_session_id=is_session_id,
        memory_id=memory_id,
        chat_logs=chat_logs_msg
    )
    return r_msg

async def _handle_existing_user(user_id: str, content: str, user_msg) -> str:
    """处理已有用户"""
    memory_id = user_msg.memory_id
    is_session_id = user_msg.is_session_id
    chat_msg = await AliBLAPI.Post_Ali_BL_chat_Api(
        session_id=is_session_id,
        content=content,
        memory_id=memory_id
    )
    r_msg = chat_msg["content"]
    
    chat_logs_msg = await _create_chat_log(content, r_msg)
    await BLChatRole.save_chat_logs_role_by_user_id(
        user_id=user_id,
        content=chat_logs_msg
    )
    return r_msg

async def on_bl_chat(user_id: str, content: str) -> Optional[str]:
    """处理用户聊天请求"""
    try:
        user_msg = await BLChatRole.get_chat_role_by_user_id(user_id)
        
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
    
async def on_bl_new_session_id(user_id: str) -> Optional[list[Dict[str, str]]]:
    """处理新建对话"""
    user_msg = await BLChatRole.get_chat_role_by_user_id(user_id)
    if user_msg is None:
        return {"code":"None","msg":"你还没有聊过天哦~"}
    else:
        chat_msg = await AliBLAPI.Post_Ali_BL_chat_Api()
        is_session_id = chat_msg["session_id"]
        r_msg = chat_msg["content"]
        await BLChatRole.update_chat_role_by_user_id(
            user_id=user_id,
            is_session_id=is_session_id
        )
        return {"code":True,"msg":r_msg}

async def on_bl_new_memory_id(user_id: str) -> Optional[str]:
    """处理新记忆"""
    user_msg = await BLChatRole.get_chat_role_by_user_id(user_id)
    if user_msg is None:
        return "你还没有聊过天哦~"
    else:
        memory_id = await AliBLAPI.Get_Ali_BL_Memory_Id(user_id=user_id)
        await BLChatRole.update_chat_role_by_user_id(
            user_id=user_id,
            memory_id=memory_id
        )
        return True