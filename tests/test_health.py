from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import create_app


async def test_health():
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_models_create_tables(session):
    result = await session.execute(
        text("select table_name from information_schema.tables where table_schema = 'public'")
    )
    assert {"services", "tariff_rows", "leads"} <= {row[0] for row in result}
