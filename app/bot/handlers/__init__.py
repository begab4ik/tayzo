from aiogram import Router

from app.bot.handlers import admin, balance, premium, profile, start, stars, subscription


def setup_routers() -> Router:
    root = Router(name="root")
    # порядок важен: admin первым (у него свой фильтр), затем остальное
    root.include_routers(
        admin.router,
        subscription.router,
        start.router,
        balance.router,
        stars.router,
        premium.router,
        profile.router,
    )
    return root
