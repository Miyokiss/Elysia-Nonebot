import requests
from nonebot import logger

__name__ = 'Kukufile Api'

class Kukufile:
    def __init__(self):
        self.upload_queue = []
        self.upload_cancel = False

    async def start_upload(self, queue_pos):
        task = self.upload_queue[queue_pos]

        method = task['server']['method'].lower()
        file_path = task['filepath']
        file_name = task['filename']
        uuid = task['uuid']
        server_url = task['server']['url']

        try:
            if method == 'post':
                with open(file_path, 'rb') as file_data:
                    files = {
                        'file_1': file_data.read()
                        }
                    data = {
                        'ajax': '1',
                        'uuid': uuid,
                        'country': 'HK',
                        'filecnt': 1,
                        "file_1_name" : file_name,
                    }
                    logger.debug(f"Request Data: {file_data}")
                    response = requests.post(server_url, files=files, data=data)
                
            elif method == 'put':
                with open(file_path, 'rb') as file_data:
                    headers = {'Content-Type': 'application/octet-stream'}
                    response = requests.put(server_url, data=file_data.read(), headers=headers)
                
            logger.debug(f"Response Status Code: {response.status_code}")
            logger.debug(f"Server Response: {response.text}")
            if response.status_code == 200:
                r_msg = response.text.split("OK:")
                r_msg[0] = "OK"
            else:
                r_msg = response.text.split("NG:")
                r_msg[0] = "NG"
            return r_msg
        except Exception as e:
            print(f"Upload Error: {str(e)}")
            task['status'] = 'error'
    async def upload_file(file_path, file_name: str = None):
        """上传文件\n
        :param file_path: 上传文件绝对路径\n
        :param file_name: 显示文件名\n
        """
        # POST方式上传文件
        # Your user key jh4t rr2h 42fc
        upload_task = {
            'id': 0,
            'uuid': 'ab896e383ba9831e5ad48189a2407062',
            'filepath': file_path,
            'filename': file_name,
            'server': {
                'method': 'post',
                'url': 'https://file203-d.kuku.lu/upload.php'
            }
        }
        uploader = Kukufile()
        uploader.upload_queue.append(upload_task)
        return await uploader.start_upload(0)