# oleg-back-services

Бекенд лендінгу вантажних перевезень: Telegram-бот (aiogram), HTTP API (FastAPI) і Postgres.

## Запуск

1. Скопіюйте `.env.example` у `.env` і заповніть:
   - `BOT_TOKEN` — токен від @BotFather;
   - `LEADS_CHAT_ID` — id каналу для заявок (бот має бути адміністратором каналу);
   - `ADMIN_IDS` — Telegram id адмінів через кому;
   - `API_KEY` — довільний секрет; той самий вказується на сайті як `BACKEND_API_KEY`;
   - `PUBLIC_BASE_URL` — адреса, за якою API бачить сайт (локально `http://localhost:8000`).
2. `docker compose up -d --build`

API: `http://localhost:8000` (`/health`, `/api/services`, `/api/pricing`, `/api/leads`, `/media/...`).
Міграції застосовує сервіс `api` під час старту. Postgres доступний з хоста на `127.0.0.1:5434`.

## Тести

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
docker compose up -d db
.venv/Scripts/python -m pytest -q
```

Тести працюють на базі `oleg_test`, Telegram у них не викликається.

## Бот

- `/start` — меню. «Залишити заявку» запускає опитування; заявка зберігається в базі та надсилається в канал.
- «Адмін-панель» (лише для `ADMIN_IDS`): види перевезень (додати, змінити фото / назву / пункти, порядок, видалити) і значення тарифів.
- «Скасувати» або `/cancel` перериває будь-який діалог.
