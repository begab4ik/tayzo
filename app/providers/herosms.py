"""HeroSMS — виртуальные номера для приёма SMS (API совместим с sms-activate).

GET https://hero-sms.com/stubs/handler_api.php?api_key=…&action=…
Цены в USD. Номер живёт 20 минут; если SMS не пришла — отмена (setStatus=8) возвращает деньги на счёт HeroSMS.
"""
from __future__ import annotations

import json
import logging

import httpx

from app.config import settings
from app.core.exceptions import ProviderError
from app.redis_client import redis

log = logging.getLogger(__name__)

BASE = "https://hero-sms.com/stubs/handler_api.php"
LIFETIME_MIN = 20

# что показываем в приложении (код сервиса HeroSMS → название); Telegram первым
SERVICES: list[tuple[str, str]] = [
    ("tg", "Telegram"), ("wa", "WhatsApp"), ("ig", "Instagram"), ("go", "Google / Gmail"), ("lf", "TikTok"),
    ("fb", "Facebook"), ("ds", "Discord"), ("tw", "Twitter / X"), ("vk", "VK"), ("ya", "Yandex"), ("mm", "Microsoft"), ("oi", "Tinder"),
]
SERVICE_NAMES = dict(SERVICES)


class NoNumbers(ProviderError):
    pass


class HeroSMS:
    @property
    def configured(self) -> bool:
        return bool(settings.herosms_api_key)

    async def _call(self, action: str, **params):
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.get(BASE, params={"api_key": settings.herosms_api_key, "action": action, **params})
        text = r.text.strip()
        try:
            data = json.loads(text)
        except ValueError:
            data = text
        if isinstance(data, dict) and data.get("title") and "info" in data and "activationId" not in data:
            # структурированная ошибка {"title": "NO_NUMBERS", ...}
            self._raise(str(data.get("title")), text)
        if isinstance(data, str):
            for code in ("NO_NUMBERS", "NO_BALANCE", "BAD_KEY", "NO_KEY", "BAD_SERVICE", "BAD_ACTION", "BANNED", "WRONG_MAX_PRICE", "ERROR_SQL", "CHANNELS_LIMIT", "ACCOUNT_INACTIVE"):
                if data.startswith(code):
                    self._raise(code, text)
        return data

    @staticmethod
    def _raise(code: str, raw: str):
        if code == "NO_NUMBERS":
            raise NoNumbers("NO_NUMBERS")
        log.warning("HeroSMS error: %s", raw[:300])
        raise ProviderError(f"HeroSMS: {code}")

    async def balance(self) -> float:
        data = await self._call("getBalance")
        return float(str(data).split(":", 1)[1]) if isinstance(data, str) and ":" in data else 0.0

    async def countries(self) -> dict[int, str]:
        raw = await redis.get("tayzo:sms:countries")
        if raw:
            return {int(k): v for k, v in json.loads(raw).items()}
        data = await self._call("getCountries")
        rows = data if isinstance(data, list) else list(data.values())
        out = {int(c["id"]): {"ru": c.get("rus") or c.get("eng"), "en": c.get("eng") or c.get("rus")} for c in rows if c.get("visible", 1)}
        await redis.set("tayzo:sms:countries", json.dumps(out), ex=24 * 3600)
        return out

    async def offers(self, service: str) -> list[dict]:
        """Страны с ценой и остатком для сервиса: [{country, usd, count}], дешёвые первыми. Кэш 5 минут."""
        key = f"tayzo:sms:offers:{service}"
        raw = await redis.get(key)
        if raw:
            return json.loads(raw)
        data = await self._call("getTopCountriesByService", service=service)
        rows = data if isinstance(data, list) else list(data.values())
        out = []
        for r in rows:
            try:
                usd = float(r.get("retail_price") or r.get("price") or 0)
                cnt = int(r.get("count") or 0)
            except (TypeError, ValueError, AttributeError):
                continue
            if usd > 0 and cnt > 0:
                out.append({"country": int(r["country"]), "usd": usd, "count": cnt})
        out.sort(key=lambda x: x["usd"])
        await redis.set(key, json.dumps(out), ex=300)
        return out

    async def get_number(self, service: str, country: int, max_usd: float) -> dict:
        data = await self._call("getNumberV2", service=service, country=country, maxPrice=round(max_usd, 4))
        if not isinstance(data, dict) or not data.get("activationId"):
            raise ProviderError(f"HeroSMS: {str(data)[:120]}")
        return data

    async def status(self, ext_id: str) -> tuple[str, str | None]:
        """('wait'|'ok'|'cancel', code)"""
        data = await self._call("getStatus", id=ext_id)
        s = str(data)
        if s.startswith("STATUS_OK"):
            return "ok", s.split(":", 1)[1] if ":" in s else None
        if s.startswith("STATUS_CANCEL"):
            return "cancel", None
        return "wait", None

    async def set_status(self, ext_id: str, status: int) -> str:
        return str(await self._call("setStatus", id=ext_id, status=status))


herosms = HeroSMS()
