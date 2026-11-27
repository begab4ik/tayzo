"""Прогон сценариев песочницы Payme против локального вебхука + создание счетов для песочницы.

    python -m scripts.payme_selftest          # самопроверка на отдельном счёте (зачислит и вернёт сумму админу)
    python -m scripts.payme_selftest new 2    # создать 2 неоплаченных счёта для песочницы Payme
"""
from __future__ import annotations

import asyncio
import base64
import sys
import time

import httpx

from app.config import settings

URL = "http://127.0.0.1:8080/webhooks/payme"


async def new_payment(amount: int) -> int:
    from app.db.base import get_session
    from app.payments import payme

    async with get_session() as s:
        p = await payme.create_payment(s, settings.admin_ids[0], amount)
        await s.commit()
        return p.id


async def rpc(c: httpx.AsyncClient, method: str, params: dict, key: str | None = None) -> dict:
    auth = base64.b64encode(f"Paycom:{key or settings.payme_test_key}".encode()).decode()
    r = await c.post(URL, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, headers={"Authorization": f"Basic {auth}"})
    return r.json()


def show(name: str, res: dict, want) -> None:
    got = res["error"]["code"] if "error" in res else res["result"].get("state", res["result"].get("allow"))
    ok = got in want if isinstance(want, (list, tuple, range)) else got == want
    print(("OK  " if ok else "FAIL"), name, "->", got)


async def selftest() -> None:
    amount = 1000
    pid = await new_payment(amount)
    acc, a = {"payment_id": str(pid)}, amount * 100
    tx, tx2, now = f"selftest{pid}a", f"selftest{pid}b", int(time.time() * 1000)
    bad = range(-31099, -31049)
    async with httpx.AsyncClient(timeout=20) as c:
        show("wrong auth", await rpc(c, "CheckPerformTransaction", {"amount": a, "account": acc}, key="wrong"), -32504)
        show("check: wrong amount", await rpc(c, "CheckPerformTransaction", {"amount": a + 1, "account": acc}), -31001)
        show("check: no account", await rpc(c, "CheckPerformTransaction", {"amount": a, "account": {"payment_id": "999999999"}}), bad)
        show("check: ok", await rpc(c, "CheckPerformTransaction", {"amount": a, "account": acc}), True)
        show("create: wrong amount", await rpc(c, "CreateTransaction", {"id": tx, "time": now, "amount": a + 1, "account": acc}), -31001)
        show("create", await rpc(c, "CreateTransaction", {"id": tx, "time": now, "amount": a, "account": acc}), 1)
        show("create again (same)", await rpc(c, "CreateTransaction", {"id": tx, "time": now, "amount": a, "account": acc}), 1)
        show("create other tx on busy account", await rpc(c, "CreateTransaction", {"id": tx2, "time": now, "amount": a, "account": acc}), bad)
        show("check tx", await rpc(c, "CheckTransaction", {"id": tx}), 1)
        show("check unknown tx", await rpc(c, "CheckTransaction", {"id": "nope"}), -31003)
        show("perform", await rpc(c, "PerformTransaction", {"id": tx}), 2)
        show("perform again", await rpc(c, "PerformTransaction", {"id": tx}), 2)
        show("cancel after perform", await rpc(c, "CancelTransaction", {"id": tx, "reason": 5}), -2)
        show("cancel again", await rpc(c, "CancelTransaction", {"id": tx, "reason": 5}), -2)
        show("check tx after cancel", await rpc(c, "CheckTransaction", {"id": tx}), -2)
        show("perform cancelled", await rpc(c, "PerformTransaction", {"id": tx}), -31008)
        pid2 = await new_payment(amount)
        tx3 = f"selftest{pid2}a"
        show("create #2", await rpc(c, "CreateTransaction", {"id": tx3, "time": now, "amount": a, "account": {"payment_id": str(pid2)}}), 1)
        show("cancel before perform", await rpc(c, "CancelTransaction", {"id": tx3, "reason": 3}), -1)
        st = await rpc(c, "GetStatement", {"from": now - 1000, "to": now + 1000})
        print("OK  " if len(st.get("result", {}).get("transactions", [])) >= 2 else "FAIL", "statement ->", len(st.get("result", {}).get("transactions", [])))


async def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "new":
        for amount in (5000, 10000, 15000, 20000)[: int(sys.argv[2]) if len(sys.argv) > 2 else 2]:
            print(f"payment_id={await new_payment(amount)} amount={amount} sum = {amount * 100} tiyin")
    else:
        await selftest()


if __name__ == "__main__":
    asyncio.run(main())
