"""Виртуальные номера: цена, покупка, проверка SMS, отмена с возвратом."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings_store as cfg
from app.core import wallet
from app.core.enums import LedgerType
from app.core.exceptions import InsufficientBalance, ProviderError
from app.db.models import Activation, User
from app.providers.herosms import LIFETIME_MIN, SERVICE_NAMES, herosms

log = logging.getLogger(__name__)

ACTIVE = ("waiting", "code")


async def price_uzs(session: AsyncSession, usd: float) -> int:
    rate = await cfg.get_dec(session, "usd_rate_uzs")
    markup = await cfg.get_dec(session, "sms_markup_percent")
    mn = await cfg.get_int(session, "sms_min_price")
    raw = Decimal(str(usd)) * rate * (1 + markup / 100)
    return max(mn, int(math.ceil(raw / 500)) * 500)


async def find_offer(service: str, country: int) -> dict | None:
    for o in await herosms.offers(service):
        if o["country"] == country:
            return o
    return None


async def buy(session: AsyncSession, user: User, service: str, country: int, lang: str = "ru") -> Activation:
    """Списать деньги и выдать номер. Номера нет — ProviderError, деньги не трогаем."""
    offer = await find_offer(service, country)
    if not offer:
        raise ProviderError("NO_NUMBERS")
    price = await price_uzs(session, offer["usd"])
    user = await wallet.lock_user(session, user.id)
    if user.balance < price:
        raise InsufficientBalance(need=price, have=user.balance)
    # номер берём до списания: не выдали — ничего не потеряли
    data = await herosms.get_number(service, country, max_usd=offer["usd"] * 1.15)
    names = (await herosms.countries()).get(country) or {}
    act = Activation(
        user_id=user.id, ext_id=str(data["activationId"]), service=service, service_name=SERVICE_NAMES.get(service, service),
        country=country, country_name=names.get(lang if lang == "en" else "ru"), phone=str(data["phoneNumber"]), price=price,
        cost_usd=str(data.get("activationCost") or offer["usd"]), status="waiting",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=LIFETIME_MIN),
    )
    session.add(act)
    await session.flush()
    await wallet.apply(session, user.id, -price, LedgerType.PURCHASE, ref_type="activation", ref_id=act.id, comment=f"Номер {act.service_name} +{act.phone}")
    try:
        await herosms.set_status(act.ext_id, 1)  # «готов принять SMS»
    except Exception as e:  # noqa: BLE001
        log.info("set_status(1) %s: %s", act.ext_id, e)
    log.info("activation %s: user=%s %s/%s +%s price=%s", act.id, user.id, service, country, act.phone, price)
    return act


async def _refund(session: AsyncSession, act: Activation, status: str) -> None:
    act.status = status
    if not act.refunded and not act.code:
        act.refunded = True
        await wallet.apply(session, act.user_id, act.price, LedgerType.REFUND, ref_type="activation", ref_id=act.id, comment=f"SMS не пришла, номер +{act.phone}")


async def refresh(session: AsyncSession, act: Activation) -> Activation:
    """Спросить у HeroSMS, пришла ли SMS; по таймауту без кода — отменить и вернуть деньги."""
    if act.status not in ACTIVE:
        return act
    try:
        st, code = await herosms.status(act.ext_id)
    except Exception as e:  # noqa: BLE001
        log.info("status %s failed: %s", act.ext_id, e)
        st, code = "wait", None
    if st == "ok" and code:
        act.code, act.status = code, "code"
    elif st == "cancel":
        await _refund(session, act, "cancelled") if not act.code else setattr(act, "status", "done")
    if act.status in ACTIVE and datetime.now(timezone.utc) >= act.expires_at:
        if act.code:
            act.status = "done"
            try:
                await herosms.set_status(act.ext_id, 6)
            except Exception:  # noqa: BLE001
                pass
        else:
            try:
                await herosms.set_status(act.ext_id, 8)
            except Exception:  # noqa: BLE001
                pass
            await _refund(session, act, "expired")
    return act


async def cancel(session: AsyncSession, act: Activation) -> tuple[bool, str]:
    """Отмена пользователем. (ok, причина). Если код уже пришёл — отменить нельзя."""
    await refresh(session, act)
    if act.status not in ACTIVE:
        return True, ""
    if act.code:
        return False, "code"
    try:
        res = await herosms.set_status(act.ext_id, 8)
    except ProviderError as e:
        res = str(e)
    if "EARLY_CANCEL_DENIED" in res:
        return False, "early"
    if "ACCESS_CANCEL" in res or "CANCEL" in res or "NO_ACTIVATION" in res:
        await _refund(session, act, "cancelled")
        return True, ""
    return False, "error"


async def finish(session: AsyncSession, act: Activation) -> None:
    if act.status == "code":
        act.status = "done"
        try:
            await herosms.set_status(act.ext_id, 6)
        except Exception:  # noqa: BLE001
            pass


async def more_sms(act: Activation) -> None:
    await herosms.set_status(act.ext_id, 3)


async def active_all(session: AsyncSession) -> list[Activation]:
    return list((await session.execute(select(Activation).where(Activation.status.in_(ACTIVE)))).scalars())


async def user_list(session: AsyncSession, user_id: int, limit: int = 20) -> list[Activation]:
    q = select(Activation).where(Activation.user_id == user_id).order_by(Activation.id.desc()).limit(limit)
    return list((await session.execute(q)).scalars())
