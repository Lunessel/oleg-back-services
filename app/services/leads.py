import html
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lead

logger = logging.getLogger(__name__)

Sender = Callable[[str], Awaitable[None]]


class LeadDeliveryError(Exception):
    def __init__(self, lead_id: int) -> None:
        super().__init__(f"lead {lead_id} was stored but not delivered")
        self.lead_id = lead_id


SOURCE_LABELS = {
    "hero": "Заявка з головної форми",
    "calculator": "Заявка з калькулятора вартості",
    "callback": "Замовлення дзвінка",
    "services_consult": "Консультація щодо вантажу",
    "bot": "Заявка з Telegram-бота",
}

SERVICE_TYPE_LABELS = {"city": "По місту", "intercity": "Міжмісто"}
VAN_SIZE_LABELS = {"small": "Малий", "medium": "Середній", "maxi": "Maxi"}
LOADERS_LABELS = {
    "none": "Без вантажників",
    "one": "1 вантажник",
    "two": "2 вантажники",
    "more": "3+ вантажники",
}


def _e(value: object) -> str:
    return html.escape(str(value))


def format_lead(source: str, payload: dict) -> str:
    lines = [f"<b>{SOURCE_LABELS[source]}</b>"]

    if source == "hero":
        lines += [
            f"Звідки: {_e(payload['from'])}",
            f"Куди: {_e(payload['to'])}",
            f"Телефон: {_e(payload['phone'])}",
        ]
    elif source == "calculator":
        lines += [
            f"Ім'я: {_e(payload['name'])}",
            f"Телефон: {_e(payload['phone'])}",
            f"Напрямок: {SERVICE_TYPE_LABELS[payload['serviceType']]}",
            f"Розмір буса: {VAN_SIZE_LABELS[payload['vanSize']]}",
            f"Вантажники: {LOADERS_LABELS[payload['loaders']]}",
            f"Послуга: {_e(payload['service'])}" + (" (вказано вручну)" if payload.get("serviceIsCustom") else ""),
            f"Звідки: {_e(payload['from'])}",
            f"Куди: {_e(payload['to'])}",
        ]
    elif source == "bot":
        count = payload.get("helpers_count") or 0
        helpers = f"Так, кількість — {count}" if count else "Ні"
        lines += [
            f"Ім'я: {_e(payload['name'])}",
            f"Послуга: {_e(payload['service'])}",
            f"Вантажники: {helpers}",
            f"Звідки: {_e(payload['address_from'])}",
            f"Куди: {_e(payload['address_to'])}",
            f"Дата: {_e(payload['date'])}",
            f"Час: {_e(payload['time'])}",
            f"Телефон: {_e(payload['phone'])}",
        ]
        if payload.get("username"):
            lines.append(f"Telegram: @{_e(payload['username'])}")
    else:  # callback, services_consult
        lines += [f"Ім'я: {_e(payload['name'])}", f"Телефон: {_e(payload['phone'])}"]

    return "\n".join(lines)


async def submit_lead(session: AsyncSession, send: Sender, source: str, payload: dict) -> Lead:
    lead = Lead(source=source, name=payload.get("name"), phone=payload["phone"], payload=payload)
    session.add(lead)
    await session.commit()

    try:
        await send(format_lead(source, payload))
    except Exception as exc:
        logger.exception("Failed to deliver lead %s", lead.id)
        raise LeadDeliveryError(lead.id) from exc

    lead.sent_at = datetime.now(timezone.utc)
    await session.commit()
    return lead
