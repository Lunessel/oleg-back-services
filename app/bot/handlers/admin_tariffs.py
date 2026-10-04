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
