from datetime import datetime
from types import SimpleNamespace

from app.bot.admin_kb import SvcCb, TarCb
from app.bot.filters import IsAdmin
from app.bot.handlers.admin_services import card_text
from app.bot.handlers.admin_tariffs import tariff_card_text
from app.bot.handlers.order import date_options, parse_helpers_count, time_options
from app.config import get_settings


def test_date_options_are_seven_days_from_today():
    options = date_options(datetime(2026, 10, 29, 9, 15))
    assert options == [
        "29-10-2026", "30-10-2026", "31-10-2026", "01-11-2026", "02-11-2026", "03-11-2026", "04-11-2026",
    ]


def test_date_options_start_tomorrow_after_last_hour_began():
    assert date_options(datetime(2026, 10, 29, 19, 59))[0] == "29-10-2026"
    assert date_options(datetime(2026, 10, 29, 20, 0))[0] == "30-10-2026"
    assert len(date_options(datetime(2026, 10, 29, 23, 0))) == 7


def test_time_options_for_another_day_cover_working_hours():
    options = time_options("30-10-2026", datetime(2026, 10, 29, 15, 0))
    assert options[0] == "8:00"
    assert options[-1] == "20:00"
    assert len(options) == 13


def test_time_options_for_today_only_upcoming_hours():
    assert time_options("29-10-2026", datetime(2026, 10, 29, 14, 30)) == [
        "15:00", "16:00", "17:00", "18:00", "19:00", "20:00",
    ]
    assert time_options("29-10-2026", datetime(2026, 10, 29, 6, 0))[0] == "8:00"
    assert time_options("29-10-2026", datetime(2026, 10, 29, 20, 5)) == []


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
