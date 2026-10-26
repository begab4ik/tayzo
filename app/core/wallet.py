"""Операции с балансом. Единственное место, где меняется users.balance.

Каждое изменение — строка в ledger. Строка пользователя блокируется (FOR UPDATE),
поэтому двойное списание при параллельных запросах невозможно.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import LedgerType
from app.core.exceptions import InsufficientBalance
from app.db.models import LedgerEntry, User


async def lock_user(session: AsyncSession, user_id: int) -> User:
    """Взять строку пользователя под FOR UPDATE. Вызывать ДО вставки связанных строк (orders и т.п.),
    иначе FK-вставка возьмёт shared-lock и параллельные транзакции могут словить deadlock."""
    # populate_existing обязателен: иначе вернётся объект из identity map со старым балансом,
    # прочитанным ДО захвата блокировки.
    q = select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True)
    user = (await session.execute(q)).scalar_one()
    return user


_lock_user = lock_user


async def apply(
    session: AsyncSession,
    user_id: int,
    amount: int,
    type_: LedgerType,
    *,
    ref_type: str | None = None,
    ref_id: str | int | None = None,
    comment: str | None = None,
    allow_negative: bool = False,
) -> LedgerEntry:
    """Изменить баланс на amount (может быть отрицательным). Возвращает запись ledger."""
    user = await _lock_user(session, user_id)
    new_balance = user.balance + amount
    if new_balance < 0 and not allow_negative:
        raise InsufficientBalance(need=-amount, have=user.balance)

    user.balance = new_balance
    if type_ == LedgerType.TOPUP:
        user.total_topup += amount
    elif type_ == LedgerType.PURCHASE:
        user.total_spent += -amount
    elif type_ == LedgerType.REFUND:
        user.total_spent -= amount

    entry = LedgerEntry(
        user_id=user_id,
        amount=amount,
        type=type_,
        balance_after=new_balance,
        ref_type=ref_type,
        ref_id=str(ref_id) if ref_id is not None else None,
        comment=comment,
    )
    session.add(entry)
    await session.flush()
    return entry


async def charge(session: AsyncSession, user_id: int, amount: int, order_id: int) -> LedgerEntry:
    return await apply(session, user_id, -amount, LedgerType.PURCHASE, ref_type="order", ref_id=order_id)


async def refund(session: AsyncSession, user_id: int, amount: int, order_id: int, comment: str | None = None) -> LedgerEntry:
    return await apply(session, user_id, amount, LedgerType.REFUND, ref_type="order", ref_id=order_id, comment=comment)


async def topup(session: AsyncSession, user_id: int, amount: int, payment_id: int) -> LedgerEntry:
    return await apply(session, user_id, amount, LedgerType.TOPUP, ref_type="payment", ref_id=payment_id)


async def history(session: AsyncSession, user_id: int, limit: int = 10) -> list[LedgerEntry]:
    q = select(LedgerEntry).where(LedgerEntry.user_id == user_id).order_by(LedgerEntry.id.desc()).limit(limit)
    return list((await session.execute(q)).scalars())
