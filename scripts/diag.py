"""Быстрая самопроверка боевого контура. Ничего не покупает и не печатает секреты.

    python -m scripts.diag
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

logging.disable(logging.WARNING)


async def main() -> None:
    from app.core import settings_store as cfg
    from app.db.base import get_session
    from app.db.models import Order, Payment
    from app.providers.fragment import PAYMENT_METHOD
    from app.providers.registry import fragment_client as fc
    from app.providers.telegram_account import tg_account

    async with get_session() as s:
        acc = await cfg.get(s, "tg_account_username")
        probe = await cfg.get(s, "premium_probe_username")
        since = datetime.now(timezone.utc) - timedelta(days=7)
        o = (await s.execute(select(Order.product, Order.status, func.count()).where(Order.created_at > since).group_by(Order.product, Order.status))).all()
        p = (await s.execute(select(Payment.provider, Payment.status, func.count()).where(Payment.created_at > since).group_by(Payment.provider, Payment.status))).all()
    print("orders 7d:", " ".join(f"{a}/{b}={c}" for a, b, c in o) or "-")
    print("pays 7d:", " ".join(f"{a}/{b}={c}" for a, b, c in p) or "-")
    print("acc set:", bool(acc), "probe set:", bool(probe))

    try:
        await fc.ton_auth()
        print("ton_auth: verified")
    except Exception as e:  # noqa: BLE001
        print("ton_auth ERR:", str(e)[:160])

    for name, q in (("acc", acc), ("probe", probe), ("durov", "durov")):
        if not q:
            continue
        try:
            f = await fc.call("searchStarsRecipient", query=q.lstrip("@"), quantity=100)
            tok = (f.get("found") or {}).get("recipient")
            print(f"stars search[{name}]:", "ok" if tok else f"no: {str(f)[:80]}")
            if tok:
                i = await fc.call("initBuyStarsRequest", recipient=tok, quantity=100, payment_method=PAYMENT_METHOD)
                print(f"stars init[{name}]: amount={i.get('amount')} keys={sorted(i)[:6]}")
        except Exception as e:  # noqa: BLE001
            print(f"stars[{name}] ERR:", str(e)[:120])
    if probe:
        try:
            f = await fc.call("searchPremiumGiftRecipient", referer="/premium/gift", query=probe.lstrip("@"), months=3)
            tok = (f.get("found") or {}).get("recipient")
            print("prem search:", "ok" if tok else f"no: {str(f)[:80]}")
            if tok:
                i = await fc.call("initGiftPremiumRequest", referer="/premium/gift", recipient=tok, months=3, payment_method=PAYMENT_METHOD)
                print("prem init: amount=", i.get("amount"))
        except Exception as e:  # noqa: BLE001
            print("prem ERR:", str(e)[:120])

    try:
        me = await tg_account.me()
        print("tg account: ok, username set:", bool(me.get("username")))
        cols = await tg_account.nft_collections(force=True)
        print("nft collections:", len(cols))
    except Exception as e:  # noqa: BLE001
        print("tg account ERR:", type(e).__name__, str(e)[:100])


if __name__ == "__main__":
    asyncio.run(main())
