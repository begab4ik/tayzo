"""Покупка Telegram Stars и Premium через fragment.com.

У Fragment нет публичного API: используется внутренний /api?hash=..., который зовёт сам сайт.
Нужны cookies залогиненного аккаунта (Telegram + TON-кошелёк подключены, KYC пройден).
Схема одной покупки:
  1. search*Recipient      — найти получателя, получить recipient-token и имя
  2. init*Request          — создать заявку, получить req_id и цену в TON
  3. get*Link              — получить транзакцию (адрес, сумма, payload) под наш кошелёк
  4. отправить транзакцию с TON-кошелька  → Fragment сам зачисляет Stars/Premium получателю

ВАЖНО: перед продом прогони 1–2 покупки на минимальные суммы и сверь с реальными ответами
Fragment — сайт периодически меняет имена полей.
"""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal

import httpx

from app.config import settings
from app.core.exceptions import ProviderAuthError, ProviderError, RecipientNotFound
from app.providers.base import FulfillResult, Provider, Recipient
from app.providers.ton_wallet import ton_wallet

log = logging.getLogger(__name__)

BASE = "https://fragment.com"
PAYMENT_METHOD = "ton"  # поле формы fragment.com: оплата с TON-кошелька (TonConnect)
DEVICE = {
    "platform": "web",
    "appName": "Tonkeeper",
    "appVersion": "3.0.0",
    "maxProtocolVersion": 2,
    "features": ["SendTransaction", {"name": "SendTransaction", "maxMessages": 4}],
}
# Заголовки «как браузер» — для загрузки HTML (иначе Fragment отдаёт урезанную страницу без api hash)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
}
# Заголовки AJAX — только для вызовов /api
API_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Origin": BASE,
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


class FragmentClient:
    def __init__(self) -> None:
        self._hash = settings.fragment_api_hash
        self._client = httpx.AsyncClient(base_url=BASE, headers=HEADERS, cookies=settings.fragment_cookies, timeout=30, follow_redirects=True)

    async def _ensure_hash(self) -> str:
        if self._hash:
            return self._hash
        last = ""
        for path in ("/stars/buy", "/", "/premium/gift"):
            try:
                r = await self._client.get(path, headers={"Referer": BASE})
            except httpx.HTTPError as e:
                last = str(e)
                continue
            m = re.search(r"api\?hash=([A-Za-z0-9_\-]+)", r.text)
            if m:
                self._hash = m.group(1)
                return self._hash
            last = f"{path}: HTTP {r.status_code}, {len(r.text)} байт"
        raise ProviderAuthError(f"Не удалось получить api hash Fragment — проверь cookies ({last})")

    async def call(self, method: str, referer: str = "/stars/buy", **data) -> dict:
        api_hash = await self._ensure_hash()
        payload = {"method": method, **{k: v for k, v in data.items() if v is not None}}
        try:
            r = await self._client.post(f"/api?hash={api_hash}", data=payload, headers={**API_HEADERS, "Referer": BASE + referer})
        except httpx.HTTPError as e:
            raise ProviderError(f"Fragment недоступен: {e}") from e
        if r.status_code in (401, 403):
            raise ProviderAuthError("Fragment вернул 401/403 — обнови cookies")
        try:
            body = r.json()
        except ValueError:
            raise ProviderError(f"Fragment: не JSON ({r.status_code})")
        if isinstance(body, dict) and body.get("error"):
            err = str(body["error"])
            if "log in" in err.lower() or "unauthorized" in err.lower():
                raise ProviderAuthError(f"Fragment: {err}")
            raise ProviderError(f"Fragment: {err}")
        return body

    async def close(self) -> None:
        await self._client.aclose()


class FragmentStarsProvider(Provider):
    code = "fragment_stars"

    def __init__(self, client: FragmentClient) -> None:
        self.client = client

    async def resolve_recipient(self, username: str, quantity: int) -> Recipient:
        username = username.lstrip("@")
        try:
            body = await self.client.call("searchStarsRecipient", query=username, quantity=quantity)
        except ProviderAuthError:
            raise
        except ProviderError as e:
            # Fragment отвечает error-текстом, если юзернейм не найден / скрыт — это не сбой, а «нет получателя»
            raise RecipientNotFound(_user_msg(e.message)) from e
        found = body.get("found")
        if not found or not found.get("recipient"):
            raise RecipientNotFound("Пользователь не найден. Проверь username — у получателя он должен быть установлен.")
        return Recipient(username=username, name=_strip_html(found.get("name") or username), token=found["recipient"])

    async def fulfill(self, recipient: Recipient, quantity: int) -> FulfillResult:
        init = await self.client.call("initBuyStarsRequest", recipient=recipient.token, quantity=quantity, payment_method=PAYMENT_METHOD)
        req_id = init.get("req_id")
        if not req_id:
            raise ProviderError(f"Fragment: нет req_id в ответе {init}")
        cost = Decimal(str(init.get("amount") or "0"))

        link = await self.client.call(
            "getBuyStarsLink",
            account=json.dumps(ton_wallet.tonconnect_account()),
            device=json.dumps(DEVICE),
            transaction="1",
            id=req_id,
            show_sender="0",
        )
        tx = link.get("transaction") or {}
        messages = tx.get("messages") or []
        if not messages:
            raise ProviderError(f"Fragment: нет транзакции в ответе {link}")
        if cost == 0:
            cost = sum(Decimal(m["amount"]) for m in messages) / Decimal(10**9)

        tx_hash = await ton_wallet.send(messages)
        return FulfillResult(ok=True, external_id=f"{req_id}:{tx_hash}", cost_ton=cost)

    async def healthcheck(self) -> str:
        await self.client._ensure_hash()
        bal = await ton_wallet.balance()
        return f"Fragment ok, TON balance {bal:.3f}"


class FragmentPremiumProvider(Provider):
    code = "fragment_premium"

    def __init__(self, client: FragmentClient) -> None:
        self.client = client

    async def resolve_recipient(self, username: str, quantity: int) -> Recipient:
        username = username.lstrip("@")
        try:
            body = await self.client.call("searchPremiumGiftRecipient", referer="/premium/gift", query=username, months=quantity)
        except ProviderAuthError:
            raise
        except ProviderError as e:
            raise RecipientNotFound(_user_msg(e.message)) from e
        found = body.get("found")
        if not found or not found.get("recipient"):
            raise RecipientNotFound("Пользователь не найден или у него уже есть Premium.")
        return Recipient(username=username, name=_strip_html(found.get("name") or username), token=found["recipient"])

    async def fulfill(self, recipient: Recipient, quantity: int) -> FulfillResult:
        init = await self.client.call("initGiftPremiumRequest", referer="/premium/gift", recipient=recipient.token, months=quantity, payment_method=PAYMENT_METHOD)
        req_id = init.get("req_id")
        if not req_id:
            raise ProviderError(f"Fragment: нет req_id в ответе {init}")
        cost = Decimal(str(init.get("amount") or "0"))
        link = await self.client.call(
            "getGiftPremiumLink",
            referer="/premium/gift",
            account=json.dumps(ton_wallet.tonconnect_account()),
            device=json.dumps(DEVICE),
            transaction="1",
            id=req_id,
            show_sender="0",
        )
        messages = (link.get("transaction") or {}).get("messages") or []
        if not messages:
            raise ProviderError(f"Fragment: нет транзакции в ответе {link}")
        if cost == 0:
            cost = sum(Decimal(m["amount"]) for m in messages) / Decimal(10**9)
        tx_hash = await ton_wallet.send(messages)
        return FulfillResult(ok=True, external_id=f"{req_id}:{tx_hash}", cost_ton=cost)


async def fetch_star_price_ton(client: FragmentClient, probe_qty: int = 100) -> Decimal | None:
    """Узнать актуальную себестоимость звезды: создаём заявку на probe_qty и смотрим цену (ничего не платим)."""
    try:
        found = await client.call("searchStarsRecipient", query="telegram", quantity=probe_qty)
        token = (found.get("found") or {}).get("recipient")
        if not token:
            return None
        init = await client.call("initBuyStarsRequest", recipient=token, quantity=probe_qty, payment_method=PAYMENT_METHOD)
        amount = init.get("amount")
        return Decimal(str(amount)) / probe_qty if amount else None
    except ProviderError as e:
        log.warning("fetch_star_price_ton failed: %s", e)
        return None


def _user_msg(err: str) -> str:
    """Текст ошибки Fragment -> понятное сообщение пользователю."""
    e = err.replace("Fragment: ", "")
    if "assigned to a user" in e or "not found" in e.lower():
        return "Пользователь не найден. Проверь username — у получателя он должен быть установлен и открыт для поиска."
    if "premium" in e.lower():
        return "У этого пользователя уже есть Premium или его нельзя подарить."
    return e


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()
