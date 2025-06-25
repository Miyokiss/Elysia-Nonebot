import os
import re
from loguru import logger
from datetime import datetime
from typing import Optional, Tuple, List
from src.providers.llm.AliBL import BLChatRole

class LLMWAF:
    def __init__(self):
        """初始化违禁词库"""
        self.bad_words = {
            'Banned': self._load_bad_words('Banned.txt'),
            'Non_replying': self._load_bad_words('Non_replying.txt')
        }

    async def process(self, user_id: str, text: str) -> tuple[bool, str | None]:
        """
        处理内容过滤
        返回是否允许继续处理和封禁原因
        """
        # 先检查用户是否被封禁
        if await self.check_user_ban_status(user_id):
            logger.info(f"用户 {user_id} 已被封禁，阻止处理")
            return True, "用户已被封禁"

        bad_type, word = self.check_content(text)
        
        if bad_type == 'Banned':
            return await self.handle_Banned(user_id, word)
            
        elif bad_type == 'Non_replying':
            return True, f"检测到过滤词：{word}"
            
        return False, "正常"

    async def handle_Banned(self, user_id: str, word: str) -> bool:
        """封禁逻辑"""
        try:
            logger.info(f"检测到封禁信息：用户{user_id} 输入包含 '{word}'")
            # 更新用户封禁状态
            await BLChatRole.update_ban_status(user_id, True, word)
            return True, f"封禁成功 包含：{word}"
        except Exception as e:
            logger.error(f"封禁用户失败: {str(e)}", exc_info=True)
            return False, f"封禁失败:{word}"

    async def check_user_ban_status(self, user_id: str) -> bool:
        """
        检查用户是否被封禁
        :param user_id: 用户ID
        :return: 是否被封禁
        """
        try:
            chat_role = await BLChatRole.get_chat_role_by_user_id(user_id)
            if chat_role and chat_role.is_banned:
                logger.info(f"用户 {user_id} 当前处于封禁状态")
                return True
            return False
        except Exception as e:
            logger.error(f"检查封禁状态失败: {str(e)}", exc_info=True)
            return False

    async def get_ban_reason(self, user_id: str) -> str:
        """
        获取用户封禁原因和时间
        :param user_id: 用户ID
        :return: 格式化的封禁原因（包含时间和具体原因）
        """
        try:
            chat_role = await BLChatRole.get_chat_role_by_user_id(user_id)
            if chat_role and chat_role.is_banned:
                ban_time = datetime.fromtimestamp(chat_role.ban_time) if chat_role.ban_time else '未知时间'
                ban_r = chat_role.ban_reason
                ban_reason = ban_r[:len(ban_r) // 2] + "*" * (len(ban_r) // 2)
                return f"存在违规内容：{ban_reason}（{ban_time}）"
            return None
        except Exception as e:
            logger.error(f"检查封禁状态失败: {str(e)}", exc_info=True)
            return None

    def _load_bad_words(self, filename: str) -> List[str]:
        """加载违禁词"""
        filepath = os.path.join(os.path.dirname(__file__), filename)
        with open(filepath, 'r', encoding='utf-8') as file:
            return [line.strip() for line in file.readlines()]

    def check_content(self, text: str) -> Tuple[str, str]:
        """检查内容"""
        if (result := self.check_Banned(text)):
            return 'Banned', result[0]
        if (result := self.check_Non_replying(text)):
            return 'Non_replying', result[0]
        return '', ''

    def check_Banned(self, text: str) -> Optional[Tuple[str, str]]:
        """检查封禁信息"""
        return self._check(text, self.bad_words['Banned'])

    def check_Non_replying(self, text: str) -> Optional[Tuple[str, str]]:
        """检查非回复信息"""
        return self._check(text, self.bad_words['Non_replying'])

    def _check(self, text: str, words: List[str]) -> Optional[Tuple[str, str]]:
        """检查文本中是否包含违禁词"""
        for word in words:
            if re.search(re.escape(word), text, re.IGNORECASE):
                return word, text
        return None
