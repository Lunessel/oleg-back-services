import pytest
from sqlalchemy import select

from app.db.models import Lead
from app.services.leads import LeadDeliveryError, format_lead, submit_lead


def test_format_hero():
    text = format_lead("hero", {"from": "Львів", "to": "Київ", "phone": "+380671234567"})
    assert text == "<b>Заявка з головної форми</b>\nЗвідки: Львів\nКуди: Київ\nТелефон: +380671234567"


def test_format_calculator_maps_enum_values():
    text = format_lead(
        "calculator",
        {
            "name": "Олег",
            "phone": "0671234567",
            "serviceType": "intercity",
            "vanSize": "maxi",
            "loaders": "two",
            "route": "Львів — Одеса",
        },
    )
    assert text == (
        "<b>Заявка з калькулятора вартості</b>\n"
        "Ім'я: Олег\n"
        "Телефон: 0671234567\n"
        "Тип: Міжмісто\n"
        "Розмір буса: Maxi\n"
        "Вантажники: 2 вантажники\n"
        "Маршрут: Львів — Одеса"
    )


def test_format_callback_and_consult():
    payload = {"name": "Ira", "phone": "0671234567"}
    assert format_lead("callback", payload) == "<b>Замовлення дзвінка</b>\nІм'я: Ira\nТелефон: 0671234567"
    assert format_lead("services_consult", payload) == (
        "<b>Консультація щодо вантажу</b>\nІм'я: Ira\nТелефон: 0671234567"
    )


BOT_PAYLOAD = {
    "name": "Олег",
    "service": "Квартирні та офісні переїзди",
    "helpers_count": 2,
    "address_from": "вул. Зелена, 1",
    "address_to": "вул. Наукова, 7",
    "date": "05-10-2026",
    "time": "10:00",
    "phone": "+380671234567",
    "username": "oleg",
}


def test_format_bot_with_helpers_and_username():
    assert format_lead("bot", BOT_PAYLOAD) == (
        "<b>Заявка з Telegram-бота</b>\n"
        "Ім'я: Олег\n"
        "Послуга: Квартирні та офісні переїзди\n"
        "Вантажники: Так, кількість — 2\n"
        "Звідки: вул. Зелена, 1\n"
        "Куди: вул. Наукова, 7\n"
        "Дата: 05-10-2026\n"
        "Час: 10:00\n"
        "Телефон: +380671234567\n"
        "Telegram: @oleg"
    )


def test_format_bot_without_helpers_or_username():
    text = format_lead("bot", {**BOT_PAYLOAD, "helpers_count": 0, "username": None})
    assert "Вантажники: Ні" in text
    assert "Telegram:" not in text


def test_format_escapes_html_in_user_values():
    text = format_lead("callback", {"name": "<b>x</b> & y", "phone": "0671234567"})
    assert "Ім'я: &lt;b&gt;x&lt;/b&gt; &amp; y" in text


async def test_submit_lead_stores_and_marks_sent(session, sender):
    payload = {"name": "Ira", "phone": "0671234567"}

    lead = await submit_lead(session, sender, "callback", payload)

    assert sender.messages == ["<b>Замовлення дзвінка</b>\nІм'я: Ira\nТелефон: 0671234567"]
    stored = (await session.execute(select(Lead))).scalar_one()
    assert stored.id == lead.id
    assert (stored.source, stored.name, stored.phone, stored.payload) == ("callback", "Ira", "0671234567", payload)
    assert stored.sent_at is not None


async def test_submit_lead_without_name(session, sender):
    await submit_lead(session, sender, "hero", {"from": "A1", "to": "B2", "phone": "0671234567"})
    assert (await session.execute(select(Lead))).scalar_one().name is None


async def test_submit_lead_keeps_unsent_lead_when_delivery_fails(session, sender):
    sender.fail = True

    with pytest.raises(LeadDeliveryError) as excinfo:
        await submit_lead(session, sender, "callback", {"name": "Ira", "phone": "0671234567"})

    stored = (await session.execute(select(Lead))).scalar_one()
    assert stored.sent_at is None
    assert excinfo.value.lead_id == stored.id
