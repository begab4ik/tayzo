"""Статистика для админа: продажи, выручка, себестоимость, прибыль, пополнения, юзеры."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.enums import OrderStatus, PaymentStatus, ProductType
from app.db.models import Order, Payment, User

PERIODS = {"today": "Сегодня", "7d": "7 дней", "30d": "30 дней", "all": "Всё время"}


def period_start(period: str) -> datetime | None:
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "7d":
        return now - timedelta(days=7)
    if period == "30d":
        return now - timedelta(days=30)
    return None


@dataclass
class Stats:
    period: str
    stars_sold: int = 0
    stars_orders: int = 0
    premium_orders: int = 0
    revenue: int = 0          # сумма price доставленных заказов
    cost: int = 0             # сумма cost_uzs доставленных
    topup_sum: int = 0
    topup_count: int = 0
    new_users: int = 0
    pending: int = 0
    manual: int = 0
    refunded_sum: int = 0

    @property
    def profit(self) -> int:
        return self.revenue - self.cost

    @property
    def margin_pct(self) -> float:
        return (self.profit / self.revenue * 100) if self.revenue else 0.0


async def collect(session: AsyncSession, period: str) -> Stats:
    s = Stats(period=period)
    start = period_start(period)

    def since(col):
        return col >= start if start else True

    delivered = Order.status == OrderStatus.DELIVERED
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(case((delivered & (Order.product == ProductType.STARS), Order.quantity), else_=0)), 0),
                func.coalesce(func.sum(case((delivered & (Order.product == ProductType.STARS), 1), else_=0)), 0),
                func.coalesce(func.sum(case((delivered & (Order.product == ProductType.PREMIUM), 1), else_=0)), 0),
                func.coalesce(func.sum(case((delivered, Order.price), else_=0)), 0),
                func.coalesce(func.sum(case((delivered, Order.cost_uzs), else_=0)), 0),
                func.coalesce(func.sum(case((Order.status == OrderStatus.REFUNDED, Order.price), else_=0)), 0),
            ).where(since(Order.created_at))
        )
    ).one()
    s.stars_sold, s.stars_orders, s.premium_orders, s.revenue, s.cost, s.refunded_sum = (int(x) for x in row)

    row = (
        await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0), func.count())
            .where(Payment.status == PaymentStatus.PAID, since(Payment.paid_at))
        )
    ).one()
    s.topup_sum, s.topup_count = int(row[0]), int(row[1])

    s.new_users = int((await session.execute(select(func.count()).where(since(User.created_at)))).scalar_one())

    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(case((Order.status.in_([OrderStatus.PENDING, OrderStatus.PROCESSING]), 1), else_=0)), 0),
                func.coalesce(func.sum(case((Order.status.in_([OrderStatus.MANUAL, OrderStatus.FAILED]), 1), else_=0)), 0),
            )
        )
    ).one()
    s.pending, s.manual = int(row[0]), int(row[1])
    return s


async def totals(session: AsyncSession) -> dict:
    users = int((await session.execute(select(func.count()).select_from(User))).scalar_one())
    balances = int((await session.execute(select(func.coalesce(func.sum(User.balance), 0)))).scalar_one())
    return {"users": users, "balances": balances}


async def top_buyers(session: AsyncSession, limit: int = 5) -> list[User]:
    q = select(User).order_by(User.total_spent.desc()).limit(limit)
    return list((await session.execute(q)).scalars())
