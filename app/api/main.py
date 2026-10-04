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
