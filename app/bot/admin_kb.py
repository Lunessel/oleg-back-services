from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.tariffs import CARDS


class SvcCb(CallbackData, prefix="svc"):
    action: str
    id: int = 0


class TarCb(CallbackData, prefix="tar"):
    action: str
    key: str = ""


def _button(text: str, callback: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback.pack())


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("Види перевезень", SvcCb(action="list"))],
            [_button("Тарифи", TarCb(action="cards"))],
        ]
    )


def services_list_kb(services) -> InlineKeyboardMarkup:
    rows = [[_button(service.title, SvcCb(action="view", id=service.id))] for service in services]
    rows.append([_button("➕ Додати", SvcCb(action="add"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def service_card_kb(service_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("Фото", SvcCb(action="photo", id=service_id)),
                _button("Назва", SvcCb(action="title", id=service_id)),
                _button("Пункти", SvcCb(action="items", id=service_id)),
            ],
            [
                _button("↑", SvcCb(action="up", id=service_id)),
                _button("↓", SvcCb(action="down", id=service_id)),
            ],
            [_button("Видалити", SvcCb(action="del", id=service_id))],
            [_button("« Назад", SvcCb(action="list"))],
        ]
    )


def delete_confirm_kb(service_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("Так, видалити", SvcCb(action="del_yes", id=service_id)),
                _button("Ні", SvcCb(action="view", id=service_id)),
            ]
        ]
    )


def tariff_cards_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_button(title, TarCb(action="card", key=card_id))] for card_id, title in CARDS]
    )


def tariff_card_kb(card: dict) -> InlineKeyboardMarkup:
    rows = [[_button(row["label"], TarCb(action="row", key=row["key"]))] for row in card["rows"]]
    rows.append([_button("« Назад", TarCb(action="cards"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)
