from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_sender, get_session, require_api_key
from app.api.schemas import LeadRequest, PricingOut, ServiceOut
from app.config import Settings, get_settings
from app.services import catalog, media, tariffs
from app.services.leads import LeadDeliveryError, Sender, submit_lead

router = APIRouter(prefix="/api")


@router.get("/services", response_model=list[ServiceOut])
async def list_services(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    return [
        ServiceOut(
            id=service.id,
            title=service.title,
            items=service.items,
            image=media.public_url(settings.public_base_url, service.image),
        )
        for service in await catalog.list_services(session)
    ]


@router.get("/pricing", response_model=PricingOut)
async def get_pricing(session: AsyncSession = Depends(get_session)):
    return {"cards": await tariffs.get_cards(session)}


@router.post("/leads", status_code=201, dependencies=[Depends(require_api_key)])
async def create_lead(
    body: LeadRequest,
    session: AsyncSession = Depends(get_session),
    send: Sender = Depends(get_sender),
):
    lead = body.root
    payload = lead.model_dump(by_alias=True, exclude={"source"})
    try:
        await submit_lead(session, send, lead.source, payload)
    except LeadDeliveryError:
        raise HTTPException(status_code=502, detail="Не вдалося надіслати заявку")
    return {"ok": True}
