# Продакшн-деплой на VM — дизайн

Дата: 2026-10-08

## Мета

Запустити сайт (`oleg-webapp`), API, бота й Postgres на одній VM (Kamatera, Франкфурт, 1 vCPU, 2 ГБ RAM, 20 ГБ NVMe) під доменом `deliveryline.com.ua` з HTTPS.

## Схема

- На VM обидва репозиторії склоновані поруч: `~/oleg/oleg-back-services` і `~/oleg/oleg-webapp`.
- `oleg-back-services/docker-compose.prod.yml` (проєкт `oleg-prod`) збирає й запускає: `db`, `api`, `bot`, `web` (збірка з `../oleg-webapp`) і `caddy`.
- Назовні відкриті лише порти 80/443 (Caddy). `db`, `api`, `web` доступні тільки в Docker-мережі.
- Caddy: `{DOMAIN}` → `web:3000`, `www.{DOMAIN}` → 301 на `{DOMAIN}`. Сертифікати Let's Encrypt автоматично.
- Усі сервіси: `restart: unless-stopped`, логи `json-file` до 3 × 10 МБ.

## Сайт

- `next.config.mjs`: `output: "standalone"`.
- `Dockerfile`: збірка на `node:22-alpine` у три етапи, запуск `node server.js` від користувача `node`, порт 3000.
- `BACKEND_URL=http://api:8000` передається як build-arg (проксі `/media` вбудовується під час збірки) і як змінна середовища під час роботи. `BACKEND_API_KEY` = `API_KEY` бекенду.
- Під час збірки бекенд недоступний, тож сторінка пререндериться зі статичних даних `data/content.ts`; дані з API підтягуються під час роботи (ISR, 60 с).

## Бекенд

- `PUBLIC_BASE_URL=http://api:8000`: адреси фото збігаються з `BACKEND_URL` сайту, тож сайт перетворює їх на власний шлях `/media/...`.
- Пароль Postgres — `POSTGRES_PASSWORD` з `.env` (тільки букви й цифри, бо підставляється в URL).
- `.env` на VM додатково містить `DOMAIN` і `POSTGRES_PASSWORD`.

## Перевірка

Повний прод-стек піднімається локально з `DOMAIN=localhost` (Caddy видає локальний сертифікат): сайт через HTTPS, редирект з www, дані й фото з API, заявка доходить у канал, API не доступний ззовні.

## Поза обсягом

Автоматичні бекапи бази й фото поза VM, CI/CD, моніторинг.
