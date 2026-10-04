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
