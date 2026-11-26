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

import asyncio
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
        self._auth_lock = asyncio.Lock()
        self.last_ok = True
        self.last_error = ""

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

    def _absorb_cookies(self, r: httpx.Response) -> None:
        """Fragment обновляет cookies (stel_ton_token после привязки кошелька). Кладём их без домена поверх
        исходных из tokens.env — иначе в jar окажутся два значения с одним именем."""
        for name, value in r.cookies.items():
            for c in [c for c in self._client.cookies.jar if c.name == name]:
                self._client.cookies.jar.clear(c.domain, c.path, c.name)
            self._client.cookies.set(name, value)

    async def _post(self, method: str, referer: str, data: dict, _retry: bool = True) -> dict:
        api_hash = await self._ensure_hash()
        payload = {"method": method, **{k: v for k, v in data.items() if v is not None}}
        try:
            r = await self._client.post(f"/api?hash={api_hash}", data=payload, headers={**API_HEADERS, "Referer": BASE + referer})
        except httpx.HTTPError as e:
            raise ProviderError(f"Fragment недоступен: {e}") from e
        if r.status_code in (401, 403):
            raise ProviderAuthError("Fragment вернул 401/403 — обнови cookies")
        self._absorb_cookies(r)
        try:
            body = r.json()
        except ValueError:
            raise ProviderError(f"Fragment: не JSON ({r.status_code})")
        body = body if isinstance(body, dict) else {"result": body}
        if _retry and str(body.get("error", "")).lower() == "bad request":
            # api hash привязан к сессии и меняется вместе с cookies — берём свежий со страницы и повторяем
            self._hash = ""
            return await self._post(method, referer, data, _retry=False)
        return body

    async def call(self, method: str, referer: str = "/stars/buy", **data) -> dict:
        body = await self._post(method, referer, data)
        if body.get("need_ton"):
            # Fragment просит заново привязать TON-кошелёк к сессии (TonConnect + ton_proof) — делаем это сами и повторяем
            await self.ton_auth()
            body = await self._post(method, referer, data)
            if body.get("need_ton"):
                raise ProviderAuthError("Fragment не принял привязку TON-кошелька (need_ton) — обнови cookies Fragment")
        if body.get("error"):
            err = str(body["error"])
            if "log in" in err.lower() or "unauthorized" in err.lower():
                raise ProviderAuthError(f"Fragment: {err}")
            raise ProviderError(f"Fragment: {err}")
        return body

    async def ton_auth(self) -> None:
        """Привязать наш TON-кошелёк к сессии Fragment так же, как это делает TonConnect в браузере:
        берём со страницы payload, подписываем ton_proof ключом кошелька, отдаём в checkTonProofAuth."""
        async with self._auth_lock:
            try:
                r = await self._client.get("/stars/buy", headers={"Referer": BASE})
            except httpx.HTTPError as e:
                raise ProviderError(f"Fragment недоступен: {e}") from e
            self._absorb_cookies(r)
            m = re.search(r'\\?"ton_proof\\?"\s*:\s*\\?"([^"\\]+)', r.text)
            if not m:
                raise ProviderAuthError("Fragment: на странице нет ton_proof — похоже, слетел вход, обнови cookies")
            m2 = re.search(r"api\?hash=([A-Za-z0-9_\-]+)", r.text)
            if m2:
                self._hash = m2.group(1)
            account = ton_wallet.tonconnect_account()
            proof = ton_wallet.ton_proof(m.group(1), "fragment.com")
            args = {"account": json.dumps(account), "device": json.dumps(DEVICE), "proof": json.dumps(proof)}
            res: dict = {}
            for _ in range(8):
                res = await self._post("checkTonProofAuth", "/stars/buy", args)
                if res.get("verified"):
                    self._hash = ""  # после привязки сессия другая — hash перечитаем со страницы
                    log.info("Fragment: TON wallet re-linked to session")
                    return
                if not res.get("pending"):
                    break
                await asyncio.sleep(2)
            raise ProviderAuthError(f"Fragment не подтвердил TON-кошелёк: {str(res.get('error') or res)[:150]}")

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
        await _record_star_cost(cost, quantity)
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


async def _record_star_cost(cost_ton: Decimal, quantity: int) -> None:
    """Фактическая себестоимость звезды по реальной покупке — надёжнее часового пробника."""
    if cost_ton <= 0 or quantity <= 0:
        return
    try:
        from app.core import settings_store as cfg
        from app.db.base import get_session

        async with get_session() as s:
            await cfg.set_value(s, "star_price_ton", str((cost_ton / quantity).quantize(Decimal("0.000001"))))
    except Exception as e:  # noqa: BLE001
        log.warning("record star cost failed: %s", e)


async def fetch_star_price_ton(client: FragmentClient, probe_qty: int = 100, probe_username: str = "") -> Decimal | None:
    """Узнать актуальную себестоимость звезды: создаём заявку на probe_qty и смотрим цену (ничего не платим)."""
    if not probe_username:
        return None
    try:
        found = await client.call("searchStarsRecipient", query=probe_username.lstrip("@"), quantity=probe_qty)
        token = (found.get("found") or {}).get("recipient")
        if not token:
            return None
        init = await client.call("initBuyStarsRequest", recipient=token, quantity=probe_qty, payment_method=PAYMENT_METHOD)
        amount = init.get("amount")
        client.last_ok, client.last_error = bool(amount), "" if amount else f"нет цены в ответе {str(init)[:120]}"
        return Decimal(str(amount)) / probe_qty if amount else None
    except ProviderError as e:
        client.last_ok, client.last_error = False, str(e)
        log.warning("fetch_star_price_ton failed: %s", e)
        return None


async def fetch_premium_prices_ton(client: FragmentClient, probe_username: str) -> dict[int, Decimal]:
    """Актуальная себестоимость Premium (3/6/12 мес) в TON: создаём заявки на probe_username, ничего не платим.
    probe_username — любой аккаунт без Premium (Fragment не даёт подарить Premium тому, у кого он уже есть)."""
    out: dict[int, Decimal] = {}
    if not probe_username:
        return out
    for months in (3, 6, 12):
        try:
            found = await client.call("searchPremiumGiftRecipient", referer="/premium/gift", query=probe_username.lstrip("@"), months=months)
            token = (found.get("found") or {}).get("recipient")
            if not token:
                continue
            init = await client.call("initGiftPremiumRequest", referer="/premium/gift", recipient=token, months=months, payment_method=PAYMENT_METHOD)
            if init.get("amount"):
                out[months] = Decimal(str(init["amount"]))
        except ProviderError as e:
            log.warning("fetch_premium_prices_ton(%s) failed: %s", months, e)
    return out


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
