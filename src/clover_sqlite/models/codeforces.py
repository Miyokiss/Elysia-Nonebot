from tortoise import fields
from src.clover_sqlite.data_init.db_connect import Model

class CodeForces(Model):
    cf_id = fields.CharField(max_length=128, null=True, discription="用户codeforces账号")
    user_id = fields.CharField(max_length=64, discription="用户openid")

    class Meta:
        table = "codeforces"
        table_description = "cf表"


    @classmethod
    async def get_cf_id(cls, user_id: str | None):
        cf_table = await CodeForces.filter(user_id=user_id).first()
        if cf_table:
            return cf_table.cf_id
        else:
            return None


    @classmethod
    async def insert_cf_id(cls, cf_id: str | None, user_id: str | None):
        if not cf_id:
            return -1

        cf_table = await CodeForces.filter(user_id=user_id).first()
        if cf_table:
            cf_table.cf_id = cf_id
            await cf_table.save()
            return 1
        else:
            await cls.create(cf_id=cf_id, user_id=user_id)
            return 0