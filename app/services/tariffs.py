from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TariffRow

CARDS = (
    ("city", "Авто по місту"),
    ("intercity", "Авто за місто та по Україні"),
    ("loaders", "Послуги вантажників"),
)
CARD_TITLES = dict(CARDS)


async def get_cards(session: AsyncSession) -> list[dict]:
    result = await session.execute(select(TariffRow).order_by(TariffRow.position, TariffRow.key))
    rows = list(result.scalars())
    return [
        {
            "id": card_id,
            "title": title,
            "rows": [{"key": r.key, "label": r.label, "value": r.value} for r in rows if r.card == card_id],
        }
        for card_id, title in CARDS
    ]


async def get_row(session: AsyncSession, key: str) -> TariffRow | None:
    return await session.get(TariffRow, key)


async def update_value(session: AsyncSession, key: str, value: str) -> TariffRow | None:
    row = await session.get(TariffRow, key)
    if row is None:
        return None
    row.value = value
    await session.commit()
    return row
