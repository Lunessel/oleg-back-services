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
