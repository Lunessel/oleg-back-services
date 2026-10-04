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
