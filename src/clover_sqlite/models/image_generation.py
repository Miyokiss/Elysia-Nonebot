from __future__ import annotations

import re
from datetime import date, timedelta
from enum import Enum

from tortoise import fields
from tortoise.transactions import in_transaction

from src.clover_sqlite.data_init.db_connect import Model


class DailyQuotaStatus(str, Enum):
    ALLOWED = "allowed"
    USER_LIMIT_REACHED = "user_limit_reached"


_last_cleanup_date: date | None = None


class ImageGenerationUsage(Model):
    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    scope_id = fields.CharField(max_length=192)
    request_date = fields.DateField(index=True)
    request_count = fields.IntField(default=0)

    class Meta:
        table = "image_generation_usage"
        table_description = "生图每日额度记录"
        unique_together = (("scope_id", "request_date"),)

    @staticmethod
    async def _increment_if_available(
        connection,
        *,
        scope_id: str,
        request_date: date,
        limit: int,
    ) -> bool:
        affected, _ = await connection.execute_query(
            """
            INSERT INTO "image_generation_usage"
                ("scope_id", "request_date", "request_count")
            VALUES (?, ?, 1)
            ON CONFLICT ("scope_id", "request_date") DO UPDATE SET
                "request_count" = "request_count" + 1
            WHERE "request_count" < ?
            """,
            [scope_id, request_date.isoformat(), limit],
        )
        return affected == 1

    @classmethod
    async def reserve_daily_usage(
        cls,
        user_id: str,
        *,
        user_limit: int,
        connection_name: str = "default",
        namespace: str = "",
    ) -> DailyQuotaStatus:
        user_limit = max(0, int(user_limit))
        if user_limit == 0:
            return DailyQuotaStatus.ALLOWED
        if namespace and not re.fullmatch(r"[a-z0-9_-]{1,32}", namespace):
            raise ValueError("invalid quota namespace")

        today = date.today()
        scope_prefix = f"{namespace}:" if namespace else ""
        async with in_transaction(connection_name) as connection:
            if not await cls._increment_if_available(
                connection,
                scope_id=f"{scope_prefix}user:{user_id}",
                request_date=today,
                limit=user_limit,
            ):
                return DailyQuotaStatus.USER_LIMIT_REACHED

            global _last_cleanup_date
            if _last_cleanup_date != today:
                await connection.execute_query(
                    'DELETE FROM "image_generation_usage" WHERE "request_date" < ?',
                    [(today - timedelta(days=90)).isoformat()],
                )
                _last_cleanup_date = today

        return DailyQuotaStatus.ALLOWED
