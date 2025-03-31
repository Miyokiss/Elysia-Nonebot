from nonebot.rule import to_me
from nonebot.plugin import on_command
from nonebot.adapters.qq import MessageEvent
from src.clover_sqlite.models.chat import GroupChatRole
from src.clover_sqlite.models.chat import MODE_ELYSIA, MODE_OFF
from nonebot import logger

Elysia_super = on_command("爱莉希雅",aliases={"妖精爱莉"},rule=to_me(),priority=10,block=True)
@Elysia_super.handle()
async def handle_function(message: MessageEvent):

    if not hasattr(message, 'group_openid'):
        await Elysia_super.finish("暂未在当前场景下开放此功能。")

    member_openid, group_openid, content = message.author.id, message.group_openid, message.get_plaintext()
    # 判断是否为管理员
    if not await GroupChatRole.get_admin_list(group_openid, member_openid):
        await Elysia_super.finish("您没有权限使用此功能。")
    else:
        current_mode = await GroupChatRole.is_on(group_openid)
        if content == "/爱莉希雅":
            if current_mode != MODE_ELYSIA:
                await GroupChatRole.ai_mode(group_openid, MODE_ELYSIA)
                await Elysia_super.finish("成功开启爱莉希雅语音对话~")
            else:
                await Elysia_super.finish("当前群已是爱莉希雅聊天~")

        elif content == "/妖精爱莉":
            if current_mode == MODE_ELYSIA:
                await GroupChatRole.ai_mode(group_openid, MODE_OFF)
                await Elysia_super.finish("成功关闭超级爱莉对话~")
            else:
                await Elysia_super.finish("当前群已开启妖精爱莉聊天~")

            
