"""HTTP-сервер: вебхуки Click + healthcheck. Крутится в том же процессе, что и бот."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.bot.loader import bot
from app.bot.texts import topup_success
from app.core.money import fmt_uzs
from app.db.base import get_session
from app.db.models import User
from app.payments import click

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
        try:
            await bot.send_message(paid.user_id, topup_success(user.language, paid.amount, user.balance))
        except Exception as e:  # noqa: BLE001 — юзер мог заблокировать бота
            log.warning("notify user %s failed: %s", paid.user_id, e)
        from app.bot.notify import notify_admins

        await notify_admins(f"💳 Пополнение {fmt_uzs(paid.amount)} от {user.display} (id{user.id})")

    return JSONResponse(response)
