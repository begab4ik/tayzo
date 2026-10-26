from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings_store as cfg
from app.core import wallet
from app.core.enums import LedgerType
from app.db.models import LedgerEntry, User


def ref_link(bot_username: str, user_id: int) -> str:
    return f"https://t.me/{bot_username}?start=ref{user_id}"


def parse_ref(payload: str | None) -> int | None:
    if payload and payload.startswith("ref") and payload[3:].isdigit():
        return int(payload[3:])
    return None


async def reward_for_topup(session: AsyncSession, user: User, topup_amount: int, payment_id: int) -> int:
    """Начислить рефереру % от пополнения. Возвращает сумму бонуса (0 если нет реферера)."""
    if not user.referrer_id:
        return 0
    percent = await cfg.get_int(session, "referral_percent")
    bonus = topup_amount * percent // 100
    if bonus <= 0:
        return 0
    await wallet.apply(
        session, user.referrer_id, bonus, LedgerType.REFERRAL_BONUS,
        ref_type="payment", ref_id=payment_id, comment=f"{percent}% от пополнения {user.display}",
    )
    return bonus


async def stats(session: AsyncSession, user_id: int) -> tuple[int, int]:
    """(кол-во рефералов, заработано сум)"""
    count = (await session.execute(select(func.count()).where(User.referrer_id == user_id))).scalar_one()
    earned = (
        await session.execute(
            select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
                LedgerEntry.user_id == user_id, LedgerEntry.type == LedgerType.REFERRAL_BONUS
            )
        )
    ).scalar_one()
    return int(count), int(earned)
