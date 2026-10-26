"""Пошаговая проверка покупки Stars на Fragment БЕЗ отправки TON.

    python -m scripts.fragment_steps <username> [qty]
Показывает ответы: searchStarsRecipient -> initBuyStarsRequest -> getBuyStarsLink.
"""
from __future__ import annotations

import asyncio
import json
import sys

from app.providers.fragment import DEVICE
from app.providers.registry import fragment_client
from app.providers.ton_wallet import ton_wallet


async def main() -> None:
    username = (sys.argv[1] if len(sys.argv) > 1 else "telegram").lstrip("@")
    qty = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    c = fragment_client

    def show(step: str, body):
        s = json.dumps(body, ensure_ascii=False)
        print(f"[{step}] {s[:400]}")

    try:
        h = await c._ensure_hash()
        print("[hash]", h)
        # что за поле payment_method в форме и залогинены ли мы
        page = await c._client.get("/stars/buy", headers={"Referer": "https://fragment.com/"})
        import re as _re
        html = page.text
        print("[page]", page.status_code, len(html), "байт; login-кнопка:", 'tm-header-login' in html, "; logout:", "logout" in html.lower())
        for m in _re.finditer(r'<[^>]*name="payment_method"[^>]*>', html):
            print("[payment_method]", m.group(0)[:200])
        for m in _re.finditer(r'(?:data-method|data-payment-method|payment_method)=\"([^\"]+)\"', html):
            print("[pm-value]", m.group(1))
        pm = sys.argv[3] if len(sys.argv) > 3 else "ton"
        r = await c.call("searchStarsRecipient", query=username, quantity=qty)
        show("search", r)
        token = (r.get("found") or {}).get("recipient")
        if not token:
            print("STOP: получатель не найден")
            return
        r = await c.call("initBuyStarsRequest", recipient=token, quantity=qty, payment_method=pm)
        show("init", r)
        req_id = r.get("req_id")
        if not req_id:
            print("STOP: нет req_id")
            return
        acc = ton_wallet.tonconnect_account()
        print("[account]", {k: (v[:20] + "…" if isinstance(v, str) and len(v) > 24 else v) for k, v in acc.items()})
        r = await c.call("getBuyStarsLink", account=json.dumps(acc), device=json.dumps(DEVICE), transaction="1", id=req_id, show_sender="0")
        show("link", r)
        msgs = (r.get("transaction") or {}).get("messages") or []
        if msgs:
            print(f"OK: транзакция готова, {len(msgs)} сообщ., сумма {sum(int(m['amount']) for m in msgs)/1e9:.4f} TON -> {msgs[0]['address']}")
            print("(TON НЕ отправлен — это только проверка)")
    except Exception as e:  # noqa: BLE001
        print("ERROR:", type(e).__name__, e)
    finally:
        await c.close()


if __name__ == "__main__":
    asyncio.run(main())
