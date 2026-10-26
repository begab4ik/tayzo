"""Проверка токенов перед запуском. Ничего не покупает, пока не передашь --buy.

    python -m scripts.check_setup                     # проверить всё
    python -m scripts.check_setup --buy 50 @username  # тестовая покупка 50 звёзд (реально спишет TON!)
    python -m scripts.check_setup --premium 3 @username
"""
from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

from app.config import settings

OK, FAIL, WARN = "✅", "❌", "⚠️"


def p(status: str, msg: str) -> None:
    print(f"  {status} {msg}")


async def check_telegram() -> bool:
    print("\n[1/4] Telegram")
    if not settings.bot_token:
        p(FAIL, "BOT_TOKEN пустой")
        return False
    from aiogram import Bot

    bot = Bot(settings.bot_token)
    try:
        me = await bot.me()
        p(OK, f"бот @{me.username}")
    except Exception as e:  # noqa: BLE001
        p(FAIL, f"BOT_TOKEN неверный: {e}")
        await bot.session.close()
        return False

    if not settings.admin_ids:
        p(FAIL, "ADMIN_IDS пустой — у тебя не будет админки")
    else:
        p(OK, f"админы: {settings.admin_ids}")

    if settings.required_channel_id:
        try:
            chat = await bot.get_chat(settings.required_channel_id)
            member = await bot.get_chat_member(chat.id, me.id)
            if member.status in ("administrator", "creator"):
                p(OK, f"канал «{chat.title}», бот — админ")
            else:
                p(FAIL, f"канал «{chat.title}»: бот НЕ админ → проверка подписки не будет работать")
        except Exception as e:  # noqa: BLE001
            p(FAIL, f"REQUIRED_CHANNEL_ID: {e}")
    else:
        p(WARN, "REQUIRED_CHANNEL_ID не задан — обязательной подписки не будет")
    await bot.session.close()
    return True


def check_click() -> None:
    print("\n[2/4] Click")
    if settings.click_configured:
        p(OK, f"service_id={settings.click_service_id}, merchant_id={settings.click_merchant_id}")
        p(WARN if "example.com" in settings.webhook_host else OK, f"вебхук: {settings.webhook_host}/webhooks/click")
    else:
        p(FAIL, "CLICK_SERVICE_ID / CLICK_MERCHANT_ID / CLICK_SECRET_KEY не заполнены — пополнение не заработает")


async def check_ton() -> Decimal | None:
    print("\n[3/4] TON-кошелёк")
    if not settings.ton_mnemonic:
        p(FAIL, "TON_MNEMONIC пустой")
        return None
    words = settings.ton_mnemonic.split()
    if len(words) not in (12, 18, 24):
        p(FAIL, f"в сид-фразе {len(words)} слов, должно быть 24 (или 12/18)")
        return None
    from app.providers.ton_wallet import ton_wallet

    try:
        addr = ton_wallet.address
        bal = await ton_wallet.balance()
    except Exception as e:  # noqa: BLE001
        p(FAIL, f"кошелёк: {e}")
        return None
    p(OK, f"адрес {addr}")
    p(OK if bal >= Decimal("0.5") else WARN, f"баланс {bal:.4f} TON (версия {settings.ton_wallet_version})")
    print("     ↳ сверь адрес с Tonkeeper. Не совпал? Поменяй TON_WALLET_VERSION (v5r1 ↔ v4r2) и перезапусти.")
    return bal


async def check_fragment() -> bool:
    print("\n[4/4] Fragment")
    if not (settings.fragment_stel_token and settings.fragment_stel_ton_token):
        p(FAIL, "FRAGMENT_STEL_TOKEN / FRAGMENT_STEL_TON_TOKEN пустые")
        return False
    from app.providers.fragment import FragmentClient, fetch_star_price_ton
    from app.providers.registry import fragment_client

    try:
        h = await fragment_client._ensure_hash()
        p(OK, f"api hash: {h[:8]}…")
    except Exception as e:  # noqa: BLE001
        p(FAIL, f"не удалось войти на Fragment: {e}")
        return False
    price = await fetch_star_price_ton(fragment_client)
    if price:
        p(OK, f"себестоимость 1 ⭐ = {price:.6f} TON")
    else:
        p(FAIL, "не удалось получить цену звезды — cookies протухли или Fragment сменил API")
        return False
    return True


async def test_buy(kind: str, qty: int, username: str) -> None:
    from app.core.enums import ProductType
    from app.providers.registry import get_provider

    product = ProductType.STARS if kind == "stars" else ProductType.PREMIUM
    provider = get_provider(product)
    if provider.code == "manual":
        print("\n❌ Провайдер в ручном режиме — автопокупка невозможна. Проверь токены выше.")
        return
    print(f"\n🧪 Тестовая покупка: {kind} x{qty} → {username}")
    rcp = await provider.resolve_recipient(username, qty)
    print(f"  получатель: {rcp.name} (@{rcp.username})")
    answer = input("  Подтвердить? Спишутся реальные TON. [y/N]: ").strip().lower()
    if answer != "y":
        print("  отменено")
        return
    res = await provider.fulfill(rcp, qty)
    print(f"  ✅ отправлено! tx: {res.external_id}  себестоимость: {res.cost_ton} TON")
    print("  Проверь у получателя через 1–3 минуты. Если пришло — автооплата работает.")


async def main() -> None:
    print("Tayzo — проверка настроек (.env + tokens.env)")
    tg = await check_telegram()
    check_click()
    bal = await check_ton()
    fr = await check_fragment()

    print("\n" + "=" * 50)
    if tg and bal is not None and fr:
        print("Автооплата через Fragment: ✅ ГОТОВА. Заказы будут выполняться сами.")
    else:
        print("Автооплата через Fragment: ❌ не готова — бот запустится в РУЧНОМ режиме.")

    args = sys.argv[1:]
    if len(args) == 3 and args[0] in ("--buy", "--premium"):
        await test_buy("stars" if args[0] == "--buy" else "premium", int(args[1]), args[2])

    from app.providers.registry import fragment_client

    await fragment_client.close()


if __name__ == "__main__":
    asyncio.run(main())
