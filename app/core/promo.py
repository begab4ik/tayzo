from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import wallet
from app.core.enums import LedgerType, PromoKind
from app.core.exceptions import TayzoError
from app.db.models import PromoCode, PromoUse


def generate_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def create(session: AsyncSession, amount: int, max_uses: int, code: str | None = None, expires_at: datetime | None = None) -> PromoCode:
    promo = PromoCode(code=(code or generate_code()).upper(), kind=PromoKind.BALANCE, amount=amount, max_uses=max_uses, expires_at=expires_at)
    session.add(promo)
    await session.flush()
    return promo


async def activate(session: AsyncSession, user_id: int, code: str) -> PromoCode:
    code = code.strip().upper()
    promo = (await session.execute(select(PromoCode).where(PromoCode.code == code).with_for_update())).scalar_one_or_none()
    if not promo or not promo.is_active:
        raise TayzoError("Промокод не найден")
    if promo.expires_at and promo.expires_at < datetime.now(timezone.utc):
        raise TayzoError("Срок действия промокода истёк")
    if promo.used_count >= promo.max_uses:
        raise TayzoError("Промокод уже использован максимальное число раз")

    session.add(PromoUse(promo_id=promo.id, user_id=user_id))
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise TayzoError("Ты уже активировал этот промокод")

    promo.used_count += 1
    await wallet.apply(session, user_id, promo.amount, LedgerType.PROMO_BONUS, ref_type="promo", ref_id=promo.id, comment=code)
    return promo


async def list_active(session: AsyncSession, limit: int = 20) -> list[PromoCode]:
    q = select(PromoCode).where(PromoCode.is_active.is_(True)).order_by(PromoCode.id.desc()).limit(limit)
    return list((await session.execute(q)).scalars())
