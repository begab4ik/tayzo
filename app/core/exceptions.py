class TayzoError(Exception):
    """Базовая ошибка с текстом, который можно показать пользователю."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InsufficientBalance(TayzoError):
    def __init__(self, need: int, have: int):
        super().__init__("Недостаточно средств")
        self.need = need
        self.have = have


class RecipientNotFound(TayzoError):
    pass


class ProviderError(TayzoError):
    """Ошибка провайдера (Fragment/TON). Заказ уходит в ретрай / ручную очередь."""
    pass


class ProviderAuthError(ProviderError):
    """Протухли cookies Fragment — нужно обновить."""
    pass
