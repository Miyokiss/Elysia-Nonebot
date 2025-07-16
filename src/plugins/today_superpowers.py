from nonebot import logger
from pathlib import Path
from nonebot.rule import to_me
from nonebot.plugin import on_command
from nonebot.adapters.qq import Message, MessageEvent, MessageSegment
from src.today_superpowers import Today_superpowers, Today_User_superpowers

today_superpowers = on_command("今日超能力", rule=to_me(), priority=1, block=True)
@today_superpowers.handle()
async def handle_today_superpowers(msg: MessageEvent):
    user_id = msg.get_user_id()
    keyword = msg.get_plaintext().replace("/今日超能力", "").split()
    if len(keyword) == 0 or len(keyword) == 1:
        # 获取今日超能力
        today_superpowers_data = await Today_superpowers.get_today_superpowers()
        user_today_superpowers = await Today_User_superpowers.get_user_today_superpowers(user_id)
        if len(keyword) == 1 and keyword[0] in ["按下", "不按"]:
            # 按下为true，不按下为false
            is_button = True if keyword[0] == "按下" else False
            if user_today_superpowers is None:
                # 保存用户今日超能力数据
                await Today_User_superpowers.save_user_today_superpowers(user_id, is_button)
                # 更新今日超能力计数
                await Today_superpowers.update_or_create(
                    time=today_superpowers_data.time,
                    defaults={
                        'press_count': today_superpowers_data.press_count + (1 if is_button else 0),
                        'not_press_count': today_superpowers_data.not_press_count + (0 if is_button else 1)
                    }
                )
                # 更新数据
                today_superpowers_data = await Today_superpowers.get_today_superpowers()
                user_today_superpowers = await Today_User_superpowers.get_user_today_superpowers(user_id)

        if user_today_superpowers is None and len(keyword) == 0:
            r_msg = Message([
                f"\n今日超能力：\n"+
                today_superpowers_data.superpowers
                + f"\n但是：\n"+
                today_superpowers_data.but
                + f"\n按下：/今日超能力 按下"
                + f"\n不按下：/今日超能力 不按"
            ])
        else:
            r_msg = Message([
                MessageSegment.text(f"\n今日超能力：\n"+
                    today_superpowers_data.superpowers
                    + f"\n但是：\n"+
                    today_superpowers_data.but
                    + f"\n\n你选择了{ '按下' if user_today_superpowers.is_button else '不按下'}(仅保存首次选择)"
                    + f"\n已有{today_superpowers_data.press_count}人选择了按下"
                    + f"\n已有{today_superpowers_data.not_press_count}人选择了不按"
                    )
                ])
        await today_superpowers.finish(r_msg)
    else:
        await today_superpowers.finish(MessageSegment.text(
            "指令格式错误，请使用：\n"
            "/今日超能力\n"
            "/今日超能力 按下\n"
            "/今日超能力 不按"
        ))