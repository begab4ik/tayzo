"""Тексты для пользователя. Все строки — в i18n.py, здесь только сборка с параметрами."""
from __future__ import annotations

from app.bot.i18n import t
from app.config import settings
from app.core.money import fmt_uzs

BOT_NAME = "Tayzo"


def welcome(lang: str, first_name: str | None) -> str:
    return t(lang, "welcome", name=first_name or "👋")


def subscribe_required(lang: str) -> str:
    return t(lang, "subscribe_required")


def menu_balance(lang: str, balance: int) -> str:
    return t(lang, "balance", balance=fmt_uzs(balance))


def profile(lang: str, user, orders_count: int, ref_count: int, ref_earned: int, ref_link: str, ref_percent: int) -> str:
    return t(
        lang, "profile",
        id=user.id, balance=fmt_uzs(user.balance), topup=fmt_uzs(user.total_topup), spent=fmt_uzs(user.total_spent),
        stars=user.total_stars, orders=orders_count, refs=ref_count, earned=fmt_uzs(ref_earned), percent=ref_percent, link=ref_link,
    )


def topup_prompt(lang: str, min_amount: int, max_amount: int) -> str:
    return t(lang, "topup_prompt", min=fmt_uzs(min_amount), max=fmt_uzs(max_amount))


def topup_link(lang: str, amount: int) -> str:
    return t(lang, "topup_link", amount=fmt_uzs(amount))


def topup_success(lang: str, amount: int, balance: int) -> str:
    return t(lang, "topup_success", amount=fmt_uzs(amount), balance=fmt_uzs(balance))


def stars_intro(lang: str, price_each: int, min_stars: int, max_stars: int) -> str:
    return t(lang, "stars_intro", price=fmt_uzs(price_each), min=min_stars, max=f"{max_stars:,}".replace(",", " "))


def ask_username(lang: str) -> str:
    return t(lang, "ask_username")


def ask_stars_qty(lang: str, recipient_name: str, username: str) -> str:
    return t(lang, "ask_stars_qty", name=recipient_name, username=username)


def confirm_order(lang: str, title: str, recipient_name: str, username: str, price: int, balance: int) -> str:
    text = t(lang, "confirm_order", title=title, name=recipient_name, username=username, price=fmt_uzs(price), balance=fmt_uzs(balance))
    if balance < price:
        text += t(lang, "confirm_missing", missing=fmt_uzs(price - balance))
    return text


def order_created(lang: str, order_id: int, title: str, manual: bool) -> str:
    return t(lang, "order_created", id=order_id, title=title, eta=t(lang, "eta_manual" if manual else "eta_auto"))


def order_title(lang: str, order) -> str:
    if order.product == "stars":
        return f"⭐ {order.quantity} Stars"
    return t(lang, "premium_title", m=order.quantity)


def order_delivered(lang: str, order) -> str:
    return t(lang, "order_delivered", id=order.id, title=order_title(lang, order), username=order.recipient_username)


def order_refunded(lang: str, order) -> str:
    return t(lang, "order_refunded", id=order.id, title=order_title(lang, order), price=fmt_uzs(order.price), support=settings.support_username)


def premium_intro(lang: str) -> str:
    return t(lang, "premium_intro")


def insufficient(lang: str, need: int, have: int) -> str:
    return t(lang, "insufficient", need=fmt_uzs(need), have=fmt_uzs(have))


def support(lang: str) -> str:
    return t(lang, "support", support=settings.support_username)


def faq(lang: str) -> str:
    return t(lang, "faq")


def maintenance(lang: str) -> str:
    return t(lang, "maintenance")


def banned(lang: str) -> str:
    return t(lang, "banned", support=settings.support_username)
