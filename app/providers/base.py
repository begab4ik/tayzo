"""Единый интерфейс поставщика цифрового товара.

Чтобы добавить новый товар (накрутка, подарки...), реализуй этот интерфейс
и зарегистрируй в providers/registry.py. Ядро (кошелёк, заказы, бот) трогать не нужно.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Recipient:
    username: str
    name: str
    token: str  # внутренний id получателя у провайдера


@dataclass
class FulfillResult:
    ok: bool
    external_id: str | None = None  # req_id / tx hash
    cost_ton: Decimal | None = None
    error: str | None = None


class Provider(ABC):
    code: str

    @abstractmethod
    async def resolve_recipient(self, username: str, quantity: int) -> Recipient:
        """Проверить, что получатель существует. Бросает RecipientNotFound."""

    @abstractmethod
    async def fulfill(self, recipient: Recipient, quantity: int) -> FulfillResult:
        """Выполнить доставку. Бросает ProviderError при сбое."""

    async def healthcheck(self) -> str:
        return "ok"
