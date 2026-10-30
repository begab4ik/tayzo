"""Узнать актуальную цену Premium на Fragment в TON (без оплаты).
    python -m scripts.premium_price <username_без_premium>
"""
from __future__ import annotations

import asyncio
import sys

from app.providers.fragment import PAYMENT_METHOD
from app.providers.registry import fragment_client


async def main() -> None:
    username = (sys.argv[1] if len(sys.argv) > 1 else "telegram").lstrip("@")
    c = fragment_client
    try:
        for months in (3, 6, 12):
            try:
                r = await c.call("searchPremiumGiftRecipient", referer="/premium/gift", query=username, months=months)
                token = (r.get("found") or {}).get("recipient")
                if not token:
                    print(months, "STOP: recipient not found", r)
                    continue
                init = await c.call("initGiftPremiumRequest", referer="/premium/gift", recipient=token, months=months, payment_method=PAYMENT_METHOD)
                print(f"{months} мес: amount={init.get('amount')} TON  (req_id={init.get('req_id')})")
            except Exception as e:  # noqa: BLE001
                print(months, "ERROR:", type(e).__name__, e)
    finally:
        await c.close()


if __name__ == "__main__":
    asyncio.run(main())
