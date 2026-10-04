from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Service


def parse_items(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


async def list_services(session: AsyncSession) -> list[Service]:
    result = await session.execute(select(Service).order_by(Service.position, Service.id))
    return list(result.scalars())


async def get_service(session: AsyncSession, service_id: int) -> Service | None:
    return await session.get(Service, service_id)


async def create_service(session: AsyncSession, *, title: str, items: list[str], image: str) -> Service:
    last = await session.scalar(select(func.max(Service.position)))
    service = Service(title=title, items=items, image=image, position=0 if last is None else last + 1)
    session.add(service)
    await session.commit()
    return service


async def update_service(
    session: AsyncSession,
    service_id: int,
    *,
    title: str | None = None,
    items: list[str] | None = None,
    image: str | None = None,
) -> Service | None:
    service = await session.get(Service, service_id)
    if service is None:
        return None
    if title is not None:
        service.title = title
    if items is not None:
        service.items = items
    if image is not None:
        service.image = image
    await session.commit()
    return service


async def delete_service(session: AsyncSession, service_id: int) -> Service | None:
    service = await session.get(Service, service_id)
    if service is None:
        return None
    await session.delete(service)
    await session.commit()
    return service


async def move_service(session: AsyncSession, service_id: int, direction: int) -> bool:
    services = await list_services(session)
    index = next((i for i, s in enumerate(services) if s.id == service_id), None)
    if index is None:
        return False
    target = index + direction
    if target < 0 or target >= len(services):
        return False
    current, neighbour = services[index], services[target]
    current.position, neighbour.position = neighbour.position, current.position
    await session.commit()
    return True
