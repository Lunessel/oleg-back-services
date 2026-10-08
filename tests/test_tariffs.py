import pytest_asyncio

from app.db.models import TariffRow
from app.db.seed import SEED_TARIFF_ROWS
from app.services import tariffs


@pytest_asyncio.fixture
async def seeded(session):
    session.add_all(TariffRow(**row) for row in SEED_TARIFF_ROWS)
    await session.commit()
    return session


async def test_get_cards_groups_rows_in_static_order(seeded):
    cards = await tariffs.get_cards(seeded)

    assert [(c["id"], c["title"]) for c in cards] == [
        ("city", "Авто по місту"),
        ("intercity", "Авто за місто та по Україні"),
        ("loaders", "Послуги вантажників"),
    ]
    assert cards[0]["rows"] == [
        {"key": "city.min_order", "label": "Мінімальне замовлення (2 год)", "value": "від 800 грн"},
        {"key": "city.next_hour", "label": "Кожна наступна година", "value": "від 350 грн/год"},
    ]


async def test_get_cards_without_rows_returns_empty_cards(session):
    cards = await tariffs.get_cards(session)
    assert [c["rows"] for c in cards] == [[], [], []]


async def test_update_value_changes_only_value(seeded):
    row = await tariffs.update_value(seeded, "city.min_order", "від 900 грн")

    assert (row.label, row.value) == ("Мінімальне замовлення (2 год)", "від 900 грн")
    assert (await tariffs.get_row(seeded, "city.min_order")).value == "від 900 грн"


async def test_unknown_key(seeded):
    assert await tariffs.get_row(seeded, "nope") is None
    assert await tariffs.update_value(seeded, "nope", "x") is None
