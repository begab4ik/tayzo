from decimal import ROUND_CEILING, Decimal


def fmt_uzs(amount: int | Decimal) -> str:
    """12345678 -> '12 345 678 сум'"""
    return f"{int(amount):,}".replace(",", " ") + " сум"


def fmt_ton(amount: Decimal | float | None) -> str:
    if amount is None:
        return "—"
    return f"{Decimal(amount).quantize(Decimal('0.001'))} TON"


def round_up_100(amount: Decimal) -> int:
    """Округляем цену вверх до 100 сум, чтобы не было 'копеек'."""
    return int((amount / 100).quantize(Decimal("1"), rounding=ROUND_CEILING) * 100)
