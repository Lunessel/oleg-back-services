# Деплой на VM

Сайт, API, бот і Postgres працюють на одній VM за Caddy (HTTPS). Конфігурація — `docker-compose.prod.yml` і `deploy/Caddyfile`.

Команди нижче — для Ubuntu 24.04/26.04, від користувача з `sudo`.

## 1. DNS

У панелі реєстратора домену створіть два A-записи на IP сервера:

| Ім'я | Тип | Значення |
|---|---|---|
| `@` (deliveryline.com.ua) | A | IP VM |
| `www` | A | IP VM |

Перевірка (з будь-якого комп'ютера): `nslookup deliveryline.com.ua` повертає IP VM. Поки DNS не оновився, Caddy не зможе отримати сертифікат.

## 2. Підготовка сервера (один раз)

```bash
# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # потім перезайдіть по SSH

# Swap 2 ГБ: запас пам'яті для збірки сайту
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Фаєрвол: лише SSH і веб
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443
sudo ufw --force enable
```

## 3. Код і налаштування

Обидва репозиторії мають лежати поруч в одній папці:

```bash
mkdir -p ~/oleg && cd ~/oleg
git clone https://github.com/Lunessel/oleg-back-services.git
git clone https://github.com/Lunessel/oleg-landing.git oleg-webapp
cd oleg-back-services
cp .env.example .env
nano .env
```

У `.env` заповніть:

| Змінна | Значення |
|---|---|
| `BOT_TOKEN` | токен бота |
| `LEADS_CHAT_ID` | id каналу для заявок |
| `ADMIN_IDS` | Telegram id адмінів через кому |
| `API_KEY` | довгий випадковий рядок: `openssl rand -hex 32` |
| `DOMAIN` | `deliveryline.com.ua` |
| `POSTGRES_PASSWORD` | лише букви й цифри: `openssl rand -hex 24` |
| `CONTACT_PHONE` | телефон для бота |

`PUBLIC_BASE_URL` і `DATABASE_URL` для продакшну задає `docker-compose.prod.yml`, їх можна не чіпати.

## 4. Запуск

```bash
cd ~/oleg/oleg-back-services
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

Перша збірка займає кілька хвилин. Усі сервіси мають бути `Up` (`db` і `api` — `healthy`). Відкрийте `https://deliveryline.com.ua`.

Послуги й тарифи з бази з'являються на сайті протягом хвилини після запуску: під час збірки бекенд недоступний, тож спершу сайт показує вбудовані дані.

## Оновлення після змін у коді

```bash
cd ~/oleg/oleg-webapp && git pull
cd ~/oleg/oleg-back-services && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker image prune -f   # прибрати старі образи
```

## Корисне

```bash
# Логи
docker compose -f docker-compose.prod.yml logs -f bot
docker compose -f docker-compose.prod.yml logs --tail 100 caddy

# Зупинити все (дані лишаються у volume; НЕ додавайте -v — це видалить базу й фото)
docker compose -f docker-compose.prod.yml down

# Ручний дамп бази
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U oleg oleg > backup-$(date +%F).sql
```

Одночасно може працювати лише один екземпляр бота з цим токеном: перед запуском на VM зупиніть бота локально (`docker compose stop bot`).
