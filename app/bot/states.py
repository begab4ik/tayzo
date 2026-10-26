from aiogram.fsm.state import State, StatesGroup


class TopUp(StatesGroup):
    amount = State()


class BuyStars(StatesGroup):
    recipient = State()
    quantity = State()
    confirm = State()


class BuyPremium(StatesGroup):
    recipient = State()
    confirm = State()


class Promo(StatesGroup):
    code = State()


class Admin(StatesGroup):
    find_user = State()
    adjust_balance = State()
    set_value = State()
    promo_create = State()
    broadcast = State()
    add_channel = State()
