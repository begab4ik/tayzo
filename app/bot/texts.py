"""Все тексты бота в одном месте. HTML-разметка."""
from __future__ import annotations

from app.config import settings
from app.core.money import fmt_uzs

BOT_NAME = "Tayzo"


def welcome(first_name: str | None) -> str:
    return (
        f"👋 Привет, <b>{first_name or 'друг'}</b>!\n\n"
        f"Это <b>{BOT_NAME}</b> — быстрая покупка Telegram Stars и Premium за сумы.\n\n"
        "⭐ Звёзды приходят автоматически за 1–3 минуты\n"
        "💳 Оплата через Click\n"
        "🎁 Реферальная программа и промокоды\n\n"
        "Выбери, что нужно 👇"
    )


def subscribe_required() -> str:
    return (
        "🔒 Чтобы пользоваться ботом, подпишись на наш канал.\n\n"
        "Там скидки, промокоды и новости проекта. После подписки нажми «Проверить»."
    )


def menu_balance(balance: int) -> str:
    return f"💰 Твой баланс: <b>{fmt_uzs(balance)}</b>"


def profile(user, orders_count: int, ref_count: int, ref_earned: int, ref_link: str, ref_percent: int) -> str:
    return (
        f"👤 <b>Профиль</b>\n\n"
        f"ID: <code>{user.id}</code>\n"
        f"Баланс: <b>{fmt_uzs(user.balance)}</b>\n"
        f"Пополнено всего: {fmt_uzs(user.total_topup)}\n"
        f"Потрачено: {fmt_uzs(user.total_spent)}\n"
        f"Куплено звёзд: ⭐ {user.total_stars}\n"
        f"Заказов: {orders_count}\n\n"
        f"👥 <b>Рефералы</b>: {ref_count} чел., заработано {fmt_uzs(ref_earned)}\n"
        f"Получай <b>{ref_percent}%</b> с каждого пополнения друзей:\n"
        f"<code>{ref_link}</code>"
    )


def topup_prompt(min_amount: int, max_amount: int) -> str:
    return (
        "💳 <b>Пополнение баланса</b>\n\n"
        f"Выбери сумму или введи свою (от {fmt_uzs(min_amount)} до {fmt_uzs(max_amount)}):"
    )


def topup_link(amount: int) -> str:
    return (
        f"💳 К оплате: <b>{fmt_uzs(amount)}</b>\n\n"
        "Нажми кнопку ниже и оплати через Click. Баланс пополнится автоматически в течение минуты."
    )


def topup_success(amount: int, balance: int) -> str:
    return f"✅ Баланс пополнен на <b>{fmt_uzs(amount)}</b>\n💰 Текущий баланс: <b>{fmt_uzs(balance)}</b>"


def stars_intro(price_each: int, min_stars: int, max_stars: int) -> str:
    return (
        "⭐ <b>Покупка Telegram Stars</b>\n\n"
        f"Цена: <b>{fmt_uzs(price_each)}</b> за 1 звезду\n"
        f"Минимум {min_stars}, максимум {max_stars:,} звёзд\n\n"
        "Кому отправить?"
    ).replace(",", " ")


def ask_username() -> str:
    return "Введи <b>@username</b> получателя (у него должен быть установлен юзернейм в Telegram):"


def ask_stars_qty(recipient_name: str, username: str) -> str:
    return f"Получатель: <b>{recipient_name}</b> (@{username})\n\nСколько звёзд отправить? Выбери или введи число:"


def confirm_order(title: str, recipient_name: str, username: str, price: int, balance: int) -> str:
    text = (
        f"🧾 <b>Подтверждение заказа</b>\n\n"
        f"Товар: <b>{title}</b>\n"
        f"Получатель: <b>{recipient_name}</b> (@{username})\n"
        f"К оплате: <b>{fmt_uzs(price)}</b>\n"
        f"Баланс: {fmt_uzs(balance)}\n"
    )
    if balance < price:
        text += f"\n⚠️ Не хватает <b>{fmt_uzs(price - balance)}</b>. Пополни баланс и вернись к заказу."
    return text


def order_created(order_id: int, title: str, manual: bool) -> str:
    eta = "Доставка займёт до 30 минут — менеджер выполнит вручную." if manual else "Обычно доставка занимает 1–3 минуты."
    return f"✅ Заказ <b>#{order_id}</b> принят: {title}\n{eta}\nЯ напишу, как только всё будет готово."


def order_delivered(order) -> str:
    return f"🎉 Заказ <b>#{order.id}</b> выполнен!\n{order.title} → @{order.recipient_username}\n\nСпасибо, что выбираешь {BOT_NAME} 💛"


def order_refunded(order) -> str:
    return (
        f"↩️ Заказ <b>#{order.id}</b> ({order.title}) не удалось выполнить.\n"
        f"Деньги <b>{fmt_uzs(order.price)}</b> вернулись на баланс. Если вопрос — @{settings.support_username}"
    )


def premium_intro() -> str:
    return "💎 <b>Telegram Premium</b>\n\nВыбери срок подписки:"


def insufficient(need: int, have: int) -> str:
    return f"❌ Недостаточно средств. Нужно {fmt_uzs(need)}, на балансе {fmt_uzs(have)}."


def support() -> str:
    return (
        f"🆘 <b>Поддержка</b>\n\n"
        f"По любым вопросам пиши: @{settings.support_username}\n"
        "Укажи номер заказа, если вопрос по нему."
    )


def faq() -> str:
    return (
        "ℹ️ <b>Как это работает</b>\n\n"
        "1️⃣ Пополни баланс через Click\n"
        "2️⃣ Выбери товар и укажи получателя (себя или друга)\n"
        "3️⃣ Подтверди — и звёзды придут автоматически\n\n"
        "<b>Почему дешевле, чем в Telegram?</b>\n"
        "Мы покупаем напрямую через Fragment без комиссий App Store / Google Play.\n\n"
        "<b>Безопасно ли это?</b>\n"
        "Да. Мы не просим пароль или код — только @username получателя.\n\n"
        f"<b>Нужен юзернейм?</b> Настройки Telegram → Имя пользователя."
    )


def maintenance() -> str:
    return "🛠 Бот на техническом обслуживании. Попробуй через несколько минут."


def banned() -> str:
    return f"🚫 Доступ ограничен. Связь: @{settings.support_username}"
