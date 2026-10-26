"""Точка входа: бот (long polling) + HTTP API для Click + воркеры — в одном процессе.

    python -m app.main
"""
from __future__ import annotations

import asyncio
import logging

import uvicorn
from aiogram.types import BotCommand, BotCommandScopeChat
from sqlalchemy import select

from app.api.app import api
from app.bot.handlers import setup_routers
from app.bot.loader import bot, dp
from app.bot.middlewares import DbSessionMiddleware, SubscriptionMiddleware, ThrottlingMiddleware, UserMiddleware
from app.config import settings
from app.db.base import engine, get_session, init_db
from app.db.models import RequiredChannel
from app.workers import fulfillment
from app.workers.scheduler import build_scheduler, update_ton_rate

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tayzo")


async def seed_channel() -> None:
    """Если в БД нет каналов, добавляем канал из .env."""
    if not settings.required_channel_id:
        return
    async with get_session() as session:
        exists = (await session.execute(select(RequiredChannel.id).limit(1))).first()
        if exists:
            return
        try:
            chat = await bot.get_chat(settings.required_channel_id)
            title = chat.title or "Канал проекта"
            url = settings.required_channel_url or (f"https://t.me/{chat.username}" if chat.username else "")
        except Exception as e:  # noqa: BLE001
            log.warning("seed_channel: get_chat failed (%s), using .env values", e)
            title, url = "Канал проекта", settings.required_channel_url or ""
        if url:
            session.add(RequiredChannel(chat_id=settings.required_channel_id, title=title, url=url))


async def set_commands() -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="profile", description="Профиль и рефералка"),
            BotCommand(command="orders", description="Мои заказы"),
            BotCommand(command="promo", description="Активировать промокод"),
            BotCommand(command="support", description="Поддержка"),
        ]
    )
    for admin_id in settings.admin_ids:
        try:
            await bot.set_my_commands(
                [
                    BotCommand(command="start", description="Главное меню"),
                    BotCommand(command="admin", description="Админ-панель"),
                    BotCommand(command="stats", description="Статистика"),
                    BotCommand(command="profile", description="Профиль"),
                    BotCommand(command="orders", description="Мои заказы"),
                ],
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception:  # noqa: BLE001 — админ ещё не писал боту
            pass


def setup_dispatcher() -> None:
    dp.update.outer_middleware(ThrottlingMiddleware())
    dp.update.outer_middleware(DbSessionMiddleware())
    dp.update.outer_middleware(UserMiddleware())
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())
    dp.include_router(setup_routers())


async def main() -> None:
    await init_db()
    await seed_channel()
    await set_commands()
    setup_dispatcher()

    stop = asyncio.Event()
    scheduler = build_scheduler()
    scheduler.start()
    asyncio.create_task(update_ton_rate())

    server = uvicorn.Server(uvicorn.Config(api, host=settings.api_host, port=settings.api_port, log_level="warning"))
    worker_task = asyncio.create_task(fulfillment.run_forever(stop))
    api_task = asyncio.create_task(server.serve())

    me = await bot.me()
    log.info("Tayzo started as @%s | click=%s fragment=%s", me.username, settings.click_configured, settings.fragment_configured)
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query", "my_chat_member"])
    finally:
        stop.set()
        server.should_exit = True
        scheduler.shutdown(wait=False)
        await asyncio.gather(worker_task, api_task, return_exceptions=True)
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Tayzo stopped")
