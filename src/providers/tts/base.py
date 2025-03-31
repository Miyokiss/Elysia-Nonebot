import os
from abc import ABC, abstractmethod
from src.utils.tts import MarkdownCleaner
from loguru import logger

__name__="TTS_base"

class TTSProviderBase(ABC):
    def __init__(self, config):
        self.output_file = config.get("output_dir")

    @abstractmethod
    def generate_fileinfo(self):
        """
        返回文件信息
        :param extension: 文件扩展名

        :return: {
            "file_path": "文件路径",
            "file_name": "文件名",
            }
        """
        pass

    async def to_tts(self, text):
        """
        生成语音文件
        :param text: 文本内容
        :return: {
            "file_path": "文件路径",
            "file_name": "文件名",
            }
        """
        tmp_file = self.generate_fileinfo()["file_path"]
        file_name = self.generate_fileinfo()["file_name"]
        logger.info(f"Generating TTS :\ntext：{text}tmp_file：:{tmp_file}file_name：{file_name}")
        try:
            max_repeat_time = 5
            text = MarkdownCleaner.clean_markdown(text)
            while not os.path.exists(tmp_file) and max_repeat_time > 0:
                await self.text_to_speak(text, tmp_file)
                if not os.path.exists(tmp_file):
                    max_repeat_time = max_repeat_time - 1
                    logger.error(f"语音生成失败: {text}:{tmp_file}，再试{max_repeat_time}次")

            if max_repeat_time > 0:
                logger.info(f"语音生成成功: {text}:{tmp_file}，重试{5 - max_repeat_time}次")

            return {
                "file_path": tmp_file,
                "file_name": file_name
            }
        except Exception as e:
            logger.info(f"Failed to generate TTS file: {e}")
            return None

    @abstractmethod
    async def text_to_speak(self, text, output_file):
        pass
