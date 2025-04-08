import requests
from nonebot import logger

__name__ = 'Anonfile Api'

async def upload_file(file_path):
    """
    ### 上传文件到anonfile并返回 \n
    :param file_path: 上传文件路径
    :return: {\n
      "success": true,\n
      "code": "文件码",\n
      "message": "File uploaded successfully",\n
      "isProtected": fales\n
    }
    ### GET获取文件信息:
    https://anonfile.io/f/{ 文件码 }

    ### GET下载文件:
    https://anonfile.io/api/download/{ 文件码 }
    """
    try:
        # 创建Data对象并添加文件
        files = {'file': open(file_path, 'rb')}
        
        upload_settings = {
            'password': '',  # 密码
            'expiryDays': 7,   # 过期天数 7、30
        }
        
        # 如果设置了密码和过期天数，则添加到Data中
        data = {}
        if upload_settings['password']:
            data['password'] = upload_settings['password']
        data['expiryDays'] = str(upload_settings['expiryDays'])

        # 发送上传请求
        response = requests.post('https://anonfile.io/api/upload', files=files, data=data)
        
        # 检查响应状态码
        if response.status_code == 200:
            return response.json()
        else:
            logger.error('Upload failed:', response.status_code, response.text)

    except Exception as error:
        # 捕获并处理上传过程中的错误
        logger.error('Upload error:', error)