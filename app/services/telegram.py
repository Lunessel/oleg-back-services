from aiogram import Bot

from app.services.leads import Sender


def make_channel_sender(bot: Bot, chat_id: int) -> Sender:
    async def send(text: str) -> None:
        await bot.send_message(chat_id, text, parse_mode="HTML")

    return send
