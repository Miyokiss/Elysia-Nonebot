import asyncio
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
            logger.error(f"Upload Error: {str(e)}")
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
                'url': 'https://ydc1-d.kuku.lu/upload.php'
            }
        }
        uploader = Kukufile()
        uploader.upload_queue.append(upload_task)
        return await uploader.start_upload(0)
        
    async def auto_delete_kukufile(hash : str, time : int):
        """定时删除文件\n
        :param hash: 文件hash\n
        :param time: 多久后删除、单位秒\n
        """
        headers = {
         'cookie':'cf_clearance=qTaH1Ne.F75jqbQeXwLIq2xAwpxhucg87JyXdEeAaAA-1751754281-1.2.1.1-YyntzTHf64T0A86O1IW4oqskEF0ebeKzeOmFGhVsDesVgmfTKCIF91XHRmUD0_GZ_SMh925ArYpbCbhYE8XbgM8ZHGwHPi2SWHwrNbc7zL4ASuk9rfteJN4HLxCcEhO6CRxtmKqV9Nh6JRpUR_TXLTxI2tPGpDwpMuTeuxrlmIpssaef75y7J6kEWA0wyV_YOiAcitXg1qA.mGJlDgz2g50PjqS0kCCOuLTr5lcNYwI; _ga=GA1.1.1061375737.1751754298; _ga_HMG13DJCGJ=GS2.1.s1751754297$o1$g1$t1751754313$j44$l0$h0; ua_ipados=; cookie_uid=ab896e383ba9831e5ad48189a2407062; ua_ipados=; _ga_MY7WC5RXVN=GS2.1.s1751885434$o1$g1$t1751885705$j57$l0$h0; ffucs=KDMyYykoMjU2MHgxNDQwKSggTlZJRElBTlZJRElBLCBOVklESUEgR2VGb3JjZSBSVFggNDA3MCBMYXB0b3AgR1BVIDB4MDAwMDI4NjAgRGlyZWN0M0QxMSB2c181XzAgcHNfNV8wLCBEM0QxMSk%3D; __gads=ID=b7f242567b7f19bb:T=1751754283:RT=1751888033:S=ALNI_Mb4Z1Iz-tumsT7kF-buE6wPv55KiQ; __gpi=UID=0000114b4adb02ad:T=1751754283:RT=1751888033:S=ALNI_MbcqjCEQRFg4fK2Sakc-lJIHhrQEA; __eoi=ID=7bd732fb18f29cbc:T=1751754283:RT=1751888033:S=AA-AfjbEbwbeFo-LTujZCtIQ9Aux; _ga_SVPVLB6BB7=GS2.1.s1751885437$o2$g1$t1751888251$j60$l0$h0; FCNEC=%5B%5B%22AKsRol8eipYEdtJ5zr7sWmxse0lWcb2sMZu1yRntxK1MfzR-3O7yQSHLmu-j6MxSez7CsYxBm-4zS1CCXoJbuamNZZpQ0lJ5uhhiS8BrYMF21PtkmuWeOfHaMDIb5mkboNFUHiuujkAKgx2C7MLXiuZCSMKVIjs0cQ%3D%3D%22%5D%5D'
         }
        payload = {
            "action": "addTimelimit",
            "set_timelimit": time
        }

        response = requests.request("POST", f"https://d.kuku.lu/view.php?hash={hash}", headers=headers, data=payload)
        if response.status_code == 200:
            logger.debug(f"Response Status Code: {response.status_code} Response: {response.text}")
            return response.text
        else:
            raise Exception(f"文件设定删除失败，状态码：{response.status_code} Response: {response.text}")   