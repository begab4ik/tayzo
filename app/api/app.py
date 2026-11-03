"""HTTP-сервер: вебхуки Click/Payme + healthcheck. Крутится в том же процессе, что и бот."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.bot.loader import bot
from app.bot.texts import topup_success
from app.core.money import fmt_uzs
from app.db.base import get_session
from app.db.models import User
from app.payments import click, payme

log = logging.getLogger(__name__)

api = FastAPI(title="Tayzo API", docs_url=None, redoc_url=None)

from app.api.miniapp import router as miniapp_router  # noqa: E402

api.include_router(miniapp_router)


@api.get("/health")
async def health():
    return {"ok": True}


@api.post("/webhooks/click")
async def click_webhook(request: Request):
    form = await request.form()
    data = {k: v for k, v in form.items()}
    log.info("Click webhook: %s", data)

    try:
        async with get_session() as session:
            response, paid = await click.handle_webhook(session, data)
            user = await session.get(User, paid.user_id) if paid else None
    except Exception:  # noqa: BLE001 — Click должен получить JSON с кодом ошибки, а не 500
        log.exception("Click webhook failed: %s", data)
        return JSONResponse({"click_trans_id": data.get("click_trans_id"), "merchant_trans_id": data.get("merchant_trans_id"), "error": -8, "error_note": "Error in request from click"})

    if paid and user:
        await _notify_paid(paid, user, "Click")

    return JSONResponse(response)


async def _notify_paid(paid, user: User, via: str) -> None:
    try:
        await bot.send_message(paid.user_id, topup_success(user.language, paid.amount, user.balance))
    except Exception as e:  # noqa: BLE001 — юзер мог заблокировать бота
        log.warning("notify user %s failed: %s", paid.user_id, e)
    from app.bot.notify import notify_admins

    await notify_admins(f"💳 Пополнение {fmt_uzs(paid.amount)} через {via} от {user.display} (id{user.id})")


@api.post("/webhooks/payme")
async def payme_webhook(request: Request):
    """Payme Merchant API: JSON-RPC 2.0, Basic auth Paycom:<key>. Ответ всегда HTTP 200."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
    rpc_id = body.get("id")
    method, params = body.get("method", ""), body.get("params") or {}
    log.info("Payme webhook: %s %s", method, params)
    if not payme.check_auth(request.headers.get("Authorization")):
        return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32504, "message": "Insufficient privileges"}})
    try:
        async with get_session() as session:
            result, paid = await payme.handle(session, method, params)
            user = await session.get(User, paid.user_id) if paid else None
    except Exception:  # noqa: BLE001
        log.exception("Payme webhook failed: %s", body)
        return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32400, "message": "Internal error"}})
    if paid and user:
        await _notify_paid(paid, user, "Payme")
    return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, **result})
