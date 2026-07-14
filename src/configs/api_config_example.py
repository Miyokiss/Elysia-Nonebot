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
