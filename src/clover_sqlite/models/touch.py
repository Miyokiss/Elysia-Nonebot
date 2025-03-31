from datetime import datetime
import random
from tortoise import fields
from typing_extensions import Self
from src.clover_sqlite.data_init.db_connect import Model


class QrTouch(Model):
    """
    摸头回复内容
    """
    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    touch_status = fields.IntField(default=0,description="状态", null=True)
    reply_touch_content = fields.CharField(max_length=255, description="响应内容", null=True)
    class Meta:
        # 指定表名
        table = "qr_touch"
        table_description = "rua回复内容"

    @classmethod
    async def touch(cls, status: int | None)-> Self | None:
        """
        获取摸头内容
        :param status:
        :return:
        """
        existing_record = await QrTouch.filter(touch_status=status).all()
        if not existing_record:
            # 执行初始化
            await cls.bulk_create(touch_initial_data)
            existing_record = await QrTouch.filter(touch_status=status).all()
        return random.choice(existing_record)


class QrTouchLog(Model):
    """
    摸头记录
    """
    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    touch_status = fields.IntField(default=0,description="状态", null=True)
    reply_touch_content = fields.CharField(max_length=255, description="响应内容", null=True)
    user_id = fields.CharField(max_length=64, description="用户id", null=True)
    extract_time = fields.DateField(description="日期", null=True)
    class Meta:
        # 指定表名
        table = "qr_touch_log"
        table_description = "rua回复内容"

    @classmethod
    async def insert_touch_log(cls, model:QrTouch, member_openid):
        """
        插入摸头记录
        :param model:
        :param member_openid:
        :return:
        """
        data = {
            "touch_status": model.touch_status,
            "reply_touch_content": model.reply_touch_content,
            "user_id": member_openid,
            "extract_time": datetime.now().date()
        }
        await cls.create(**data)

    @classmethod
    async def touch_count(cls, member_openid):
        """
        获取摸头次数
        :param member_openid:
        :return:
        """
        result = await QrTouchLog.filter(user_id=member_openid, extract_time=datetime.now().date()).count()
        return result

touch_initial_data=[QrTouch(touch_status=0,reply_touch_content="哼！你怎么突然摸我的头？我可是精心整理过的发型呢，这下可要你负责帮我重新梳理好哦♪"),
                    QrTouch(touch_status=0,reply_touch_content="你的手真是温柔呢，感觉就像被粉色的花瓣轻轻拂过一样，再多摸一会儿也没关系哦♪"),
                    QrTouch(touch_status=0,reply_touch_content="嘿，你以为摸我的头就能讨好我啦？不过看在你手法还不错的份上，这次就允许你啦，但要记得给我准备小蛋糕哦♪"),
                    QrTouch(touch_status=0,reply_touch_content="哎呀，别停呀，你的摸头动作真是太棒啦，我都快融化在你的温柔里啦♪"),
                    QrTouch(touch_status=0,reply_touch_content="哼，虽然我是一只高傲的妖精，但被你摸摸头的感觉还不赖哦，不过，你可得小心点，要是把我惹毛了，我可是会亮出我的‘魔法’哦♪"),
                    QrTouch(touch_status=0,reply_touch_content="你的手好温暖呀，每次被摸摸头，我就觉得自己是世界上最幸福的妖精啦，希望你能一直这样摸下去呢♪"),
                    QrTouch(touch_status=0,reply_touch_content="呜呜～被摸摸头的感觉好温馨哦，我都想在你的腿上睡一觉啦，记得要一直摸着我，不然我会生气的哦♪"),
                    QrTouch(touch_status=0,reply_touch_content="嘿，你的摸头让我感觉自己像个小宝贝呢，我会用最可爱的样子来报答你哦，多摸摸我的头，让我更加闪耀吧♪"),
                    QrTouch(touch_status=0,reply_touch_content="我喜欢这种被抚摸的感觉呢，就像沉浸在温暖的阳光中，你可以多摸摸我的头，这样我会更有活力哦，说不定会帮你创造更多奇迹呢♪"),
                    QrTouch(touch_status=0,reply_touch_content="好啦好啦~我已经被你摸得服服帖帖啦，感觉整个人都变得更加轻盈啦！继续保持哦~我会更喜欢你的呢♪"),
                    QrTouch(touch_status=0,reply_touch_content="你在摸我的头，是不是觉得我很可爱呀？我可以让你多摸一会儿，不过作为交换，你要陪我哦♪"),
                    QrTouch(touch_status=0,reply_touch_content="谢谢你的摸头啦，你真是个好人呢，我会给你带来好运的哦，就像幸运女神一样，只要你继续给我摸摸头♪"),
                    QrTouch(touch_status=0,reply_touch_content="嘿，你这个可爱的舰长，摸头的动作还挺熟练嘛，我允许你再摸一会儿啦，不过可别想随便摸我的发饰哦♪"),
                    QrTouch(touch_status=0,reply_touch_content="被摸摸头真是太美妙啦，感觉我的每一缕发丝都变得更加灵动啦，你是我最喜欢的人啦，继续给我摸摸头吧♪"),
                    QrTouch(touch_status=0,reply_touch_content="呜呜～被摸摸头的时候，我觉得自己是最幸福的啦，希望你能一直守护我，就像我守护自己的小秘密一样♪"),
                    QrTouch(touch_status=0,reply_touch_content="嘿，你在摸我的头呢，是不是在给我施展魔法呀？我已经被你的魔法控制啦，要一直摸下去哦♪"),
                    QrTouch(touch_status=0,reply_touch_content="每次你摸我的头，我就会变得更加慵懒哦，我会躺在你的怀里，享受这种惬意的时光，希望你能多陪陪我呢♪"),
                    QrTouch(touch_status=0,reply_touch_content="嘿，别以为摸我的头是一件简单的事情哦，这可是需要技巧的呢，不过你现在做得还不错啦，继续加油哦♪"),
                    QrTouch(touch_status=0,reply_touch_content="我要把我的头靠在你手上啦，这样你就可以更方便地摸我啦，我会发出轻轻的笑声来表示我的快乐哦♪"),
                    QrTouch(touch_status=0,reply_touch_content="呜呜～你是在给我按摩吗？我太喜欢啦，我会用最可爱的动作来感谢你，多摸摸我的头，我会更有精神哦♪"),
                    QrTouch(touch_status=1,reply_touch_content="你是不是没看到我的表情都变得严肃啦？还不把手缩回去，我马上就要用我的‘魔法’来反击啦！♪")
                    ]