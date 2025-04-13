import os
from pathlib import Path

path = os.getcwd()+'/src/resources'


# 塔罗牌图片路径
image_local_qq_image_path =  path+'/image/qq_image'
os.makedirs(image_local_qq_image_path, exist_ok=True)
# 本地图片路径
image_local_path= path+"/image/Elysia"
os.makedirs(image_local_path, exist_ok=True)
# 塔罗牌图片路径
tarots_img_path = path+'/image/tarot/TarotImages/'
os.makedirs(tarots_img_path, exist_ok=True)
# 摸摸头图片路径
rua_png = path+'/image/rua/'
os.makedirs(rua_png, exist_ok=True)
# 喜报、悲报图片路径
good_bad = path+'/image/good_bad_news/'
os.makedirs(good_bad, exist_ok=True)
#谁说 生成图片路径
who_say_path = path+'/image/who_say/'
os.makedirs(who_say_path, exist_ok=True)
#yuc_wiki 动漫wiki
yuc_wiki_path = path + '/image/yuc_wiki/'
os.makedirs(yuc_wiki_path, exist_ok=True)
# 字体路径
font_path = path + '/font/'
os.makedirs(font_path, exist_ok=True)
# 临时数据路径
temp_path = path + '/temp/'
os.makedirs(temp_path, exist_ok=True)
# JM下载位置
jm_path = path + '/image/jm/'
os.makedirs(jm_path, exist_ok=True)
# 日志路径
log_path = path+'/log/'
os.makedirs(log_path, exist_ok=True)
# 视频路径
video_path = path+'/video/'
os.makedirs(video_path, exist_ok=True)

#jm配置文件路径
jm_config_path = os.getcwd()+'/src/configs/jm_config.yml'

# 语音路径
AUDIO_TEMP_PATH = path+'/aduio/'
os.makedirs(video_path, exist_ok=True)
# # 文本路径
# TEXT_PATH = Path() / "src" / "resources" / "text"
# # 数据路径
# DATA_PATH = Path() / "src" / "data"
# # 网页模板路径
# TEMPLATE_PATH = Path() / "src" / "resources" / "template"
# # 视频路径
# VIDEO_PATH = Path() / "src" / "resources" / "videos"