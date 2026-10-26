from enum import StrEnum


class LedgerType(StrEnum):
    TOPUP = "topup"                  # пополнение через Click
    PURCHASE = "purchase"            # списание за заказ
    REFUND = "refund"                # возврат за неудавшийся заказ
    REFERRAL_BONUS = "referral_bonus"
    PROMO_BONUS = "promo_bonus"
    ADMIN_ADJUST = "admin_adjust"    # ручная корректировка админом


class PaymentStatus(StrEnum):
    CREATED = "created"
    PREPARED = "prepared"
    PAID = "paid"
    CANCELLED = "cancelled"


class ProductType(StrEnum):
    STARS = "stars"
    PREMIUM = "premium"


class OrderStatus(StrEnum):
    PENDING = "pending"        # оплачен с баланса, ждёт выполнения
    PROCESSING = "processing"  # воркер выполняет
    DELIVERED = "delivered"    # доставлено
    FAILED = "failed"          # ошибка, будет ретрай
    MANUAL = "manual"          # ушёл в ручную очередь админа
    REFUNDED = "refunded"      # деньги возвращены


class PromoKind(StrEnum):
    BALANCE = "balance"        # фиксированный бонус на баланс
