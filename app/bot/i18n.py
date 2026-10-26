"""Переводы бота: ru / en / uz. Админка остаётся на русском."""
from __future__ import annotations

LANGS = {"ru": "🇷🇺 Русский", "en": "🇬🇧 English", "uz": "🇺🇿 O'zbekcha"}
DEFAULT = "ru"

T: dict[str, dict[str, str]] = {
    # --- кнопки главного меню ---
    "btn_stars": {"ru": "⭐ Купить Stars", "en": "⭐ Buy Stars", "uz": "⭐ Stars sotib olish"},
    "btn_premium": {"ru": "💎 Premium", "en": "💎 Premium", "uz": "💎 Premium"},
    "btn_balance": {"ru": "💰 Баланс", "en": "💰 Balance", "uz": "💰 Balans"},
    "btn_profile": {"ru": "👤 Профиль", "en": "👤 Profile", "uz": "👤 Profil"},
    "btn_orders": {"ru": "📦 Мои заказы", "en": "📦 My orders", "uz": "📦 Buyurtmalarim"},
    "btn_promo": {"ru": "🎟 Промокод", "en": "🎟 Promo code", "uz": "🎟 Promokod"},
    "btn_faq": {"ru": "ℹ️ Как это работает", "en": "ℹ️ How it works", "uz": "ℹ️ Bu qanday ishlaydi"},
    "btn_support": {"ru": "🆘 Поддержка", "en": "🆘 Support", "uz": "🆘 Yordam"},
    "btn_lang": {"ru": "🌐 Язык", "en": "🌐 Language", "uz": "🌐 Til"},
    "btn_admin": {"ru": "🛠 Админка", "en": "🛠 Admin", "uz": "🛠 Admin"},
    # --- inline-кнопки ---
    "ib_check_sub": {"ru": "✅ Проверить подписку", "en": "✅ Check subscription", "uz": "✅ Obunani tekshirish"},
    "ib_topup": {"ru": "💳 Пополнить", "en": "💳 Top up", "uz": "💳 To'ldirish"},
    "ib_history": {"ru": "📜 История", "en": "📜 History", "uz": "📜 Tarix"},
    "ib_custom_amount": {"ru": "✏️ Своя сумма", "en": "✏️ Custom amount", "uz": "✏️ Boshqa summa"},
    "ib_back": {"ru": "◀️ Назад", "en": "◀️ Back", "uz": "◀️ Orqaga"},
    "ib_cancel": {"ru": "❌ Отмена", "en": "❌ Cancel", "uz": "❌ Bekor qilish"},
    "ib_pay_click": {"ru": "💳 Оплатить через Click", "en": "💳 Pay via Click", "uz": "💳 Click orqali to'lash"},
    "ib_check_pay": {"ru": "🔄 Проверить оплату", "en": "🔄 Check payment", "uz": "🔄 To'lovni tekshirish"},
    "ib_self": {"ru": "👤 Себе", "en": "👤 For myself", "uz": "👤 O'zimga"},
    "ib_other": {"ru": "🎁 Другу (ввести @username)", "en": "🎁 For a friend (enter @username)", "uz": "🎁 Do'stga (@username kiriting)"},
    "ib_confirm": {"ru": "✅ Подтвердить", "en": "✅ Confirm", "uz": "✅ Tasdiqlash"},
    "ib_topup_missing": {"ru": "💳 Пополнить на {amount}", "en": "💳 Top up {amount}", "uz": "💳 {amount} to'ldirish"},
    "ib_months": {"ru": "💎 {m} мес — {price}", "en": "💎 {m} mo — {price}", "uz": "💎 {m} oy — {price}"},
    # --- тексты ---
    "welcome": {
        "ru": "👋 Привет, <b>{name}</b>!\n\nЭто <b>Tayzo</b> — быстрая покупка Telegram Stars и Premium за сумы.\n\n⭐ Звёзды приходят автоматически за 1–3 минуты\n💳 Оплата через Click\n🎁 Реферальная программа и промокоды\n\nВыбери, что нужно 👇",
        "en": "👋 Hi, <b>{name}</b>!\n\nThis is <b>Tayzo</b> — fast purchase of Telegram Stars and Premium for UZS.\n\n⭐ Stars arrive automatically in 1–3 minutes\n💳 Payment via Click\n🎁 Referral program and promo codes\n\nChoose what you need 👇",
        "uz": "👋 Salom, <b>{name}</b>!\n\nBu <b>Tayzo</b> — Telegram Stars va Premium'ni so'mda tez sotib olish.\n\n⭐ Yulduzlar 1–3 daqiqada avtomatik keladi\n💳 Click orqali to'lov\n🎁 Referal dasturi va promokodlar\n\nKerakli bo'limni tanlang 👇",
    },
    "choose_lang": {"ru": "🌐 Выбери язык / Choose language / Tilni tanlang:", "en": "🌐 Выбери язык / Choose language / Tilni tanlang:", "uz": "🌐 Выбери язык / Choose language / Tilni tanlang:"},
    "lang_set": {"ru": "✅ Язык: Русский", "en": "✅ Language: English", "uz": "✅ Til: O'zbekcha"},
    "menu_hint": {"ru": "Выбери действие в меню ниже 👇", "en": "Choose an action in the menu below 👇", "uz": "Quyidagi menyudan tanlang 👇"},
    "cancelled": {"ru": "↩️ Отменено. Выбери действие в меню ниже 👇", "en": "↩️ Cancelled. Choose an action in the menu below 👇", "uz": "↩️ Bekor qilindi. Quyidagi menyudan tanlang 👇"},
    "subscribe_required": {
        "ru": "🔒 Чтобы пользоваться ботом, подпишись на наш канал.\n\nТам скидки, промокоды и новости проекта. После подписки нажми «Проверить».",
        "en": "🔒 To use the bot, subscribe to our channel.\n\nDiscounts, promo codes and news are posted there. After subscribing, press “Check”.",
        "uz": "🔒 Botdan foydalanish uchun kanalimizga obuna bo'ling.\n\nU yerda chegirmalar, promokodlar va yangiliklar. Obuna bo'lgach «Tekshirish» tugmasini bosing.",
    },
    "sub_not_found": {"ru": "Подписка не найдена. Подпишись и нажми ещё раз.", "en": "Subscription not found. Subscribe and try again.", "uz": "Obuna topilmadi. Obuna bo'lib, yana bosing."},
    "sub_ok": {"ru": "✅ Подписка подтверждена, доступ открыт.", "en": "✅ Subscription confirmed, access granted.", "uz": "✅ Obuna tasdiqlandi, kirish ochildi."},
    "sub_thanks": {"ru": "Спасибо за подписку! 💛", "en": "Thanks for subscribing! 💛", "uz": "Obuna uchun rahmat! 💛"},
    "balance": {"ru": "💰 Твой баланс: <b>{balance}</b>", "en": "💰 Your balance: <b>{balance}</b>", "uz": "💰 Balansingiz: <b>{balance}</b>"},
    "no_ops": {"ru": "Операций пока нет", "en": "No transactions yet", "uz": "Hali amallar yo'q"},
    "history_title": {"ru": "📜 <b>Последние операции</b>", "en": "📜 <b>Recent transactions</b>", "uz": "📜 <b>So'nggi amallar</b>"},
    "topup_prompt": {
        "ru": "💳 <b>Пополнение баланса</b>\n\nВыбери сумму или введи свою (от {min} до {max}):",
        "en": "💳 <b>Top up balance</b>\n\nChoose an amount or enter your own (from {min} to {max}):",
        "uz": "💳 <b>Balansni to'ldirish</b>\n\nSummani tanlang yoki o'zingiz kiriting ({min} dan {max} gacha):",
    },
    "topup_custom": {"ru": "Введи сумму пополнения в сумах (только число):", "en": "Enter the top-up amount in UZS (numbers only):", "uz": "To'ldirish summasini so'mda kiriting (faqat raqam):"},
    "need_number": {"ru": "Нужно число, например <code>50000</code>", "en": "Enter a number, e.g. <code>50000</code>", "uz": "Raqam kiriting, masalan <code>50000</code>"},
    "topup_max": {"ru": "Максимальная сумма пополнения — {max}", "en": "Maximum top-up amount is {max}", "uz": "Maksimal to'ldirish summasi — {max}"},
    "topup_unavailable": {"ru": "💳 Приём оплаты временно недоступен. Напиши в поддержку.", "en": "💳 Payments are temporarily unavailable. Contact support.", "uz": "💳 To'lov qabul qilish vaqtincha ishlamayapti. Yordamga yozing."},
    "topup_link": {
        "ru": "💳 К оплате: <b>{amount}</b>\n\nНажми кнопку ниже и оплати через Click. Баланс пополнится автоматически в течение минуты.",
        "en": "💳 To pay: <b>{amount}</b>\n\nPress the button below and pay via Click. Your balance will update automatically within a minute.",
        "uz": "💳 To'lov: <b>{amount}</b>\n\nQuyidagi tugmani bosing va Click orqali to'lang. Balans bir daqiqa ichida avtomatik to'ldiriladi.",
    },
    "topup_success": {"ru": "✅ Баланс пополнен на <b>{amount}</b>\n💰 Текущий баланс: <b>{balance}</b>", "en": "✅ Balance topped up by <b>{amount}</b>\n💰 Current balance: <b>{balance}</b>", "uz": "✅ Balans <b>{amount}</b> ga to'ldirildi\n💰 Joriy balans: <b>{balance}</b>"},
    "pay_not_found": {"ru": "Платёж не найден", "en": "Payment not found", "uz": "To'lov topilmadi"},
    "pay_received": {"ru": "✅ Оплата получена!", "en": "✅ Payment received!", "uz": "✅ To'lov qabul qilindi!"},
    "pay_cancelled": {"ru": "❌ Платёж отменён", "en": "❌ Payment cancelled", "uz": "❌ To'lov bekor qilindi"},
    "pay_pending": {"ru": "Оплата ещё не поступила. Если ты уже оплатил — подожди минуту.", "en": "Payment not received yet. If you already paid, wait a minute.", "uz": "To'lov hali kelmadi. To'lagan bo'lsangiz, bir daqiqa kuting."},
    "stars_intro": {
        "ru": "⭐ <b>Покупка Telegram Stars</b>\n\nЦена: <b>{price}</b> за 1 звезду\nМинимум {min}, максимум {max} звёзд\n\nКому отправить?",
        "en": "⭐ <b>Buy Telegram Stars</b>\n\nPrice: <b>{price}</b> per star\nMin {min}, max {max} stars\n\nWho is it for?",
        "uz": "⭐ <b>Telegram Stars sotib olish</b>\n\nNarx: 1 yulduz — <b>{price}</b>\nKamida {min}, ko'pi bilan {max} yulduz\n\nKimga yuboramiz?",
    },
    "stars_disabled": {"ru": "⭐ Продажа звёзд временно приостановлена.", "en": "⭐ Star sales are temporarily paused.", "uz": "⭐ Yulduzlar sotuvi vaqtincha to'xtatilgan."},
    "premium_disabled": {"ru": "💎 Продажа Premium временно приостановлена.", "en": "💎 Premium sales are temporarily paused.", "uz": "💎 Premium sotuvi vaqtincha to'xtatilgan."},
    "ask_username": {"ru": "Введи <b>@username</b> получателя (у него должен быть установлен юзернейм в Telegram):", "en": "Enter the recipient's <b>@username</b> (they must have a Telegram username set):", "uz": "Qabul qiluvchining <b>@username</b>'ini kiriting (Telegram'da username o'rnatilgan bo'lishi kerak):"},
    "bad_username": {"ru": "Неверный формат. Пример: <code>@durov</code>", "en": "Invalid format. Example: <code>@durov</code>", "uz": "Noto'g'ri format. Masalan: <code>@durov</code>"},
    "recipient_check_fail": {"ru": "⚠️ Не удалось проверить получателя, попробуй через минуту.", "en": "⚠️ Could not verify the recipient, try again in a minute.", "uz": "⚠️ Qabul qiluvchini tekshirib bo'lmadi, bir daqiqadan so'ng urinib ko'ring."},
    "recipient_not_found": {"ru": "Пользователь не найден. Проверь username — у получателя он должен быть установлен.", "en": "User not found. Check the username — the recipient must have one set.", "uz": "Foydalanuvchi topilmadi. Username'ni tekshiring — u o'rnatilgan bo'lishi kerak."},
    "recipient_premium_fail": {"ru": "Пользователь не найден или у него уже есть Premium.", "en": "User not found or already has Premium.", "uz": "Foydalanuvchi topilmadi yoki unda Premium allaqachon bor."},
    "ask_stars_qty": {"ru": "Получатель: <b>{name}</b> (@{username})\n\nСколько звёзд отправить? Выбери или введи число:", "en": "Recipient: <b>{name}</b> (@{username})\n\nHow many stars? Choose or enter a number:", "uz": "Qabul qiluvchi: <b>{name}</b> (@{username})\n\nNechta yulduz? Tanlang yoki raqam kiriting:"},
    "qty_number": {"ru": "Введи число звёзд, например <code>150</code>", "en": "Enter the number of stars, e.g. <code>150</code>", "uz": "Yulduzlar sonini kiriting, masalan <code>150</code>"},
    "qty_range": {"ru": "Количество должно быть от {min} до {max}", "en": "Quantity must be between {min} and {max}", "uz": "Miqdor {min} dan {max} gacha bo'lishi kerak"},
    "confirm_order": {
        "ru": "🧾 <b>Подтверждение заказа</b>\n\nТовар: <b>{title}</b>\nПолучатель: <b>{name}</b> (@{username})\nК оплате: <b>{price}</b>\nБаланс: {balance}\n",
        "en": "🧾 <b>Order confirmation</b>\n\nItem: <b>{title}</b>\nRecipient: <b>{name}</b> (@{username})\nTotal: <b>{price}</b>\nBalance: {balance}\n",
        "uz": "🧾 <b>Buyurtmani tasdiqlash</b>\n\nMahsulot: <b>{title}</b>\nQabul qiluvchi: <b>{name}</b> (@{username})\nTo'lov: <b>{price}</b>\nBalans: {balance}\n",
    },
    "confirm_missing": {"ru": "\n⚠️ Не хватает <b>{missing}</b>. Пополни баланс и вернись к заказу.", "en": "\n⚠️ Missing <b>{missing}</b>. Top up your balance and come back.", "uz": "\n⚠️ <b>{missing}</b> yetishmaydi. Balansni to'ldirib, qaytib keling."},
    "price_changed": {"ru": "Цена обновилась, проверь ещё раз", "en": "Price has changed, please check again", "uz": "Narx yangilandi, qayta tekshiring"},
    "order_accepted": {"ru": "Заказ принят ✅", "en": "Order accepted ✅", "uz": "Buyurtma qabul qilindi ✅"},
    "order_created": {
        "ru": "✅ Заказ <b>#{id}</b> принят: {title}\n{eta}\nЯ напишу, как только всё будет готово.",
        "en": "✅ Order <b>#{id}</b> accepted: {title}\n{eta}\nI'll message you as soon as it's done.",
        "uz": "✅ Buyurtma <b>#{id}</b> qabul qilindi: {title}\n{eta}\nTayyor bo'lishi bilan xabar beraman.",
    },
    "eta_auto": {"ru": "Обычно доставка занимает 1–3 минуты.", "en": "Delivery usually takes 1–3 minutes.", "uz": "Odatda yetkazish 1–3 daqiqa oladi."},
    "eta_manual": {"ru": "Доставка займёт до 30 минут — менеджер выполнит вручную.", "en": "Delivery may take up to 30 minutes — a manager will process it manually.", "uz": "Yetkazish 30 daqiqagacha oladi — menejer qo'lda bajaradi."},
    "order_delivered": {"ru": "🎉 Заказ <b>#{id}</b> выполнен!\n{title} → @{username}\n\nСпасибо, что выбираешь Tayzo 💛", "en": "🎉 Order <b>#{id}</b> completed!\n{title} → @{username}\n\nThanks for choosing Tayzo 💛", "uz": "🎉 Buyurtma <b>#{id}</b> bajarildi!\n{title} → @{username}\n\nTayzo'ni tanlaganingiz uchun rahmat 💛"},
    "order_refunded": {
        "ru": "↩️ Заказ <b>#{id}</b> ({title}) не удалось выполнить.\nДеньги <b>{price}</b> вернулись на баланс. Если вопрос — @{support}",
        "en": "↩️ Order <b>#{id}</b> ({title}) could not be completed.\n<b>{price}</b> has been returned to your balance. Questions — @{support}",
        "uz": "↩️ Buyurtma <b>#{id}</b> ({title}) bajarilmadi.\n<b>{price}</b> balansga qaytarildi. Savollar — @{support}",
    },
    "premium_intro": {"ru": "💎 <b>Telegram Premium</b>\n\nВыбери срок подписки:", "en": "💎 <b>Telegram Premium</b>\n\nChoose a subscription period:", "uz": "💎 <b>Telegram Premium</b>\n\nObuna muddatini tanlang:"},
    "premium_who": {"ru": "💎 Premium на <b>{m} мес.</b>\n\nКому оформить?", "en": "💎 Premium for <b>{m} months</b>\n\nWho is it for?", "uz": "💎 <b>{m} oylik</b> Premium\n\nKimga?"},
    "premium_title": {"ru": "💎 Premium {m} мес.", "en": "💎 Premium {m} mo", "uz": "💎 Premium {m} oy"},
    "insufficient": {"ru": "❌ Недостаточно средств. Нужно {need}, на балансе {have}.", "en": "❌ Insufficient funds. Need {need}, balance {have}.", "uz": "❌ Mablag' yetarli emas. Kerak {need}, balansda {have}."},
    "profile": {
        "ru": "👤 <b>Профиль</b>\n\nID: <code>{id}</code>\nБаланс: <b>{balance}</b>\nПополнено всего: {topup}\nПотрачено: {spent}\nКуплено звёзд: ⭐ {stars}\nЗаказов: {orders}\n\n👥 <b>Рефералы</b>: {refs} чел., заработано {earned}\nПолучай <b>{percent}%</b> с каждого пополнения друзей:\n<code>{link}</code>",
        "en": "👤 <b>Profile</b>\n\nID: <code>{id}</code>\nBalance: <b>{balance}</b>\nTotal topped up: {topup}\nSpent: {spent}\nStars bought: ⭐ {stars}\nOrders: {orders}\n\n👥 <b>Referrals</b>: {refs}, earned {earned}\nGet <b>{percent}%</b> of every friend's top-up:\n<code>{link}</code>",
        "uz": "👤 <b>Profil</b>\n\nID: <code>{id}</code>\nBalans: <b>{balance}</b>\nJami to'ldirilgan: {topup}\nSarflangan: {spent}\nSotib olingan yulduzlar: ⭐ {stars}\nBuyurtmalar: {orders}\n\n👥 <b>Referallar</b>: {refs} kishi, topilgan {earned}\nDo'stlaringizning har bir to'ldirishidan <b>{percent}%</b> oling:\n<code>{link}</code>",
    },
    "no_orders": {"ru": "📦 Заказов пока нет. Самое время купить звёзды ⭐", "en": "📦 No orders yet. Time to buy some stars ⭐", "uz": "📦 Hali buyurtmalar yo'q. Yulduz sotib olish vaqti ⭐"},
    "orders_title": {"ru": "📦 <b>Последние заказы</b>", "en": "📦 <b>Recent orders</b>", "uz": "📦 <b>So'nggi buyurtmalar</b>"},
    "st_pending": {"ru": "в очереди", "en": "queued", "uz": "navbatda"},
    "st_processing": {"ru": "выполняется", "en": "processing", "uz": "bajarilmoqda"},
    "st_delivered": {"ru": "выполнен", "en": "completed", "uz": "bajarildi"},
    "st_manual": {"ru": "проверяется менеджером", "en": "under manager review", "uz": "menejer tekshirmoqda"},
    "st_refunded": {"ru": "возврат", "en": "refunded", "uz": "qaytarildi"},
    "promo_enter": {"ru": "🎟 Введи промокод:", "en": "🎟 Enter promo code:", "uz": "🎟 Promokodni kiriting:"},
    "promo_ok": {"ru": "🎉 Промокод активирован! +{amount}\n💰 Баланс: <b>{balance}</b>", "en": "🎉 Promo code activated! +{amount}\n💰 Balance: <b>{balance}</b>", "uz": "🎉 Promokod faollashtirildi! +{amount}\n💰 Balans: <b>{balance}</b>"},
    "support": {"ru": "🆘 <b>Поддержка</b>\n\nПо любым вопросам пиши: @{support}\nУкажи номер заказа, если вопрос по нему.", "en": "🆘 <b>Support</b>\n\nFor any questions: @{support}\nInclude your order number if relevant.", "uz": "🆘 <b>Yordam</b>\n\nHar qanday savol bo'yicha: @{support}\nBuyurtma bo'yicha bo'lsa, raqamini yozing."},
    "faq": {
        "ru": "ℹ️ <b>Как это работает</b>\n\n1️⃣ Пополни баланс через Click\n2️⃣ Выбери товар и укажи получателя (себя или друга)\n3️⃣ Подтверди — и звёзды придут автоматически\n\n<b>Почему дешевле, чем в Telegram?</b>\nМы покупаем напрямую через Fragment без комиссий App Store / Google Play.\n\n<b>Безопасно ли это?</b>\nДа. Мы не просим пароль или код — только @username получателя.\n\n<b>Нужен юзернейм?</b> Настройки Telegram → Имя пользователя.",
        "en": "ℹ️ <b>How it works</b>\n\n1️⃣ Top up your balance via Click\n2️⃣ Choose a product and the recipient (you or a friend)\n3️⃣ Confirm — stars arrive automatically\n\n<b>Why cheaper than in Telegram?</b>\nWe buy directly via Fragment without App Store / Google Play fees.\n\n<b>Is it safe?</b>\nYes. We never ask for a password or code — only the recipient's @username.\n\n<b>Need a username?</b> Telegram Settings → Username.",
        "uz": "ℹ️ <b>Bu qanday ishlaydi</b>\n\n1️⃣ Balansni Click orqali to'ldiring\n2️⃣ Mahsulot va qabul qiluvchini tanlang (o'zingiz yoki do'stingiz)\n3️⃣ Tasdiqlang — yulduzlar avtomatik keladi\n\n<b>Nega Telegram'dan arzon?</b>\nBiz App Store / Google Play komissiyasisiz to'g'ridan-to'g'ri Fragment orqali olamiz.\n\n<b>Xavfsizmi?</b>\nHa. Parol yoki kod so'ramaymiz — faqat qabul qiluvchining @username'i.\n\n<b>Username kerakmi?</b> Telegram sozlamalari → Foydalanuvchi nomi.",
    },
    "maintenance": {"ru": "🛠 Бот на техническом обслуживании. Попробуй через несколько минут.", "en": "🛠 The bot is under maintenance. Try again in a few minutes.", "uz": "🛠 Bot texnik xizmatda. Bir necha daqiqadan so'ng urinib ko'ring."},
    "banned": {"ru": "🚫 Доступ ограничен. Связь: @{support}", "en": "🚫 Access restricted. Contact: @{support}", "uz": "🚫 Kirish cheklangan. Aloqa: @{support}"},
    "slow_down": {"ru": "Не так быстро 🙂", "en": "Not so fast 🙂", "uz": "Shoshilmang 🙂"},
    "admin_balance_changed": {"ru": "🛠 Администратор изменил твой баланс: {sign}{amount}{comment}\n💰 Баланс: {balance}", "en": "🛠 An administrator changed your balance: {sign}{amount}{comment}\n💰 Balance: {balance}", "uz": "🛠 Administrator balansingizni o'zgartirdi: {sign}{amount}{comment}\n💰 Balans: {balance}"},
}


def norm(lang: str | None) -> str:
    return lang if lang in LANGS else DEFAULT


def t(lang: str | None, key: str, **kw) -> str:
    s = T[key].get(norm(lang)) or T[key][DEFAULT]
    return s.format(**kw) if kw else s


def labels(key: str) -> set[str]:
    """Все языковые варианты кнопки — для фильтров хендлеров."""
    return set(T[key].values())
