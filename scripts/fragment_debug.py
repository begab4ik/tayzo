"""Диагностика Fragment и TON-кошелька. Ничего не покупает.

    python -m scripts.fragment_debug
"""
from __future__ import annotations

import asyncio
import re

import httpx

from app.config import settings


async def wallets() -> None:
    print("\n[TON] адреса по сид-фразе для обеих версий кошелька:")
    if not settings.ton_mnemonic:
        print("  TON_MNEMONIC пустой")
        return
    from ton_core import NetworkGlobalID
    from tonutils.clients import ToncenterClient
    from tonutils.contracts import WalletV4R2, WalletV5R1

    client = ToncenterClient(NetworkGlobalID.MAINNET, api_key=settings.toncenter_api_key or None, timeout=20)
    for name, cls in (("v4r2", WalletV4R2), ("v5r1", WalletV5R1)):
        try:
            w, *_ = cls.from_mnemonic(client, settings.ton_mnemonic.split())
            await w.refresh()
            bal = w.balance / 10**9
            mark = "  ← сейчас выбрана" if settings.ton_wallet_version.lower() == name else ""
            print(f"  {name}: {w.address.to_str(is_user_friendly=True, is_bounceable=False)}  баланс {bal:.4f} TON{mark}")
        except Exception as e:  # noqa: BLE001
            print(f"  {name}: ошибка {e}")


async def fragment() -> None:
    print("\n[Fragment] проверка cookies:")
    cookies = settings.fragment_cookies
    print("  cookies переданы:", ", ".join(cookies) or "нет")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
    }
    async with httpx.AsyncClient(base_url="https://fragment.com", headers=headers, cookies=cookies, timeout=30, follow_redirects=True) as c:
        for path in ("/stars/buy", "/", "/premium/gift"):
            try:
                r = await c.get(path)
            except Exception as e:  # noqa: BLE001
                print(f"  GET {path}: ошибка сети {e}")
                continue
            html = r.text
            title = re.search(r"<title>(.*?)</title>", html, re.S)
            hashes = re.findall(r"hash=([A-Za-z0-9_\-]{6,})", html)
            logged = "logout" in html.lower() or "stel_token" in html or 'class="tm-header-login"' not in html
            print(f"  GET {path}: {r.status_code}, {len(html)} байт, title={title.group(1).strip()[:50] if title else '-'}")
            print(f"     hash= найдено: {sorted(set(hashes))[:3]}  | признак входа: {'да' if logged else 'нет'}")
            if "cf-" in html[:3000].lower() or "challenge" in html.lower()[:5000]:
                print("     ⚠️ похоже на Cloudflare-проверку")
            m = re.search(r"api\?hash=([A-Za-z0-9_\-]+)", html)
            if m:
                print(f"     ✅ api hash: {m.group(1)}")
                api = await c.post(f"/api?hash={m.group(1)}", data={"method": "searchStarsRecipient", "query": "telegram", "quantity": 50},
                                   headers={"X-Requested-With": "XMLHttpRequest", "Origin": "https://fragment.com", "Referer": "https://fragment.com/stars/buy"})
                print(f"     API searchStarsRecipient: {api.status_code} {api.text[:200]}")
                return
    print("  ❌ api hash не найден ни на одной странице — cookies не дают залогиненную сессию")


async def main() -> None:
    await wallets()
    await fragment()


if __name__ == "__main__":
    asyncio.run(main())
