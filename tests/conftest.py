import os
import tempfile

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://oleg:oleg@127.0.0.1:5434/oleg_test"
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
async def session_factory():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(session_factory):
    async with session_factory() as s:
        yield s
