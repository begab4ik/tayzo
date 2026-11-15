"""Mini App API: виртуальные номера (HeroSMS)."""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.miniapp import MIN_PAY, C, _err
from app.bot.i18n import t
from app.bot.loader import bot
from app.core import settings_store as cfg
from app.core import sms
from app.core.exceptions import InsufficientBalance, ProviderError
from app.core.money import fmt_uzs
from app.db.models import Activation
from app.payments import common as pay
from app.providers.herosms import SERVICES, herosms

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sms")


def act_json(a: Activation) -> dict:
    return {
        "id": a.id, "service": a.service, "service_name": a.service_name, "country": a.country, "country_name": a.country_name,
        "phone": a.phone, "price": a.price, "status": a.status, "code": a.code, "refunded": a.refunded,
        "created_at": a.created_at.isoformat(), "expires_at": a.expires_at.isoformat(),
    }


async def _enabled(s) -> bool:
    return herosms.configured and await cfg.get_bool(s, "sms_enabled")


@router.get("/services")
async def services(c: C):
    if not await _enabled(c.session):
        return {"enabled": False, "services": []}
    return {"enabled": True, "services": [{"code": k, "name": v} for k, v in SERVICES]}


@router.get("/offers")
async def offers(c: C, service: str = "tg"):
    s = c.session
    if not await _enabled(s):
        _err(400, "disabled", "sms disabled")
    if service not in dict(SERVICES):
        _err(400, "bad_service", "unknown service")
    try:
        rows = await herosms.offers(service)
        names = await herosms.countries()
    except Exception as e:  # noqa: BLE001
        log.warning("sms offers failed: %s", e)
        _err(502, "provider", t(c.lang, "err"))
    key = "en" if c.lang == "en" else "ru"
    out = []
    for r in rows:
        n = names.get(r["country"])
        if not n:
            continue
        out.append({"country": r["country"], "name": n.get(key) or n.get("ru"), "count": r["count"], "price": await sms.price_uzs(s, r["usd"])})
    out.sort(key=lambda x: (x["price"], x["name"]))
    return {"service": service, "offers": out}


class BuyIn(BaseModel):
    service: str
    country: int
    pay_method: str | None = None


@router.post("/buy")
async def buy(c: C, body: BuyIn):
    s, u = c.session, c.user
    if not await _enabled(s):
        _err(400, "disabled", "sms disabled")
    if body.service not in dict(SERVICES):
        _err(400, "bad_service", "unknown service")
    offer = await sms.find_offer(body.service, body.country)
    if not offer:
        _err(404, "no_numbers", t(c.lang, "sms_no_numbers"))
    price = await sms.price_uzs(s, offer["usd"])
    if u.balance < price:
        methods = pay.available()
        if body.pay_method and body.pay_method in methods:
            amount = max(price - u.balance, MIN_PAY)
            payment = await pay.create(s, u.id, amount, body.pay_method)
            payment.intent = {"product": "sms", "service": body.service, "country": body.country, "total": price, "lang": c.lang}
            await s.commit()
            me = await bot.me()
            return {"pay": {"payment_id": payment.id, "method": body.pay_method, "amount": amount, "total": price,
                            "url": pay.pay_url(payment, return_url=f"https://t.me/{me.username}", lang=c.lang)}}
        _err(402, "insufficient", t(c.lang, "insufficient", need=fmt_uzs(price), have=fmt_uzs(u.balance)), need=price, have=u.balance)
    try:
        act = await sms.buy(s, u, body.service, body.country, c.lang)
    except InsufficientBalance as e:
        _err(402, "insufficient", t(c.lang, "insufficient", need=fmt_uzs(e.need), have=fmt_uzs(e.have)), need=e.need, have=e.have)
    except ProviderError as e:
        log.warning("sms buy failed: %s", e)
        _err(409, "no_numbers", t(c.lang, "sms_no_numbers"))
    await s.commit()
    await s.refresh(u)
    return {"activation": act_json(act), "balance": u.balance}


@router.get("/list")
async def my_list(c: C):
    rows = await sms.user_list(c.session, c.user.id)
    return {"items": [act_json(a) for a in rows]}


async def _mine(c, act_id: int) -> Activation:
    a = await c.session.get(Activation, act_id, with_for_update=True)
    if not a or a.user_id != c.user.id:
        _err(404, "not_found", "not found")
    return a


@router.get("/{act_id}")
async def get_one(c: C, act_id: int):
    a = await _mine(c, act_id)
    await sms.refresh(c.session, a)
    await c.session.commit()
    await c.session.refresh(c.user)
    return {"activation": act_json(a), "balance": c.user.balance}


@router.post("/{act_id}/cancel")
async def cancel(c: C, act_id: int):
    a = await _mine(c, act_id)
    ok, why = await sms.cancel(c.session, a)
    await c.session.commit()
    await c.session.refresh(c.user)
    if not ok:
        _err(409, "cancel_" + why, t(c.lang, {"early": "sms_cancel_early", "code": "sms_cancel_code"}.get(why, "err")))
    return {"activation": act_json(a), "balance": c.user.balance}


@router.post("/{act_id}/done")
async def done(c: C, act_id: int):
    a = await _mine(c, act_id)
    await sms.finish(c.session, a)
    await c.session.commit()
    return {"activation": act_json(a), "balance": c.user.balance}


@router.post("/{act_id}/more")
async def more(c: C, act_id: int):
    a = await _mine(c, act_id)
    if a.status == "code":
        try:
            await sms.more_sms(a)
            a.status, a.notified_code = "waiting", a.code
            a.code = None
        except Exception as e:  # noqa: BLE001
            log.info("more sms failed: %s", e)
            _err(409, "more", t(c.lang, "err"))
    await c.session.commit()
    return {"activation": act_json(a), "balance": c.user.balance}
