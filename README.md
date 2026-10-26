# Tayzo — бот продажи Telegram Stars и Premium

Telegram-бот: баланс в сумах, пополнение через **Click**, покупка **Stars / Premium** через **Fragment**
(оплата с TON-кошелька), обязательная подписка на канал, рефералы, промокоды, админка со статистикой.

## Что умеет

**Пользователь**
- ⭐ Купить Stars себе или другу по @username (проверка получателя через Fragment, показывает имя)
- 💎 Premium на 3/6/12 мес
- 💰 Баланс, пополнение через Click (пресеты + своя сумма), история операций
- 👤 Профиль, реферальная ссылка (% от пополнений друзей), мои заказы
- 🎟 Промокоды
- 🔒 Обязательная подписка на канал(ы) проекта с кнопкой «Проверить»

**Админ** (`/admin`)
- 📊 Статистика: звёзд продано, выручка, себестоимость, **прибыль и маржа**, пополнения, новые юзеры, топ покупателей — за сегодня / 7д / 30д / всё время (`/stats`)
- 📦 Очередь проблемных заказов: повторить / выполнено вручную / вернуть деньги
- 👥 Поиск юзера, начисление/списание, бан
- ⚙️ Настройки на лету: наценка, курс TON, лимиты, реферальный %, техработы, вкл/выкл товаров
- 📢 Управление каналами обязательной подписки
- 📣 Рассылка
- 💎 Баланс TON-кошелька, алерт при низком балансе, ежедневный отчёт в 09:00

## Структура

```
app/
├── main.py              # запуск: бот + HTTP API + воркеры в одном процессе
├── config.py            # .env
├── db/models.py         # users, ledger, payments, orders, promo, settings, channels, audit
├── core/
│   ├── wallet.py        # баланс = ledger; единственное место, где меняются деньги
│   ├── orders.py        # жизненный цикл заказа
│   ├── pricing.py       # цена = себестоимость TON × курс × (1+наценка)
│   ├── stats.py         # статистика
│   ├── settings_store.py# настройки из админки (БД + Redis кэш)
│   ├── referrals.py, promo.py
├── providers/
│   ├── base.py          # интерфейс Provider — сюда потом добавятся накрутка/подарки
│   ├── fragment.py      # Stars + Premium через fragment.com
│   ├── ton_wallet.py    # отправка TON-транзакций
│   └── registry.py      # product -> provider, ручной режим
├── payments/click.py    # Click SHOP-API: подпись, Prepare/Complete, идемпотентность
├── api/app.py           # FastAPI: /webhooks/click, /health
├── workers/             # доставка заказов, курс TON, алерты, отчёт
└── bot/                 # aiogram 3: handlers, keyboards, middlewares, texts
```

## Запуск

### 1. Подготовка
- `tokens.env` — **все токены и секреты** (бот, Click, Fragment, TON). Откуда их брать — пошагово в **`SETUP_TOKENS.md`**.
- `.env` — обычные настройки (уже создан, менять по необходимости).
```bash
python -m scripts.check_setup          # проверит каждый токен и скажет, что не так
python -m scripts.check_setup --buy 50 @me   # тестовая покупка 50 ⭐ (реально спишет TON)
```

### 2. Docker (рекомендуется)
```bash
docker compose up -d --build
docker compose logs -f bot
```

### 3. Без Docker
```bash
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt
# нужны запущенные PostgreSQL и Redis (см. DATABASE_URL / REDIS_URL)
python -m app.main
```
Таблицы создаются автоматически при первом запуске. Для миграций в проде:
```bash
alembic revision --autogenerate -m "init" && alembic upgrade head
```

## Настройка Click
1. В кабинете Click Business создай сервис, получи `SERVICE_ID`, `MERCHANT_ID`, `MERCHANT_USER_ID`, `SECRET_KEY`.
2. Укажи **Prepare URL** и **Complete URL**: `https://<твой-домен>/webhooks/click` (оба одинаковые).
3. Нужен HTTPS — поставь перед ботом Caddy или nginx + certbot, проксируй на `:8080`.
4. Проверка: `curl https://<домен>/health` → `{"ok":true}`.

## Настройка Fragment + TON
1. Зайди на fragment.com, войди через Telegram, подключи TON-кошелёк (Tonkeeper/MyTonWallet), пройди KYC.
2. DevTools → Application → Cookies → fragment.com → скопируй `stel_ssid`, `stel_token`, `stel_dt`, `stel_ton_token` в `.env`.
3. `TON_MNEMONIC` — сид того же кошелька, что подключён к Fragment. `TON_WALLET_VERSION` — v5r1 (Tonkeeper) или v4r2.
4. Держи на кошельке оборотные средства + ~0.3 TON на комиссии.
5. Cookies живут ограниченно — при 401 бот переведёт заказы в ручную очередь и напишет админу. Обнови cookies и перезапусти.

**Пока Fragment не настроен** (или `MANUAL_FULFILLMENT=true`) бот работает в ручном режиме: деньги списываются,
заказ падает админу с кнопками «Выполнено вручную / Вернуть». Так можно запуститься в первый день без TON.

> ⚠️ У Fragment нет официального API — используется внутренний API сайта. Перед продом сделай 1–2 тестовые
> покупки на 50 звёзд и проверь, что поля ответов совпадают с кодом в `providers/fragment.py`.

## Ценообразование
`цена = себестоимость_TON × курс_TON_UZS × (1 + наценка%)`, округление вверх до 100 сум.
- Курс TON обновляется каждые 10 мин (CoinGecko × ЦБ РУз), себестоимость звезды — раз в час с Fragment.
- Всё можно переопределить в ⚙️ Настройках, включая фиксированную цену звезды в сумах.
- В каждом заказе сохраняется `cost_uzs` на момент покупки → статистика показывает реальную прибыль.

## Как добавить новый товар (накрутка, подарки)
1. Реализуй `Provider` из `providers/base.py` (`resolve_recipient`, `fulfill`).
2. Добавь `ProductType` в `core/enums.py`, зарегистрируй в `providers/registry.py`.
3. Добавь расчёт цены в `core/pricing.py` и хендлер в `bot/handlers/`.
Кошелёк, заказы, статистика, возвраты — уже работают для любого товара.

## Безопасность
- `.env` никогда не коммитить. Сид-фраза даёт полный доступ к кошельку.
- Все вебхуки Click проверяются по подписи и идемпотентны (`click_trans_id` уникален).
- Баланс меняется только через `core/wallet.py` с блокировкой строки — двойное списание невозможно.
- Бэкап Postgres: `docker compose exec postgres pg_dump -U tayzo tayzo > backup.sql` (поставь в cron).
