# Wing Zone Telegram Bot

Редакционный бот для Telegram-канала `где-то в зоне крыла`: собирает новости F1/NASCAR из RSS, дедуплицирует их, делает пост в голосе канала и отправляет в ревью-чат. По умолчанию бот ничего не публикует сам: сначала присылает черновик с кнопками `Publish` / `Drop`.

## Что умеет

- RSS/Atom ingestion для новостей и будущих live-источников.
- SQLite-хранилище для seen items и черновиков.
- Ручной approval через Telegram-команды и inline-кнопки.
- Опциональный OpenAI Responses API для генерации постов.
- Template fallback, если `OPENAI_API_KEY` не задан.
- Docker/Docker Compose и базовый GitHub Actions CI.

## Быстрый старт

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Заполни `.env`:

- `TELEGRAM_BOT_TOKEN` - токен от BotFather.
- `TELEGRAM_CHANNEL_ID` - `@username` канала или numeric chat id.
- `TELEGRAM_REVIEW_CHAT_ID` - личка/группа, куда бот отправляет черновики.
- `ADMIN_USER_IDS` - Telegram user id людей, которым можно публиковать.
- `OPENAI_API_KEY` - опционально, без него будет шаблонный режим.
- `NEWS_FEEDS` - RSS/Atom источники через запятую; Formula1.com RSS иногда отвечает 403, поэтому не стоит полагаться на него как на единственный источник.

Инициализация базы:

```powershell
python -m wingzone_bot.cli init-db
```

Проверить сбор новостей без отправки в Telegram:

```powershell
python -m wingzone_bot.cli once --dry-run
```

Запуск воркера:

```powershell
python -m wingzone_bot.cli worker
```

## Docker

```bash
cp .env.example .env
docker compose up --build -d
```

SQLite будет лежать в `./data`.

## Telegram setup

1. Создай бота через BotFather.
2. Добавь бота админом в канал с правом публиковать сообщения.
3. Напиши боту в личку или добавь его в закрытый review group.
4. Узнай свой Telegram user id и добавь его в `ADMIN_USER_IDS`.
5. Узнай `TELEGRAM_REVIEW_CHAT_ID`. Самый простой путь: временно запустить worker, написать боту `/ping`, посмотреть лог апдейта или добавить маленький debug print.

## Команды

- `/ping` - проверка, что бот жив.
- `/help` - список команд.
- `/once` - вручную собрать новости и отправить новые черновики в ревью.
- `/draft <заметка>` - сделать черновик из ручной live-заметки.
- `/drafts` - последние черновики.
- `/post <id>` - опубликовать черновик.
- `/drop <id>` - отклонить черновик.

## Редакционный режим

По умолчанию:

```env
AUTO_PUBLISH=false
ALLOW_PROFANITY=false
VOICE_INTENSITY=3
```

Главная настройка голоса - не мат, а ироничный саркастический юмор. `ALLOW_PROFANITY=true` можно включить отдельно, но это скорее редкая специя для совсем нервных моментов, а не основной стиль. Промпт просит писать живо, смешно и колко, но без травли, выдуманных фактов и токсичного наезда на людей.

## Будущие расширения

- Live race mode: отдельный источник событий/тайминга, не только RSS.
- Meme queue: папка/таблица с мемами, которые бот предлагает к новости; Telegram-клиент уже умеет отправлять фото.
- Two-person voice: разные режимы под тебя и друга.
- NASCAR lane: отдельные источники, теги и тон.
- Admin web panel: посмотреть черновики, править текст перед публикацией.

## GitHub

Этот каталог уже готов как отдельный репозиторий. Следующий шаг: дать URL существующего GitHub repo или имя нового repo, например `wing-zone-telegram-bot`, и можно будет залить туда проект.
