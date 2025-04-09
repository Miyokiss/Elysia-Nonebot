import requests
from nonebot.plugin import on_command
from nonebot.rule import to_me
from nonebot.adapters.qq import Message, MessageEvent, MessageSegment
from pathlib import Path

from src.clover_sqlite.models.codeforces import CodeForces
from src.configs.path_config import path, rating_path
from src.clover_sqlite.models.user import UserList
from datetime import datetime
import matplotlib.pyplot as plt

cf_query = on_command("cf", rule=to_me(), priority=10, block=True)
@cf_query.handle()
async def get_cf_rounds():
    await cf_query.send("正在为您整理近期比赛信息哦~\n请稍等💭💡🎈")
    try:
        result = requests.get('https://codeforces.com/api/contest.list?gym=false').json()
    except BaseException:
        await cf_query.finish("API请求失败，这绝对不是咱的错，绝对不是！")
    all_matches = ""
    for matches in result['result']:
        phase = get_match_phase(matches["phase"])
        one_match = ("\n比赛：" + str(matches["name"]) + "\n状态：" + phase + "\n时长：" + str(int(matches["durationSeconds"]) / 3600) +"h\n")
        all_matches = "".join([all_matches, one_match])
        if phase == "未开始":
            until_start_time_min = 0 - int(matches["relativeTimeSeconds"]) / 60
            until_start = get_until_start_time(until_start_time_min)
            all_matches = "".join([all_matches, until_start])
        if matches["phase"] == "FINISHED":
            break

    cf_image_path = path + "/image/codeforces/cfContestQR.png"
    msg = Message([
        MessageSegment.file_image(Path(cf_image_path)),
        MessageSegment.text(all_matches),
    ])

    await cf_query.finish(msg)


cf_ratings = on_command("cfrt", rule=to_me(), priority=10, block=True)
@cf_ratings.handle()
async def get_cf_ratings(message: MessageEvent):
    content = message.get_plaintext().strip().split(" ")
    if len(content) > 1:
        status = await CodeForces.insert_cf_id(content[1], message.get_user_id())
        if status == 1:
            await cf_ratings.send(f"成功将cf账号换绑为{content[1]}🥳")
        elif status == 0:
            await cf_ratings.send(f"成功绑定cf账号{content[1]}🎉")
        else:
            await cf_ratings.finish(f"出现未知错误，我也不知道啥原因，但是能触发这个没什么用的异常也挺厉害的。")

    cf_id = await CodeForces.get_cf_id(message.author.id)
    if cf_id:
        await cf_ratings.send("正在查询CodeForces Rating，请稍后👀")
        try:
            results = requests.get("https://codeforces.com/api/user.rating?handle={}".format(cf_id)).json()
        except BaseException:
            await cf_ratings.finish("API请求失败，这绝对不是咱的错，绝对不是！")

        if results["status"] != "OK":
            await  cf_ratings.finish(f"未查询到该用户的信息哦，请检查用户名{cf_id}是否正确💦\n可使用 /cfrt+用户名 换绑")

        # 准备绘图数据
        timestamps = []
        ratings = []
        # 遍历所有比赛记录
        for result in results["result"]:
            # 提取时间戳和rating数据
            timestamps.append(result["ratingUpdateTimeSeconds"])
            ratings.append(result["newRating"])

        if not timestamps:
            await cf_ratings.finish("未找到Rating变化记录哦~")

            # 转换时间戳为日期格式
        dates = [datetime.fromtimestamp(ts) for ts in timestamps]

        # 创建图表
        plt.figure(figsize=(12, 6))
        plt.plot(
                dates,
                ratings,
                marker='o',
                linestyle='-',
                color='#2196F3',
                linewidth=2,
                markersize=6,
                label='CF Rating'
        )

        # 美化图表
        plt.title(f'Codeforces Rating Trend ({cf_id})', fontsize=14)
        plt.xlabel('Contest Time', fontsize=12)
        plt.ylabel('Rating', fontsize=12)
        plt.grid(True, linestyle='--', alpha=0.7)

        # 自动旋转日期标签
        plt.gcf().autofmt_xdate()

        # 添加最新分数标注
        last_rating = ratings[-1]
        plt.annotate(f'{last_rating}',
                         xy=(dates[-1], last_rating),
                         xytext=(10, -20),
                         textcoords='offset points',
                         arrowprops=dict(arrowstyle="->"))

        # 保存图片
        save_path = rating_path + f'cf_rating_{cf_id}.png'
        plt.savefig(save_path, bbox_inches='tight', dpi=300)
        plt.close()  # 释放内存

        # 发送图片（根据你的机器人框架调整发送逻辑）
        await cf_ratings.finish(MessageSegment.file_image(Path(save_path)))

    else:
        await cf_ratings.send("您还未绑定CodeForces账户\n请输入 /cfrt+账户名 来绑定吧。")



def get_match_phase(phase):
    phase_map = {
        "BEFORE": "未开始",
        "FINISHED": "已结束",
        "CODING": "进行中",
        "PENDING_SYSTEM_TEST": "等待判题",
        "SYSTEM_TEST": "判题中",
    }
    return phase_map.get(phase, "未知")


def get_until_start_time(until_start_time_min):
    if until_start_time_min <= 180:
        return "距开始：" + str(int(until_start_time_min)) + "min\n"
    elif 180 < until_start_time_min <= 1440:
        return "距开始：" + str(int(until_start_time_min / 60)) + "h\n"
    elif until_start_time_min > 1440:
        return "距开始：" + str(int(until_start_time_min / 60 / 24)) + "days\n"
    else:
        return "距开始：未知\n"
