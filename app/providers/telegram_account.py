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
NFT_DIR = GIFTS_DIR / "nft"
NFT_COLL_KEY = "tayzo:nft:collections"
NFT_COLL_TTL = 10 * 60
NFT_ATTRS_TTL = 15 * 60
NFT_LIST_TTL = 45


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

    # ---------- NFT (рынок перепродажи коллекционных подарков) ----------
    async def nft_collections(self, force: bool = False) -> list[dict]:
        """Коллекции, у которых есть лоты на перепродаже: id, title, floor (⭐), count, картинка."""
        if not force:
            raw = await redis.get(NFT_COLL_KEY)
            if raw:
                return json.loads(raw)
        from telethon.tl.functions.payments import GetStarGiftsRequest

        c = await self.client()
        res = await c(GetStarGiftsRequest(hash=0))
        GIFTS_DIR.mkdir(parents=True, exist_ok=True)
        out: list[dict] = []
        for g in getattr(res, "gifts", None) or []:
            if type(g).__name__ != "StarGift" or not getattr(g, "availability_resale", 0):
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
                    "title": getattr(g, "title", None) or "",
                    "floor": int(getattr(g, "resell_min_stars", 0) or 0),
                    "count": int(g.availability_resale),
                    "total": getattr(g, "availability_total", None),
                    "image": f"/gifts/{fname}",
                    "kind": ext,
                }
            )
        out.sort(key=lambda x: (-x["count"], x["floor"]))
        await redis.set(NFT_COLL_KEY, json.dumps(out), ex=NFT_COLL_TTL)
        return out

    async def nft_collection(self, gift_id: str) -> dict | None:
        for g in await self.nft_collections():
            if g["id"] == str(gift_id):
                return g
        return None

    @staticmethod
    def _rarity(attr) -> int:
        r = getattr(attr, "rarity", None)
        return int(getattr(r, "permille", 0) or 0)

    @staticmethod
    def _hex(v: int | None) -> str:
        return f"#{int(v or 0):06x}"

    async def _model_image(self, c, doc) -> str | None:
        """Стикер модели (tgs) → site/gifts/nft/m_<id>.tgs (скачивается один раз)."""
        NFT_DIR.mkdir(parents=True, exist_ok=True)
        mime = getattr(doc, "mime_type", "") or ""
        ext = "tgs" if "tgs" in mime or mime == "application/x-tgsticker" else ("webm" if "webm" in mime else "webp")
        path = NFT_DIR / f"m_{doc.id}.{ext}"
        if not path.exists():
            try:
                await c.download_media(doc, file=str(path))
            except Exception as e:  # noqa: BLE001
                log.warning("nft model %s download failed: %s", doc.id, e)
                return None
        return f"/gifts/nft/{path.name}"

    async def _unique_json(self, c, g, with_images: bool = True) -> dict:
        model = backdrop = pattern = None
        for a in g.attributes:
            n = type(a).__name__
            if n == "StarGiftAttributeModel":
                model = {"id": str(a.document.id), "name": a.name, "rarity": self._rarity(a), "image": (await self._model_image(c, a.document)) if with_images else None}
            elif n == "StarGiftAttributeBackdrop":
                backdrop = {"id": str(a.backdrop_id), "name": a.name, "rarity": self._rarity(a), "center": self._hex(a.center_color), "edge": self._hex(a.edge_color), "pattern": self._hex(a.pattern_color), "text": self._hex(a.text_color)}
            elif n == "StarGiftAttributePattern":
                pattern = {"id": str(a.document.id), "name": a.name, "rarity": self._rarity(a)}
        stars = None
        for am in getattr(g, "resell_amount", None) or []:
            if type(am).__name__ == "StarsAmount":
                stars = int(am.amount)
        return {
            "slug": g.slug,
            "num": int(g.num),
            "title": g.title,
            "gift_id": str(g.gift_id),
            "stars": stars,
            "ton_only": bool(getattr(g, "resale_ton_only", False)) or stars is None,
            "model": model,
            "backdrop": backdrop,
            "pattern": pattern,
            "issued": getattr(g, "availability_issued", None),
            "total": getattr(g, "availability_total", None),
        }

    async def nft_attributes(self, gift_id: int) -> dict:
        """Фильтры коллекции: модели/фоны/узоры с количеством лотов на продаже (кэш 15 мин)."""
        key = f"tayzo:nft:attrs:{gift_id}"
        raw = await redis.get(key)
        if raw:
            return json.loads(raw)
        from telethon.tl.functions.payments import GetResaleStarGiftsRequest

        c = await self.client()
        res = await c(GetResaleStarGiftsRequest(gift_id=int(gift_id), offset="", limit=1, attributes_hash=0, sort_by_price=True))
        counts: dict[tuple[str, str], int] = {}
        for ct in getattr(res, "counters", None) or []:
            a = ct.attribute
            n = type(a).__name__
            if n == "StarGiftAttributeIdModel":
                counts[("model", str(a.document_id))] = int(ct.count)
            elif n == "StarGiftAttributeIdBackdrop":
                counts[("backdrop", str(a.backdrop_id))] = int(ct.count)
            elif n == "StarGiftAttributeIdPattern":
                counts[("pattern", str(a.document_id))] = int(ct.count)
        models, backdrops, patterns = [], [], []
        for a in getattr(res, "attributes", None) or []:
            n = type(a).__name__
            if n == "StarGiftAttributeModel":
                models.append({"id": str(a.document.id), "name": a.name, "rarity": self._rarity(a), "count": counts.get(("model", str(a.document.id)), 0), "image": await self._model_image(c, a.document)})
            elif n == "StarGiftAttributeBackdrop":
                backdrops.append({"id": str(a.backdrop_id), "name": a.name, "rarity": self._rarity(a), "count": counts.get(("backdrop", str(a.backdrop_id)), 0), "center": self._hex(a.center_color), "edge": self._hex(a.edge_color)})
            elif n == "StarGiftAttributePattern":
                patterns.append({"id": str(a.document.id), "name": a.name, "rarity": self._rarity(a), "count": counts.get(("pattern", str(a.document.id)), 0)})
        for lst in (models, backdrops, patterns):
            lst.sort(key=lambda x: (-x["count"], x["name"]))
        out = {"models": [m for m in models if m["count"]], "backdrops": [b for b in backdrops if b["count"]], "patterns": [p for p in patterns if p["count"]], "count": int(getattr(res, "count", 0) or 0)}
        await redis.set(key, json.dumps(out), ex=NFT_ATTRS_TTL)
        return out

    async def nft_list(self, gift_id: int, offset: str = "", limit: int = 30, sort: str = "price", model: str | None = None, backdrop: str | None = None, pattern: str | None = None) -> dict:
        """Лоты коллекции на перепродаже (только за ⭐), с фильтрами. Кэш 45 сек."""
        key = f"tayzo:nft:list:{gift_id}:{offset}:{limit}:{sort}:{model or ''}:{backdrop or ''}:{pattern or ''}"
        raw = await redis.get(key)
        if raw:
            return json.loads(raw)
        from telethon.tl.functions.payments import GetResaleStarGiftsRequest
        from telethon.tl.types import StarGiftAttributeIdBackdrop, StarGiftAttributeIdModel, StarGiftAttributeIdPattern

        attrs = []
        if model:
            attrs.append(StarGiftAttributeIdModel(document_id=int(model)))
        if backdrop:
            attrs.append(StarGiftAttributeIdBackdrop(backdrop_id=int(backdrop)))
        if pattern:
            attrs.append(StarGiftAttributeIdPattern(document_id=int(pattern)))
        c = await self.client()
        res = await c(
            GetResaleStarGiftsRequest(
                gift_id=int(gift_id), offset=offset, limit=limit, sort_by_price=sort == "price" or None, sort_by_num=sort == "num" or None,
                stars_only=True, attributes=attrs or None,
            )
        )
        items = []
        for g in getattr(res, "gifts", None) or []:
            if type(g).__name__ != "StarGiftUnique":
                continue
            j = await self._unique_json(c, g)
            if j["ton_only"]:
                continue
            items.append(j)
        out = {"items": items, "next_offset": getattr(res, "next_offset", None) or "", "count": int(getattr(res, "count", 0) or 0)}
        await redis.set(key, json.dumps(out), ex=NFT_LIST_TTL)
        return out

    async def nft_item(self, slug: str) -> dict | None:
        """Актуальное состояние лота (цена/владелец) — без кэша, для подтверждения перед покупкой."""
        from telethon.errors import RPCError
        from telethon.tl.functions.payments import GetUniqueStarGiftRequest

        c = await self.client()
        try:
            res = await c(GetUniqueStarGiftRequest(slug=slug))
        except RPCError as e:
            log.warning("nft_item %s: %s", slug, e)
            return None
        g = res.gift
        if type(g).__name__ != "StarGiftUnique":
            return None
        j = await self._unique_json(c, g)
        j["for_sale"] = bool(getattr(g, "resell_amount", None))
        return j

    async def buy_nft(self, slug: str, to_username: str, expected_stars: int) -> int:
        """Купить лот на рынке перепродажи сразу на получателя. Возвращает списанные ⭐."""
        from telethon.errors import RPCError
        from telethon.tl.functions.payments import GetPaymentFormRequest, SendStarsFormRequest
        from telethon.tl.types import InputInvoiceStarGiftResale

        c = await self.client()
        async with self._lock:
            peer = await c.get_input_entity(to_username.lstrip("@"))
            invoice = InputInvoiceStarGiftResale(slug=slug, to_id=peer, show_name=False)
            try:
                form = await c(GetPaymentFormRequest(invoice=invoice))
                total = sum(int(p.amount) for p in form.invoice.prices)
                if total > expected_stars:
                    raise ProviderError(f"Цена лота изменилась: {total}⭐ вместо {expected_stars}⭐ — заказ отдан админу")
                await c(SendStarsFormRequest(form_id=form.form_id, invoice=invoice))
                return total
            except RPCError as e:
                msg = str(e)
                if "BALANCE_TOO_LOW" in msg:
                    raise ProviderError("На аккаунте не хватает звёзд для покупки NFT")
                if "STARGIFT_RESELL" in msg or "NOT_FOUND" in msg or "SLUG_INVALID" in msg or "STARGIFT_INVALID" in msg:
                    raise ProviderError(f"Лот {slug} уже продан или снят с продажи")
                if "USER_PRIVACY" in msg or "PEER_ID_INVALID" in msg:
                    raise RecipientNotFound("Получатель закрыл приём подарков в настройках приватности")
                raise ProviderError(f"Telegram: {msg}")


tg_account = TelegramAccount()
