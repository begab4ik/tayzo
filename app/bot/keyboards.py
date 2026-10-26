from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.core.money import fmt_uzs
from app.db.models import RequiredChannel

# ---------- Reply (главное меню) ----------
BTN_STARS = "⭐ Купить Stars"
BTN_PREMIUM = "💎 Premium"
BTN_BALANCE = "💰 Баланс"
BTN_PROFILE = "👤 Профиль"
BTN_ORDERS = "📦 Мои заказы"
BTN_PROMO = "🎟 Промокод"
BTN_FAQ = "ℹ️ Как это работает"
BTN_SUPPORT = "🆘 Поддержка"
BTN_ADMIN = "🛠 Админка"


def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.button(text=BTN_STARS)
    b.button(text=BTN_PREMIUM)
    b.button(text=BTN_BALANCE)
    b.button(text=BTN_PROFILE)
    b.button(text=BTN_ORDERS)
    b.button(text=BTN_PROMO)
    b.button(text=BTN_FAQ)
    b.button(text=BTN_SUPPORT)
    if is_admin:
        b.button(text=BTN_ADMIN)
    b.adjust(2, 2, 2, 2, 1)
    return b.as_markup(resize_keyboard=True)


# ---------- Inline ----------
def subscribe_kb(channels: list[RequiredChannel]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        b.button(text=f"📢 {ch.title}", url=ch.url)
    b.button(text="✅ Проверить подписку", callback_data="check_sub")
    b.adjust(1)
    return b.as_markup()


def balance_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="💳 Пополнить", callback_data="topup")
    b.button(text="📜 История", callback_data="ledger")
    b.adjust(2)
    return b.as_markup()


TOPUP_PRESETS = (10_000, 25_000, 50_000, 100_000, 250_000, 500_000)


def topup_amounts_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for a in TOPUP_PRESETS:
        b.button(text=fmt_uzs(a), callback_data=f"topup:{a}")
    b.button(text="✏️ Своя сумма", callback_data="topup:custom")
    b.button(text="◀️ Назад", callback_data="balance")
    b.adjust(2, 2, 2, 1, 1)
    return b.as_markup()


def pay_kb(url: str, payment_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="💳 Оплатить через Click", url=url)
    b.button(text="🔄 Проверить оплату", callback_data=f"paycheck:{payment_id}")
    b.adjust(1)
    return b.as_markup()


def recipient_kb(has_username: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if has_username:
        b.button(text="👤 Себе", callback_data="rcp:self")
    b.button(text="🎁 Другу (ввести @username)", callback_data="rcp:other")
    b.button(text="◀️ Отмена", callback_data="menu")
    b.adjust(1)
    return b.as_markup()


STAR_PRESETS = (50, 100, 250, 500, 1000, 2500)


def stars_qty_kb(price_each: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for q in STAR_PRESETS:
        b.button(text=f"⭐ {q} — {fmt_uzs(q * price_each)}", callback_data=f"qty:{q}")
    b.button(text="◀️ Отмена", callback_data="menu")
    b.adjust(2, 2, 2, 1)
    return b.as_markup()


def premium_kb(prices: dict[int, int]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for months, price in prices.items():
        b.button(text=f"💎 {months} мес — {fmt_uzs(price)}", callback_data=f"prem:{months}")
    b.button(text="◀️ Отмена", callback_data="menu")
    b.adjust(1)
    return b.as_markup()


def confirm_kb(enough: bool, missing: int = 0) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if enough:
        b.button(text="✅ Подтвердить", callback_data="order:confirm")
    else:
        b.button(text=f"💳 Пополнить на {fmt_uzs(missing)}", callback_data=f"topup:{missing}")
    b.button(text="❌ Отмена", callback_data="menu")
    b.adjust(1)
    return b.as_markup()


def back_kb(cb: str = "menu") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="◀️ Назад", callback_data=cb)
    return b.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="❌ Отмена", callback_data="menu")
    return b.as_markup()


# ---------- Admin ----------
def admin_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📊 Статистика", callback_data="adm:stats:today")
    b.button(text="📦 Очередь заказов", callback_data="adm:queue")
    b.button(text="💰 Цены и наценка", callback_data="adm:sec:prices")
    b.button(text="⚙️ Все настройки", callback_data="adm:settings")
    b.button(text="👥 Пользователь", callback_data="adm:user")
    b.button(text="🎟 Промокоды", callback_data="adm:promo")
    b.button(text="📢 Каналы", callback_data="adm:channels")
    b.button(text="📣 Рассылка", callback_data="adm:broadcast")
    b.button(text="💎 TON кошелёк", callback_data="adm:ton")
    b.adjust(2, 2, 2, 2, 1)
    return b.as_markup()


def stats_period_kb(current: str) -> InlineKeyboardMarkup:
    from app.core.stats import PERIODS

    b = InlineKeyboardBuilder()
    for key, title in PERIODS.items():
        b.button(text=("• " if key == current else "") + title, callback_data=f"adm:stats:{key}")
    b.button(text="🔄 Обновить", callback_data=f"adm:stats:{current}")
    b.button(text="◀️ Админка", callback_data="adm:menu")
    b.adjust(4, 2)
    return b.as_markup()


def order_admin_kb(order_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔁 Повторить", callback_data=f"adm:order:retry:{order_id}")
    b.button(text="✅ Выполнено вручную", callback_data=f"adm:order:done:{order_id}")
    b.button(text="↩️ Вернуть деньги", callback_data=f"adm:order:refund:{order_id}")
    b.adjust(1)
    return b.as_markup()


def user_admin_kb(user_id: int, banned: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Начислить", callback_data=f"adm:ubal:add:{user_id}")
    b.button(text="➖ Списать", callback_data=f"adm:ubal:sub:{user_id}")
    b.button(text="✅ Разбанить" if banned else "🚫 Забанить", callback_data=f"adm:uban:{user_id}")
    b.button(text="◀️ Админка", callback_data="adm:menu")
    b.adjust(2, 1, 1)
    return b.as_markup()


def admin_back_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="◀️ Админка", callback_data="adm:menu")
    return b.as_markup()


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🚀 Отправить всем", callback_data="adm:bc:go")
    b.button(text="❌ Отмена", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()
