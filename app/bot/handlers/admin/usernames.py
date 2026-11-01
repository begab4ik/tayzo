"""/usernames — охота за свободными короткими юзернеймами через аккаунт владельца (MTProto).

    /usernames                 — проверить встроенный список коротких осмысленных слов
    /usernames word1 word2 …   — проверить свои варианты
    /usernames +suffix         — встроенный список с суффиксом/префиксом: /usernames +uz  → appleuz, …   /usernames uz+ → uzapple
Результат приходит сообщениями по мере проверки. Лимиты Telegram соблюдаются (пауза, FLOOD_WAIT).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.core.exceptions import ProviderAuthError
from app.providers.telegram_account import tg_account

log = logging.getLogger(__name__)
router = Router(name="admin_usernames")

WORDS_FILE = Path(__file__).resolve().parents[3] / "data" / "usernames_words.txt"
_running: set[int] = set()


def _load_words() -> list[str]:
    try:
        return [w.strip().lower() for w in WORDS_FILE.read_text().splitlines() if w.strip()]
    except OSError:
        return []


async def _check(client, name: str) -> str:
    """'free' | 'taken' | 'fragment' | 'invalid'"""
    from telethon.errors import FloodWaitError, RPCError
    from telethon.tl.functions.account import CheckUsernameRequest

    while True:
        try:
            ok = await client(CheckUsernameRequest(username=name))
            return "free" if ok else "taken"
        except FloodWaitError as e:
            log.warning("FLOOD_WAIT %ss on checkUsername", e.seconds)
            await asyncio.sleep(e.seconds + 1)
        except RPCError as e:
            m = str(e)
            if "USERNAME_PURCHASE_AVAILABLE" in m:
                return "fragment"
            if "USERNAME_INVALID" in m or "USERNAME_OCCUPIED" in m:
                return "invalid" if "INVALID" in m else "taken"
            return "invalid"


@router.message(Command("usernames", "hunt"))
async def hunt(message: Message, command: CommandObject):
    uid = message.from_user.id
    if uid in _running:
        await message.answer("Проверка уже идёт — дождись окончания.")
        return
    args = (command.args or "").split()
    base = _load_words()
    if args and all(a.startswith("+") or a.endswith("+") for a in args):
        names = []
        for a in args:
            if a.startswith("+"):
                names += [w + a[1:] for w in base]
            else:
                names += [a[:-1] + w for w in base]
    elif args:
        names = [a.lstrip("@").lower() for a in args]
    else:
        names = base
    names = [n for n in dict.fromkeys(names) if 5 <= len(n) <= 32]
    if not names:
        await message.answer("Список пуст. Пример: <code>/usernames apple mango</code> или <code>/usernames +uz</code>")
        return
    try:
        client = await tg_account.client()
    except ProviderAuthError as e:
        await message.answer(f"Нужен вход в аккаунт (Админка → 🎁 Подарки → Войти): {e}")
        return

    _running.add(uid)
    await message.answer(f"🔎 Проверяю {len(names)} вариантов… (~{len(names) // 2} сек). Свободные пришлю списком.")
    free: list[str] = []
    fragment: list[str] = []
    try:
        for i, n in enumerate(names, 1):
            st = await _check(client, n)
            if st == "free":
                free.append(n)
            elif st == "fragment":
                fragment.append(n)
            if free and len(free) % 15 == 0 and i < len(names):
                await message.answer("✅ Свободны:\n" + "\n".join(f"@{x}" for x in free[-15:]))
            await asyncio.sleep(0.5)
    finally:
        _running.discard(uid)
    tail = free[-(len(free) % 15):] if len(free) % 15 else []
    text = f"Готово: проверено {len(names)}, свободно <b>{len(free)}</b>, на Fragment {len(fragment)}."
    if tail:
        text += "\n\n✅ Свободны:\n" + "\n".join(f"@{x}" for x in tail)
    if fragment:
        text += "\n\n💎 Продаются на Fragment (уже NFT):\n" + "\n".join(f"@{x}" for x in fragment[:30])
    if free:
        text += "\n\nПолный список свободных:\n<code>" + " ".join(free) + "</code>"
    for chunk in [text[i : i + 3800] for i in range(0, len(text), 3800)]:
        await message.answer(chunk)
