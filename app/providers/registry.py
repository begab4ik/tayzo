"""Реестр провайдеров: product -> Provider."""
from __future__ import annotations

from app.config import settings
from app.core.enums import ProductType
from app.core.exceptions import ProviderError
from app.providers.base import FulfillResult, Provider, Recipient
from app.providers.fragment import FragmentClient, FragmentPremiumProvider, FragmentStarsProvider

fragment_client = FragmentClient()


class ManualProvider(Provider):
    """Заглушка: получателя не проверяем, выполнение — только руками админа."""

    code = "manual"

    async def resolve_recipient(self, username: str, quantity: int) -> Recipient:
        username = username.lstrip("@")
        return Recipient(username=username, name=username, token="")

    async def fulfill(self, recipient: Recipient, quantity: int) -> FulfillResult:
        raise ProviderError("Ручной режим: выполни заказ вручную")


_providers: dict[ProductType, Provider] = {}


def get_provider(product: ProductType) -> Provider:
    if not _providers:
        if settings.manual_fulfillment or not settings.fragment_configured:
            _providers[ProductType.STARS] = ManualProvider()
            _providers[ProductType.PREMIUM] = ManualProvider()
        else:
            _providers[ProductType.STARS] = FragmentStarsProvider(fragment_client)
            _providers[ProductType.PREMIUM] = FragmentPremiumProvider(fragment_client)
    return _providers[product]


def is_manual_mode() -> bool:
    return isinstance(get_provider(ProductType.STARS), ManualProvider)
