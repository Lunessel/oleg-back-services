"""Drive real dialogs through the Dispatcher with a fake Telegram transport."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import GetFile, SendMessage, SendPhoto
from aiogram.types import CallbackQuery, Chat, Contact, File, Message, PhotoSize, Update, User
from sqlalchemy import select

from app.bot.admin_kb import SvcCb, TarCb
from app.bot.handlers import admin_services, admin_tariffs, order, start

from app.bot.keyboards import BTN_ADMIN, BTN_CANCEL, BTN_CONTACT, BTN_ORDER
from app.config import get_settings
from app.db.models import Lead, TariffRow
from app.db.seed import SEED_TARIFF_ROWS
from app.services import catalog, media

ADMIN_ID = 11  # from ADMIN_IDS in conftest
USER_ID = 500


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list = []

    async def close(self) -> None:
        pass

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, (SendMessage, SendPhoto)):
            return Message(
                message_id=len(self.calls),
                date=datetime.now(),
                chat=Chat(id=method.chat_id, type="private"),
                text=getattr(method, "text", None),
            )
        if isinstance(method, GetFile):
            return File(file_id=method.file_id, file_unique_id="u", file_path="photos/file.jpg")
        return True

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        yield b"jpeg-bytes"


class Chat_:
    """One Telegram user talking to the bot."""

    def __init__(self, dispatcher: Dispatcher, bot: Bot, transport: FakeSession, user_id: int) -> None:
        self.dispatcher, self.bot, self.transport = dispatcher, bot, transport
        self.user = User(id=user_id, is_bot=False, first_name="Test", username="tester")
        self.chat = Chat(id=user_id, type="private")
        self._update_id = 0

    def _message(self, **fields) -> Message:
        self._update_id += 1
        return Message(
            message_id=self._update_id, date=datetime.now(), chat=self.chat, from_user=self.user, **fields
        )

    async def _feed(self, **update_fields) -> list:
        before = len(self.transport.calls)
        await self.dispatcher.feed_update(self.bot, Update(update_id=self._update_id, **update_fields))
        return self.transport.calls[before:]

    async def say(self, text: str) -> list:
        return await self._feed(message=self._message(text=text))

    async def send_contact(self, phone: str) -> list:
        contact = Contact(phone_number=phone, first_name="Test")
        return await self._feed(message=self._message(contact=contact))

    async def send_photo(self) -> list:
        photo = [PhotoSize(file_id="small", file_unique_id="s", width=90, height=90),
                 PhotoSize(file_id="big", file_unique_id="b", width=800, height=800)]
        return await self._feed(message=self._message(photo=photo))

    async def press(self, callback_data) -> list:
        query = CallbackQuery(
            id="1", from_user=self.user, chat_instance="ci", data=callback_data.pack(), message=self._message(text="menu")
        )
        return await self._feed(callback_query=query)


def texts(calls: list) -> list[str]:
    return [c.text if isinstance(c, SendMessage) else c.caption for c in calls if isinstance(c, (SendMessage, SendPhoto))]


@pytest.fixture
def make_chat(session_factory, sender):
    transport = FakeSession()
    bot = Bot("123456:TEST", session=transport)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher["settings"] = get_settings()
    dispatcher["session_factory"] = session_factory
    dispatcher["send_lead"] = sender
    dispatcher.include_routers(start.router, order.router, admin_services.router, admin_tariffs.router)

    yield lambda user_id: Chat_(dispatcher, bot, transport, user_id)

    # Routers are module-level singletons; detach them so the next test can attach again.
    for router in (start.router, order.router, admin_services.router, admin_tariffs.router):
        router._parent_router = None


class Clock:
    """The bot's notion of "now", fixed so dialogs don't depend on when the tests run."""

    def __init__(self) -> None:
        self.now = datetime(2026, 10, 5, 7, 30, tzinfo=ZoneInfo(get_settings().tz))


@pytest.fixture(autouse=True)
def clock(monkeypatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(order, "_now", lambda settings: clock.now)
    return clock


def today_option() -> str:
    return "05-10-2026"


def reply_buttons(calls: list) -> list[str]:
    return [b.text for row in calls[0].reply_markup.keyboard for b in row]


async def _reach_date_step(user) -> None:
    for text in (BTN_ORDER, "Олег", "Ні", "A-1", "B-2"):
        await user.say(text)


async def test_today_offers_only_upcoming_hours(make_chat, session, clock):
    clock.now = clock.now.replace(hour=14, minute=30)
    user = make_chat(USER_ID)
    await _reach_date_step(user)

    replies = await user.say(today_option())

    assert reply_buttons(replies) == ["15:00", "16:00", "17:00", "18:00", "19:00", "20:00", BTN_CANCEL]
    assert texts(await user.say("10:00")) == ["Будь ласка, оберіть час з кнопок."]


async def test_date_list_starts_tomorrow_in_the_evening(make_chat, session, clock):
    clock.now = clock.now.replace(hour=20, minute=10)
    user = make_chat(USER_ID)
    for text in (BTN_ORDER, "Олег", "Ні", "A-1"):
        await user.say(text)

    replies = await user.say("B-2")

    assert reply_buttons(replies)[0] == "06-10-2026"
    assert texts(await user.say(today_option())) == ["Будь ласка, оберіть дату з кнопок."]


async def test_hour_that_passed_while_choosing_is_rejected(make_chat, session, clock):
    clock.now = clock.now.replace(hour=15, minute=50)
    user = make_chat(USER_ID)
    await _reach_date_step(user)
    await user.say(today_option())

    clock.now = clock.now.replace(hour=16, minute=5)
    replies = await user.say("16:00")

    assert texts(replies) == ["Будь ласка, оберіть час з кнопок."]
    assert reply_buttons(replies)[0] == "17:00"


async def test_today_without_hours_left_goes_back_to_dates(make_chat, session, clock):
    clock.now = clock.now.replace(hour=19, minute=50)
    user = make_chat(USER_ID)
    await _reach_date_step(user)
    await user.say(today_option())

    clock.now = clock.now.replace(hour=20, minute=5)
    replies = await user.say("20:00")

    assert texts(replies) == ["На цю дату вже немає вільних годин. Оберіть іншу дату:"]
    assert reply_buttons(replies)[0] == "06-10-2026"
    assert texts(await user.say("06-10-2026")) == ["Оберіть час перевезення:"]


async def test_full_order_flow_delivers_lead(make_chat, session, sender):
    await catalog.create_service(session, title="Переїзди", items=["a"], image="https://cdn/x.jpg")
    user = make_chat(USER_ID)

    assert "Вітаю!" in texts(await user.say("/start"))[0]
    assert texts(await user.say(BTN_ORDER)) == ["Як вас звати?"]
    assert texts(await user.say("Олег")) == ["Оберіть послугу:"]
    assert texts(await user.say("нема такої")) == ["Будь ласка, оберіть послугу з кнопок."]
    assert texts(await user.say("Переїзди")) == ["Чи потрібні вантажники?"]
    assert texts(await user.say("Так")) == ["Скільки вантажників потрібно? Введіть число:"]
    assert texts(await user.say("багато")) == ["Будь ласка, введіть правильне число вантажників."]
    assert texts(await user.say("2")) == ["Звідки забираємо вантаж? Введіть адресу:"]
    assert texts(await user.say("вул. Зелена, 1")) == ["Куди доставити вантаж? Введіть адресу:"]
    assert texts(await user.say("вул. Наукова, 7")) == ["Оберіть дату перевезення:"]
    assert texts(await user.say("завтра")) == ["Будь ласка, оберіть дату з кнопок."]
    assert texts(await user.say(today_option())) == ["Оберіть час перевезення:"]
    assert texts(await user.say("10:00")) == ["Будь ласка, надішліть ваш номер телефону:"]
    assert texts(await user.say("123")) == ["Вкажіть номер у форматі +380XXXXXXXXX або 0XXXXXXXXX."]
    assert texts(await user.send_contact("380671234567")) == [
        "Дякуємо за замовлення! Ми зв'яжемося з вами найближчим часом."
    ]

    lead = (await session.execute(select(Lead))).scalar_one()
    assert (lead.source, lead.name, lead.phone) == ("bot", "Олег", "+380671234567")
    assert lead.sent_at is not None
    assert sender.messages == [
        "<b>Заявка з Telegram-бота</b>\n"
        "Ім'я: Олег\n"
        "Послуга: Переїзди\n"
        "Вантажники: Так, кількість — 2\n"
        "Звідки: вул. Зелена, 1\n"
        "Куди: вул. Наукова, 7\n"
        f"Дата: {today_option()}\n"
        "Час: 10:00\n"
        "Телефон: +380671234567\n"
        "Telegram: @tester"
    ]


async def test_order_with_custom_service(make_chat, session, sender):
    await catalog.create_service(session, title="Переїзди", items=["a"], image="https://cdn/x.jpg")
    user = make_chat(USER_ID)
    await user.say(BTN_ORDER)

    replies = await user.say("Олег")
    buttons = [b.text for row in replies[0].reply_markup.keyboard for b in row]
    assert buttons == ["Переїзди", "Інше", BTN_CANCEL]

    # Free text without pressing "Інше" is still rejected.
    assert texts(await user.say("Піаніно")) == ["Будь ласка, оберіть послугу з кнопок."]
    assert texts(await user.say("Інше")) == ["Опишіть, що потрібно перевезти:"]
    assert texts(await user.say(" ")) == ["Будь ласка, опишіть послугу текстом."]
    assert texts(await user.say("Піаніно на 3 поверх")) == ["Чи потрібні вантажники?"]
    for text in ("Ні", "A-1", "B-2", today_option(), "8:00", "0671234567"):
        await user.say(text)

    assert "Послуга: Піаніно на 3 поверх (вказано вручну)" in sender.messages[0]
    lead = (await session.execute(select(Lead))).scalar_one()
    assert lead.payload["service_is_custom"] is True


async def test_order_without_services_skips_service_step(make_chat, session, sender):
    user = make_chat(USER_ID)
    await user.say(BTN_ORDER)
    assert texts(await user.say("Олег")) == ["Чи потрібні вантажники?"]
    await user.say("Ні")
    await user.say("A-1")
    await user.say("B-2")
    await user.say(today_option())
    await user.say("8:00")
    await user.say("0671234567")

    assert "Послуга: не вказано" in sender.messages[0]
    assert "Вантажники: Ні" in sender.messages[0]


async def test_delivery_failure_asks_user_to_call(make_chat, session, sender):
    sender.fail = True
    user = make_chat(USER_ID)
    for text in (BTN_ORDER, "Олег", "Ні", "A-1", "B-2", today_option(), "8:00"):
        await user.say(text)

    reply = texts(await user.say("0671234567"))

    assert reply == [f"Не вдалося надіслати заявку. Будь ласка, зателефонуйте нам: {get_settings().contact_phone}"]
    assert (await session.execute(select(Lead))).scalar_one().sent_at is None


async def test_cancel_resets_dialog(make_chat, session, sender):
    user = make_chat(USER_ID)
    await user.say(BTN_ORDER)
    await user.say("Олег")

    assert texts(await user.say(BTN_CANCEL)) == ["Скасовано."]
    # No dialog is active any more: free text gets no reply and nothing is stored.
    assert await user.say("Ні") == []
    assert (await session.execute(select(Lead))).first() is None


async def test_main_menu_shows_admin_button_only_to_admins(make_chat, session):
    def buttons(calls):
        return [b.text for row in calls[0].reply_markup.keyboard for b in row]

    assert buttons(await make_chat(USER_ID).say("/start")) == [BTN_ORDER]
    assert buttons(await make_chat(ADMIN_ID).say("/start")) == [BTN_ORDER, BTN_ADMIN]


async def test_non_admin_cannot_reach_admin_handlers(make_chat, session):
    session.add_all(TariffRow(**row) for row in SEED_TARIFF_ROWS)
    await session.commit()
    user = make_chat(USER_ID)

    assert await user.say(BTN_ADMIN) == []
    assert await user.press(SvcCb(action="list")) == []
    assert await user.press(TarCb(action="row", key="city.min_order")) == []
    assert await user.say("від 1 грн") == []

    await session.rollback()
    assert (await session.get(TariffRow, "city.min_order")).value == "від 800 грн"


async def test_admin_changes_tariff_value(make_chat, session):
    session.add_all(TariffRow(**row) for row in SEED_TARIFF_ROWS)
    await session.commit()
    admin = make_chat(ADMIN_ID)

    assert texts(await admin.say(BTN_ADMIN)) == ["Адмін-панель:"]
    assert texts(await admin.press(TarCb(action="cards"))) == ["Оберіть картку тарифів:"]
    assert "Мінімальне замовлення (2 год): від 800 грн" in texts(await admin.press(TarCb(action="card", key="city")))[0]
    assert "Зараз: від 800 грн" in texts(await admin.press(TarCb(action="row", key="city.min_order")))[0]

    replies = texts(await admin.say("від 950 грн"))

    assert replies[0] == "Збережено."
    assert "Мінімальне замовлення (2 год): від 950 грн" in replies[1]
    session.expire_all()
    row = await session.get(TariffRow, "city.min_order")
    assert (row.label, row.value) == ("Мінімальне замовлення (2 год)", "від 950 грн")


async def test_admin_adds_edits_reorders_and_deletes_service(make_chat, session):
    media_dir = get_settings().media_dir
    first_id = (await catalog.create_service(session, title="Перша", items=["a"], image="https://cdn/x.jpg")).id
    admin = make_chat(ADMIN_ID)

    # add: photo -> title -> items
    assert texts(await admin.press(SvcCb(action="add"))) == ["Надішліть фото для нового виду перевезень."]
    assert texts(await admin.say("це не фото")) == ["Надішліть саме фото (не файл)."]
    assert texts(await admin.send_photo()) == ["Надішліть назву."]
    await admin.say("Нова послуга")
    assert "щонайменше один пункт" in texts(await admin.say("   "))[0]
    replies = texts(await admin.say("Пункт 1\n\n Пункт 2 "))
    assert replies == ["Додано.", "Нова послуга\n\n✓ Пункт 1\n✓ Пункт 2"]

    services = await catalog.list_services(session)
    assert [s.title for s in services] == ["Перша", "Нова послуга"]
    assert services[1].items == ["Пункт 1", "Пункт 2"]
    # Plain values: ORM objects are expired below to re-read what the bot wrote.
    created_id = services[1].id
    old_file = media.image_path(media_dir, services[1].image)
    assert old_file.read_bytes() == b"jpeg-bytes"

    # edit title and items
    await admin.press(SvcCb(action="title", id=created_id))
    assert texts(await admin.say("Перейменована"))[0] == "Збережено."
    await admin.press(SvcCb(action="items", id=created_id))
    await admin.say("Один")

    # replace photo: new file is stored, the old one is removed
    await admin.press(SvcCb(action="photo", id=created_id))
    await admin.send_photo()
    session.expire_all()
    updated = await catalog.get_service(session, created_id)
    assert (updated.title, updated.items) == ("Перейменована", ["Один"])
    new_file = media.image_path(media_dir, updated.image)
    assert new_file != old_file and new_file.exists() and not old_file.exists()

    # reorder
    await admin.press(SvcCb(action="up", id=created_id))
    session.expire_all()
    assert [s.title for s in await catalog.list_services(session)] == ["Перейменована", "Перша"]

    # delete with confirmation
    assert texts(await admin.press(SvcCb(action="del", id=created_id))) == ["Видалити цей вид перевезень?"]
    await admin.press(SvcCb(action="del_yes", id=created_id))
    session.expire_all()
    assert [s.id for s in await catalog.list_services(session)] == [first_id]
    assert not new_file.exists()


async def test_cancel_during_add_removes_uploaded_photo(make_chat, session):
    media_dir = get_settings().media_dir
    admin = make_chat(ADMIN_ID)
    before = set((media_dir / "services").glob("*")) if (media_dir / "services").exists() else set()

    await admin.press(SvcCb(action="add"))
    await admin.send_photo()
    assert len(set((media_dir / "services").glob("*")) - before) == 1

    await admin.say(BTN_CANCEL)

    assert set((media_dir / "services").glob("*")) == before
    assert await catalog.list_services(session) == []
