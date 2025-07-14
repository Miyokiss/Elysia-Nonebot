# https://github.com/maxesisn/nonebot_plugin_songpicker2/blob/master/nonebot_plugin_songpicker2/data_source.py

import httpx
import time

class DataApi():
    '''
    从网易云音乐接口直接获取数据（实验性）
    '''
    headers = {"referer": "http://music.163.com"}
    cookies = {"appver": "2.0.2"}

    async def getHotComments(self, song_id: int):
        '''
        获取热评
        '''
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"https://music.163.com/weapi/v1/resource/hotcomments/R_SO_4_{song_id}?csrf_token=",
                data={
                    # 不知道从哪毛来的key
                    "params": 'D33zyir4L/58v1qGPcIPjSee79KCzxBIBy507IYDB8EL7jEnp41aDIqpHBhowfQ6iT1Xoka8jD+0p44nRKNKUA0dv+n5RWPOO57dZLVrd+T1J/sNrTdzUhdHhoKRIgegVcXYjYu+CshdtCBe6WEJozBRlaHyLeJtGrABfMOEb4PqgI3h/uELC82S05NtewlbLZ3TOR/TIIhNV6hVTtqHDVHjkekrvEmJzT5pk1UY6r0=',
                    "encSecKey": '45c8bcb07e69c6b545d3045559bd300db897509b8720ee2b45a72bf2d3b216ddc77fb10daec4ca54b466f2da1ffac1e67e245fea9d842589dc402b92b262d3495b12165a721aed880bf09a0a99ff94c959d04e49085dc21c78bbbe8e3331827c0ef0035519e89f097511065643120cbc478f9c0af96400ba4649265781fc9079'
                },
                headers=self.headers,
                cookies=self.cookies
            )
        jsonified_r = r.json()
        if "hotComments" not in jsonified_r:
            raise APINotWorkingException(r.text)
        return jsonified_r

class DataGet(DataApi):
    '''
    从dataApi获取数据，并做简单处理
    '''

    api = DataApi()
    async def song_comments(self, song_id: int, amount=3) -> dict:
        '''
        根据传递的单一song_id，获取song_comments dict [默认评论数量上限：3]
        '''
        song_comments = []
        r = await self.api.getHotComments(song_id)
        comments_range = amount if amount < len(
            r['hotComments']) else len(r['hotComments'])
        for i in range(comments_range):
            # 获取头像
            avatar = r['hotComments'][i]['user']['avatarUrl']
            # 获取昵称
            nickname = r['hotComments'][i]['user']['nickname']
            # 获取评论内容
            content = r['hotComments'][i]['content']
            # 获取评论时间
            r_time = r['hotComments'][i]['time']
            # 获取点赞数
            liked_count = r['hotComments'][i]['likedCount']

            if not isinstance(r_time, (int, float)) or r_time <= 0:
                raise ValueError(f"Invalid timestamp: {r_time}")
            time_struct = time.localtime(r_time / 1000 if r_time > 1e12 else r_time)
                
            song_comments.append({
                "avatar": avatar,
                "nickname": nickname,
                "content": content,
                "time": time.strftime("%Y年%m月%d日", time_struct),
                "liked_count": liked_count
            })
        return song_comments

class APINotWorkingException(Exception):
    def __init__(self, wrongData):
        self.uniExceptionTip = "网易云音乐接口返回了意料之外的数据：\n"
        self.wrongData = wrongData

    def __str__(self):
        return self.uniExceptionTip+self.wrongData
    

if __name__ == "__main__":
    import asyncio
    async def main():
        data_get = DataGet()
        comments = await data_get.song_comments(1971144923)
        print(comments)

    asyncio.run(main())
