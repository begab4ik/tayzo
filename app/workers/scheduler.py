"""Периодические задачи: курс TON, себестоимость звезды с Fragment, алерт по балансу, дневной отчёт."""
from __future__ import annotations

import logging
from decimal import Decimal

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.bot.notify import notify_admins
from app.config import settings
from app.core import settings_store as cfg
from app.core import stats as stats_svc
from app.core.money import fmt_uzs
from app.db.base import get_session
from app.providers.registry import fragment_client, is_manual_mode

log = logging.getLogger(__name__)


async def update_ton_rate() -> None:
    """TON→USD с CoinGecko × USD→UZS с ЦБ Узбекистана."""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            cg = await c.get("https://api.coingecko.com/api/v3/simple/price", params={"ids": "the-open-network", "vs_currencies": "usd"})
            ton_usd = Decimal(str(cg.json()["the-open-network"]["usd"]))
            cbu = await c.get("https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/")
            usd_uzs = Decimal(str(cbu.json()[0]["Rate"]))
        rate = (ton_usd * usd_uzs).quantize(Decimal("1"))
        async with get_session() as session:
            await cfg.set_value(session, "ton_rate_uzs", str(rate))
        log.info("TON rate updated: %s UZS (ton=%s usd, usd=%s uzs)", rate, ton_usd, usd_uzs)
    except Exception as e:  # noqa: BLE001
        log.warning("update_ton_rate failed: %s", e)


async def update_star_cost() -> None:
    if is_manual_mode():
        return
    from app.providers.fragment import fetch_star_price_ton

    price = await fetch_star_price_ton(fragment_client)
    if price:
        async with get_session() as session:
            await cfg.set_value(session, "star_price_ton", str(price.quantize(Decimal("0.000001"))))
        log.info("star cost updated: %s TON", price)


async def check_ton_balance() -> None:
    if is_manual_mode():
        return
    from app.providers.ton_wallet import ton_wallet

    try:
        bal = await ton_wallet.balance()
    except Exception as e:  # noqa: BLE001
        log.warning("ton balance check failed: %s", e)
        return
    async with get_session() as session:
        threshold = await cfg.get_dec(session, "low_ton_alert")
    if bal < threshold:
        await notify_admins(f"⚠️ На TON-кошельке осталось <b>{bal:.3f} TON</b> (порог {threshold}). Пополни, иначе заказы встанут.")


async def daily_report() -> None:
    async with get_session() as session:
        s = await stats_svc.collect(session, "today")
    await notify_admins(
        "🌅 <b>Отчёт за вчера/сегодня</b>\n"
        f"⭐ {s.stars_sold} звёзд · 💎 {s.premium_orders} premium\n"
        f"💵 Выручка {fmt_uzs(s.revenue)} · прибыль {fmt_uzs(s.profit)}\n"
        f"💳 Пополнений {fmt_uzs(s.topup_sum)} · 👤 новых {s.new_users}\n"
        f"👨‍💻 Требуют внимания: {s.manual}"
    )


def build_scheduler() -> AsyncIOScheduler:
    sch = AsyncIOScheduler(timezone=settings.timezone)
    sch.add_job(update_ton_rate, IntervalTrigger(minutes=10), next_run_time=None, id="ton_rate")
    sch.add_job(update_star_cost, IntervalTrigger(hours=1), id="star_cost")
    sch.add_job(check_ton_balance, IntervalTrigger(minutes=30), id="ton_balance")
    sch.add_job(daily_report, CronTrigger(hour=9, minute=0), id="daily_report")
    return sch
