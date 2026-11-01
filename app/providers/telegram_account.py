"""Telegram-аккаунт владельца (MTProto через Telethon): каталог подарков, баланс звёзд, отправка подарков.

Нужны TG_API_ID / TG_API_HASH (my.telegram.org) в tokens.env и один раз войти в аккаунт из админки бота
(телефон → код → пароль 2FA). Строка сессии хранится в настройках (settings.tg_session).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from app.config import settings
from app.core import settings_store as cfg
from app.core.exceptions import ProviderAuthError, ProviderError, RecipientNotFound
from app.db.base import get_session
from app.redis_client import redis

log = logging.getLogger(__name__)

GIFTS_DIR = Path(os.environ.get("GIFTS_DIR", "/app/site/gifts"))
GIFTS_CACHE_KEY = "tayzo:gifts:catalog"
GIFTS_CACHE_TTL = 30 * 60


class TelegramAccount:
    def __init__(self) -> None:
        self._client = None
        self._lock = asyncio.Lock()
        self._login_clients: dict[int, object] = {}  # admin_id -> временный клиент во время входа

    # ---------- base ----------
    @property
    def configured(self) -> bool:
        return bool(settings.tg_api_id and settings.tg_api_hash)

    async def _session_string(self) -> str:
        async with get_session() as s:
            return await cfg.get(s, "tg_session")

    async def client(self):
        """Подключённый авторизованный клиент (singleton)."""
        if not self.configured:
            raise ProviderAuthError("TG_API_ID / TG_API_HASH не заданы в tokens.env")
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        if self._client is not None and self._client.is_connected():
            return self._client
        session = await self._session_string()
        if not session:
            raise ProviderAuthError("Аккаунт для подарков не подключён — Админка → 🎁 Подарки → Войти")
        c = TelegramClient(StringSession(session), settings.tg_api_id, settings.tg_api_hash, device_model="Tayzo", system_version="1.0", app_version="1.0")
        await c.connect()
        if not await c.is_user_authorized():
            await c.disconnect()
            raise ProviderAuthError("Сессия Telegram-аккаунта слетела — войди заново в админке")
        self._client = c
        return c

    async def me(self) -> dict:
        c = await self.client()
        u = await c.get_me()
        return {"id": u.id, "username": u.username, "name": " ".join(filter(None, [u.first_name, u.last_name]))}

    async def star_balance(self) -> int:
        from telethon.tl.functions.payments import GetStarsStatusRequest
        from telethon.tl.types import InputPeerSelf

        c = await self.client()
        st = await c(GetStarsStatusRequest(peer=InputPeerSelf()))
        bal = st.balance
        return int(getattr(bal, "amount", bal))

    # ---------- login flow (из админки) ----------
    async def login_start(self, admin_id: int, phone: str) -> None:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        if not self.configured:
            raise ProviderAuthError("TG_API_ID / TG_API_HASH не заданы в tokens.env")
        c = TelegramClient(StringSession(), settings.tg_api_id, settings.tg_api_hash, device_model="Tayzo", system_version="1.0", app_version="1.0")
        await c.connect()
        await c.send_code_request(phone)
        self._login_clients[admin_id] = (c, phone)

    async def login_code(self, admin_id: int, code: str) -> bool:
        """True — вошли; False — нужен пароль 2FA."""
        from telethon.errors import SessionPasswordNeededError

        c, phone = self._login_clients[admin_id]
        try:
            await c.sign_in(phone, code.replace(" ", "").replace("-", ""))
        except SessionPasswordNeededError:
            return False
        await self._finish_login(admin_id, c)
        return True

    async def login_password(self, admin_id: int, password: str) -> None:
        c, _ = self._login_clients[admin_id]
        await c.sign_in(password=password)
        await self._finish_login(admin_id, c)

    async def _finish_login(self, admin_id: int, c) -> None:
        me = await c.get_me()
        async with get_session() as s:
            await cfg.set_value(s, "tg_session", c.session.save())
            await cfg.set_value(s, "tg_account_username", me.username or "")
        self._login_clients.pop(admin_id, None)
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
        self._client = None
        log.info("Telegram account connected: @%s", me.username)

    async def login_cancel(self, admin_id: int) -> None:
        item = self._login_clients.pop(admin_id, None)
        if item:
            try:
                await item[0].disconnect()
            except Exception:  # noqa: BLE001
                pass

    async def logout(self) -> None:
        if self._client is not None:
            try:
                await self._client.log_out()
            except Exception:  # noqa: BLE001
                pass
            self._client = None
        async with get_session() as s:
            await cfg.set_value(s, "tg_session", "")

    # ---------- gifts ----------
    async def fetch_gifts(self) -> list[dict]:
        """Каталог подарков Telegram + кэш стикеров в site/gifts (отдаёт Caddy)."""
        from telethon.tl.functions.payments import GetStarGiftsRequest

        c = await self.client()
        res = await c(GetStarGiftsRequest(hash=0))
        gifts = getattr(res, "gifts", None) or []
        GIFTS_DIR.mkdir(parents=True, exist_ok=True)
        out: list[dict] = []
        for g in gifts:
            if type(g).__name__ != "StarGift" or getattr(g, "sold_out", False) or getattr(g, "auction", False):
                continue
            doc = g.sticker
            mime = getattr(doc, "mime_type", "") or ""
            ext = "tgs" if "tgs" in mime or mime == "application/x-tgsticker" else ("webm" if "webm" in mime else "webp")
            fname = f"{g.id}.{ext}"
            path = GIFTS_DIR / fname
            if not path.exists():
                try:
                    await c.download_media(doc, file=str(path))
                except Exception as e:  # noqa: BLE001
                    log.warning("gift sticker %s download failed: %s", g.id, e)
                    continue
            out.append(
                {
                    "id": str(g.id),
                    "stars": int(g.stars),
                    "title": getattr(g, "title", None) or "",
                    "limited": bool(getattr(g, "limited", False)),
                    "remains": getattr(g, "availability_remains", None),
                    "total": getattr(g, "availability_total", None),
                    "require_premium": bool(getattr(g, "require_premium", False)),
                    "per_user_remains": getattr(g, "per_user_remains", None),
                    "image": f"/gifts/{fname}",
                    "kind": ext,
                }
            )
        out.sort(key=lambda x: (x["stars"], x["id"]))
        await redis.set(GIFTS_CACHE_KEY, json.dumps(out), ex=GIFTS_CACHE_TTL)
        return out

    async def gifts(self, force: bool = False) -> list[dict]:
        if not force:
            raw = await redis.get(GIFTS_CACHE_KEY)
            if raw:
                return json.loads(raw)
        return await self.fetch_gifts()

    async def gift_by_id(self, gift_id: str) -> dict | None:
        for g in await self.gifts():
            if g["id"] == str(gift_id):
                return g
        for g in await self.gifts(force=True):
            if g["id"] == str(gift_id):
                return g
        return None

    async def resolve_user(self, username: str) -> dict:
        from telethon.errors import UsernameInvalidError, UsernameNotOccupiedError
        from telethon.tl.types import User

        c = await self.client()
        try:
            ent = await c.get_entity(username.lstrip("@"))
        except (UsernameInvalidError, UsernameNotOccupiedError, ValueError):
            raise RecipientNotFound("Пользователь не найден. Проверь username.")
        if not isinstance(ent, User) or ent.bot:
            raise RecipientNotFound("Подарок можно отправить только пользователю (не боту и не каналу).")
        return {"id": ent.id, "username": ent.username or username.lstrip("@"), "name": " ".join(filter(None, [ent.first_name, ent.last_name])) or ent.username or ""}

    async def send_gift(self, username: str, gift_id: int, hide_name: bool = True, message: str | None = None) -> None:
        from telethon.errors import RPCError
        from telethon.tl.functions.payments import GetPaymentFormRequest, SendStarsFormRequest
        from telethon.tl.types import InputInvoiceStarGift, TextWithEntities

        c = await self.client()
        async with self._lock:
            peer = await c.get_input_entity(username.lstrip("@"))
            invoice = InputInvoiceStarGift(
                peer=peer,
                gift_id=int(gift_id),
                hide_name=hide_name,
                message=TextWithEntities(text=message, entities=[]) if message else None,
            )
            try:
                form = await c(GetPaymentFormRequest(invoice=invoice))
                await c(SendStarsFormRequest(form_id=form.form_id, invoice=invoice))
            except RPCError as e:
                msg = str(e)
                if "BALANCE_TOO_LOW" in msg:
                    raise ProviderError("На аккаунте не хватает звёзд для подарка")
                if "STARGIFT_USAGE_LIMITED" in msg or "SOLD_OUT" in msg:
                    raise ProviderError("Подарок закончился (sold out)")
                if "USER_PRIVACY" in msg or "PEER_ID_INVALID" in msg:
                    raise RecipientNotFound("Получатель закрыл приём подарков в настройках приватности")
                raise ProviderError(f"Telegram: {msg}")


tg_account = TelegramAccount()
