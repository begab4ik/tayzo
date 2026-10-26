# Деплой Tayzo на VDS (Ubuntu 24.04, 2 ГБ RAM)

Весь путь — минут 20. Делай по порядку, команды копируй как есть.

## Что должно быть на руках
- IP сервера, логин `root` и пароль (придут от ahost после оплаты)
- Домен (например `bot.tayzo.uz`). Если нет — купи на ahost, `.uz` или любой дешёвый
- Заполненный `tokens.env` на компьютере (см. `SETUP_TOKENS.md`)

---

## Шаг 1. Домен → IP сервера

В панели домена (ahost → Домены → DNS) создай **A-запись**:

| Тип | Имя | Значение |
|---|---|---|
| A | `bot` (или `@`, если домен целиком) | `IP_СЕРВЕРА` |

Проверка через 5–30 минут: на компьютере в cmd `nslookup bot.tayzo.uz` → должен показать IP сервера.
Пока DNS не разъехался, HTTPS не получится — не торопись с шагом 5.

## Шаг 2. Подключиться к серверу

Windows: открой **PowerShell** (или терминал Windows):
```
ssh root@IP_СЕРВЕРА
```
Первый раз спросит `Are you sure…?` → `yes`, потом пароль (при вводе не отображается — это нормально).

Сразу смени пароль на свой длинный:
```
passwd
```

## Шаг 3. Настроить сервер (один раз)

На сервере:
```bash
mkdir -p /opt/tayzo && cd /opt/tayzo
```
Потом **на компьютере** в PowerShell, из папки проекта `C:\Users\b.abduraxmonov\Desktop\tayzo`:
```powershell
scp -r .\* root@IP_СЕРВЕРА:/opt/tayzo/
scp .\tokens.env .\.env root@IP_СЕРВЕРА:/opt/tayzo/
```
(первая команда не копирует файлы с точкой в начале, поэтому вторая — отдельно).

Снова на сервере:
```bash
cd /opt/tayzo
bash deploy/server_setup.sh
```
Скрипт обновит систему, поставит Docker, включит swap 2 ГБ, файрвол (только 22/80/443) и fail2ban.
Займёт 3–5 минут. Если спросит про перезапуск сервисов — `Enter`.

## Шаг 4. Проверить настройки

```bash
cd /opt/tayzo
nano .env
```
Впиши свой домен в две строки:
```
DOMAIN=bot.tayzo.uz
WEBHOOK_HOST=https://bot.tayzo.uz
```
Сохранить: `Ctrl+O`, `Enter`, выйти: `Ctrl+X`.

`tokens.env` ты уже заполнил на компьютере — проверь, что он на месте: `cat tokens.env | head -5`.

## Шаг 5. Запуск

```bash
bash deploy/up.sh
```
Первый раз собирает образ ~2–3 минуты. В конце покажет таблицу — у всех четырёх сервисов должно быть `running`/`healthy`.

Логи бота:
```bash
docker compose logs -f bot
```
Ищи строку `Tayzo started as @tayzo_bot | click=True fragment=True`. Выход из логов — `Ctrl+C` (бот продолжит работать).

Проверка HTTPS (с компьютера, в браузере): `https://bot.tayzo.uz/health` → `{"ok":true}`.
Если «не защищено» / ошибка сертификата — DNS ещё не доехал, подожди и `docker compose restart caddy`.

Напиши боту `/start` — должен ответить. `/admin` — админка.

## Шаг 6. Подключить Click

В кабинете Click → Сервисы → ✏️ у сервиса 114312 → в **оба** поля:
```
https://bot.tayzo.uz/webhooks/click
```
Сохранить. Потом в боте: 💰 Баланс → Пополнить → 5 000 сум → оплатить. Через ~10 секунд бот напишет «Баланс пополнен».
Если нет — смотри `docker compose logs -f bot`: там будет строка `Click webhook: {...}` с ответом. Нет такой строки вообще → Click не достучался (DNS/URL/HTTPS).

## Шаг 7. Бэкапы базы (обязательно)

```bash
crontab -e
```
(первый раз спросит редактор — выбери `1` nano). Добавь строку в конец:
```
0 4 * * * cd /opt/tayzo && bash deploy/backup.sh >> /var/log/tayzo_backup.log 2>&1
```
`Ctrl+O`, `Enter`, `Ctrl+X`. Каждую ночь в 04:00 — копия базы в `/opt/tayzo/backups/`, хранятся 14 последних.

Раз в неделю скачивай бэкап на компьютер (PowerShell):
```powershell
scp root@IP_СЕРВЕРА:/opt/tayzo/backups/*.sql.gz C:\Users\b.abduraxmonov\Desktop\tayzo_backups\
```

---

## Повседневные команды (на сервере, из `/opt/tayzo`)

| Что | Команда |
|---|---|
| Логи бота | `docker compose logs -f bot` |
| Перезапустить бота | `docker compose restart bot` |
| Остановить всё | `docker compose down` |
| Запустить / обновить после правок кода | `bash deploy/up.sh` |
| Обновил tokens.env (новые cookies Fragment) | `docker compose up -d bot` |
| Статус | `docker compose ps` |
| Место на диске | `df -h /` и `docker system df` |
| Почистить старые образы | `docker image prune -f` |
| Бэкап сейчас | `bash deploy/backup.sh` |
| Восстановить | `bash deploy/restore.sh backups/файл.sql.gz` |
| Зайти в базу | `docker compose exec postgres psql -U tayzo` |

## Обновление кода

Поправил что-то на компьютере → скопировал → перезапустил:
```powershell
scp -r .\app root@IP_СЕРВЕРА:/opt/tayzo/
```
```bash
cd /opt/tayzo && bash deploy/up.sh
```

## Если что-то сломалось

- **Бот не отвечает** → `docker compose ps` — если `bot` не `running`, смотри `docker compose logs --tail=100 bot`, ошибка будет в конце.
- **`fragment=False` в логе при старте** → не все токены Fragment/TON заполнены, бот в ручном режиме. Проверь `tokens.env`.
- **Click не зачисляет** → `https://домен/health` открывается? URL в кабинете Click без опечаток? В логах есть `Click webhook`?
- **Заказы падают в ручную очередь** → в карточке заказа в админке текст ошибки. `401/обнови cookies` → перелогинься на Fragment и обнови 4 cookie в `tokens.env`, затем `docker compose up -d bot`.
- **Кончилось место** → `docker image prune -f`, удалить старые бэкапы.
- **Сервер перезагрузился** → всё поднимется само (`restart: unless-stopped`), ничего делать не надо.
