"""API для Telegram Mini App (tayzo.uz/app).

Авторизация: заголовок `Authorization: tma <initData>` — строка initData из Telegram.WebApp,
проверяем подпись HMAC по токену бота (https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app).
Вся бизнес-логика — та же, что у бота (core.*), поэтому балансы/заказы общие.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from decimal import Decimal
from typing import Annotated
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.i18n import LANGS, t
from app.bot.loader import bot
from app.bot.middlewares.subscription import get_channels, is_subscribed
from app.bot.notify import notify_admins
from app.config import settings
from app.core import orders as orders_svc
from app.core import pricing, referrals, wallet
from app.core import settings_store as cfg
from app.core.enums import ProductType
from app.core.exceptions import InsufficientBalance, ProviderError, RecipientNotFound
from app.core.money import fmt_uzs
from app.db.base import get_session
from app.db.models import Order, User
from app.payments import common as pay
from app.providers.base import Recipient
from app.providers.registry import get_provider, is_manual_mode
from app.providers.telegram_account import tg_account

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

INITDATA_MAX_AGE = 24 * 3600


# ---------- auth ----------
def _check_init_data(init_data: str) -> dict:
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", None)
    if not received:
        raise HTTPException(401, "no hash")
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise HTTPException(401, "bad signature")
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        auth_date = 0
    if time.time() - auth_date > INITDATA_MAX_AGE:
        raise HTTPException(401, "init data expired")
    try:
        pairs["user"] = json.loads(pairs.get("user", "{}"))
    except ValueError:
        raise HTTPException(401, "bad user")
    return pairs


async def _get_user(session: AsyncSession, tg: dict, start_param: str | None) -> User:
    user = await session.get(User, int(tg["id"]))
    if user is None:
        referrer_id = referrals.parse_ref(start_param)
        if referrer_id == tg["id"] or (referrer_id and await session.get(User, referrer_id) is None):
            referrer_id = None
        lang = (tg.get("language_code") or "ru")[:2]
        user = User(
            id=int(tg["id"]),
            username=tg.get("username"),
            first_name=tg.get("first_name"),
            language=lang if lang in LANGS else "ru",
            referrer_id=referrer_id,
        )
        session.add(user)
        await session.flush()
    elif user.username != tg.get("username") or user.first_name != tg.get("first_name"):
        user.username = tg.get("username")
        user.first_name = tg.get("first_name")
    return user


class Ctx:
    def __init__(self, session: AsyncSession, user: User, start_param: str | None):
        self.session, self.user, self.start_param = session, user, start_param
        self.lang = user.language


async def ctx(authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith("tma "):
        raise HTTPException(401, "unauthorized")
    data = _check_init_data(authorization[4:])
    tg = data.get("user") or {}
    if not tg.get("id"):
        raise HTTPException(401, "no user")
    async with get_session() as session:
        user = await _get_user(session, tg, data.get("start_param"))
        if user.is_banned and not settings.is_admin(user.id):
            raise HTTPException(403, "banned")
        if not settings.is_admin(user.id) and await cfg.get_bool(session, "maintenance"):
            raise HTTPException(503, "maintenance")
        c = Ctx(session, user, data.get("start_param"))
        yield c
        await session.commit()


C = Annotated[Ctx, Depends(ctx)]


def _err(status: int, code: str, message: str, **extra):
    raise HTTPException(status, {"code": code, "message": message, **extra})


def _order_json(o: Order) -> dict:
    return {
        "id": o.id,
        "product": o.product,
        "quantity": o.quantity,
        "recipient": o.recipient_username,
        "recipient_name": o.recipient_name,
        "gift_id": str(o.gift_id) if o.gift_id else None,
        "gift_title": o.gift_title,
        "price": o.price,
        "status": o.status,
        "created_at": o.created_at.isoformat(),
        "delivered_at": o.delivered_at.isoformat() if o.delivered_at else None,
    }


# ---------- endpoints ----------
@router.get("/me")
async def me(c: C):
    s, u = c.session, c.user
    channels = await get_channels(s)
    missing = await is_subscribed(bot, u.id, channels) if channels else []
    premium = {m: (await pricing.quote_premium(s, m)).price_uzs for m in pricing.PREMIUM_MONTHS}
    bot_me = await bot.me()
    recent = await orders_svc.user_orders(s, u.id, limit=5)
    return {
        "user": {
            "id": u.id, "name": u.first_name or "", "username": u.username, "lang": u.language,
            "balance": u.balance, "total_stars": u.total_stars, "total_spent": u.total_spent,
            "referral_link": referrals.ref_link(bot_me.username, u.id),
            "referral_percent": await cfg.get_int(s, "referral_percent"),
        },
        "prices": {
            "star": await pricing.star_price_each(s),
            "premium": premium,
            "min_stars": await cfg.get_int(s, "min_stars"),
            "max_stars": await cfg.get_int(s, "max_stars"),
            "min_topup": await cfg.get_int(s, "min_topup"),
            "max_topup": await cfg.get_int(s, "max_topup"),
        },
        "flags": {
            "stars": await cfg.get_bool(s, "stars_enabled"),
            "premium": await cfg.get_bool(s, "premium_enabled"),
            "gifts": await cfg.get_bool(s, "gifts_enabled") and tg_account.configured and bool(await cfg.get(s, "tg_session")),
            "click": bool(settings.payment_methods),
            "payment_methods": settings.payment_methods,
            "manual": is_manual_mode(),
        },
        "need_subscribe": [{"title": ch.title, "url": ch.url} for ch in missing],
        "support": settings.support_username,
        "bot": bot_me.username,
        "recent_orders": [_order_json(o) for o in recent],
    }


class LangIn(BaseModel):
    lang: str


@router.post("/lang")
async def set_lang(c: C, body: LangIn):
    if body.lang not in LANGS:
        _err(400, "bad_lang", "unknown language")
    c.user.language = body.lang
    c.user.lang_chosen = True
    return {"ok": True}


@router.api_route("/subscribe/check", methods=["GET", "POST"])
async def subscribe_check(c: C):
    channels = await get_channels(c.session)
    missing = await is_subscribed(bot, c.user.id, channels, force=True) if channels else []
    return {"need_subscribe": [{"title": ch.title, "url": ch.url} for ch in missing]}


class QuoteIn(BaseModel):
    qty: int = Field(ge=1, le=1_000_000)


@router.post("/stars/quote")
async def stars_quote(c: C, body: QuoteIn):
    mn, mx = await cfg.get_int(c.session, "min_stars"), await cfg.get_int(c.session, "max_stars")
    if not (mn <= body.qty <= mx):
        _err(400, "qty_range", t(c.lang, "qty_range", min=mn, max=mx))
    q = await pricing.quote_stars(c.session, body.qty)
    return {"qty": body.qty, "price": q.price_uzs, "balance": c.user.balance}


@router.get("/gifts")
async def gifts(c: C):
    s = c.session
    enabled = await cfg.get_bool(s, "gifts_enabled") and tg_account.configured and bool(await cfg.get(s, "tg_session"))
    if not enabled:
        return {"enabled": False, "gifts": []}
    try:
        items = await tg_account.gifts()
    except Exception as e:  # noqa: BLE001
        log.warning("gifts catalog unavailable: %s", e)
        return {"enabled": True, "gifts": [], "error": "catalog"}
    out = []
    for g in items:
        q = await pricing.quote_gift(s, g["stars"])
        out.append({**g, "price": q.price_uzs})
    return {"enabled": True, "gifts": out}


class RecipientIn(BaseModel):
    product: str = "stars"
    username: str = Field(min_length=1, max_length=64)
    qty: int = 50


@router.post("/recipient")
async def resolve_recipient(c: C, body: RecipientIn):
    username = body.username.strip().lstrip("@")
    if not username or not all(ch.isalnum() or ch == "_" for ch in username) or len(username) < 4:
        _err(400, "bad_username", t(c.lang, "bad_username"))
    product = {"premium": ProductType.PREMIUM, "gift": ProductType.GIFT}.get(body.product, ProductType.STARS)
    qty = body.qty if product != ProductType.PREMIUM else (body.qty if body.qty in pricing.PREMIUM_MONTHS else 3)
    try:
        rcp = await get_provider(product).resolve_recipient(username, qty)
    except RecipientNotFound as e:
        _err(404, "not_found", str(e) or t(c.lang, "recipient_not_found"))
    except ProviderError as e:
        await notify_admins(f"⚠️ Fragment resolve error (miniapp): {e.message}")
        _err(502, "provider", t(c.lang, "recipient_check_fail"))
    return {"username": rcp.username, "name": rcp.name, "token": rcp.token}


class OrderIn(BaseModel):
    product: str
    qty: int = 0
    gift_id: str | None = None
    count: int = Field(default=1, ge=1, le=20)        # сколько подарков
    message: str | None = Field(default=None, max_length=255)  # подпись к подарку
    recipient_username: str
    recipient_name: str = ""
    recipient_token: str = ""


@router.post("/orders")
async def create_order(c: C, body: OrderIn):
    s, u = c.session, c.user
    channels = await get_channels(s)
    if channels and await is_subscribed(bot, u.id, channels):
        _err(403, "subscribe", "subscribe required")
    gift = None
    if body.product == "stars":
        if not await cfg.get_bool(s, "stars_enabled"):
            _err(400, "disabled", t(c.lang, "stars_disabled"))
        mn, mx = await cfg.get_int(s, "min_stars"), await cfg.get_int(s, "max_stars")
        if not (mn <= body.qty <= mx):
            _err(400, "qty_range", t(c.lang, "qty_range", min=mn, max=mx))
        quote = await pricing.quote_stars(s, body.qty)
    elif body.product == "premium":
        if not await cfg.get_bool(s, "premium_enabled"):
            _err(400, "disabled", t(c.lang, "premium_disabled"))
        if body.qty not in pricing.PREMIUM_MONTHS:
            _err(400, "bad_months", "months must be 3, 6 or 12")
        quote = await pricing.quote_premium(s, body.qty)
    elif body.product == "gift":
        if not (await cfg.get_bool(s, "gifts_enabled") and tg_account.configured):
            _err(400, "disabled", "gifts disabled")
        gift = await tg_account.gift_by_id(body.gift_id or "")
        if not gift:
            _err(404, "gift_not_found", "gift not found")
        if gift.get("remains") == 0:
            _err(400, "sold_out", "sold out")
        quote = await pricing.quote_gift(s, gift["stars"])
        body.qty = gift["stars"]
    else:
        _err(400, "bad_product", "unknown product")
    rcp = Recipient(username=body.recipient_username.lstrip("@"), name=body.recipient_name or body.recipient_username, token=body.recipient_token)
    if not rcp.token:
        # токен не передали — проверяем получателя сами
        try:
            rcp = await get_provider(quote.product).resolve_recipient(rcp.username, body.qty)
        except RecipientNotFound as e:
            _err(404, "not_found", str(e) or t(c.lang, "recipient_not_found"))
        except ProviderError:
            _err(502, "provider", t(c.lang, "recipient_check_fail"))
    count = body.count if body.product == "gift" else 1
    if gift and gift.get("per_user_remains") is not None:
        count = min(count, max(1, int(gift["per_user_remains"])))
    if gift and gift.get("remains") is not None:
        count = min(count, max(1, int(gift["remains"])))
    msg = (body.message or "").strip()[:255] or None
    if u.balance < quote.price_uzs * count:
        _err(402, "insufficient", t(c.lang, "insufficient", need=fmt_uzs(quote.price_uzs * count), have=fmt_uzs(u.balance)), need=quote.price_uzs * count, have=u.balance)
    created = []
    try:
        for _ in range(count):
            created.append(await orders_svc.create(s, u, quote, rcp, gift=gift, gift_message=msg))
    except InsufficientBalance as e:
        _err(402, "insufficient", t(c.lang, "insufficient", need=fmt_uzs(e.need), have=fmt_uzs(e.have)), need=e.need, have=e.have)
    await s.commit()
    await s.refresh(u)
    from app.bot.handlers.stars import notify_new_order

    for order in created:
        await notify_new_order(order, u)
    return {"order": _order_json(created[0]), "orders": [_order_json(o) for o in created], "count": len(created), "balance": u.balance}


@router.get("/orders")
async def list_orders(c: C, limit: int = 30):
    rows = await orders_svc.user_orders(c.session, c.user.id, limit=min(limit, 100))
    return {"orders": [_order_json(o) for o in rows]}


@router.get("/orders/{order_id}")
async def get_order(c: C, order_id: int):
    o = await c.session.get(Order, order_id)
    if not o or o.user_id != c.user.id:
        _err(404, "not_found", "order not found")
    await c.session.refresh(c.user)
    return {"order": _order_json(o), "balance": c.user.balance}


class TopupIn(BaseModel):
    amount: int = Field(ge=1000, le=100_000_000)
    method: str = "click"


@router.post("/topup")
async def topup(c: C, body: TopupIn):
    s, u = c.session, c.user
    mn, mx = await cfg.get_int(s, "min_topup"), await cfg.get_int(s, "max_topup")
    if not (mn <= body.amount <= mx):
        _err(400, "amount_range", f"{fmt_uzs(mn)} – {fmt_uzs(mx)}", min=mn, max=mx)
    methods = pay.available()
    if not methods:
        _err(503, "unavailable", t(c.lang, "topup_unavailable"))
    method = body.method if body.method in methods else methods[0]
    payment = await pay.create(s, u.id, body.amount, method)
    await s.commit()
    bot_me = await bot.me()
    return {"payment_id": payment.id, "method": method, "url": pay.pay_url(payment, return_url=f"https://t.me/{bot_me.username}", lang=c.lang)}


@router.get("/ledger")
async def ledger(c: C, limit: int = 30):
    rows = await wallet.history(c.session, c.user.id, limit=min(limit, 100))
    return {
        "items": [
            {"id": r.id, "amount": r.amount, "type": r.type, "balance_after": r.balance_after, "comment": r.comment, "created_at": r.created_at.isoformat()}
            for r in rows
        ]
    }
