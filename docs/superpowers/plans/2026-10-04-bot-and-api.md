# Telegram Bot and API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend for the cargo-van landing page: an aiogram bot that takes orders and lets admins edit site content, a FastAPI service the site reads content from and posts leads to, and Postgres behind both.

**Architecture:** One Python package `app` with a shared DB and service layer. Two processes run from it: `api` (FastAPI) and `bot` (aiogram long polling). Both call `app/services` directly; the bot never calls the API over HTTP. `docker compose` runs `db`, `api`, `bot`.

**Tech Stack:** Python 3.12 (Docker image; local venv may be 3.13), aiogram 3, FastAPI, SQLAlchemy 2 async + asyncpg, Alembic, pydantic-settings, pytest + pytest-asyncio + httpx, Postgres 16, pip.

**Spec:** `docs/superpowers/specs/2026-10-04-bot-and-api-design.md`

## Global Constraints

- Backend repo: `D:\Workspace\nextjs\OLEG\oleg-back-services` (remote `https://github.com/Lunessel/oleg-back-services.git`, branch `main`). All paths in Tasks 1–10 and 12 are relative to it.
- Site repo: `D:\Workspace\nextjs\OLEG\oleg-webapp`. Only Task 11 touches it. **Never commit in `oleg-webapp`** — it has unrelated uncommitted work.
- Commit messages: a single line `feat: …` / `fix: …` / `chore: …` / `test: …` / `docs: …`. No body, no trailers, no co-author line. Push to `origin main` after each commit.
- All user-facing bot and API texts are Ukrainian, copied verbatim from this plan.
- Channel messages use HTML parse mode; every user-supplied value is passed through `html.escape`. Bot replies to users use no parse mode.
- Phone rule (same as the site): after stripping everything except digits and `+`, the number must match `^(\+380|0)\d{9}$`. A bare `380XXXXXXXXX` (Telegram contact format) is accepted and stored as `+380XXXXXXXXX`.
- Tests run against Postgres database `oleg_test` on `localhost:5433` (the compose `db` service). Telegram is never called in tests.
- Run tests with `.venv/Scripts/python -m pytest -q` (Windows venv).
- Never commit `.env`.

## File Structure

```
requirements.txt  requirements-dev.txt  pytest.ini  .gitignore  .dockerignore  .env.example
Dockerfile  docker-compose.yml  docker/initdb/01-test-db.sql
alembic.ini  alembic/env.py  alembic/script.py.mako  alembic/versions/0001_initial.py
app/
  config.py                 Settings + get_settings()
  db/base.py                Base
  db/models.py              Service, TariffRow, Lead
  db/seed.py                SEED_SERVICES, SEED_TARIFF_ROWS (used by migration and tests)
  services/phone.py         normalize_phone
  services/leads.py         format_lead, submit_lead, LeadDeliveryError
  services/telegram.py      make_channel_sender
  services/catalog.py       services CRUD + ordering, parse_items
  services/tariffs.py       CARDS, get_cards, get_row, update_value
  services/media.py         image naming, paths, deletion, public URL
  api/main.py               create_app, lifespan, /health, /media
  api/deps.py               get_session, get_sender, require_api_key
  api/schemas.py            request/response models
  api/routes.py             /api/services, /api/pricing, /api/leads
  bot/main.py               Dispatcher wiring, polling
  bot/filters.py            IsAdmin
  bot/states.py             OrderForm, AdminService, AdminTariff
  bot/keyboards.py          reply keyboards + button texts
  bot/admin_kb.py           callback factories + inline keyboards
  bot/handlers/start.py     /start, cancel
  bot/handlers/order.py     order flow
  bot/handlers/admin_services.py
  bot/handlers/admin_tariffs.py
tests/
  conftest.py  test_config.py  test_health.py  test_phone.py  test_leads.py
  test_catalog.py  test_tariffs.py  test_media.py  test_api.py  test_bot_helpers.py
```

Every `app/**` and `tests` directory that holds modules gets an empty `__init__.py` (`app/`, `app/db/`, `app/services/`, `app/api/`, `app/bot/`, `app/bot/handlers/`, `tests/`). Create each one in the task that first adds a file to that directory.

---

### Task 1: Project scaffold, database, migration with seed data

**Files:**
- Create: `.gitignore`, `.dockerignore`, `.env.example`, `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `Dockerfile`, `docker-compose.yml`, `docker/initdb/01-test-db.sql`, `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/0001_initial.py`
- Create: `app/__init__.py`, `app/config.py`, `app/db/__init__.py`, `app/db/base.py`, `app/db/models.py`, `app/db/seed.py`, `app/api/__init__.py`, `app/api/main.py`
- Test: `tests/__init__.py`, `tests/conftest.py`, `tests/test_config.py`, `tests/test_health.py`

**Interfaces:**
- Produces:
  - `app.config.Settings` with fields `bot_token: str`, `leads_chat_id: int`, `admin_ids: list[int]`, `database_url: str`, `api_key: str`, `public_base_url: str`, `media_dir: Path`, `tz: str`, `contact_phone: str`; `app.config.get_settings() -> Settings` (cached).
  - `app.db.base.Base`; models `Service(id, title, items: list[str], image, position)`, `TariffRow(key, card, label, value, position)`, `Lead(id, source, name, phone, payload: dict, created_at, sent_at)`.
  - `app.db.seed.SEED_SERVICES: list[dict]` (keys `title`, `items`, `image`), `SEED_TARIFF_ROWS: list[dict]` (keys `key`, `card`, `label`, `value`, `position`).
  - `app.api.main.create_app() -> FastAPI`, module-level `app`.
  - Test fixtures: `session` (AsyncSession on a freshly created schema), `sender` (`FakeSender` with `.messages: list[str]`, `.fail: bool`).

- [ ] **Step 1: Write dependency and tooling files**

`requirements.txt`:

```
aiogram>=3.13,<4
fastapi>=0.115
uvicorn[standard]>=0.30
sqlalchemy[asyncio]>=2.0.35,<2.1
asyncpg>=0.30
alembic>=1.13
pydantic-settings>=2.7
tzdata
```

`requirements-dev.txt`:

```
-r requirements.txt
pytest>=8
pytest-asyncio>=0.24
httpx>=0.27
```

`pytest.ini`:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

`.gitignore`:

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.env
media/
```

`.dockerignore`:

```
.venv
.git
__pycache__
.pytest_cache
.env
media
tests
docs
```

`.env.example`:

```
BOT_TOKEN=
LEADS_CHAT_ID=
ADMIN_IDS=
API_KEY=
PUBLIC_BASE_URL=http://localhost:8000
CONTACT_PHONE=+38 (097) 011-33-61
# Used only when running outside docker compose (compose overrides it):
DATABASE_URL=postgresql+asyncpg://oleg:oleg@localhost:5433/oleg
```

- [ ] **Step 2: Write Docker files**

`Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic alembic
COPY app app
```

`docker/initdb/01-test-db.sql`:

```sql
CREATE DATABASE oleg_test;
```

`docker-compose.yml`:

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: oleg
      POSTGRES_PASSWORD: oleg
      POSTGRES_DB: oleg
    ports:
      - "127.0.0.1:5433:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./docker/initdb:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U oleg -d oleg"]
      interval: 3s
      timeout: 3s
      retries: 20

  api:
    build: .
    command: sh -c "alembic upgrade head && uvicorn app.api.main:app --host 0.0.0.0 --port 8000"
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://oleg:oleg@db:5432/oleg
      MEDIA_DIR: /app/media
    ports:
      - "8000:8000"
    volumes:
      - media:/app/media
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 5s
      timeout: 3s
      retries: 20
    restart: unless-stopped

  bot:
    build: .
    command: python -m app.bot.main
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://oleg:oleg@db:5432/oleg
      MEDIA_DIR: /app/media
    volumes:
      - media:/app/media
    depends_on:
      api:
        condition: service_healthy
    restart: unless-stopped

volumes:
  pgdata:
  media:
```

The bot waits for a healthy `api` because `api` is the service that runs migrations.

- [ ] **Step 3: Create the venv and start Postgres**

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
docker compose up -d db
```

Expected: install succeeds; `docker compose ps` shows `db` as `healthy`.

- [ ] **Step 4: Write the failing tests**

`tests/__init__.py`: empty. `app/__init__.py`, `app/db/__init__.py`, `app/api/__init__.py`: empty.

`tests/conftest.py`:

```python
import os
import tempfile

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://oleg:oleg@localhost:5433/oleg_test"
)

# Settings are read from the environment; set them before any app import.
os.environ.update(
    BOT_TOKEN="123456:TEST",
    LEADS_CHAT_ID="-1001",
    ADMIN_IDS="11, 22",
    DATABASE_URL=TEST_DATABASE_URL,
    API_KEY="test-key",
    PUBLIC_BASE_URL="http://backend.test",
    MEDIA_DIR=tempfile.mkdtemp(prefix="oleg-media-"),
)

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import models  # noqa: F401  (registers tables on Base.metadata)
from app.db.base import Base


class FakeSender:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.fail = False

    async def __call__(self, text: str) -> None:
        if self.fail:
            raise RuntimeError("telegram down")
        self.messages.append(text)


@pytest.fixture
def sender() -> FakeSender:
    return FakeSender()


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()
```

`tests/test_config.py`:

```python
from app.config import Settings, get_settings


def test_admin_ids_parsed_from_comma_separated_string():
    assert get_settings().admin_ids == [11, 22]


def test_admin_ids_empty_string_gives_empty_list(monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "")
    assert Settings().admin_ids == []


def test_leads_chat_id_is_int():
    assert get_settings().leads_chat_id == -1001
```

`tests/test_health.py`:

```python
from httpx import ASGITransport, AsyncClient

from app.api.main import create_app


async def test_health():
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_models_create_tables(session):
    from sqlalchemy import text

    result = await session.execute(
        text("select table_name from information_schema.tables where table_schema = 'public'")
    )
    assert {"services", "tariff_rows", "leads"} <= {row[0] for row in result}
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest -q`
Expected: collection error, `ModuleNotFoundError: No module named 'app.db.base'` (or `app.config`).

- [ ] **Step 6: Write config, models, seed data and the app factory**

`app/config.py`:

```python
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    leads_chat_id: int
    admin_ids: Annotated[list[int], NoDecode] = []
    database_url: str
    api_key: str
    public_base_url: str = "http://localhost:8000"
    media_dir: Path = Path("media")
    tz: str = "Europe/Kyiv"
    contact_phone: str = "+38 (097) 011-33-61"

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _split_admin_ids(cls, value):
        if isinstance(value, str):
            return [int(part) for part in value.split(",") if part.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`app/db/base.py`:

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

`app/db/models.py`:

```python
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    items: Mapped[list[str]] = mapped_column(JSON)
    image: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, index=True)


class TariffRow(Base):
    __tablename__ = "tariff_rows"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    card: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    value: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

`app/db/seed.py` (values copied from `oleg-webapp/data/content.ts`):

```python
SEED_SERVICES = [
    {
        "title": "Квартирні та офісні переїзди",
        "items": [
            "Комплексний переїзд під ключ",
            "Пакування речей",
            "Розбирання та збирання меблів",
        ],
        "image": "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?q=80&w=800&auto=format&fit=crop",
    },
    {
        "title": "Доставка меблів, побутової техніки",
        "items": [
            "Доставка диванів і шаф",
            "Холодильники, пральні машини, посудомийки",
            "обслуговування магазинів, кав'ярень, салонів та клінік",
        ],
        "image": "https://images.unsplash.com/photo-1558997519-83ea9252edf8?q=80&w=800&auto=format&fit=crop",
    },
    {
        "title": "Доставка будівельних матеріалів",
        "items": [
            "Доставка з будівельних гіпермаркетів і складів",
            "Профілі, дошки, мішки, металочерепиці",
            "Сухі суміші та сипучі матеріали до 2 тонн",
        ],
        "image": "https://images.unsplash.com/photo-1541976590-713941681591?q=80&w=800&auto=format&fit=crop",
    },
    {
        "title": "Вивіз побутового та будівельного сміття",
        "items": [
            "Утилізація будівельних відходів",
            "Утилізація та демонтаж старих меблів та техніки",
            "Утилізація органічних відходів",
        ],
        "image": "https://images.unsplash.com/photo-1786252591948-3c1f1e7d0512?q=80&w=800&auto=format&fit=crop",
    },
    {
        "title": "Послуги вантажників та текалажних робіт",
        "items": [
            "Розвантаження та завантаження меблів, техніки та будматеріалів",
            "Підйом і спуск вантажів",
            "Монтаж і демонтаж обладнання",
        ],
        "image": "https://images.unsplash.com/photo-1657490016235-8246d81064d2?q=80&w=1074&auto=format&fit=crop&ixlib=rb-4.1.0&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D",
    },
]

SEED_TARIFF_ROWS = [
    {"key": "city.min_order", "card": "city", "label": "Мінімальне замовлення (2 год)", "value": "від 800 грн", "position": 0},
    {"key": "city.next_hour", "card": "city", "label": "Кожна наступна година", "value": "від 350 грн/год", "position": 1},
    {"key": "intercity.per_km", "card": "intercity", "label": "Вартість за кілометр", "value": "від 18 грн/км", "position": 0},
    {"key": "intercity.calculation", "card": "intercity", "label": "Розрахунок", "value": "в обидва боки або в один бік", "position": 1},
    {"key": "loaders.one_loader", "card": "loaders", "label": "1 вантажник (мін. 2 год)", "value": "від 250 грн/год", "position": 0},
    {"key": "loaders.stairs", "card": "loaders", "label": "Підйом/спуск без ліфта", "value": "від 60 грн/поверх", "position": 1},
]
```

`app/api/main.py` (routes and lifespan resources are added in Task 7):

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    settings.media_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="oleg-back-services")
    app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest -q`
Expected: `5 passed`.

- [ ] **Step 8: Write Alembic config and the initial migration**

`alembic.ini`:

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
```

`alembic/env.py`:

```python
import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import models  # noqa: F401
from app.db.base import Base

target_metadata = Base.metadata


def run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def main() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.connect() as connection:
        await connection.run_sync(run_migrations)
    await engine.dispose()


asyncio.run(main())
```

`alembic/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""
import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

`alembic/versions/0001_initial.py`:

```python
"""initial schema and seed data

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

from app.db.seed import SEED_SERVICES, SEED_TARIFF_ROWS

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    services = op.create_table(
        "services",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("items", sa.JSON, nullable=False),
        sa.Column("image", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
    )
    op.create_index("ix_services_position", "services", ["position"])

    tariff_rows = op.create_table(
        "tariff_rows",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("card", sa.Text, nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
    )

    op.create_table(
        "leads",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=True),
        sa.Column("phone", sa.Text, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.bulk_insert(services, [{**row, "position": index} for index, row in enumerate(SEED_SERVICES)])
    op.bulk_insert(tariff_rows, SEED_TARIFF_ROWS)


def downgrade() -> None:
    op.drop_table("leads")
    op.drop_table("tariff_rows")
    op.drop_index("ix_services_position", table_name="services")
    op.drop_table("services")
```

- [ ] **Step 9: Verify the migration against the real database**

```bash
DATABASE_URL=postgresql+asyncpg://oleg:oleg@localhost:5433/oleg .venv/Scripts/python -m alembic upgrade head
docker compose exec db psql -U oleg -d oleg -c "select count(*) from services" -c "select count(*) from tariff_rows"
```

Expected: migration runs without error; counts are `5` and `6`.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat: scaffold project with database schema and seed data"
git push origin main
```

---

### Task 2: Phone normalization and lead message formatting

**Files:**
- Create: `app/services/__init__.py`, `app/services/phone.py`, `app/services/leads.py`
- Test: `tests/test_phone.py`, `tests/test_leads.py`

**Interfaces:**
- Produces:
  - `app.services.phone.normalize_phone(raw: str) -> str | None` — normalized number or `None` if invalid.
  - `app.services.leads.format_lead(source: str, payload: dict) -> str` — HTML text for the channel.
  - Payload keys per source — `hero`: `from`, `to`, `phone`; `calculator`: `name`, `phone`, `serviceType`, `vanSize`, `loaders`, `route`; `callback` / `services_consult`: `name`, `phone`; `bot`: `name`, `service`, `helpers_count` (int, `0` = none), `address_from`, `address_to`, `date`, `time`, `phone`, `username` (str or `None`).

- [ ] **Step 1: Write the failing tests**

`tests/test_phone.py`:

```python
import pytest

from app.services.phone import normalize_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+38 (067) 123-45-67", "+380671234567"),
        ("+380671234567", "+380671234567"),
        ("0671234567", "0671234567"),
        ("380671234567", "+380671234567"),
        ("067 123 45 67", "0671234567"),
    ],
)
def test_valid_numbers(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "12345", "+38067123456", "+3806712345678", "hello", "+1 202 555 0100"])
def test_invalid_numbers(raw):
    assert normalize_phone(raw) is None
```

`tests/test_leads.py`:

```python
from app.services.leads import format_lead


def test_format_hero():
    text = format_lead("hero", {"from": "Львів", "to": "Київ", "phone": "+380671234567"})
    assert text == "<b>Заявка з головної форми</b>\nЗвідки: Львів\nКуди: Київ\nТелефон: +380671234567"


def test_format_calculator_maps_enum_values():
    text = format_lead(
        "calculator",
        {
            "name": "Олег",
            "phone": "0671234567",
            "serviceType": "intercity",
            "vanSize": "maxi",
            "loaders": "two",
            "route": "Львів — Одеса",
        },
    )
    assert text == (
        "<b>Заявка з калькулятора вартості</b>\n"
        "Ім'я: Олег\n"
        "Телефон: 0671234567\n"
        "Тип: Міжмісто\n"
        "Розмір буса: Maxi\n"
        "Вантажники: 2 вантажники\n"
        "Маршрут: Львів — Одеса"
    )


def test_format_callback_and_consult():
    payload = {"name": "Ira", "phone": "0671234567"}
    assert format_lead("callback", payload) == "<b>Замовлення дзвінка</b>\nІм'я: Ira\nТелефон: 0671234567"
    assert format_lead("services_consult", payload) == (
        "<b>Консультація щодо вантажу</b>\nІм'я: Ira\nТелефон: 0671234567"
    )


BOT_PAYLOAD = {
    "name": "Олег",
    "service": "Квартирні та офісні переїзди",
    "helpers_count": 2,
    "address_from": "вул. Зелена, 1",
    "address_to": "вул. Наукова, 7",
    "date": "05-10-2026",
    "time": "10:00",
    "phone": "+380671234567",
    "username": "oleg",
}


def test_format_bot_with_helpers_and_username():
    assert format_lead("bot", BOT_PAYLOAD) == (
        "<b>Заявка з Telegram-бота</b>\n"
        "Ім'я: Олег\n"
        "Послуга: Квартирні та офісні переїзди\n"
        "Вантажники: Так, кількість — 2\n"
        "Звідки: вул. Зелена, 1\n"
        "Куди: вул. Наукова, 7\n"
        "Дата: 05-10-2026\n"
        "Час: 10:00\n"
        "Телефон: +380671234567\n"
        "Telegram: @oleg"
    )


def test_format_bot_without_helpers_or_username():
    text = format_lead("bot", {**BOT_PAYLOAD, "helpers_count": 0, "username": None})
    assert "Вантажники: Ні" in text
    assert "Telegram:" not in text


def test_format_escapes_html_in_user_values():
    text = format_lead("callback", {"name": "<b>x</b> & y", "phone": "0671234567"})
    assert "Ім'я: &lt;b&gt;x&lt;/b&gt; &amp; y" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_phone.py tests/test_leads.py -q`
Expected: `ModuleNotFoundError: No module named 'app.services'`.

- [ ] **Step 3: Write the implementation**

`app/services/__init__.py`: empty.

`app/services/phone.py`:

```python
import re

_PHONE_RE = re.compile(r"^(\+380|0)\d{9}$")


def normalize_phone(raw: str) -> str | None:
    """Return the number as +380XXXXXXXXX / 0XXXXXXXXX, or None if it is not a valid UA number."""
    cleaned = re.sub(r"[^\d+]", "", raw)
    if cleaned.startswith("380"):
        cleaned = "+" + cleaned
    return cleaned if _PHONE_RE.match(cleaned) else None
```

`app/services/leads.py`:

```python
import html

SOURCE_LABELS = {
    "hero": "Заявка з головної форми",
    "calculator": "Заявка з калькулятора вартості",
    "callback": "Замовлення дзвінка",
    "services_consult": "Консультація щодо вантажу",
    "bot": "Заявка з Telegram-бота",
}

SERVICE_TYPE_LABELS = {"city": "По місту", "intercity": "Міжмісто"}
VAN_SIZE_LABELS = {"small": "Малий", "medium": "Середній", "maxi": "Maxi"}
LOADERS_LABELS = {
    "none": "Без вантажників",
    "one": "1 вантажник",
    "two": "2 вантажники",
    "more": "3+ вантажники",
}


def _e(value: object) -> str:
    return html.escape(str(value))


def format_lead(source: str, payload: dict) -> str:
    lines = [f"<b>{SOURCE_LABELS[source]}</b>"]

    if source == "hero":
        lines += [
            f"Звідки: {_e(payload['from'])}",
            f"Куди: {_e(payload['to'])}",
            f"Телефон: {_e(payload['phone'])}",
        ]
    elif source == "calculator":
        lines += [
            f"Ім'я: {_e(payload['name'])}",
            f"Телефон: {_e(payload['phone'])}",
            f"Тип: {SERVICE_TYPE_LABELS[payload['serviceType']]}",
            f"Розмір буса: {VAN_SIZE_LABELS[payload['vanSize']]}",
            f"Вантажники: {LOADERS_LABELS[payload['loaders']]}",
            f"Маршрут: {_e(payload['route'])}",
        ]
    elif source == "bot":
        count = payload.get("helpers_count") or 0
        helpers = f"Так, кількість — {count}" if count else "Ні"
        lines += [
            f"Ім'я: {_e(payload['name'])}",
            f"Послуга: {_e(payload['service'])}",
            f"Вантажники: {helpers}",
            f"Звідки: {_e(payload['address_from'])}",
            f"Куди: {_e(payload['address_to'])}",
            f"Дата: {_e(payload['date'])}",
            f"Час: {_e(payload['time'])}",
            f"Телефон: {_e(payload['phone'])}",
        ]
        if payload.get("username"):
            lines.append(f"Telegram: @{_e(payload['username'])}")
    else:  # callback, services_consult
        lines += [f"Ім'я: {_e(payload['name'])}", f"Телефон: {_e(payload['phone'])}"]

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_phone.py tests/test_leads.py -q`
Expected: `17 passed`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add phone normalization and lead formatting"
git push origin main
```

---

### Task 3: Lead submission (store, deliver, mark sent)

**Files:**
- Modify: `app/services/leads.py`
- Create: `app/services/telegram.py`
- Test: `tests/test_leads.py` (append)

**Interfaces:**
- Consumes: `Lead` model, `format_lead`, fixtures `session`, `sender`.
- Produces:
  - `app.services.leads.Sender = Callable[[str], Awaitable[None]]`
  - `app.services.leads.LeadDeliveryError(Exception)` with attribute `lead_id: int`
  - `async submit_lead(session: AsyncSession, send: Sender, source: str, payload: dict) -> Lead` — commits the lead, calls `send(text)`, sets `sent_at`; on any send exception leaves `sent_at` NULL and raises `LeadDeliveryError`.
  - `app.services.telegram.make_channel_sender(bot: aiogram.Bot, chat_id: int) -> Sender`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_leads.py`:

```python
import pytest
from sqlalchemy import select

from app.db.models import Lead
from app.services.leads import LeadDeliveryError, submit_lead


async def test_submit_lead_stores_and_marks_sent(session, sender):
    payload = {"name": "Ira", "phone": "0671234567"}

    lead = await submit_lead(session, sender, "callback", payload)

    assert sender.messages == ["<b>Замовлення дзвінка</b>\nІм'я: Ira\nТелефон: 0671234567"]
    stored = (await session.execute(select(Lead))).scalar_one()
    assert stored.id == lead.id
    assert (stored.source, stored.name, stored.phone, stored.payload) == ("callback", "Ira", "0671234567", payload)
    assert stored.sent_at is not None


async def test_submit_lead_without_name(session, sender):
    await submit_lead(session, sender, "hero", {"from": "A1", "to": "B2", "phone": "0671234567"})
    assert (await session.execute(select(Lead))).scalar_one().name is None


async def test_submit_lead_keeps_unsent_lead_when_delivery_fails(session, sender):
    sender.fail = True

    with pytest.raises(LeadDeliveryError) as excinfo:
        await submit_lead(session, sender, "callback", {"name": "Ira", "phone": "0671234567"})

    stored = (await session.execute(select(Lead))).scalar_one()
    assert stored.sent_at is None
    assert excinfo.value.lead_id == stored.id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_leads.py -q`
Expected: `ImportError: cannot import name 'LeadDeliveryError'`.

- [ ] **Step 3: Write the implementation**

Add to the top of `app/services/leads.py` (keep the existing `import html`):

```python
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lead

logger = logging.getLogger(__name__)

Sender = Callable[[str], Awaitable[None]]


class LeadDeliveryError(Exception):
    def __init__(self, lead_id: int) -> None:
        super().__init__(f"lead {lead_id} was stored but not delivered")
        self.lead_id = lead_id
```

Append to the bottom of `app/services/leads.py`:

```python
async def submit_lead(session: AsyncSession, send: Sender, source: str, payload: dict) -> Lead:
    lead = Lead(source=source, name=payload.get("name"), phone=payload["phone"], payload=payload)
    session.add(lead)
    await session.commit()

    try:
        await send(format_lead(source, payload))
    except Exception as exc:
        logger.exception("Failed to deliver lead %s", lead.id)
        raise LeadDeliveryError(lead.id) from exc

    lead.sent_at = datetime.now(timezone.utc)
    await session.commit()
    return lead
```

`app/services/telegram.py`:

```python
from aiogram import Bot

from app.services.leads import Sender


def make_channel_sender(bot: Bot, chat_id: int) -> Sender:
    async def send(text: str) -> None:
        await bot.send_message(chat_id, text, parse_mode="HTML")

    return send
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_leads.py -q`
Expected: `9 passed`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: store leads and deliver them to the channel"
git push origin main
```

---

### Task 4: Catalog service (cargo service types)

**Files:**
- Create: `app/services/catalog.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: `Service` model, fixture `session`.
- Produces (all take `session: AsyncSession` first):
  - `async list_services(session) -> list[Service]` ordered by `position`, then `id`
  - `async get_service(session, service_id: int) -> Service | None`
  - `async create_service(session, *, title: str, items: list[str], image: str) -> Service` — placed last
  - `async update_service(session, service_id: int, *, title: str | None = None, items: list[str] | None = None, image: str | None = None) -> Service | None`
  - `async delete_service(session, service_id: int) -> Service | None` — returns the deleted row (caller removes its image)
  - `async move_service(session, service_id: int, direction: int) -> bool` — `-1` up, `+1` down; `False` at an edge or unknown id
  - `parse_items(text: str) -> list[str]` — one item per non-empty line, stripped

- [ ] **Step 1: Write the failing tests**

`tests/test_catalog.py`:

```python
from app.services import catalog


async def _make(session, *titles):
    return [await catalog.create_service(session, title=t, items=["a"], image=f"{t}.jpg") for t in titles]


async def _titles(session):
    return [s.title for s in await catalog.list_services(session)]


def test_parse_items_splits_lines_and_drops_blanks():
    assert catalog.parse_items("  one \n\n two\n   \nthree") == ["one", "two", "three"]
    assert catalog.parse_items("  \n ") == []


async def test_create_appends_to_the_end(session):
    await _make(session, "A", "B", "C")
    assert await _titles(session) == ["A", "B", "C"]


async def test_get_service(session):
    (a,) = await _make(session, "A")
    assert (await catalog.get_service(session, a.id)).title == "A"
    assert await catalog.get_service(session, 999) is None


async def test_update_changes_only_given_fields(session):
    (a,) = await _make(session, "A")

    updated = await catalog.update_service(session, a.id, items=["x", "y"])

    assert (updated.title, updated.items, updated.image) == ("A", ["x", "y"], "A.jpg")
    assert await catalog.update_service(session, 999, title="Z") is None


async def test_delete_returns_deleted_row(session):
    a, b = await _make(session, "A", "B")

    deleted = await catalog.delete_service(session, a.id)

    assert deleted.image == "A.jpg"
    assert await _titles(session) == ["B"]
    assert await catalog.delete_service(session, 999) is None


async def test_move_swaps_with_neighbour(session):
    a, b, c = await _make(session, "A", "B", "C")

    assert await catalog.move_service(session, c.id, -1) is True
    assert await _titles(session) == ["A", "C", "B"]

    assert await catalog.move_service(session, a.id, 1) is True
    assert await _titles(session) == ["C", "A", "B"]


async def test_move_at_edges_does_nothing(session):
    a, b = await _make(session, "A", "B")

    assert await catalog.move_service(session, a.id, -1) is False
    assert await catalog.move_service(session, b.id, 1) is False
    assert await catalog.move_service(session, 999, 1) is False
    assert await _titles(session) == ["A", "B"]


async def test_create_after_delete_still_goes_last(session):
    a, b = await _make(session, "A", "B")
    await catalog.delete_service(session, a.id)
    await _make(session, "C")
    assert await _titles(session) == ["B", "C"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_catalog.py -q`
Expected: `ImportError: cannot import name 'catalog'`.

- [ ] **Step 3: Write the implementation**

`app/services/catalog.py`:

```python
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Service


def parse_items(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


async def list_services(session: AsyncSession) -> list[Service]:
    result = await session.execute(select(Service).order_by(Service.position, Service.id))
    return list(result.scalars())


async def get_service(session: AsyncSession, service_id: int) -> Service | None:
    return await session.get(Service, service_id)


async def create_service(session: AsyncSession, *, title: str, items: list[str], image: str) -> Service:
    last = await session.scalar(select(func.max(Service.position)))
    service = Service(title=title, items=items, image=image, position=0 if last is None else last + 1)
    session.add(service)
    await session.commit()
    return service


async def update_service(
    session: AsyncSession,
    service_id: int,
    *,
    title: str | None = None,
    items: list[str] | None = None,
    image: str | None = None,
) -> Service | None:
    service = await session.get(Service, service_id)
    if service is None:
        return None
    if title is not None:
        service.title = title
    if items is not None:
        service.items = items
    if image is not None:
        service.image = image
    await session.commit()
    return service


async def delete_service(session: AsyncSession, service_id: int) -> Service | None:
    service = await session.get(Service, service_id)
    if service is None:
        return None
    await session.delete(service)
    await session.commit()
    return service


async def move_service(session: AsyncSession, service_id: int, direction: int) -> bool:
    services = await list_services(session)
    index = next((i for i, s in enumerate(services) if s.id == service_id), None)
    if index is None:
        return False
    target = index + direction
    if target < 0 or target >= len(services):
        return False
    current, neighbour = services[index], services[target]
    current.position, neighbour.position = neighbour.position, current.position
    await session.commit()
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_catalog.py -q`
Expected: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add catalog service for cargo service types"
git push origin main
```

---

### Task 5: Tariffs service

**Files:**
- Create: `app/services/tariffs.py`
- Test: `tests/test_tariffs.py`

**Interfaces:**
- Consumes: `TariffRow` model, `SEED_TARIFF_ROWS`, fixture `session`.
- Produces:
  - `CARDS: tuple[tuple[str, str], ...]` = `(("city", "По місту"), ("intercity", "За місто / по Україні"), ("loaders", "Послуги вантажників"))`; `CARD_TITLES: dict[str, str]`
  - `async get_cards(session) -> list[dict]` — `[{"id": str, "title": str, "rows": [{"key": str, "label": str, "value": str}]}]`, always all three cards in `CARDS` order, rows by `position`
  - `async get_row(session, key: str) -> TariffRow | None`
  - `async update_value(session, key: str, value: str) -> TariffRow | None`

- [ ] **Step 1: Write the failing tests**

`tests/test_tariffs.py`:

```python
import pytest_asyncio

from app.db.models import TariffRow
from app.db.seed import SEED_TARIFF_ROWS
from app.services import tariffs


@pytest_asyncio.fixture
async def seeded(session):
    session.add_all(TariffRow(**row) for row in SEED_TARIFF_ROWS)
    await session.commit()
    return session


async def test_get_cards_groups_rows_in_static_order(seeded):
    cards = await tariffs.get_cards(seeded)

    assert [(c["id"], c["title"]) for c in cards] == [
        ("city", "По місту"),
        ("intercity", "За місто / по Україні"),
        ("loaders", "Послуги вантажників"),
    ]
    assert cards[0]["rows"] == [
        {"key": "city.min_order", "label": "Мінімальне замовлення (2 год)", "value": "від 800 грн"},
        {"key": "city.next_hour", "label": "Кожна наступна година", "value": "від 350 грн/год"},
    ]


async def test_get_cards_without_rows_returns_empty_cards(session):
    cards = await tariffs.get_cards(session)
    assert [c["rows"] for c in cards] == [[], [], []]


async def test_update_value_changes_only_value(seeded):
    row = await tariffs.update_value(seeded, "city.min_order", "від 900 грн")

    assert (row.label, row.value) == ("Мінімальне замовлення (2 год)", "від 900 грн")
    assert (await tariffs.get_row(seeded, "city.min_order")).value == "від 900 грн"


async def test_unknown_key(seeded):
    assert await tariffs.get_row(seeded, "nope") is None
    assert await tariffs.update_value(seeded, "nope", "x") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_tariffs.py -q`
Expected: `ImportError: cannot import name 'tariffs'`.

- [ ] **Step 3: Write the implementation**

`app/services/tariffs.py`:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TariffRow

CARDS = (
    ("city", "По місту"),
    ("intercity", "За місто / по Україні"),
    ("loaders", "Послуги вантажників"),
)
CARD_TITLES = dict(CARDS)


async def get_cards(session: AsyncSession) -> list[dict]:
    result = await session.execute(select(TariffRow).order_by(TariffRow.position, TariffRow.key))
    rows = list(result.scalars())
    return [
        {
            "id": card_id,
            "title": title,
            "rows": [{"key": r.key, "label": r.label, "value": r.value} for r in rows if r.card == card_id],
        }
        for card_id, title in CARDS
    ]


async def get_row(session: AsyncSession, key: str) -> TariffRow | None:
    return await session.get(TariffRow, key)


async def update_value(session: AsyncSession, key: str, value: str) -> TariffRow | None:
    row = await session.get(TariffRow, key)
    if row is None:
        return None
    row.value = value
    await session.commit()
    return row
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_tariffs.py -q`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add tariffs service"
git push origin main
```

---

### Task 6: Media helpers

**Files:**
- Create: `app/services/media.py`
- Test: `tests/test_media.py`

**Interfaces:**
- Produces:
  - `is_local(image: str) -> bool` — `False` for `http://` / `https://` values
  - `new_image_name() -> str` — `services/<32 hex>.jpg`
  - `image_path(media_dir: Path, image: str) -> Path`
  - `delete_image(media_dir: Path, image: str) -> None` — removes a local file; no-op for URLs and missing files
  - `public_url(base_url: str, image: str) -> str` — URLs unchanged; local → `{base_url}/media/{image}`

- [ ] **Step 1: Write the failing tests**

`tests/test_media.py`:

```python
import re

from app.services import media


def test_is_local():
    assert media.is_local("services/a.jpg") is True
    assert media.is_local("https://images.unsplash.com/x") is False
    assert media.is_local("http://example.com/x.jpg") is False


def test_new_image_name_is_unique_and_under_services():
    first, second = media.new_image_name(), media.new_image_name()
    assert re.fullmatch(r"services/[0-9a-f]{32}\.jpg", first)
    assert first != second


def test_public_url():
    assert media.public_url("http://api.test/", "services/a.jpg") == "http://api.test/media/services/a.jpg"
    assert media.public_url("http://api.test", "https://cdn/x.jpg") == "https://cdn/x.jpg"


def test_delete_image_removes_local_file(tmp_path):
    target = media.image_path(tmp_path, "services/a.jpg")
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x")

    media.delete_image(tmp_path, "services/a.jpg")

    assert not target.exists()


def test_delete_image_ignores_urls_and_missing_files(tmp_path):
    media.delete_image(tmp_path, "https://cdn/x.jpg")
    media.delete_image(tmp_path, "services/missing.jpg")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_media.py -q`
Expected: `ImportError: cannot import name 'media'`.

- [ ] **Step 3: Write the implementation**

`app/services/media.py`:

```python
from pathlib import Path
from uuid import uuid4


def is_local(image: str) -> bool:
    return not image.startswith(("http://", "https://"))


def new_image_name() -> str:
    return f"services/{uuid4().hex}.jpg"


def image_path(media_dir: Path, image: str) -> Path:
    return media_dir / image


def delete_image(media_dir: Path, image: str) -> None:
    if is_local(image):
        image_path(media_dir, image).unlink(missing_ok=True)


def public_url(base_url: str, image: str) -> str:
    if not is_local(image):
        return image
    return f"{base_url.rstrip('/')}/media/{image}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_media.py -q`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add media helpers"
git push origin main
```

---

### Task 7: HTTP API

**Files:**
- Create: `app/api/deps.py`, `app/api/schemas.py`, `app/api/routes.py`
- Modify: `app/api/main.py` (replace whole file)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `catalog.list_services`, `tariffs.get_cards`, `submit_lead`, `LeadDeliveryError`, `media.public_url`, `make_channel_sender`, `normalize_phone`, `get_settings`, fixtures `session`, `sender`.
- Produces:
  - `app.api.deps.get_session`, `get_sender`, `require_api_key` (FastAPI dependencies; tests override the first two)
  - `GET /api/services` → `[{id, title, items, image}]`
  - `GET /api/pricing` → `{cards: [{id, title, rows: [{label, value}]}]}`
  - `POST /api/leads` with header `X-API-Key` → `201 {"ok": true}`; `401` bad/missing key; `422` invalid body; `502` when delivery fails

- [ ] **Step 1: Write the failing tests**

`tests/test_api.py`:

```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.deps import get_sender, get_session
from app.api.main import create_app
from app.db.models import Lead, TariffRow
from app.db.seed import SEED_TARIFF_ROWS
from app.services import catalog

AUTH = {"X-API-Key": "test-key"}
CALLBACK = {"source": "callback", "name": "Ira", "phone": "+38 (067) 123-45-67"}


@pytest_asyncio.fixture
async def client(session, sender):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_sender] = lambda: sender
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_services_are_ordered_with_public_image_urls(client, session):
    a = await catalog.create_service(session, title="A", items=["x"], image="services/a.jpg")
    b = await catalog.create_service(session, title="B", items=["y", "z"], image="https://cdn/b.jpg")
    await catalog.move_service(session, b.id, -1)

    response = await client.get("/api/services")

    assert response.status_code == 200
    assert response.json() == [
        {"id": b.id, "title": "B", "items": ["y", "z"], "image": "https://cdn/b.jpg"},
        {"id": a.id, "title": "A", "items": ["x"], "image": "http://backend.test/media/services/a.jpg"},
    ]


async def test_pricing_shape(client, session):
    session.add_all(TariffRow(**row) for row in SEED_TARIFF_ROWS)
    await session.commit()

    response = await client.get("/api/pricing")

    cards = response.json()["cards"]
    assert [c["id"] for c in cards] == ["city", "intercity", "loaders"]
    assert cards[1] == {
        "id": "intercity",
        "title": "За місто / по Україні",
        "rows": [
            {"label": "Вартість за кілометр", "value": "від 18 грн/км"},
            {"label": "Розрахунок", "value": "в обидва боки або в один бік"},
        ],
    }


async def test_create_lead_stores_normalized_phone_and_sends(client, session, sender):
    response = await client.post("/api/leads", json=CALLBACK, headers=AUTH)

    assert response.status_code == 201
    assert response.json() == {"ok": True}
    lead = (await session.execute(select(Lead))).scalar_one()
    assert (lead.source, lead.phone, lead.payload) == (
        "callback",
        "+380671234567",
        {"name": "Ira", "phone": "+380671234567"},
    )
    assert sender.messages == ["<b>Замовлення дзвінка</b>\nІм'я: Ira\nТелефон: +380671234567"]


async def test_create_hero_lead_keeps_from_key(client, session, sender):
    body = {"source": "hero", "from": "Львів", "to": "Київ", "phone": "0671234567"}

    response = await client.post("/api/leads", json=body, headers=AUTH)

    assert response.status_code == 201
    lead = (await session.execute(select(Lead))).scalar_one()
    assert lead.payload == {"from": "Львів", "to": "Київ", "phone": "0671234567"}
    assert "Звідки: Львів" in sender.messages[0]


async def test_create_calculator_lead(client, sender):
    body = {
        "source": "calculator",
        "name": "Олег",
        "phone": "0671234567",
        "serviceType": "city",
        "vanSize": "small",
        "loaders": "none",
        "route": "Львів",
    }
    response = await client.post("/api/leads", json=body, headers=AUTH)
    assert response.status_code == 201
    assert "Розмір буса: Малий" in sender.messages[0]


async def test_lead_requires_api_key(client, sender):
    assert (await client.post("/api/leads", json=CALLBACK)).status_code == 401
    assert (await client.post("/api/leads", json=CALLBACK, headers={"X-API-Key": "wrong"})).status_code == 401
    assert sender.messages == []


async def test_lead_validation_errors(client):
    bad_phone = {**CALLBACK, "phone": "123"}
    bad_source = {**CALLBACK, "source": "unknown"}
    short_name = {**CALLBACK, "name": "I"}
    for body in (bad_phone, bad_source, short_name):
        assert (await client.post("/api/leads", json=body, headers=AUTH)).status_code == 422


async def test_lead_delivery_failure_returns_502_and_keeps_lead(client, session, sender):
    sender.fail = True

    response = await client.post("/api/leads", json=CALLBACK, headers=AUTH)

    assert response.status_code == 502
    assert (await session.execute(select(Lead))).scalar_one().sent_at is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_api.py -q`
Expected: `ModuleNotFoundError: No module named 'app.api.deps'`.

- [ ] **Step 3: Write the implementation**

`app/api/deps.py`:

```python
import secrets
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.services.leads import Sender


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


def get_sender(request: Request) -> Sender:
    return request.app.state.send_lead


def require_api_key(
    x_api_key: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if x_api_key is None or not secrets.compare_digest(x_api_key.encode(), settings.api_key.encode()):
        raise HTTPException(status_code=401, detail="Invalid API key")
```

`app/api/schemas.py`:

```python
from typing import Annotated, Literal, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, RootModel, StringConstraints

from app.services.phone import normalize_phone


def _valid_phone(value: str) -> str:
    phone = normalize_phone(value)
    if phone is None:
        raise ValueError("Вкажіть повний номер телефону")
    return phone


Phone = Annotated[str, AfterValidator(_valid_phone)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]


class HeroLead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source: Literal["hero"]
    from_: Address = Field(alias="from")
    to: Address
    phone: Phone


class CalculatorLead(BaseModel):
    source: Literal["calculator"]
    name: Name
    phone: Phone
    serviceType: Literal["city", "intercity"]
    vanSize: Literal["small", "medium", "maxi"]
    loaders: Literal["none", "one", "two", "more"]
    route: Address


class CallbackLead(BaseModel):
    source: Literal["callback"]
    name: Name
    phone: Phone


class ServicesConsultLead(BaseModel):
    source: Literal["services_consult"]
    name: Name
    phone: Phone


class LeadRequest(RootModel):
    root: Annotated[
        Union[HeroLead, CalculatorLead, CallbackLead, ServicesConsultLead],
        Field(discriminator="source"),
    ]


class ServiceOut(BaseModel):
    id: int
    title: str
    items: list[str]
    image: str


class PricingRowOut(BaseModel):
    label: str
    value: str


class PricingCardOut(BaseModel):
    id: str
    title: str
    rows: list[PricingRowOut]


class PricingOut(BaseModel):
    cards: list[PricingCardOut]
```

`app/api/routes.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_sender, get_session, require_api_key
from app.api.schemas import LeadRequest, PricingOut, ServiceOut
from app.config import Settings, get_settings
from app.services import catalog, media, tariffs
from app.services.leads import LeadDeliveryError, Sender, submit_lead

router = APIRouter(prefix="/api")


@router.get("/services", response_model=list[ServiceOut])
async def list_services(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    return [
        ServiceOut(
            id=service.id,
            title=service.title,
            items=service.items,
            image=media.public_url(settings.public_base_url, service.image),
        )
        for service in await catalog.list_services(session)
    ]


@router.get("/pricing", response_model=PricingOut)
async def get_pricing(session: AsyncSession = Depends(get_session)):
    return {"cards": await tariffs.get_cards(session)}


@router.post("/leads", status_code=201, dependencies=[Depends(require_api_key)])
async def create_lead(
    body: LeadRequest,
    session: AsyncSession = Depends(get_session),
    send: Sender = Depends(get_sender),
):
    lead = body.root
    payload = lead.model_dump(by_alias=True, exclude={"source"})
    try:
        await submit_lead(session, send, lead.source, payload)
    except LeadDeliveryError:
        raise HTTPException(status_code=502, detail="Не вдалося надіслати заявку")
    return {"ok": True}
```

Replace `app/api/main.py`:

```python
from contextlib import asynccontextmanager

from aiogram import Bot
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes import router
from app.config import get_settings
from app.services.telegram import make_channel_sender


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    bot = Bot(settings.bot_token)
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.send_lead = make_channel_sender(bot, settings.leads_chat_id)
    yield
    await bot.session.close()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    settings.media_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="oleg-back-services", lifespan=lifespan)
    app.include_router(router)
    app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 4: Run the whole suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all tests pass (`50 passed`).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add http api for services, pricing and leads"
git push origin main
```

---

### Task 8: Bot core — start, cancel, order flow

**Files:**
- Create: `app/bot/__init__.py`, `app/bot/handlers/__init__.py`, `app/bot/filters.py`, `app/bot/states.py`, `app/bot/keyboards.py`, `app/bot/handlers/start.py`, `app/bot/handlers/order.py`, `app/bot/main.py`
- Test: `tests/test_bot_helpers.py`

**Interfaces:**
- Consumes: `Settings`, `catalog.list_services`, `submit_lead`, `LeadDeliveryError`, `normalize_phone`, `make_channel_sender`, `media.delete_image`.
- Produces:
  - Dispatcher workflow data available to every handler by argument name: `session_factory: async_sessionmaker[AsyncSession]`, `settings: Settings`, `send_lead: Sender`.
  - `app.bot.filters.IsAdmin` — filter; `await IsAdmin()(event, settings) -> bool`.
  - `app.bot.states`: `OrderForm` (`name`, `service`, `helpers_needed`, `helpers_count`, `address_from`, `address_to`, `date`, `time`, `phone`), `AdminService` (`new_photo`, `new_title`, `new_items`, `edit_photo`, `edit_title`, `edit_items`), `AdminTariff` (`value`).
  - `app.bot.keyboards`: constants `BTN_ORDER`, `BTN_ADMIN`, `BTN_CANCEL`, `BTN_YES`, `BTN_NO`, `BTN_CONTACT`; functions `main_menu(is_admin: bool)`, `cancel_kb()`, `options_kb(options: list[str])`, `yes_no_kb()`, `contact_kb()`.
  - FSM data key `pending_image` — a saved-but-unattached photo path; the cancel handler deletes that file.
  - `app.bot.handlers.order.date_options(today: date) -> list[str]`, `TIME_OPTIONS: list[str]`, `parse_helpers_count(text: str) -> int | None`.
  - Routers `start.router`, `order.router`; `app.bot.main.main()` (Task 9 and 10 add their routers there).

- [ ] **Step 1: Write the failing tests**

`tests/test_bot_helpers.py`:

```python
from datetime import date
from types import SimpleNamespace

from app.bot.filters import IsAdmin
from app.bot.handlers.order import TIME_OPTIONS, date_options, parse_helpers_count
from app.config import get_settings


def test_date_options_are_seven_days_from_today():
    options = date_options(date(2026, 10, 29))
    assert options == [
        "29-10-2026", "30-10-2026", "31-10-2026", "01-11-2026", "02-11-2026", "03-11-2026", "04-11-2026",
    ]


def test_time_options_cover_working_hours():
    assert TIME_OPTIONS[0] == "8:00"
    assert TIME_OPTIONS[-1] == "20:00"
    assert len(TIME_OPTIONS) == 13


def test_parse_helpers_count():
    assert parse_helpers_count(" 3 ") == 3
    assert parse_helpers_count("0") is None
    assert parse_helpers_count("-1") is None
    assert parse_helpers_count("two") is None


async def test_is_admin_checks_sender_id():
    settings = get_settings()  # ADMIN_IDS = 11, 22
    admin = SimpleNamespace(from_user=SimpleNamespace(id=11))
    stranger = SimpleNamespace(from_user=SimpleNamespace(id=99))
    anonymous = SimpleNamespace(from_user=None)

    assert await IsAdmin()(admin, settings) is True
    assert await IsAdmin()(stranger, settings) is False
    assert await IsAdmin()(anonymous, settings) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_bot_helpers.py -q`
Expected: `ModuleNotFoundError: No module named 'app.bot'`.

- [ ] **Step 3: Write filters, states, keyboards**

`app/bot/__init__.py`, `app/bot/handlers/__init__.py`: empty.

`app/bot/filters.py`:

```python
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from app.config import Settings


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, settings: Settings) -> bool:
        return event.from_user is not None and event.from_user.id in settings.admin_ids
```

`app/bot/states.py`:

```python
from aiogram.fsm.state import State, StatesGroup


class OrderForm(StatesGroup):
    name = State()
    service = State()
    helpers_needed = State()
    helpers_count = State()
    address_from = State()
    address_to = State()
    date = State()
    time = State()
    phone = State()


class AdminService(StatesGroup):
    new_photo = State()
    new_title = State()
    new_items = State()
    edit_photo = State()
    edit_title = State()
    edit_items = State()


class AdminTariff(StatesGroup):
    value = State()
```

`app/bot/keyboards.py`:

```python
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_ORDER = "Залишити заявку"
BTN_ADMIN = "Адмін-панель"
BTN_CANCEL = "Скасувати"
BTN_YES = "Так"
BTN_NO = "Ні"
BTN_CONTACT = "Надіслати номер телефону"


def _markup(rows: list[list[KeyboardButton]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def main_menu(is_admin: bool) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=BTN_ORDER)]]
    if is_admin:
        rows.append([KeyboardButton(text=BTN_ADMIN)])
    return _markup(rows)


def cancel_kb() -> ReplyKeyboardMarkup:
    return _markup([[KeyboardButton(text=BTN_CANCEL)]])


def options_kb(options: list[str]) -> ReplyKeyboardMarkup:
    return _markup([[KeyboardButton(text=option)] for option in options] + [[KeyboardButton(text=BTN_CANCEL)]])


def yes_no_kb() -> ReplyKeyboardMarkup:
    return _markup([[KeyboardButton(text=BTN_YES), KeyboardButton(text=BTN_NO)], [KeyboardButton(text=BTN_CANCEL)]])


def contact_kb() -> ReplyKeyboardMarkup:
    return _markup([[KeyboardButton(text=BTN_CONTACT, request_contact=True)], [KeyboardButton(text=BTN_CANCEL)]])
```

- [ ] **Step 4: Write the start and order handlers**

`app/bot/handlers/start.py`:

```python
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.keyboards import BTN_CANCEL, main_menu
from app.config import Settings
from app.services import media

router = Router()


def _is_admin(message: Message, settings: Settings) -> bool:
    return message.from_user is not None and message.from_user.id in settings.admin_ids


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    await message.answer(
        "Вітаю! Тут можна залишити заявку на вантажне перевезення.",
        reply_markup=main_menu(_is_admin(message, settings)),
    )


@router.message(Command("cancel"))
@router.message(F.text == BTN_CANCEL)
async def cancel(message: Message, state: FSMContext, settings: Settings) -> None:
    data = await state.get_data()
    if data.get("pending_image"):
        media.delete_image(settings.media_dir, data["pending_image"])
    await state.clear()
    await message.answer("Скасовано.", reply_markup=main_menu(_is_admin(message, settings)))
```

`app/bot/handlers/order.py`:

```python
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.keyboards import BTN_NO, BTN_ORDER, BTN_YES, cancel_kb, contact_kb, main_menu, options_kb, yes_no_kb
from app.bot.states import OrderForm
from app.config import Settings
from app.services import catalog
from app.services.leads import LeadDeliveryError, Sender, submit_lead
from app.services.phone import normalize_phone

router = Router()

SERVICE_UNSET = "не вказано"
TIME_OPTIONS = [f"{hour}:00" for hour in range(8, 21)]


def date_options(today: date) -> list[str]:
    return [(today + timedelta(days=offset)).strftime("%d-%m-%Y") for offset in range(7)]


def parse_helpers_count(text: str) -> int | None:
    try:
        count = int(text.strip())
    except ValueError:
        return None
    return count if count > 0 else None


def _today(settings: Settings) -> date:
    return datetime.now(ZoneInfo(settings.tz)).date()


async def _service_titles(session_factory: async_sessionmaker[AsyncSession]) -> list[str]:
    async with session_factory() as session:
        return [service.title for service in await catalog.list_services(session)]


async def _ask_helpers(message: Message, state: FSMContext) -> None:
    await state.set_state(OrderForm.helpers_needed)
    await message.answer("Чи потрібні вантажники?", reply_markup=yes_no_kb())


async def _ask_address_from(message: Message, state: FSMContext) -> None:
    await state.set_state(OrderForm.address_from)
    await message.answer("Звідки забираємо вантаж? Введіть адресу:", reply_markup=cancel_kb())


@router.message(F.text == BTN_ORDER)
async def begin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(OrderForm.name)
    await message.answer("Як вас звати?", reply_markup=cancel_kb())


@router.message(OrderForm.name, F.text)
async def got_name(message: Message, state: FSMContext, session_factory: async_sessionmaker[AsyncSession]) -> None:
    await state.update_data(name=message.text.strip())
    titles = await _service_titles(session_factory)
    if not titles:
        await state.update_data(service=SERVICE_UNSET)
        await _ask_helpers(message, state)
        return
    await state.set_state(OrderForm.service)
    await message.answer("Оберіть послугу:", reply_markup=options_kb(titles))


@router.message(OrderForm.service, F.text)
async def got_service(message: Message, state: FSMContext, session_factory: async_sessionmaker[AsyncSession]) -> None:
    titles = await _service_titles(session_factory)
    if message.text not in titles:
        await message.answer("Будь ласка, оберіть послугу з кнопок.", reply_markup=options_kb(titles))
        return
    await state.update_data(service=message.text)
    await _ask_helpers(message, state)


@router.message(OrderForm.helpers_needed, F.text)
async def got_helpers_needed(message: Message, state: FSMContext) -> None:
    if message.text == BTN_YES:
        await state.set_state(OrderForm.helpers_count)
        await message.answer("Скільки вантажників потрібно? Введіть число:", reply_markup=cancel_kb())
    elif message.text == BTN_NO:
        await state.update_data(helpers_count=0)
        await _ask_address_from(message, state)
    else:
        await message.answer("Будь ласка, оберіть «Так» або «Ні».", reply_markup=yes_no_kb())


@router.message(OrderForm.helpers_count, F.text)
async def got_helpers_count(message: Message, state: FSMContext) -> None:
    count = parse_helpers_count(message.text)
    if count is None:
        await message.answer("Будь ласка, введіть правильне число вантажників.")
        return
    await state.update_data(helpers_count=count)
    await _ask_address_from(message, state)


@router.message(OrderForm.address_from, F.text)
async def got_address_from(message: Message, state: FSMContext) -> None:
    await state.update_data(address_from=message.text.strip())
    await state.set_state(OrderForm.address_to)
    await message.answer("Куди доставити вантаж? Введіть адресу:", reply_markup=cancel_kb())


@router.message(OrderForm.address_to, F.text)
async def got_address_to(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.update_data(address_to=message.text.strip())
    await state.set_state(OrderForm.date)
    await message.answer("Оберіть дату перевезення:", reply_markup=options_kb(date_options(_today(settings))))


@router.message(OrderForm.date, F.text)
async def got_date(message: Message, state: FSMContext, settings: Settings) -> None:
    options = date_options(_today(settings))
    if message.text not in options:
        await message.answer("Будь ласка, оберіть дату з кнопок.", reply_markup=options_kb(options))
        return
    await state.update_data(date=message.text)
    await state.set_state(OrderForm.time)
    await message.answer("Оберіть час перевезення:", reply_markup=options_kb(TIME_OPTIONS))


@router.message(OrderForm.time, F.text)
async def got_time(message: Message, state: FSMContext) -> None:
    if message.text not in TIME_OPTIONS:
        await message.answer("Будь ласка, оберіть час з кнопок.", reply_markup=options_kb(TIME_OPTIONS))
        return
    await state.update_data(time=message.text)
    await state.set_state(OrderForm.phone)
    await message.answer("Будь ласка, надішліть ваш номер телефону:", reply_markup=contact_kb())


@router.message(OrderForm.phone, F.contact | F.text)
async def got_phone(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    send_lead: Sender,
    settings: Settings,
) -> None:
    raw = message.contact.phone_number if message.contact else message.text
    phone = normalize_phone(raw)
    if phone is None:
        await message.answer("Вкажіть номер у форматі +380XXXXXXXXX або 0XXXXXXXXX.", reply_markup=contact_kb())
        return

    payload = {**await state.get_data(), "phone": phone, "username": message.from_user.username}
    await state.clear()
    menu = main_menu(message.from_user.id in settings.admin_ids)

    try:
        async with session_factory() as session:
            await submit_lead(session, send_lead, "bot", payload)
    except LeadDeliveryError:
        await message.answer(
            f"Не вдалося надіслати заявку. Будь ласка, зателефонуйте нам: {settings.contact_phone}",
            reply_markup=menu,
        )
        return

    await message.answer("Дякуємо за замовлення! Ми зв'яжемося з вами найближчим часом.", reply_markup=menu)
```

- [ ] **Step 5: Write the bot entry point**

`app/bot/main.py`:

```python
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bot.handlers import order, start
from app.config import get_settings
from app.services.telegram import make_channel_sender


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    bot = Bot(settings.bot_token)

    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher["settings"] = settings
    dispatcher["session_factory"] = async_sessionmaker(engine, expire_on_commit=False)
    dispatcher["send_lead"] = make_channel_sender(bot, settings.leads_chat_id)
    # start.router goes first so that "Скасувати" and /cancel win over any state handler.
    dispatcher.include_routers(start.router, order.router)

    try:
        await dispatcher.start_polling(bot)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 6: Run the whole suite and an import smoke check**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all tests pass (`54 passed`).

Run: `.venv/Scripts/python -c "import app.bot.main"`
Expected: no output, exit code 0.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: add bot with order flow"
git push origin main
```

---

### Task 9: Bot admin — cargo service types

**Files:**
- Create: `app/bot/admin_kb.py`, `app/bot/handlers/admin_services.py`
- Modify: `app/bot/main.py` (imports and `include_routers` line)
- Test: `tests/test_bot_helpers.py` (append)

**Interfaces:**
- Consumes: `IsAdmin`, `AdminService` states, `BTN_ADMIN`, `cancel_kb`, `main_menu`, `catalog.*`, `media.*`, workflow data `session_factory`, `settings`.
- Produces:
  - `app.bot.admin_kb.SvcCb(CallbackData, prefix="svc")` with `action: str`, `id: int = 0`; actions: `list`, `add`, `view`, `photo`, `title`, `items`, `up`, `down`, `del`, `del_yes`.
  - `app.bot.admin_kb.TarCb(CallbackData, prefix="tar")` with `action: str`, `key: str = ""`; actions: `cards`, `card` (key = card id), `row` (key = tariff row key).
  - `admin_menu_kb()`, `services_list_kb(services)`, `service_card_kb(service_id)`, `delete_confirm_kb(service_id)`, `tariff_cards_kb()`, `tariff_card_kb(card: dict)`.
  - `app.bot.handlers.admin_services.router`, `card_text(service) -> str`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bot_helpers.py`:

```python
from app.bot.admin_kb import SvcCb, TarCb
from app.bot.handlers.admin_services import card_text


def test_card_text_lists_title_and_items():
    service = SimpleNamespace(title="Переїзди", items=["Пакування", "Меблі"])
    assert card_text(service) == "Переїзди\n\n✓ Пакування\n✓ Меблі"


def test_card_text_fits_telegram_caption_limit():
    service = SimpleNamespace(title="T", items=["x" * 600, "y" * 600])
    assert len(card_text(service)) == 1024


def test_callback_data_round_trip_and_size():
    assert SvcCb.unpack(SvcCb(action="view", id=7).pack()) == SvcCb(action="view", id=7)
    packed = TarCb(action="row", key="intercity.calculation").pack()
    assert TarCb.unpack(packed).key == "intercity.calculation"
    assert len(packed.encode()) <= 64
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_bot_helpers.py -q`
Expected: `ModuleNotFoundError: No module named 'app.bot.admin_kb'`.

- [ ] **Step 3: Write the admin keyboards**

`app/bot/admin_kb.py`:

```python
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.tariffs import CARDS


class SvcCb(CallbackData, prefix="svc"):
    action: str
    id: int = 0


class TarCb(CallbackData, prefix="tar"):
    action: str
    key: str = ""


def _button(text: str, callback: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback.pack())


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("Види перевезень", SvcCb(action="list"))],
            [_button("Тарифи", TarCb(action="cards"))],
        ]
    )


def services_list_kb(services) -> InlineKeyboardMarkup:
    rows = [[_button(service.title, SvcCb(action="view", id=service.id))] for service in services]
    rows.append([_button("➕ Додати", SvcCb(action="add"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def service_card_kb(service_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("Фото", SvcCb(action="photo", id=service_id)),
                _button("Назва", SvcCb(action="title", id=service_id)),
                _button("Пункти", SvcCb(action="items", id=service_id)),
            ],
            [
                _button("↑", SvcCb(action="up", id=service_id)),
                _button("↓", SvcCb(action="down", id=service_id)),
            ],
            [_button("Видалити", SvcCb(action="del", id=service_id))],
            [_button("« Назад", SvcCb(action="list"))],
        ]
    )


def delete_confirm_kb(service_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("Так, видалити", SvcCb(action="del_yes", id=service_id)),
                _button("Ні", SvcCb(action="view", id=service_id)),
            ]
        ]
    )


def tariff_cards_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_button(title, TarCb(action="card", key=card_id))] for card_id, title in CARDS]
    )


def tariff_card_kb(card: dict) -> InlineKeyboardMarkup:
    rows = [[_button(row["label"], TarCb(action="row", key=row["key"]))] for row in card["rows"]]
    rows.append([_button("« Назад", TarCb(action="cards"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

- [ ] **Step 4: Write the admin services handlers**

`app/bot/handlers/admin_services.py`:

```python
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.admin_kb import SvcCb, admin_menu_kb, delete_confirm_kb, service_card_kb, services_list_kb
from app.bot.filters import IsAdmin
from app.bot.keyboards import BTN_ADMIN, cancel_kb, main_menu
from app.bot.states import AdminService
from app.config import Settings
from app.services import catalog, media

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

SessionFactory = async_sessionmaker[AsyncSession]

ITEMS_PROMPT = "Надішліть пункти одним повідомленням — кожен з нового рядка."
EDIT_PROMPTS = {
    "photo": (AdminService.edit_photo, "Надішліть нове фото."),
    "title": (AdminService.edit_title, "Надішліть нову назву."),
    "items": (AdminService.edit_items, ITEMS_PROMPT),
}


def card_text(service) -> str:
    lines = [service.title, ""] + [f"✓ {item}" for item in service.items]
    return "\n".join(lines)[:1024]


async def save_photo(bot: Bot, message: Message, media_dir: Path) -> str:
    name = media.new_image_name()
    path = media.image_path(media_dir, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    await bot.download(message.photo[-1], destination=path)
    return name


async def send_list(message: Message, session_factory: SessionFactory) -> None:
    async with session_factory() as session:
        services = await catalog.list_services(session)
    text = "Види перевезень:" if services else "Видів перевезень ще немає."
    await message.answer(text, reply_markup=services_list_kb(services))


async def send_card(message: Message, service, settings: Settings) -> None:
    text = card_text(service)
    keyboard = service_card_kb(service.id)
    if media.is_local(service.image):
        photo = FSInputFile(media.image_path(settings.media_dir, service.image))
    else:
        photo = service.image
    try:
        await message.answer_photo(photo, caption=text, reply_markup=keyboard)
    except (TelegramAPIError, OSError):
        # Missing local file or an URL Telegram cannot fetch: show the card without the photo.
        await message.answer(text, reply_markup=keyboard)


@router.message(F.text == BTN_ADMIN)
async def admin_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Адмін-панель:", reply_markup=admin_menu_kb())


@router.callback_query(SvcCb.filter(F.action == "list"))
async def cb_list(callback: CallbackQuery, session_factory: SessionFactory) -> None:
    await callback.answer()
    await send_list(callback.message, session_factory)


@router.callback_query(SvcCb.filter(F.action == "view"))
async def cb_view(
    callback: CallbackQuery, callback_data: SvcCb, session_factory: SessionFactory, settings: Settings
) -> None:
    await callback.answer()
    async with session_factory() as session:
        service = await catalog.get_service(session, callback_data.id)
    if service is None:
        await send_list(callback.message, session_factory)
        return
    await send_card(callback.message, service, settings)


# --- add ---------------------------------------------------------------


@router.callback_query(SvcCb.filter(F.action == "add"))
async def cb_add(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(AdminService.new_photo)
    await callback.message.answer("Надішліть фото для нового виду перевезень.", reply_markup=cancel_kb())


@router.message(AdminService.new_photo, F.photo)
async def new_photo(message: Message, state: FSMContext, bot: Bot, settings: Settings) -> None:
    image = await save_photo(bot, message, settings.media_dir)
    await state.update_data(pending_image=image)
    await state.set_state(AdminService.new_title)
    await message.answer("Надішліть назву.")


@router.message(AdminService.new_title, F.text)
async def new_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip())
    await state.set_state(AdminService.new_items)
    await message.answer(ITEMS_PROMPT)


@router.message(AdminService.new_items, F.text)
async def new_items(message: Message, state: FSMContext, session_factory: SessionFactory, settings: Settings) -> None:
    items = catalog.parse_items(message.text)
    if not items:
        await message.answer("Потрібен щонайменше один пункт. " + ITEMS_PROMPT)
        return
    data = await state.get_data()
    await state.clear()
    async with session_factory() as session:
        service = await catalog.create_service(session, title=data["title"], items=items, image=data["pending_image"])
    await message.answer("Додано.", reply_markup=main_menu(True))
    await send_card(message, service, settings)


# --- edit --------------------------------------------------------------


@router.callback_query(SvcCb.filter(F.action.in_(set(EDIT_PROMPTS))))
async def cb_edit(callback: CallbackQuery, callback_data: SvcCb, state: FSMContext) -> None:
    await callback.answer()
    target_state, prompt = EDIT_PROMPTS[callback_data.action]
    await state.clear()
    await state.set_state(target_state)
    await state.update_data(service_id=callback_data.id)
    await callback.message.answer(prompt, reply_markup=cancel_kb())


async def finish_edit(
    message: Message, state: FSMContext, session_factory: SessionFactory, settings: Settings, **fields
):
    data = await state.get_data()
    await state.clear()
    async with session_factory() as session:
        service = await catalog.update_service(session, data["service_id"], **fields)
    if service is None:
        await message.answer("Послугу не знайдено.", reply_markup=main_menu(True))
        return None
    await message.answer("Збережено.", reply_markup=main_menu(True))
    await send_card(message, service, settings)
    return service


@router.message(AdminService.edit_photo, F.photo)
async def edit_photo(
    message: Message, state: FSMContext, bot: Bot, session_factory: SessionFactory, settings: Settings
) -> None:
    data = await state.get_data()
    async with session_factory() as session:
        current = await catalog.get_service(session, data["service_id"])
    old_image = current.image if current else None

    image = await save_photo(bot, message, settings.media_dir)
    updated = await finish_edit(message, state, session_factory, settings, image=image)
    if updated is None:
        media.delete_image(settings.media_dir, image)
    elif old_image:
        media.delete_image(settings.media_dir, old_image)


@router.message(StateFilter(AdminService.new_photo, AdminService.edit_photo))
async def photo_expected(message: Message) -> None:
    await message.answer("Надішліть саме фото (не файл).")


@router.message(AdminService.edit_title, F.text)
async def edit_title(message: Message, state: FSMContext, session_factory: SessionFactory, settings: Settings) -> None:
    await finish_edit(message, state, session_factory, settings, title=message.text.strip())


@router.message(AdminService.edit_items, F.text)
async def edit_items(message: Message, state: FSMContext, session_factory: SessionFactory, settings: Settings) -> None:
    items = catalog.parse_items(message.text)
    if not items:
        await message.answer("Потрібен щонайменше один пункт. " + ITEMS_PROMPT)
        return
    await finish_edit(message, state, session_factory, settings, items=items)


# --- order and delete --------------------------------------------------


@router.callback_query(SvcCb.filter(F.action.in_({"up", "down"})))
async def cb_move(callback: CallbackQuery, callback_data: SvcCb, session_factory: SessionFactory) -> None:
    direction = -1 if callback_data.action == "up" else 1
    async with session_factory() as session:
        moved = await catalog.move_service(session, callback_data.id, direction)
    await callback.answer("Переміщено." if moved else "Далі рухати нікуди.")
    await send_list(callback.message, session_factory)


@router.callback_query(SvcCb.filter(F.action == "del"))
async def cb_delete(callback: CallbackQuery, callback_data: SvcCb) -> None:
    await callback.answer()
    await callback.message.answer("Видалити цей вид перевезень?", reply_markup=delete_confirm_kb(callback_data.id))


@router.callback_query(SvcCb.filter(F.action == "del_yes"))
async def cb_delete_confirmed(
    callback: CallbackQuery, callback_data: SvcCb, session_factory: SessionFactory, settings: Settings
) -> None:
    async with session_factory() as session:
        deleted = await catalog.delete_service(session, callback_data.id)
    if deleted is not None:
        media.delete_image(settings.media_dir, deleted.image)
    await callback.answer("Видалено." if deleted else "Вже видалено.")
    await send_list(callback.message, session_factory)
```

- [ ] **Step 5: Register the router**

In `app/bot/main.py` change the handlers import and the `include_routers` call to:

```python
from app.bot.handlers import admin_services, order, start
```

```python
    dispatcher.include_routers(start.router, order.router, admin_services.router)
```

- [ ] **Step 6: Run the whole suite and the import smoke check**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all tests pass (`57 passed`).

Run: `.venv/Scripts/python -c "import app.bot.main"`
Expected: no output, exit code 0.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: add admin panel for cargo service types"
git push origin main
```

---

### Task 10: Bot admin — tariffs

**Files:**
- Create: `app/bot/handlers/admin_tariffs.py`
- Modify: `app/bot/main.py` (imports and `include_routers` line)
- Test: `tests/test_bot_helpers.py` (append)

**Interfaces:**
- Consumes: `TarCb`, `tariff_cards_kb`, `tariff_card_kb`, `IsAdmin`, `AdminTariff`, `cancel_kb`, `main_menu`, `tariffs.get_cards`, `tariffs.get_row`, `tariffs.update_value`, `tariffs.CARD_TITLES`.
- Produces: `app.bot.handlers.admin_tariffs.router`, `tariff_card_text(card: dict) -> str`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bot_helpers.py`:

```python
from app.bot.handlers.admin_tariffs import tariff_card_text


def test_tariff_card_text():
    card = {
        "id": "city",
        "title": "По місту",
        "rows": [
            {"key": "city.min_order", "label": "Мінімальне замовлення (2 год)", "value": "від 800 грн"},
            {"key": "city.next_hour", "label": "Кожна наступна година", "value": "від 350 грн/год"},
        ],
    }
    assert tariff_card_text(card) == (
        "По місту\n\n"
        "Мінімальне замовлення (2 год): від 800 грн\n"
        "Кожна наступна година: від 350 грн/год\n\n"
        "Оберіть рядок, щоб змінити значення."
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_bot_helpers.py -q`
Expected: `ModuleNotFoundError: No module named 'app.bot.handlers.admin_tariffs'`.

- [ ] **Step 3: Write the handlers**

`app/bot/handlers/admin_tariffs.py`:

```python
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.admin_kb import TarCb, tariff_card_kb, tariff_cards_kb
from app.bot.filters import IsAdmin
from app.bot.keyboards import cancel_kb, main_menu
from app.bot.states import AdminTariff
from app.services import tariffs

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

SessionFactory = async_sessionmaker[AsyncSession]


def tariff_card_text(card: dict) -> str:
    rows = "\n".join(f"{row['label']}: {row['value']}" for row in card["rows"])
    return f"{card['title']}\n\n{rows}\n\nОберіть рядок, щоб змінити значення."


async def send_card(message: Message, session_factory: SessionFactory, card_id: str) -> None:
    async with session_factory() as session:
        cards = await tariffs.get_cards(session)
    card = next((c for c in cards if c["id"] == card_id), None)
    if card is None:
        await message.answer("Оберіть картку тарифів:", reply_markup=tariff_cards_kb())
        return
    await message.answer(tariff_card_text(card), reply_markup=tariff_card_kb(card))


@router.callback_query(TarCb.filter(F.action == "cards"))
async def cb_cards(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer("Оберіть картку тарифів:", reply_markup=tariff_cards_kb())


@router.callback_query(TarCb.filter(F.action == "card"))
async def cb_card(callback: CallbackQuery, callback_data: TarCb, session_factory: SessionFactory) -> None:
    await callback.answer()
    await send_card(callback.message, session_factory, callback_data.key)


@router.callback_query(TarCb.filter(F.action == "row"))
async def cb_row(
    callback: CallbackQuery, callback_data: TarCb, state: FSMContext, session_factory: SessionFactory
) -> None:
    await callback.answer()
    async with session_factory() as session:
        row = await tariffs.get_row(session, callback_data.key)
    if row is None:
        await callback.message.answer("Оберіть картку тарифів:", reply_markup=tariff_cards_kb())
        return
    await state.clear()
    await state.set_state(AdminTariff.value)
    await state.update_data(key=row.key)
    await callback.message.answer(
        f"«{row.label}»\nЗараз: {row.value}\n\nНадішліть нове значення.", reply_markup=cancel_kb()
    )


@router.message(AdminTariff.value, F.text)
async def got_value(message: Message, state: FSMContext, session_factory: SessionFactory) -> None:
    value = message.text.strip()
    if not value:
        await message.answer("Значення не може бути порожнім.")
        return
    data = await state.get_data()
    await state.clear()
    async with session_factory() as session:
        row = await tariffs.update_value(session, data["key"], value)
    if row is None:
        await message.answer("Рядок не знайдено.", reply_markup=main_menu(True))
        return
    await message.answer("Збережено.", reply_markup=main_menu(True))
    await send_card(message, session_factory, row.card)
```

- [ ] **Step 4: Register the router**

In `app/bot/main.py` change the handlers import and the `include_routers` call to:

```python
from app.bot.handlers import admin_services, admin_tariffs, order, start
```

```python
    dispatcher.include_routers(start.router, order.router, admin_services.router, admin_tariffs.router)
```

- [ ] **Step 5: Run the whole suite and the import smoke check**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all tests pass (`58 passed`).

Run: `.venv/Scripts/python -c "import app.bot.main"`
Expected: no output, exit code 0.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add admin panel for tariffs"
git push origin main
```

---

### Task 11: Site integration (`oleg-webapp`)

All paths in this task are relative to `D:\Workspace\nextjs\OLEG\oleg-webapp`. **Do not run `git add` or `git commit` in this repo.** The repo has no test runner; verification is type-check, build and a manual check.

**Files:**
- Create: `lib/backend.ts`
- Delete: `lib/telegram.ts`
- Modify: `app/api/lead/route.ts`, `app/page.tsx`, `components/Services/Services.tsx`, `components/Pricing/Pricing.tsx`, `next.config.mjs`, `.env.example`

**Interfaces:**
- Consumes: backend `GET /api/services`, `GET /api/pricing`, `POST /api/leads` (Task 7); `LeadPayload` from `lib/validation.ts`; `services`, `pricing` from `data/content.ts` as fallback.
- Produces: `lib/backend.ts` exports `ServiceData`, `PricingData`, `getServices(): Promise<ServiceData[]>`, `getPricing(): Promise<PricingData>`, `sendLead(lead: LeadPayload): Promise<void>`.

- [ ] **Step 1: Create `lib/backend.ts`**

```ts
import { pricing as fallbackPricing, services as fallbackServices } from "@/data/content";
import type { LeadPayload } from "./validation";

export type ServiceData = {
  id: string | number;
  title: string;
  items: string[];
  image: string;
};

export type PricingData = {
  cards: { id: string; title: string; rows: { label: string; value: string }[] }[];
};

const REVALIDATE_SECONDS = 60;

// Returns null when the backend is not configured, unreachable or answers with an error,
// so callers can fall back to the static content.
async function getJson<T>(path: string): Promise<T | null> {
  const baseUrl = process.env.BACKEND_URL;
  if (!baseUrl) return null;

  try {
    const response = await fetch(`${baseUrl}${path}`, { next: { revalidate: REVALIDATE_SECONDS } });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch (error) {
    console.error(`Backend request failed: ${path}`, error);
    return null;
  }
}

export async function getServices(): Promise<ServiceData[]> {
  const data = await getJson<ServiceData[]>("/api/services");
  return data && data.length > 0 ? data : fallbackServices;
}

export async function getPricing(): Promise<PricingData> {
  const data = await getJson<PricingData>("/api/pricing");
  return data && data.cards.length > 0 ? data : fallbackPricing;
}

export async function sendLead(lead: LeadPayload): Promise<void> {
  const baseUrl = process.env.BACKEND_URL;
  const apiKey = process.env.BACKEND_API_KEY;

  if (!baseUrl || !apiKey) {
    throw new Error("Backend credentials are not configured");
  }

  const response = await fetch(`${baseUrl}/api/leads`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
    body: JSON.stringify(lead),
    cache: "no-store",
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Backend error: ${response.status} ${detail}`);
  }
}
```

- [ ] **Step 2: Point the lead route at the backend and delete `lib/telegram.ts`**

In `app/api/lead/route.ts` replace

```ts
import { sendLeadToTelegram } from "@/lib/telegram";
```

with

```ts
import { sendLead } from "@/lib/backend";
```

and replace

```ts
    await sendLeadToTelegram(parsed.data);
  } catch (error) {
    console.error("Failed to send lead to Telegram", error);
```

with

```ts
    await sendLead(parsed.data);
  } catch (error) {
    console.error("Failed to send lead to backend", error);
```

Then delete the old sender:

```bash
rm lib/telegram.ts
```

- [ ] **Step 3: Pass data into the Services and Pricing sections**

`components/Services/Services.tsx` — remove the `services` import from `@/data/content`, add the type import and a prop:

```tsx
"use client";

import { useState } from "react";
import type { ServiceData } from "@/lib/backend";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { NamePhoneForm } from "@/components/ui/NamePhoneForm";
import { ServiceCard } from "./ServiceCard";
import styles from "./Services.module.css";

export function Services({ services }: { services: ServiceData[] }) {
```

The rest of the component body stays as is.

`components/Pricing/Pricing.tsx` — remove the `pricing` import from `@/data/content`, add the type import and a prop:

```tsx
import type { PricingData } from "@/lib/backend";
import { CalculatorForm } from "./CalculatorForm";
import styles from "./Pricing.module.css";

export function Pricing({ pricing }: { pricing: PricingData }) {
```

The rest of the component body stays as is.

`app/page.tsx` — replace the component with:

```tsx
import { Header } from "@/components/Header/Header";
import { Hero } from "@/components/Hero/Hero";
import { Services } from "@/components/Services/Services";
import { Pricing } from "@/components/Pricing/Pricing";
import { Advantages } from "@/components/Advantages/Advantages";
import { Faq } from "@/components/Faq/Faq";
import { Footer } from "@/components/Footer/Footer";
import { getPricing, getServices } from "@/lib/backend";

export default async function Home() {
  const [services, pricing] = await Promise.all([getServices(), getPricing()]);

  return (
    <>
      <Header />
      <main>
        <Hero />
        <Services services={services} />
        <Pricing pricing={pricing} />
        <Advantages />
        <Faq />
      </main>
      <Footer />
    </>
  );
}
```

- [ ] **Step 4: Allow backend images and update env example**

Replace `next.config.mjs` with:

```js
// Photos uploaded through the bot are served by the backend under /media.
const backendUrl = process.env.BACKEND_URL ? new URL(process.env.BACKEND_URL) : null;

/** @type {import('next').NextConfig} */
const nextConfig = {
  agentRules: false,
  // Allow opening the dev server from other devices on the local network (e.g. a phone).
  allowedDevOrigins: ["192.168.0.151"],
  images: {
    // The local backend runs on localhost, which the image optimizer blocks by default.
    dangerouslyAllowLocalIP: process.env.NODE_ENV !== "production",
    remotePatterns: [
      { protocol: "https", hostname: "images.unsplash.com" },
      ...(backendUrl
        ? [
            {
              protocol: backendUrl.protocol.replace(":", ""),
              hostname: backendUrl.hostname,
              port: backendUrl.port,
              pathname: "/media/**",
            },
          ]
        : []),
    ],
  },
};

export default nextConfig;
```

`BACKEND_URL` must be the same origin as the backend's `PUBLIC_BASE_URL`, because image URLs in API responses are built from `PUBLIC_BASE_URL`.

If `next build` reports `dangerouslyAllowLocalIP` as an unrecognized option for the installed Next.js version, remove that line; local-backend photos then need `PUBLIC_BASE_URL` to be a non-loopback address.

Replace `.env.example` with:

```
BACKEND_URL=http://localhost:8000
BACKEND_API_KEY=
```

- [ ] **Step 5: Type-check and build**

```bash
npx tsc --noEmit
npm run build
```

Expected: both finish without errors. With `BACKEND_URL` unset the build uses the static fallback.

- [ ] **Step 6: Verify nothing was committed here**

Run: `git -C . log -1 --format=%s`
Expected: `fix hero title` (unchanged).

---

### Task 12: README and end-to-end verification

Paths are relative to `oleg-back-services` again.

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write the README**

`README.md`:

````markdown
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
Міграції застосовує сервіс `api` під час старту.

## Тести

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
docker compose up -d db
.venv/Scripts/python -m pytest -q
```

Тести працюють на базі `oleg_test` (порт `5433`), Telegram у них не викликається.

## Бот

- `/start` — меню. «Залишити заявку» запускає опитування; заявка зберігається в базі та надсилається в канал.
- «Адмін-панель» (лише для `ADMIN_IDS`): види перевезень (додати, змінити фото / назву / пункти, порядок, видалити) і значення тарифів.
- «Скасувати» або `/cancel` перериває будь-який діалог.
````

- [ ] **Step 2: Bring the stack up**

Requires a real `.env` (ask the user for `BOT_TOKEN`, `LEADS_CHAT_ID`, `ADMIN_IDS` if it does not exist — do not invent values).

```bash
docker compose up -d --build
docker compose ps
curl -s http://localhost:8000/health
curl -s http://localhost:8000/api/services
curl -s http://localhost:8000/api/pricing
```

Expected: `db`, `api`, `bot` are running; `/health` returns `{"status":"ok"}`; services returns 5 items; pricing returns 3 cards.

- [ ] **Step 3: Verify lead delivery through the API**

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/leads \
  -H "Content-Type: application/json" -d '{"source":"callback","name":"Test","phone":"0671234567"}'
curl -s -X POST http://localhost:8000/api/leads -H "Content-Type: application/json" \
  -H "X-API-Key: <API_KEY from .env>" -d '{"source":"callback","name":"Test","phone":"0671234567"}'
```

Expected: first call prints `401`; second returns `{"ok":true}` and the message «Замовлення дзвінка» appears in the channel.

- [ ] **Step 4: Manual bot checklist**

Check each item in Telegram and report the result of each one:

1. `/start` as a non-admin shows only «Залишити заявку»; as an admin also «Адмін-панель».
2. Full order flow ends with «Дякуємо за замовлення!…» and the lead appears in the channel with all fields.
3. Invalid input (text for helpers count, a date not from the buttons, phone `123`) re-asks the same step.
4. «Скасувати» mid-flow returns to the main menu.
5. Admin: add a service (photo → title → items); it appears in `GET /api/services` with a `/media/services/….jpg` URL that opens in a browser.
6. Admin: change title, items and photo of that service; move it up and down; delete it — the image file is gone from the `media` volume.
7. Admin: change a tariff value; `GET /api/pricing` returns the new value and the label is unchanged.
8. A non-admin who sends the text «Адмін-панель» gets no admin menu.

- [ ] **Step 5: Verify the site against the running backend**

In `oleg-webapp` create `.env.local` with `BACKEND_URL=http://localhost:8000` and `BACKEND_API_KEY=<API_KEY>`, run `npm run dev`, then check:

1. The services and pricing sections show backend data (change a tariff in the bot, reload after about a minute, the new value is shown).
2. Submitting the hero form delivers «Заявка з головної форми» to the channel.
3. `docker compose stop api`, restart `npm run dev`, the page still renders with the static fallback; then `docker compose start api`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "docs: add readme"
git push origin main
```
