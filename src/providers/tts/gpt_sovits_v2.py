import os
import uuid
import requests
from nonebot import logger
from datetime import datetime
from src.configs.tts import gpt_sovits_v2_api
from src.providers.tts.base import TTSProviderBase

__name__ = "GPT_SoVITS_V2"

class TTSProvider(TTSProviderBase):
    def __init__(self, config=gpt_sovits_v2_api.get_config()):
        super().__init__(config)
        self.url = config.get("url")
        self.text_lang = config.get("text_lang", "zh")
        self.ref_audio_path = config.get("ref_audio_path")
        self.prompt_text = config.get("prompt_text")
        self.prompt_lang = config.get("prompt_lang", "zh")
        self.top_k = config.get("top_k", 5)
        self.top_p = config.get("top_p", 1)
        self.temperature = config.get("temperature", 1)
        self.text_split_method = config.get("text_split_method", "cut0")
        self.batch_size = config.get("batch_size", 1)
        self.batch_threshold = config.get("batch_threshold", 0.75)
        self.split_bucket = config.get("split_bucket", True)
        self.speed_factor = config.get("speed_factor", 1.0)
        self.streaming_mode = config.get("streaming_mode", False)
        self.seed = config.get("seed", -1)
        self.parallel_infer = config.get("parallel_infer", True)
        self.repetition_penalty = config.get("repetition_penalty", 1.35)
        self.aux_ref_audio_paths = config.get("aux_ref_audio_paths", [])
        self.sample_steps = config.get("sample_steps", 32)
        self.super_sampling = config.get("super_sampling", False)

    def generate_fileinfo(self, extension=".wav"):
        """
        返回文件信息
        :param extension: 文件扩展名

        :return: {
            "file_path": "文件路径",
            "file_name": "文件名",
            }
        """
        file_name = f"tts-{datetime.now().date()}@{uuid.uuid4().hex}{extension}"
        return {
            "file_path": os.path.join(self.output_file,file_name),
            "file_name": file_name,
        }

    async def text_to_speak(self, text, output_file):
        request_json = {
            "text": text,
            "text_lang": self.text_lang,
            "ref_audio_path": self.ref_audio_path,
            "aux_ref_audio_paths": self.aux_ref_audio_paths,
            "prompt_text": self.prompt_text,
            "prompt_lang": self.prompt_lang,
            "top_k": self.top_k,
            "top_p": self.top_p,
            "temperature": self.temperature,
            "text_split_method": self.text_split_method,
            "batch_size": self.batch_size,
            "batch_threshold": self.batch_threshold,
            "split_bucket": self.split_bucket,
            "speed_factor": self.speed_factor,
            "streaming_mode": self.streaming_mode,
            "seed": self.seed,
            "parallel_infer": self.parallel_infer,
            "repetition_penalty": self.repetition_penalty,
            "sample_steps": self.sample_steps,
            "super_sampling": self.super_sampling,
        }

        resp = requests.post(self.url, json=request_json)
        if resp.status_code == 200:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, "wb") as file:
                file.write(resp.content)
        else:
            logger.error(f"GPT_SoVITS_V2 TTS请求失败: {resp.status_code} - {resp.text}")
