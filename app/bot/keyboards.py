from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.bot.i18n import LANGS, labels, t
from app.core.money import fmt_uzs
from app.db.models import RequiredChannel

# ---------- Reply (главное меню) ----------
MENU_KEYS = ["btn_stars", "btn_premium", "btn_balance", "btn_profile", "btn_orders", "btn_promo", "btn_faq", "btn_support", "btn_lang"]


def L(key: str) -> set[str]:
    """Все языковые варианты подписи кнопки (для фильтров F.text.in_(...))."""
    return labels(key)


def main_menu(lang: str, is_admin: bool = False) -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    for key in MENU_KEYS:
        b.button(text=t(lang, key))
    if is_admin:
        b.button(text=t(lang, "btn_admin"))
    b.adjust(2, 2, 2, 2, 1, 1)
    return b.as_markup(resize_keyboard=True)


def lang_kb(back: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for code, title in LANGS.items():
        b.button(text=title, callback_data=f"lang:{code}")
    b.adjust(1)
    return b.as_markup()


# ---------- Inline ----------
def subscribe_kb(lang: str, channels: list[RequiredChannel]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        b.button(text=f"📢 {ch.title}", url=ch.url)
    b.button(text=t(lang, "ib_check_sub"), callback_data="check_sub")
    b.adjust(1)
    return b.as_markup()


def balance_kb(lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "ib_topup"), callback_data="topup")
    b.button(text=t(lang, "ib_history"), callback_data="ledger")
    b.adjust(2)
    return b.as_markup()


TOPUP_PRESETS = (10_000, 25_000, 50_000, 100_000, 250_000, 500_000)


def topup_amounts_kb(lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for a in TOPUP_PRESETS:
        b.button(text=fmt_uzs(a), callback_data=f"topup:{a}")
    b.button(text=t(lang, "ib_custom_amount"), callback_data="topup:custom")
    b.button(text=t(lang, "ib_back"), callback_data="balance")
    b.adjust(2, 2, 2, 1, 1)
    return b.as_markup()


def pay_kb(lang: str, url: str, payment_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "ib_pay_click"), url=url)
    b.button(text=t(lang, "ib_check_pay"), callback_data=f"paycheck:{payment_id}")
    b.adjust(1)
    return b.as_markup()


def recipient_kb(lang: str, has_username: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if has_username:
        b.button(text=t(lang, "ib_self"), callback_data="rcp:self")
    b.button(text=t(lang, "ib_other"), callback_data="rcp:other")
    b.button(text=t(lang, "ib_cancel"), callback_data="menu")
    b.adjust(1)
    return b.as_markup()


STAR_PRESETS = (50, 100, 250, 500, 1000, 2500)


def stars_qty_kb(lang: str, price_each: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for q in STAR_PRESETS:
        b.button(text=f"⭐ {q} — {fmt_uzs(q * price_each)}", callback_data=f"qty:{q}")
    b.button(text=t(lang, "ib_cancel"), callback_data="menu")
    b.adjust(2, 2, 2, 1)
    return b.as_markup()


def premium_kb(lang: str, prices: dict[int, int]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for months, price in prices.items():
        b.button(text=t(lang, "ib_months", m=months, price=fmt_uzs(price)), callback_data=f"prem:{months}")
    b.button(text=t(lang, "ib_cancel"), callback_data="menu")
    b.adjust(1)
    return b.as_markup()


def confirm_kb(lang: str, enough: bool, missing: int = 0) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if enough:
        b.button(text=t(lang, "ib_confirm"), callback_data="order:confirm")
    else:
        b.button(text=t(lang, "ib_topup_missing", amount=fmt_uzs(missing)), callback_data=f"topup:{missing}")
    b.button(text=t(lang, "ib_cancel"), callback_data="menu")
    b.adjust(1)
    return b.as_markup()


def back_kb(lang: str, cb: str = "menu") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "ib_back"), callback_data=cb)
    return b.as_markup()


def cancel_kb(lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "ib_cancel"), callback_data="menu")
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
