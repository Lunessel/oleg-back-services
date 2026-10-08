import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.deps import get_sender, get_session
from app.api.main import create_app
from app.db.models import Lead, TariffRow
from app.db.seed import SEED_TARIFF_ROWS
from app.services import catalog

AUTH = {"X-API-Key": "test-key"}
CALLBACK = {"source": "callback", "name": "Ira", "phone": "+38 (067) 123-45-67"}


@pytest_asyncio.fixture
async def client(session, sender):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_sender] = lambda: sender
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_services_are_ordered_with_public_image_urls(client, session):
    a = await catalog.create_service(session, title="A", items=["x"], image="services/a.jpg")
    b = await catalog.create_service(session, title="B", items=["y", "z"], image="https://cdn/b.jpg")
    await catalog.move_service(session, b.id, -1)

    response = await client.get("/api/services")

    assert response.status_code == 200
    assert response.json() == [
        {"id": b.id, "title": "B", "items": ["y", "z"], "image": "https://cdn/b.jpg"},
        {"id": a.id, "title": "A", "items": ["x"], "image": "http://backend.test/media/services/a.jpg"},
    ]


async def test_pricing_shape(client, session):
    session.add_all(TariffRow(**row) for row in SEED_TARIFF_ROWS)
    await session.commit()

    response = await client.get("/api/pricing")

    cards = response.json()["cards"]
    assert [c["id"] for c in cards] == ["city", "intercity", "loaders"]
    assert cards[1] == {
        "id": "intercity",
        "title": "Авто за місто та по Україні",
        "rows": [
            {"label": "Вартість за кілометр", "value": "від 18 грн/км"},
            {"label": "Розрахунок", "value": "в обидва боки або в один бік"},
        ],
    }


async def test_create_lead_stores_normalized_phone_and_sends(client, session, sender):
    response = await client.post("/api/leads", json=CALLBACK, headers=AUTH)

    assert response.status_code == 201
    assert response.json() == {"ok": True}
    lead = (await session.execute(select(Lead))).scalar_one()
    assert (lead.source, lead.phone, lead.payload) == (
        "callback",
        "+380671234567",
        {"name": "Ira", "phone": "+380671234567"},
    )
    assert sender.messages == ["<b>Замовлення дзвінка</b>\nІм'я: Ira\nТелефон: +380671234567"]


async def test_create_hero_lead_keeps_from_key(client, session, sender):
    body = {"source": "hero", "from": "Львів", "to": "Київ", "phone": "0671234567"}

    response = await client.post("/api/leads", json=body, headers=AUTH)

    assert response.status_code == 201
    lead = (await session.execute(select(Lead))).scalar_one()
    assert lead.payload == {"from": "Львів", "to": "Київ", "phone": "0671234567"}
    assert "Звідки: Львів" in sender.messages[0]


async def test_create_calculator_lead(client, sender):
    body = {
        "source": "calculator",
        "name": "Олег",
        "phone": "0671234567",
        "serviceType": "city",
        "vanSize": "small",
        "loaders": "more",
        "service": "Інша річ",
        "serviceIsCustom": True,
        "from": "Львів",
        "to": "Винники",
    }
    response = await client.post("/api/leads", json=body, headers=AUTH)
    assert response.status_code == 201
    assert "Розмір буса: Малий" in sender.messages[0]
    assert "Вантажники: 3+ вантажники" in sender.messages[0]
    assert "Послуга: Інша річ (вказано вручну)" in sender.messages[0]
    assert "Звідки: Львів\nКуди: Винники" in sender.messages[0]


async def test_calculator_lead_requires_service_and_addresses(client):
    body = {
        "source": "calculator",
        "name": "Олег",
        "phone": "0671234567",
        "serviceType": "city",
        "vanSize": "small",
        "loaders": "none",
        "route": "Львів",
    }
    assert (await client.post("/api/leads", json=body, headers=AUTH)).status_code == 422


async def test_lead_requires_api_key(client, sender):
    assert (await client.post("/api/leads", json=CALLBACK)).status_code == 401
    assert (await client.post("/api/leads", json=CALLBACK, headers={"X-API-Key": "wrong"})).status_code == 401
    assert sender.messages == []


async def test_lead_validation_errors(client):
    bad_phone = {**CALLBACK, "phone": "123"}
    bad_source = {**CALLBACK, "source": "unknown"}
    short_name = {**CALLBACK, "name": "I"}
    for body in (bad_phone, bad_source, short_name):
        assert (await client.post("/api/leads", json=body, headers=AUTH)).status_code == 422


async def test_lead_delivery_failure_returns_502_and_keeps_lead(client, session, sender):
    sender.fail = True

    response = await client.post("/api/leads", json=CALLBACK, headers=AUTH)

    assert response.status_code == 502
    assert (await session.execute(select(Lead))).scalar_one().sent_at is None
