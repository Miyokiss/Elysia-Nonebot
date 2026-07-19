app_id="" # 上线前 配置 正确 Bot_ID 号
bot_account= "" # 上线前 配置 正确 QQ 号

"""
自建邮箱配置
"""
server_smtp_server = "example.com"
server_email = ""
server_password = "xxx"
server_port = 587

"""
图床配置
"""
# SMMS图床相关配置
smms_token= "<KEY>"  # sm.ms图床的token
smms_image_upload_history= "https://sm.ms/api/v2/upload_history"  # sm.ms图床获取上传图片历史API地址

# 聚合图床相关配置
ju_he_token= "<KEY>"  # 聚合图床的token
ju_he_image_list= "https://api.superbed.cn/timeline"  # 聚合图床获取上传图片历史API地址

#随机图 anosu
anosu_url = "https://image.anosu.top/pixiv/json"
#随机图 岁月小筑 API
xjh_url = "https://img.xjh.me/random_img.php?return=json"

# 搜番/acg api
animetrace_url = "https://api.animetrace.com/v1/search"

"""
生图 API 配置
"""
# 生产环境应使用 HTTPS；HTTP 仅适用于完全可信的本地或内网服务。
# GPT 生图、Seedream 生图和生图助手可以指向不同的兼容端点并使用独立密钥。
image_generation_gpt_base_url = "http://127.0.0.1:3000"
image_generation_gpt_api_key = "<KEY>"
image_generation_gpt_model = "gpt-image-2"

image_generation_seedream_base_url = "http://127.0.0.1:3000"
image_generation_seedream_api_key = "<KEY>"
image_generation_seedream_model = "doubao-seedream-5-0-260128"

# 用户未指定单次分辨率时使用：GPT 支持 auto 或有效的 WxH
image_generation_size = "1024x1024"
# Seedream 支持 auto、1K、2K、4K 或宽高均不超过 4096px 的 WxH
image_generation_seedream_size = "2K"
image_generation_timeout = 300.0
image_generation_max_concurrency = 2
image_generation_user_cooldown = 60.0
image_generation_daily_user_limit = 10

image_prompt_assistant_base_url = "http://127.0.0.1:3000"
image_prompt_assistant_api_key = "<KEY>"
image_prompt_assistant_model = "gpt-5.6-terra"
# 安全判定和提示词生成两个阶段共享的总时间预算；瞬时故障会在预算内重试一次。
image_prompt_assistant_timeout = 120.0
image_prompt_assistant_max_concurrency = 3
image_prompt_assistant_user_cooldown = 15.0
image_prompt_assistant_daily_user_limit = 20

"""
生视频 API 配置
"""
# New API 兼容端点；真实密钥只应写入本地 api_config.py。
video_generation_base_url = "http://127.0.0.1:3000"
video_generation_api_key = "<KEY>"
video_generation_model = "Seedance2.0"
# Seedance 2.0 固定输出时长，支持 4-15 秒。
video_generation_duration = 5
video_generation_timeout = 900.0
video_generation_poll_interval = 5.0
video_generation_max_concurrency = 1
video_generation_user_cooldown = 300.0
video_generation_daily_user_limit = 3

"""
AI
"""
admin_password= "123456" # 默认注册管理员密码
# 图灵机器人相关配置
v3url= "https://api.vveai.com/v1/chat/completions"
v3key= "<KEY>"
# DeepSeek相关配置
deepseek_url= "https://api.deepseek.com"
deepseek_key= "<KEY>"
# 阿里百炼API相关配置
ALI_KEY= "<KEY>"
ALI_BLAPP_ID= "<ID>"

ALIBABA_CLOUD_ACCESS_KEY_ID = "<KEY>"
ALIBABA_CLOUD_ACCESS_KEY_SECRET = "<KEY>"
workspaceId= "your_workspace_id" # 阿里百炼工作空间ID

#硅基流动
silicon_flow_key = "<KEY>"

"""
Dify配置
"""
# Dify API Key (使用必填)
dify_api_key = "app-XXX"  # 请替换为实际的API Key
# Dify Base URL (使用必填)
dify_base_url = "http://127.0.0.1/v1"

"""
Memobase配置
"""
Memobase_ACCESS_TOKEN = "XXX"  # 请替换为实际的API token
Memobase_API_Url = "http://192.168.5.31:8019"  # 请替换为实际的服务地址


"""
Wenku8账号
"""
wenku8_username = "<user_name>"
wenku8_password = "<passwd>"

"""
多米HTTP代理api
"""
proxy_api_enabled = True  # False 时 Wenku8 直接连接，不请求代理 API
proxy_api = "<KEY>"

"""
二维码生成 API 参数
"""
qrserver_url = "https://api.qrserver.com/v1/create-qr-code/"
qrserver_size= "200x200"

"""
爱发电API
"""
afdian_user_id = "your_afdian_user_id"
afdian_token = "your_afdian_token"

"""
openlist配置
"""
url: str = "https://XXX.com"  # 替换为你的Openlist实例URL
openlist_storage_file_path: str = "/BOT/" # 替换为你希望存储文件的路径
username: str = ""
password: str = "" # 需要请求API的password字段

"""
Boto3配置
"""
endpoint_url = "https://xxx.com"
aws_access_key_id = "key"
aws_secret_access_key = "access_key"
signature_version = "s3v4"
bucket_name = ""
