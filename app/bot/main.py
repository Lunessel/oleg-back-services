import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bot.handlers import admin_services, admin_tariffs, order, start
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
    dispatcher.include_routers(start.router, order.router, admin_services.router, admin_tariffs.router)

    try:
        await dispatcher.start_polling(bot)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
