from nonebot.adapters.qq import MessageEvent
from nonebot.plugin import on_command
from nonebot.rule import to_me
from src.clover_sqlite.models.questions import Question

get_question = on_command("问答", rule=to_me(), priority=10)
@get_question.handle()
async def answer_question(message: MessageEvent):
    content = message.get_plaintext().replace("/问答", "").strip(" ")
    reply = await Question.search(content, via_question=True, fuzzy=False)
    if len(reply) > 0:
        await get_question.finish(reply[0][2])
    else:
        await get_question.finish("这个问题我没听说过哦")
