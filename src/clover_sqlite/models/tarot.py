import random
from datetime import datetime
from os import getcwd

from tortoise import fields
from typing_extensions import Self
from nonebot_plugin_htmlrender import template_to_pic
from src.clover_sqlite.data_init.db_connect import Model
from src.configs.path_config import tarots_img_path,temp_path


class MajorArcana(Model):
    """
    大阿尔克纳牌
    """
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255, unique=True, description="牌名")
    upright_meaning = fields.TextField(description="正位含义")
    reversed_meaning = fields.TextField(description="逆位含义")
    image = fields.CharField(max_length=255, description="图片文件名")

    class Meta:
        # 指定表名
        table = "major_arcana"
        table_description = "大阿尔克纳牌"

class MinorArcana(Model):
    """
    小阿尔克纳牌
    """
    id = fields.IntField(pk=True)
    ranks = fields.CharField(max_length=25, description="牌面等级")
    suits = fields.CharField(max_length=64, description="花色")
    upright_meaning = fields.TextField(description="正位含义")
    reversed_meaning = fields.TextField(description="逆位含义")
    image = fields.CharField(max_length=255, description="图片文件名")

    class Meta:
        # 指定表名
        table = "minor_arcana"
        table_description = "小阿尔克纳牌"


# 新增牌阵位置模型
class TarotSpreadPosition(Model):
    """牌阵位置含义"""
    id = fields.IntField(pk=True)
    spread_type = fields.IntField(description="牌阵类型")
    position = fields.IntField(description="位置编号")
    meaning = fields.CharField(max_length=255, description="位置含义")

    class Meta:
        table = "tarot_spread_position"
        unique_together = ("spread_type", "position")



class TarotExtractLog(Model):
    """
    大阿尔克纳牌
    """
    id = fields.IntField(pk=True)
    user_id = fields.CharField(max_length=255, description="用户id")
    extract_type = fields.IntField(description="抽取类型")#0大阿尔克纳牌 1小阿尔克纳牌 3混合牌组 4三角牌阵 5六芒星牌阵 6凯尔特十字牌阵 7恋人牌阵
    orientation = fields.CharField(max_length=64,description="正逆",null=True)
    name = fields.CharField(max_length=64, description="牌名")
    meaning = fields.TextField(description="正位/逆位含义")
    image = fields.CharField(max_length=255, description="图片文件名")
    create_time = fields.DateField(auto_now_add=True)
    # 新增关联字段
    spread_data = fields.JSONField( description="牌阵详细数据",null=True)  # 存储多张牌信息

    class Meta:
        # 指定表名
        table = "tarot_extract_log"
        table_description = "塔罗牌抽取日志"


    @classmethod
    async def tarotChoice(cls,extract_type: int | None,user_id: str | None) -> Self | None:
        """
        阿尔克纳牌抽取
        :param extract_type : 1大阿尔克纳牌 2小阿尔克纳牌 3 混合牌组 4三角牌阵 5六芒星牌阵 6凯尔特十字牌阵 7恋人牌阵
        :param user_id:
        :return:
        """
        record = await cls.filter(user_id=user_id,extract_type = extract_type,create_time = datetime.now().date()).first()
        if record:
            return record

        if extract_type in [1, 2, 3]:
            # 0正1逆
            orientation = "正位" if random.randint(0, 1) == 0 else "逆位"
            arcana_mapping = {
                1: await MajorArcana.all(),
                2: await MinorArcana.all(),
                3: await MajorArcana.all() + await MinorArcana.all()
            }
            arcana = arcana_mapping.get(extract_type)
            if not arcana:
                if extract_type == 1:
                    await MajorArcana.bulk_create(Major_arcana_initial_data)
                    arcana = await MajorArcana.all()
                if extract_type == 2:
                    await MinorArcana.bulk_create(Minor_arcana_initial_data)
                    arcana = await MinorArcana.all()
                if extract_type == 3:
                    await MajorArcana.bulk_create(Major_arcana_initial_data)
                    await MinorArcana.bulk_create(Minor_arcana_initial_data)
                    arcana = await MajorArcana.all() + await MinorArcana.all()
                # arcana = arcana_mapping[extract_type]

            tarots = random.choice(arcana)
            # 创建记录
            log = await cls.create(
                user_id=user_id,
                extract_type=extract_type,
                orientation=orientation,
                name=f"{tarots.name if isinstance(tarots, MajorArcana) else f'{tarots.ranks} of {tarots.suits}'}",
                meaning=tarots.upright_meaning if orientation == "正位" else tarots.reversed_meaning,
                image=tarots_img_path + tarots.image,
                create_time=datetime.now().date()
            )
            return log
        #牌阵
        elif extract_type in [4, 5, 6, 7]:
            cards = []
            deck = []
            spread_config = {
                4: {"name":"三角牌阵","count": 3, "positions": ["过去", "现在", "未来"]},
                5: {"name":"六芒星牌阵","count": 6, "positions": ["现状", "挑战", "建议", "根源", "希望", "结果"]},
                6: {"name":"凯尔特十字牌阵","count": 10,"positions": ["核心", "阻碍", "过去", "现在", "未来", "潜在", "态度", "环境", "希望", "结果"]},
                7: {"name":"恋人牌阵","count": 5, "positions": ["自我状态", "对方状态", "关系现状", "挑战", "未来"]}
            }
            deck = await MajorArcana.all() + await MinorArcana.all()
            # 防止重复抽牌
            selected = set()
            for _ in range(spread_config[extract_type]["count"]):
                while True:
                    card = random.choice(deck)
                    if card.id not in selected:
                        selected.add(card.id)
                        break
                orientation = "正位" if random.randint(0, 1) == 0 else "逆位"
                cards.append({
                    "name": card.name if isinstance(card, MajorArcana) else f"{card.ranks} of {card.suits}",
                    "meaning": card.upright_meaning if orientation == "正位" else card.reversed_meaning,
                    "image": tarots_img_path + card.image,
                    "orientation": orientation,
                    "position_meaning": spread_config[extract_type]["positions"][len(cards)]
                })
            file_path = temp_path + user_id + f"{spread_config[extract_type]['name']}{datetime.now().date()}.png"
            # 创建记录
            log = await cls.create(
                user_id=user_id,
                extract_type=extract_type,
                orientation="",  # 牌阵无需全局正逆
                name=f"{spread_config[extract_type]['name']}",
                meaning="",  # 含义存到spread_data
                image=file_path,
                spread_data={ "spread_type": extract_type,"cards": cards},
                create_time=datetime.now().date()
            )
            image_bytes = await template_to_pic(
                template_path = tarots_img_path,
                template_name="A1CelticCross.html",
                templates={"data": log.spread_data.get("cards")},
                pages={
                    "viewport": {"width": 980, "height": 900},
                    "base_url": f"file://{getcwd()}",
                },
                wait=2,
            )
            with open(file_path, "wb") as file:
                file.write(image_bytes)
            return log
        else:
            return None

    @classmethod
    async def create_batch(cls, logs: list)-> Self | None:
        """批量创建记录"""
        return await cls.bulk_create([
            TarotExtractLog(
                user_id=log['user_id'],
                extract_type=log['extract_type'],
                orientation=log['orientation'],
                name=log['name'],
                meaning=log['meaning'],
                image=log['image'],
                create_time=log['create_time']
            ) for log in logs
        ])


Major_arcana_initial_data = [
    MajorArcana(
        name="愚者 (The Fool) ",
        upright_meaning="从零开始; 好赌运; 不墨守成规; 追求新奇的梦想; 冒险; 放浪形骸; 艺术家的气质; 异于常人; 直攻要害、盲点; 爱情狩猎者; 爱情历经沧桑; 不拘形式的自由恋爱",
        reversed_meaning=" 不安定; 孤注一掷会失败; 缺乏责任感; 损失; 脚跟站不稳; 堕落; 没发展; 没计划; 走错路; 行为乖张; 轻浮的恋情; 感情忽冷忽热; 不安定的爱情之旅",
        image="The Fool.jpg"),
    MajorArcana(
        name="魔术师 (The Magician)",
        upright_meaning="好的开始; 具独创性; 有发展的; 新计划成功; 想像力丰富或有好点子; 有恋情发生; 拥有默契良好的伴侣; 有新恋人出现; 值得效仿的对象出现",
        reversed_meaning=" 失败; 优柔寡断; 才能平庸; 有被欺诈的危险; 技术不足; 过于消极; 没有判断力; 缺乏创造力; 爱情没有进展 ",
        image="The Magician.jpg"),
    MajorArcana(
        name="女祭司 (The High Priestess)",
        upright_meaning="知性、优秀的判断力; 具洞察力及先见之明; 强大的战斗意志; 冷静的统率力; 学问、研究等精神方面幸运; 独立自主的女性; 柏拉图式的爱情; 有心灵上交往至深的友人; 冷淡的恋情 ",
        reversed_meaning=" 无知、缺乏理解力; 研究不足; 不理性的态度; 自我封闭; 神经质; 洁癖; 与女性朋友柒争执; 对人冷淡; 晚婚或独身主义; 没有结果的单相思; 气色不好; 不孕",
        image="The High Priestess.jpg"),
    MajorArcana(
        name="皇后 (The Empress)",
        upright_meaning="充满创造力与母性光辉; 生活富足、美满; 事业上有出色的规划与执行能力，易取得成果; 感情中温柔体贴，是理想的伴侣; 孕育新生命或有新的创意项目诞生",
        reversed_meaning=" 创造力受阻; 生活陷入混乱，经济上可能出现问题; 感情中可能变得情绪化、占有欲强; 缺乏实际行动，计划难以实现; 健康方面可能有妇科问题",
        image="The Empress.jpg"),
    MajorArcana(
        name="皇帝 (The Emperor)",
        upright_meaning="以坚强的意志力及手腕获致成功; 富裕和力量; 有责任感; 良好的处理能力; 具领导能力; 男性的思考; 坚持到底; 虽有点专制却值得信赖; 条件诱人的提亲; 与年长者恋爱 ",
        reversed_meaning=" 不成熟; 意志薄弱; 虚有其表; 看不清现实; 欠缺实务能力; 因傲慢而招人反感; 工作过度; 固执; 没有经济基础; 没有好对象; 苦恋结束; 勉强的感情",
        image="The Emperor.jpg"),
    MajorArcana(
        name="教皇 (The Hierophant) ",
        upright_meaning="受人信赖; 有贵人相助; 贡献; 受上司重视; 能胜任工作; 拥有一颗温柔的心; 受惠于有益的建言; 接触宗教的事物大吉; 与年长的异性有缘; 良缘; 深情宽大的爱; 有结良缘的机会 ",
        reversed_meaning=" 没信用; 没有贵人相助; 孤立无援; 不受欢迎的好意; 依赖心是最大的敌人; 太罗嗦而讨人厌; 碍于私情而无法成功; 心胸狭窄; 得不到亲人的谅解的恋情; 彼此过于关心; 缘分浅薄的恋情 ",
        image="The Hierophant.jpg"),
    MajorArcana(
        name="恋人 (The Lovers) ",
        upright_meaning="幸运的结合; 有希望的将来; 有共同做事的伙伴; 与人合作或社团活动; 敏感决定前进之路的好时机; 有意气相投的朋友; 爱情机会将到来; 罗曼蒂克的恋情; 爱的预感",
        reversed_meaning=" 分离; 消解; 不合作的态度; 眼花缭乱; 没有满意的成果; 无法持续; 退休; 妨碍; 血气方刚; 多情的人; 分手; 冷漠的爱; 背信; 逃避爱情; 短暂的恋情",
        image="The Lovers.jpg"),
    MajorArcana(
        name="战车 (The Chariot)",
        upright_meaning="前进必胜; 先下手为强; 独立; 起程; 在颠簸中仍有好成绩; 活泼; 有野心; 以速度取胜; 有开拓精神; 握有指挥权; 战胜敌手; 富行动力的恋情; 恋爱的胜利者 ",
        reversed_meaning=" 失败; 丧失战斗意志; 状态不佳; 挫折; 性子过急为失败之因; 不感兴趣; 效率不佳; 资金运转困难; 无奋斗精神; 有强劲敌手进入; 被拒绝; 因怯懦而使恋情不顺 ",
        image="The Chariot.jpg"),
    MajorArcana(
        name="力量 (Strength) ",
        upright_meaning="不屈不挠的精神; 将不可能化为可能的意志力; 全力以赴; 突破难关; 坚强的信念和努力; 挑战已知危险的勇气; 神秘的力量; 旺盛的斗志; 轰轰烈烈的恋情; 克服困难的真实爱情",
        reversed_meaning=" 疑心病; 犹豫不决; 实力不足; 无忍耐力; 危险的赌注; 勉强为之而适得其反; 丧失自信; 喜欢故弄玄虚; 体力不足; 自大自负; 误用力气 ",
        image="Strength.jpg"),
    MajorArcana(
        name="隐士 (The Hermit) ",
        upright_meaning="智能与卓越见解; 不断地追求更高层次的东西; 思虑周密; 冷静沉着; 不多言; 接触知性事物吉; 正中核心的建言; 活动慢慢进行较有成果; 出局; 追求柏拉图式的爱情; 暗中的爱情",
        reversed_meaning=" 一视同仁; 不够通融; 不专心易生错误; 过分警戒，无法顺利进行; 秘密泄漏; 过于固执不听别人的意见; 孤独; 动机不单纯; 因怨言及偏见招人嫌; 轻浮的爱情; 怀疑爱情",
        image="The Hermit.jpg"),
    MajorArcana(
        name="命运之轮 (The Wheel of Fortune) ",
        upright_meaning="机会到来; 随机应变能力佳; 好运; 转换期; 意想不到的幸运; 升迁有望; 变化丰富; 好时机; 宿命的相逢; 一见钟情; 幸运的婚姻; 富贵的身份 ",
        reversed_meaning=" 低潮期; 时机未到; 评估易出错; 时机不好; 没有头绪; 处于劣势; 生活艰苦; 情况恶化; 计划停滞需要再等待; 失恋; 短暂的恋情; 易错失良机; 不敌诱惑; 爱情无法持久 ",
        image="The Wheel of Fortune.jpg"),
    MajorArcana(
        name="正义 (Justice)",
        upright_meaning="公正; 严正的意见; 良好的均衡关系; 严守中立立场; 凡事合理化; 身兼两种工作; 协调者; 与裁判、法律相关者; 表里一致的公正人物; 以诚实之心光明正大地交往; 彼此能获得协调 ",
        reversed_meaning=" 不公正; 不平衡; 不利的条件; 偏颇; 先入为主的观念; 偏见与独断; 纷争、诉讼; 问心有愧; 无法两全; 天平两边无法平衡; 性格不一致; 无视于社会道德观的恋情; 偏爱",
        image="Justice.jpg"),
    MajorArcana(
        name="倒吊人 (The Hanged Man)",
        upright_meaning="接受考验; 无法动弹; 被牺牲; 有失必有得; 从痛苦的体验中获得教训; 过度期; 不贪图眼前利益; 浴火重生; 多方学习; 奉献的爱; 明知辛苦但全力以赴",
        reversed_meaning=" 无谓的牺牲; 折断骨头; 有噩运、居于劣势; 任性妄为; 不努力; 变得没有耐性; 利己主义者; 受到惩罚; 无偿的爱; 缺乏共同奋斗的伙伴",
        image="The Hanged Man.jpg"),
    MajorArcana(
        name="死神 (Death)",
        upright_meaning="失败; 毁灭之日将近; 损害继续延续; 失业; 进展停滞; 交易停止; 为时已晚; 停滞状态; 生病或意外的暗示; 味如嚼蜡的生活; 不幸的恋情; 恋情终止; 彼此间有很深的鸿沟; 别离 ",
        reversed_meaning=" 起死回生的机会; 脱离低迷期; 改变印象; 回心转意再出发; 挽回名誉; 奇迹似地康复; 突然改变方针; 已经死心的事有了转机; 斩断情丝，重新出发",
        image="Death.jpg"),
    MajorArcana(
        name="节欲 (Temperance) ",
        upright_meaning="单纯化; 顺畅; 交往平顺; 两者相融顺畅; 调整; 彼此交换有利条件; 平凡中也有重要的契机; 平顺的心境; 纯爱; 从好感转为爱意; 深爱 ",
        reversed_meaning=" 消耗; 每节制的损耗，对身心产生不好的影响; 疲劳; 不定性的工作; 缺乏调整能力; 下降; 浪费; 不要与人 合作; 不融洽; 爱情的配合度不佳 ",
        image="Temperance.jpg"),
    MajorArcana(
        name="恶魔 (The Devil)",
        upright_meaning="被束缚; 堕落; 恶魔的私语; 卑躬屈膝; 欲望的俘虏; 荒废的生活; 举债度日; 病魔入侵; 夜游过多; 不可告人的事; 恶意; 不可抗拒的诱惑; 私密恋情; 沉溺于感官刺激之下",
        reversed_meaning=" 逃离拘束; 长期的苦恼获得解放; 斩断前缘; 越过难关; 暂时停止; 拒绝诱惑; 舍弃私欲; 治愈长期病痛; 别离 时刻; 如深陷泥沼爱恨交加的恋情",
        image="The Devil.jpg"),
    MajorArcana(
        name="塔 (The Tower) ",
        upright_meaning="致命的打击; 纷争; 纠纷不断; 与周遭事物对立，情况恶化; 意想不到的事情; 急病; 受牵连; 急剧的大变动; 信念奔溃; 逆境; 破产; 没有预警，突然分离; 破灭的爱; 玩火自焚",
        reversed_meaning=" 紧迫的状态; 险恶的气氛; 内讧; 即将破灭; 急需解决的问题; 承受震撼; 背水一战; 注意刑事问题; 因骄傲自大将付出惨痛的代价; 状况不佳; 困境; 爱情危机; 分离的预感 ",
        image="The Tower.jpg"),
    MajorArcana(
        name="星辰 (The Star) ",
        upright_meaning="愿望达成; 前途光明; 充满希望的未来; 美好的生活; 曙光出现; 大胆的幻想; 水准提高; 新的创造力; 想像力; 理想的对象; 美好的恋情; 爱苗滋生 ",
        reversed_meaning=" 挫折、失败; 理想过高; 缺乏想像力; 异想天开; 事与愿违; 失望; 从事不喜欢的工作; 好高骛远; 情况悲观; 不可期待的对象; 没 有爱的生活; 秘密恋情; 仓皇失措",
        image="The Star.jpg"),
    MajorArcana(
        name="月亮 (The Moon) ",
        upright_meaning="不安与动摇; 心中不平静; 谎言; 暧昧不明; 鬼迷心窍; 暗藏动乱; 欺骗; 终止; 不安的爱; 三角关系",
        reversed_meaning=" 从危险的骗局中逃脱; 状况稍为好转; 误会冰释; 破除迷惘; 时间能解决一切; 眼光要长远; 静观等待; 早期发现早期治疗有效; 事前察知危险; 对虚情假意的恋情已不在乎 ",
        image="The Moon.jpg"),
    MajorArcana(
        name="太阳 (The Sun)",
        upright_meaning="丰富的生命力; 巨大的成就感; 人际关系非常好; 爱情美满; 内心充满了热情和力量; 一定能够实现的约定; 飞黄腾达; 无忧无虑",
        reversed_meaning=" 情绪低落; 事情失败; 朋友的离去和人际关系的恶化; 无法安定内心; 忧郁孤单寂寞; 爱情不顺 利; 取消的计划; 工作上困难重重 ",
        image="The Sun.jpg"),
    MajorArcana(
        name="审判 (Judgement)",
        upright_meaning="复活的喜悦; 开运; 公开; 改革期; 危机解除; 决断; 荣升; 崭露头角; 好消息; 爱的使者; 恢复健康; 坦白; 复苏的爱; 再会; 爱的奇迹 ",
        reversed_meaning="一败不起; 幻灭; 离复苏还有很长的时间; 不利的决定; 不被采用; 还未开始就结束了; 坏消息; 延期; 无法决定; 虽重新开始，却又恢复原状; 分离、消除; 恋恋不舍",
        image="Judgement.jpg"),
    MajorArcana(
        name="世界 (The World)",
        upright_meaning="完成; 成功; 拥有毕生的志业; 达成目标; 永续不断; 最盛期; 完美无缺; 接触异国，将获得幸运; 到达标准; 精神亢奋; 快乐的结束; 模范情侣 ",
        reversed_meaning=" 未完成; 无法达到计划中的成就; 因准备不足而失败; 中途无法在进行; 不完全燃烧; 一时不顺利; 饱和状态; 烦恼延续; 精神松弛; 个人惯用的表现方式; 因不成熟而 使情感受挫; 合谋; 态度不够圆融",
        image="The World.jpg")]

Minor_arcana_initial_data = [
    # Ace系列
    MinorArcana(ranks="Ace",
                 suits="Cups",
                 upright_meaning="情感新契机的降临；无条件的爱与关怀的流动；直觉力显著提升的征兆；艺术创作灵感的迸发；深层情感需求的满足",
                 reversed_meaning="情感表达遭遇障碍；错失建立亲密关系的机会；过度依赖理性压抑感受；创作灵感枯竭期；情感需求未被满足的空虚感",
                 image="Ace of Cups.jpg"),

    MinorArcana(ranks="Ace",
                 suits="Pentacles",
                 upright_meaning="新财务机遇的出现；建立物质基础的良机；务实规划带来的安全感；身体能量恢复的信号；值得投资的长期项目",
                 reversed_meaning="创业资金筹措受阻；过度追求物质产生的焦虑；忽视健康透支精力；错失房产投资良机；短期利益诱惑导致失利",
                 image="Ace of Pentacles.jpg"),

    MinorArcana(ranks="Ace",
                 suits="Swords",
                 upright_meaning="突破性思维模式的建立；真相浮出水面的时刻；果断决策的最佳时机；用逻辑破除困境；获得公平的竞争环境",
                 reversed_meaning="思维混乱导致判断失误；残酷真相带来的冲击；滥用话语权伤害他人；陷入法律纠纷的预警；知识垄断引发的矛盾",
                 image="Ace of Swords.jpg"),

    MinorArcana(ranks="Ace",
                 suits="Wands",
                 upright_meaning="新创意项目的启动信号；充满热情的能量爆发期；开拓新领域的冒险召唤；个人创造力的觉醒时刻；自我实现道路的开启",
                 reversed_meaning="创业计划遭遇资金冻结；三分钟热度导致半途而废；过度冒险引发安全隐患；创意被商业利益扭曲；身份认同危机的显现",
                 image="Ace of Wands.jpg"),

    # 二号牌系列
    MinorArcana(ranks="Second",
                 suits="Cups",
                 upright_meaning="平等情感关系的建立；合作达成双赢的局面；心灵共鸣产生的深刻连接；关系中付出与接受的平衡；新合作契机的出现",
                 reversed_meaning="情感付出得不到回应；商业合作出现信任危机；文化差异导致沟通障碍；情感勒索的潜在风险；错失建立战略伙伴的机会",
                 image="Second of Cups.jpg"),

    MinorArcana(ranks="Second",
                 suits="Pentacles",
                 upright_meaning="多项目间的灵活调度；适应变化的应对能力；财务收支的动态平衡；把握转瞬即逝的机遇；乐观心态化解压力",
                 reversed_meaning="工作生活严重失衡；突发状况超出应对能力；信用卡透支的财务警示；只顾眼前利益的短视行为；高风险投资的失败预兆",
                 image="Second of Pentacles.jpg"),

    MinorArcana(ranks="Second",
                 suits="Swords",
                 upright_meaning="面临重大抉择的僵持状态；用回避暂时缓解压力；理性与感性的激烈拉锯；需要更多客观信息的提示；暂时搁置决定的权宜之计",
                 reversed_meaning="最终做出痛苦但必要的选择；直面不愿承认的事实真相；价值观冲突后的自我整合；关键证据打破信息不对称；第三方视角提供解决方案",
                 image="Second of Swords.jpg"),

    MinorArcana(ranks="Second",
                 suits="Wands",
                 upright_meaning="站在十字路口的未来规划；多个发展方向的综合评估；掌控局面的领导者姿态；通过合作扩大事业版图；开拓新市场的预备阶段",
                 reversed_meaning="选择困难导致机会流失；对市场趋势判断失误；刚愎自用引发团队矛盾；跨国合作的文化适应问题；过度扩张造成的资源分散",
                 image="Second of Wands.jpg"),
    # 三号牌系列
    MinorArcana(ranks="Three",
                suits="Cups",
                upright_meaning="庆祝与欢聚的时刻；真挚的友谊连接；社交活动带来的喜悦；合作关系取得成果；情感丰盛的象征",
                reversed_meaning="过度沉溺享乐影响判断；感到被社交圈孤立；合作关系出现裂痕；潜藏的嫉妒心理；对社交产生倦怠感",
                image="Three of Cups.jpg"),

    MinorArcana(ranks="Three",
                suits="Pentacles",
                upright_meaning="团队协作达成卓越；专业技能的精进过程；长期项目的扎实奠基；职场地位的提升契机；通过务实努力获得认可",
                reversed_meaning="团队配合度不足；工作成果流于平庸；急躁导致细节失误；忽视专业价值；陷入孤立无援的处境",
                image="Three of Pentacles.jpg"),

    MinorArcana(ranks="Three",
                suits="Swords",
                upright_meaning="经历深刻的心碎时刻；遭遇信任背叛的伤痛；不得不面对的情感失落；内心价值观的激烈冲突；做出艰难的情感抉择",
                reversed_meaning="伤口开始结痂愈合；直面现实的勇气涌现；学习宽恕与自我释怀；停止自我伤害的循环；情绪压力逐渐缓解",
                image="Three of Swords.jpg"),

    MinorArcana(ranks="Three",
                suits="Wands",
                upright_meaning="展现前瞻性的商业眼光；拓展事业版图的良机；跨国跨文化的合作机遇；筹备成熟的计划等待实施；领导才能的充分展现",
                reversed_meaning="外部因素导致进度延迟；视野局限错过潜在机会；过度自信埋下隐患；文化差异引发合作摩擦；资源配置不当造成浪费",
                image="Three of Wands.jpg"),
    # 四号牌系列
    MinorArcana(ranks="Four",
                suits="Cups",
                upright_meaning="对现状产生情感麻木感；忽视眼前的新机会；被动等待改变的消极状态；需要深入自我反思的时刻；转向内在灵性探索",
                reversed_meaning="主动把握被忽视的机遇；重拾对生活的热情；突破自我设限的舒适圈；将想法转化为实际行动；打破固有行为模式",
                image="Four of Cups.jpg"),

    MinorArcana(ranks="Four",
                suits="Pentacles",
                upright_meaning="采取保守的财务策略；对资源进行严格控制；追求安全稳定的生活保障；节俭至上的消费观念；抗拒改变现有经济状态",
                reversed_meaning="过度控制引发反效果；面临意外的财务流失；学会灵活运用资金；接受必要的经济变动；尝试分享资源的可能性",
                image="Four of Pentacles.jpg"),

    MinorArcana(ranks="Four",
                suits="Swords",
                upright_meaning="身体强制进入休整期；心灵创伤的疗愈过程；战略性暂停以积蓄力量；通过冥想获得内心平静；主动避免无谓的冲突",
                reversed_meaning="长期疲劳导致健康预警；用虚假平静掩盖问题；情绪压抑到达临界点；不得不重新面对困境；被迫中断休息状态",
                image="Four of Swords.jpg"),

    MinorArcana(ranks="Four",
                suits="Wands",
                upright_meaning="家庭团聚的温馨时刻；完成重要阶段的目标；建立和谐的生活根基；获得社区归属的安全感；稳定持久的幸福感体验",
                reversed_meaning="生活基础出现不稳定因素；值得庆祝的事被迫延期；缺乏归属感的漂泊状态；固守传统阻碍进步；表面繁荣掩盖实质问题",
                image="Four of Wands.jpg"),
    # 五号牌系列
    MinorArcana(ranks="Five",
                suits="Cups",
                upright_meaning="沉浸于失去的悲伤；忽视现存的美好；过度自责的情绪循环；关系破裂后的自我封闭；酒精逃避现实的警示",
                reversed_meaning="接受不可逆转的失去；发现被忽略的支持资源；痛苦中萌发新希望；重建情感连接的努力；戒除成瘾行为的契机",
                image="Five of Cups.jpg"),

    MinorArcana(ranks="Five",
                suits="Pentacles",
                upright_meaning="经济窘迫的物质困境；身体病痛的长期困扰；被主流社会边缘化的孤独；急需外界援助的处境；寒冬般的艰难时期",
                reversed_meaning="获得公益组织的救助；慢性疾病的康复开端；重建社会归属的尝试；开发非物质价值资源；逆境中展现人性光辉",
                image="Five of Pentacles.jpg"),

    MinorArcana(ranks="Five",
                suits="Swords",
                upright_meaning="不惜代价取得的惨胜；言语暴力造成的心理创伤；利用信息差获得的优势；胜者孤独的处境警示；知识产权纠纷的预兆",
                reversed_meaning="放弃无意义的争斗；修复被破坏的关系；承认自身认知局限；选择合作替代对抗；法律途径解决争端",
                image="Five of Swords.jpg"),

    MinorArcana(ranks="Five",
                suits="Wands",
                upright_meaning="良性竞争激发潜能；多方势力博弈的局面；体育竞技的活力展现；创意碰撞的火花；需要确立比赛规则的时刻",
                reversed_meaning="竞争演变成恶意争斗；规则漏洞被滥用；体能过度消耗的预警；团队内部派系分化；胜负失去实际意义",
                image="Five of Wands.jpg"),

    # 六号牌系列
    MinorArcana(ranks="Six",
                suits="Cups",
                upright_meaning="纯真童年的温暖回忆；传统习俗的情感连结；不求回报的赠予行为；疗愈内在小孩的契机；怀旧物品的特殊意义",
                reversed_meaning="沉溺回忆逃避现实；过度美化过去经历；情感绑架式的付出；童年创伤再次浮现；突破固有情感模式",
                image="Six of Cups.jpg"),

    MinorArcana(ranks="Six",
                suits="Pentacles",
                upright_meaning="财富资源的合理分配；慈善行为的正向循环；知识技能的传承分享；建立公平的奖惩机制；获得应得的经济回报",
                reversed_meaning="权力不对等的施舍；伪善的慈善营销；知识垄断形成壁垒；薪酬分配严重不公；陷入债务依赖关系",
                image="Six of Pentacles.jpg"),

    MinorArcana(ranks="Six",
                suits="Swords",
                upright_meaning="离开创伤环境的过渡期；心理咨询的介入阶段；知识移民的适应过程；渐趋平静的情绪状态；需要理性导航的旅程",
                reversed_meaning="逃避问题的无效迁移；学术研究的瓶颈期；跨境适应的文化休克；疗愈进程出现反复；过度依赖导航系统",
                image="Six of Swords.jpg"),

    MinorArcana(ranks="Six",
                suits="Wands",
                upright_meaning="获得公众认可的胜利；领导权威的正式确立；凯旋归来的荣耀时刻；成为行业标杆的潜力；正向口碑的传播效应",
                reversed_meaning="过度追捧迷失自我；竞争失利后的舆论反噬；权威受到公开挑战；虚假宣传遭揭露；胜利果实被他人窃取",
                image="Six of Wands.jpg"),

    # 七号牌系列
    MinorArcana(ranks="Seven",
                suits="Cups",
                upright_meaning="面对众多选择的迷茫；虚幻妄想的诱惑陷阱；逃避现实的空想状态；需要区分虚实的信息洪流；潜意识欲望的具象化",
                reversed_meaning="明确核心需求的筛选；识破虚假宣传的骗局；将创意落地的执行力；深度挖掘潜在机会；克服选择恐惧症",
                image="Seven of Cups.jpg"),

    MinorArcana(ranks="Seven",
                suits="Pentacles",
                upright_meaning="长期投入后的收获评估；农业生产的自然周期；职业技能的深耕细作；退休金规划的现实考量；需要耐心等待的成长期",
                reversed_meaning="投入产出严重失衡；地质污染影响收成；职业倦怠期的到来；养老金危机的预警；急于求成破坏进程",
                image="Seven of Pentacles.jpg"),

    MinorArcana(ranks="Seven",
                suits="Swords",
                upright_meaning="巧妙规避风险的战略；知识产权灰色地带的操作；危机中的应急方案；独自承担压力的孤军奋战；数据安全防护的警示",
                reversed_meaning="商业间谍行为曝光；防御系统出现漏洞；过度谨慎错失良机；需要团队支持的信号；承认计谋失败的勇气",
                image="Seven of Swords.jpg"),

    MinorArcana(ranks="Seven",
                suits="Wands",
                upright_meaning="坚守立场的勇气考验；应对多方挑战的韧劲；市场地位的保卫战；独特价值的坚持主张；危机中的快速反应能力",
                reversed_meaning="多线作战导致溃败；防御姿态错失先机；过度敏感产生误判；创新力不足的守旧派；需要战略撤退的预警",
                image="Seven of Wands.jpg"),

    # 八号牌系列
    MinorArcana(ranks="Eight",
                 suits="Cups",
                 upright_meaning="主动离开情感舒适区；追寻更高精神层次的渴望；结束消耗性关系的勇气；灵性觉醒的孤独旅程；月光下的自我救赎之路",
                 reversed_meaning="困在不健康关系中自我欺骗；逃避必要的感情终结；灵性成长的停滞期；过度理想化导致迷失方向；需要回归现实的警示",
                 image="Eight of Cups.jpg"),

    MinorArcana(ranks="Eight",
                 suits="Pentacles",
                 upright_meaning="专注打磨专业技能的匠人精神；职业教育带来的提升；产品质量的严格把控；手工制作的温度与价值；通过重复训练达到精通",
                 reversed_meaning="陷入机械重复缺乏创新；职业资格认证受阻；产品质量问题频发；工作倦怠感持续累积；技能过时的危机显现",
                 image="Eight of Pentacles.jpg"),

    MinorArcana(ranks="Eight",
                 suits="Swords",
                 upright_meaning="自我设限的思维牢笼；过度依赖他人判断的困境；信息茧房导致的认知扭曲；需要突破的心理禁忌；受害情结的恶性循环",
                 reversed_meaning="打破思维禁锢的觉醒时刻；心理咨询带来的认知重构；重建信息筛选系统；直面恐惧获得思想自由；法律维权的必要行动",
                 image="Eight of Swords.jpg"),

    MinorArcana(ranks="Eight",
                 suits="Wands",
                 upright_meaning="高速推进的跨国项目；即时通讯带来的高效协同；突发事件要求的快速反应；灵感迸发的创作高峰期；签证获批的旅行信号",
                 reversed_meaning="网络故障导致沟通延迟；跨国物流的突发阻滞；冲动决策埋下隐患；创作灵感昙花一现；行程取消的意外变动",
                 image="Eight of Wands.jpg"),

    # 九号牌系列
    MinorArcana(ranks="Nine",
                 suits="Cups",
                 upright_meaning="情感需求的全方位满足；享受独处时光的充实感；物质与精神的平衡状态；被认可的价值实现感；值得庆祝的阶段性成果",
                 reversed_meaning="过度消费带来的空虚感；社交面具下的孤独本质；自我放纵导致的健康问题；成就被低估的失落情绪；需要节制欲望的提醒",
                 image="Nine of Cups.jpg"),

    MinorArcana(ranks="Nine",
                 suits="Pentacles",
                 upright_meaning="经济独立的优雅生活；投资理财的智慧成果；奢侈品鉴赏的专业眼光；人与自然和谐共处的境界；传承工艺的守护者姿态",
                 reversed_meaning="炫耀性消费引发财务危机；投资组合失衡的风险；过度物质主义迷失本心；生态破坏后的反思时刻；传统技艺失传的危机",
                 image="Nine of Pentacles.jpg"),

    MinorArcana(ranks="Nine",
                 suits="Swords",
                 upright_meaning="午夜惊醒的焦虑发作；道德困境引发的自我谴责；隐私泄露的精神压力；医疗诊断带来的心理负担；难以启齿的秘密煎熬",
                 reversed_meaning="认知行为疗法的介入；坦白秘密后的释然；逐步建立的睡眠管理；医疗方案的积极进展；原谅自己的救赎之路",
                 image="Nine of Swords.jpg"),

    MinorArcana(ranks="Nine",
                 suits="Wands",
                 upright_meaning="伤痕累累的坚持者；危机应对的应急预案；防御体系的最后防线；移民申请的持久战；老兵不死的战斗精神",
                 reversed_meaning="强弩之末的崩溃边缘；安防系统的漏洞暴露；签证拒签的挫折经历；过度防御造成的社交孤立；需要战略休整的提醒",
                 image="Nine of Wands.jpg"),

    # 十号牌系列
    MinorArcana(ranks="Ten",
                 suits="Cups",
                 upright_meaning="三世同堂的和谐景象；跨代际的情感传承；社区共建的理想状态；灵魂家族的归属认同；圆满关系的精神升华",
                 reversed_meaning="家族矛盾的集中爆发；领养家庭的适应挑战；社区排斥带来的孤独感；传统价值观的冲突激化；完美家庭表象的破裂",
                 image="Ten of Cups.jpg"),

    MinorArcana(ranks="Ten",
                 suits="Pentacles",
                 upright_meaning="家族企业的顺利传承；不动产投资的长期收益；家谱研究的文化价值；退休规划的完善方案；跨代际财富管理智慧",
                 reversed_meaning="遗产分配引发的纠纷；房产投资的法律风险；传统文化断层的危机；养老金规划的失误；过度物质导向的家庭关系",
                 image="Ten of Pentacles.jpg"),

    MinorArcana(ranks="Ten",
                 suits="Swords",
                 upright_meaning="重大打击后的彻底终结；系统性崩溃的危机时刻；必须放弃的沉没成本；创伤后应激的临界点；破而后立的必要过程",
                 reversed_meaning="触底反弹的恢复迹象；危机公关的转机出现；放弃执念的心理解脱；创伤疗愈的专业介入；数字化重生的新机遇",
                 image="Ten of Swords.jpg"),

    MinorArcana(ranks="Ten",
                 suits="Wands",
                 upright_meaning="创业者的事必躬亲；跨国项目的管理重担；过度承诺导致的超负荷；家庭事业双重压力的窒息感；急需优先级的重新排序",
                 reversed_meaning="工作委派的实施策略；智能工具的减负应用；设立健康界限的觉醒；压力源的系统性梳理；团队重组提升效率",
                 image="Ten of Wands.jpg"),

    # 宫廷牌-侍从系列
    MinorArcana(ranks="Page",
                 suits="Cups",
                 upright_meaning="情感启蒙的纯真阶段；艺术天赋的初现端倪；直觉敏锐的梦境启示；青春期的诗意情怀；新媒体创作的试水期",
                 reversed_meaning="情感幼稚导致的误会；网络交友的情感诈骗；艺术模仿缺乏原创；过度依赖灵感的低产期；逃避现实的幻想倾向",
                 image="Page of Cups.jpg"),

    MinorArcana(ranks="Page",
                 suits="Pentacles",
                 upright_meaning="职业教育的入门阶段；储蓄习惯的初步建立；传统工艺的学徒时期；自然观察的学习热情；实习期的踏实表现",
                 reversed_meaning="学业拖延影响进度；消费主义侵蚀储蓄观；传统技艺的枯燥抗拒；实习期的眼高手低；生态意识的严重缺乏",
                 image="Page of Pentacles.jpg"),

    MinorArcana(ranks="Page",
                 suits="Swords",
                 upright_meaning="辩论新秀的犀利锋芒；信息检索的快速学习；网络安全的初级防护；法律常识的普及教育；思维导图的运用能力",
                 reversed_meaning="网络暴力的参与倾向；信息过载的判断失误；数据泄露的无知导致；法律常识的严重缺乏；思维跳跃缺乏逻辑",
                 image="Page of Swords.jpg"),

    MinorArcana(ranks="Page",
                 suits="Wands",
                 upright_meaning="体育新星的潜力展现；创意火花的迸发初期；自媒体运营的启动阶段；探索欲旺盛的旅行计划；新文化现象的快速吸收",
                 reversed_meaning="运动伤害的预防不足；创意抄袭的争议事件；自媒体数据的过度焦虑；旅行计划的草率制定；文化快餐的浅薄认知",
                 image="Page of Wands.jpg"),

    # 宫廷牌-骑士系列
    MinorArcana(ranks="Knight",
                 suits="Cups",
                 upright_meaning="浪漫关系的主动推进；艺术灵感的激情迸发；情感疗愈的温柔力量；跨文化恋情的可能性；诗意生活的实践者",
                 reversed_meaning="情感泛滥的承诺恐惧；艺术创作的商业妥协；过度共情导致能量枯竭；异国恋的文化冲突；理想主义的生活逃避",
                 image="Knight of Cups.jpg"),

    MinorArcana(ranks="Knight",
                 suits="Pentacles",
                 upright_meaning="农业科技的创新实践；稳健理财的长期主义者；职业认证的备考冲刺；传统企业的数字化转型；工匠精神的现代化传承",
                 reversed_meaning="农业投资的自然风险；理财策略的过度保守；考证压力的身心失衡；转型期的阵痛加剧；传统改良的市场抵触",
                 image="Knight of Pentacles.jpg"),

    MinorArcana(ranks="Knight",
                 suits="Swords",
                 upright_meaning="法律行动的果断出击；舆论战的信息操控高手；军事策略的快速部署；学术研究的突破进展；危机处理的冷静决策",
                 reversed_meaning="法律手段的过度滥用；网络论战的失控升级；冒进策略的惨痛代价；学术不端的风险行为；危机处理的情绪化失误",
                 image="Knight of Swords.jpg"),

    MinorArcana(ranks="Knight",
                 suits="Wands",
                 upright_meaning="创业项目的闪电推进；跨文化市场的开拓先锋；体育赛事的激情表现；新媒体营销的病毒传播；探险旅行的组织实施",
                 reversed_meaning="创业节奏的失控风险；文化误读的市场失败；运动过量的伤害预警；虚假宣传的反噬危机；探险准备不足的险境",
                 image="Knight of Wands.jpg"),

    # 宫廷牌-皇后系列
    MinorArcana(ranks="Queen",
                 suits="Cups",
                 upright_meaning="情感咨询的专业能力；艺术疗愈的实践专家；梦境解析的直觉大师；跨代际的情感纽带维系者；温柔而强大的共情者",
                 reversed_meaning="情感依赖的共生关系；艺术表达的过度商业化；直觉误判导致决策失误；家族秘密的情感绑架；共情过载的心理耗竭",
                 image="Queen of Cups.jpg"),

    MinorArcana(ranks="Queen",
                 suits="Pentacles",
                 upright_meaning="生态农业的领军人物；家族财富的管理能手；不动产投资的精准眼光；传统美食的文化传承者；大地母亲的滋养能量",
                 reversed_meaning="过度开发导致的生态破坏；财富管理的控制欲膨胀；房产投资的杠杆风险；传统工艺的商业化争议；物质主义的深度沉迷",
                 image="Queen of Pentacles.jpg"),

    MinorArcana(ranks="Queen",
                 suits="Swords",
                 upright_meaning="女性领导者的理性决策；法律纠纷的谈判专家；信息安全的守护女神；学术领域的权威声音；危机公关的冷静操盘手",
                 reversed_meaning="理性至上的情感冷漠；法律手段的过度强势；信息监控的权力滥用；学术权威的思维固化；公关策略的伦理越界",
                 image="Queen of Swords.jpg"),

    MinorArcana(ranks="Queen",
                 suits="Wands",
                 upright_meaning="创意产业的领军女性；社群运营的能量中心；跨国文化的魅力使者；舞台表演的绝对掌控；女性创业的励志典范",
                 reversed_meaning="创意枯竭的转型困境；社群管理的权力斗争；文化挪用的争议事件；表演型人格的社交疲惫；创业压力的健康预警",
                 image="Queen of Wands.jpg"),

    # 宫廷牌-国王系列
    MinorArcana(ranks="King",
                 suits="Cups",
                 upright_meaning="情感智慧的终极导师；艺术领域的造雨者；跨文化沟通的桥梁人物；心理行业的权威专家；情商管理的典范人物",
                 reversed_meaning="情感操控的隐性暴君；艺术资本的权力垄断；文化融合的表面工程；心理咨询的伦理越界；情绪压抑的身体反噬",
                 image="King of Cups.jpg"),

    MinorArcana(ranks="King",
                 suits="Pentacles",
                 upright_meaning="商业帝国的掌舵者；百年企业的传承智慧；区块链技术的合规应用；传统金融的革新力量；城市建设的宏观规划",
                 reversed_meaning="商业垄断的监管危机；传统企业的转型困境；加密货币的投资风险；金融创新的伦理争议；城市规划的生态破坏",
                 image="King of Pentacles.jpg"),

    MinorArcana(ranks="King",
                 suits="Swords",
                 upright_meaning="司法体系的权威代表；人工智能的伦理制定者；军事战略的终极决策；学术领域的诺贝尔级人物；信息时代的规则制定者",
                 reversed_meaning="司法腐败的权力滥用；算法霸权的伦理危机；军事扩张的灾难后果；学术权威的知识垄断；信息管控的自由争议",
                 image="King of Swords.jpg"),

    MinorArcana(ranks="King",
                 suits="Wands",
                 upright_meaning="跨国集团的战略家；文化输出的国家名片；体育产业的改革推动者；危机中的魅力领导者；新能源革命的领军人物",
                 reversed_meaning="全球化战略的文化冲突；国家形象的公关危机；体育丑闻的连带责任；领导魅力的个人崇拜；新能源开发的生态代价",
                 image="King of Wands.jpg")]
Spread_position_initial_data = [
    # 三角牌阵（4）
    TarotSpreadPosition(spread_type=4, position=0, meaning="过去影响因素"),
    TarotSpreadPosition(spread_type=4, position=1, meaning="当前状况分析"),
    TarotSpreadPosition(spread_type=4, position=2, meaning="未来发展趋势"),

    # 六芒星牌阵（5）
    TarotSpreadPosition(spread_type=5, position=0, meaning="问题现状"),
    TarotSpreadPosition(spread_type=5, position=1, meaning="当前挑战"),
    TarotSpreadPosition(spread_type=5, position=2, meaning="行动建议"),
    TarotSpreadPosition(spread_type=5, position=3, meaning="潜在根源"),
    TarotSpreadPosition(spread_type=5, position=4, meaning="希望与恐惧"),
    TarotSpreadPosition(spread_type=5, position=5, meaning="最终结果"),

    # 凯尔特十字（6）
    TarotSpreadPosition(spread_type=6, position=0, meaning="当前状况核心"),
    TarotSpreadPosition(spread_type=6, position=1, meaning="直接影响因素/障碍"),
    TarotSpreadPosition(spread_type=6, position=2, meaning="过去影响因素"),
    TarotSpreadPosition(spread_type=6, position=3, meaning="未来近期发展"),
    TarotSpreadPosition(spread_type=6, position=4, meaning="潜在目标/高处"),
    TarotSpreadPosition(spread_type=6, position=5, meaning="问题根源/基础"),
    TarotSpreadPosition(spread_type=6, position=6, meaning="自我态度/情绪"),
    TarotSpreadPosition(spread_type=6, position=7, meaning="环境/他人影响"),
    TarotSpreadPosition(spread_type=6, position=8, meaning="希望与恐惧"),
    TarotSpreadPosition(spread_type=6, position=9, meaning="最终结果"),


    # 恋人牌阵（7）
    TarotSpreadPosition(spread_type=7, position=0, meaning="求问者现状"),
    TarotSpreadPosition(spread_type=7, position=1, meaning="对方状态"),
    TarotSpreadPosition(spread_type=7, position=2, meaning="关系现状"),
    TarotSpreadPosition(spread_type=7, position=3, meaning="面临挑战"),
    TarotSpreadPosition(spread_type=7, position=4, meaning="未来发展趋势")
]