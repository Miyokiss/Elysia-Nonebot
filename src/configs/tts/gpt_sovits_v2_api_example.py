from src.configs.path_config import AUDIO_TEMP_PATH

def get_config():
    return{
                'url': "your_api_url",
                'output_dir': AUDIO_TEMP_PATH,
                'text_lang': "auto",
                'ref_audio_path': "参考音频.wav",
                'prompt_text': "参考音频文本",
                'prompt_lang': "zh",
                'top_k': 5,
                'top_p': 1,
                'temperature': 1,
                'text_split_method': "cut0",
                'batch_size': 1,
                'batch_threshold': 0.75,
                'split_bucket': 'true',
                'return_fragment': 'false',
                'speed_factor': 1.0,
                'streaming_mode': 'false',
                'seed': -1,
                'parallel_infer': 'true',
                'repetition_penalty': 1.35,
                'aux_ref_audio_paths': []
            }