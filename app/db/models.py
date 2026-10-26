from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import LedgerType, OrderStatus, PaymentStatus, ProductType, PromoKind
from app.db.base import Base


def now_col(**kw):
    return mapped_column(DateTime(timezone=True), server_default=func.now(), **kw)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # telegram id
    username: Mapped[str | None] = mapped_column(String(64), index=True)
    first_name: Mapped[str | None] = mapped_column(String(128))
    language: Mapped[str] = mapped_column(String(5), default="ru")
    referrer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    balance: Mapped[int] = mapped_column(BigInteger, default=0)  # UZS, целые сумы
    total_topup: Mapped[int] = mapped_column(BigInteger, default=0)
    total_spent: Mapped[int] = mapped_column(BigInteger, default=0)
    total_stars: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = now_col()
    last_active_at: Mapped[datetime] = now_col(onupdate=func.now())

    orders: Mapped[list["Order"]] = relationship(back_populates="user")

    @property
    def display(self) -> str:
        return f"@{self.username}" if self.username else f"id{self.id}"


class LedgerEntry(Base):
    """Журнал движений денег. Баланс пользователя = сумма amount. Никогда не редактируется."""

    __tablename__ = "ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)  # +/- UZS
    type: Mapped[LedgerType] = mapped_column(String(32))
    balance_after: Mapped[int] = mapped_column(BigInteger)
    ref_type: Mapped[str | None] = mapped_column(String(32))  # payment / order / promo / user
    ref_id: Mapped[str | None] = mapped_column(String(64))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = now_col(index=True)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(16), default="click")
    amount: Mapped[int] = mapped_column(BigInteger)  # UZS
    status: Mapped[PaymentStatus] = mapped_column(String(16), default=PaymentStatus.CREATED, index=True)
    click_trans_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    click_paydoc_id: Mapped[str | None] = mapped_column(String(64))
    raw: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = now_col(index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    product: Mapped[ProductType] = mapped_column(String(16), index=True)
    recipient_username: Mapped[str] = mapped_column(String(64))
    recipient_name: Mapped[str | None] = mapped_column(String(128))
    recipient_token: Mapped[str | None] = mapped_column(String(128))  # recipient id из Fragment
    quantity: Mapped[int] = mapped_column(Integer)  # звёзды или месяцы премиума
    price: Mapped[int] = mapped_column(BigInteger)  # списано с баланса, UZS
    cost_ton: Mapped[Decimal | None] = mapped_column(Numeric(18, 9))  # себестоимость в TON
    cost_uzs: Mapped[int | None] = mapped_column(BigInteger)  # себестоимость в UZS по курсу на момент
    status: Mapped[OrderStatus] = mapped_column(String(16), default=OrderStatus.PENDING, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    fragment_req_id: Mapped[str | None] = mapped_column(String(64))
    tx_hash: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = now_col(index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="orders")

    @property
    def title(self) -> str:
        if self.product == ProductType.STARS:
            return f"⭐ {self.quantity} Stars"
        return f"💎 Premium {self.quantity} мес."


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    kind: Mapped[PromoKind] = mapped_column(String(16), default=PromoKind.BALANCE)
    amount: Mapped[int] = mapped_column(BigInteger)  # UZS бонус
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = now_col()


class PromoUse(Base):
    __tablename__ = "promo_uses"
    __table_args__ = (UniqueConstraint("promo_id", "user_id", name="uq_promo_user"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    promo_id: Mapped[int] = mapped_column(Integer, ForeignKey("promo_codes.id"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    created_at: Mapped[datetime] = now_col()


class RequiredChannel(Base):
    __tablename__ = "required_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    title: Mapped[str] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Setting(Base):
    """Key-value настройки, меняются из админки без перезапуска."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = now_col(onupdate=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = now_col()


Index("ix_orders_status_created", Order.status, Order.created_at)
