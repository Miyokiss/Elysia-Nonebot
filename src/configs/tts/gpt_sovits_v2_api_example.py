from src.configs.path_config import temp_path

def get_config():
    return{
                'url': "your_api_url",
                'output_dir': temp_path,
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
                'split_bucket': True,
                'speed_factor': 1.0,
                'streaming_mode': False,
                'seed': -1,
                'parallel_infer': True,
                'repetition_penalty': 1.35,
                'sample_steps': 32,
                'super_sampling': False,
                'aux_ref_audio_paths': []
            }

def get_tone_config(tone):
    tone_lists = {
        '普通': {
            'path': '参考音频.wav',
            'text': '参考音频文本'
        }
    }
    return tone_lists.get(tone, "普通")