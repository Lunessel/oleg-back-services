from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_ORDER = "Залишити заявку"
BTN_ADMIN = "Адмін-панель"
BTN_CANCEL = "Скасувати"
BTN_OTHER = "Інше"
BTN_YES = "Так"
BTN_NO = "Ні"
BTN_CONTACT = "Надіслати номер телефону"


def _markup(rows: list[list[KeyboardButton]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def main_menu(is_admin: bool) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=BTN_ORDER)]]
    if is_admin:
        rows.append([KeyboardButton(text=BTN_ADMIN)])
    return _markup(rows)


def cancel_kb() -> ReplyKeyboardMarkup:
    return _markup([[KeyboardButton(text=BTN_CANCEL)]])


def options_kb(options: list[str]) -> ReplyKeyboardMarkup:
    return _markup([[KeyboardButton(text=option)] for option in options] + [[KeyboardButton(text=BTN_CANCEL)]])


def yes_no_kb() -> ReplyKeyboardMarkup:
    return _markup([[KeyboardButton(text=BTN_YES), KeyboardButton(text=BTN_NO)], [KeyboardButton(text=BTN_CANCEL)]])


def contact_kb() -> ReplyKeyboardMarkup:
    return _markup([[KeyboardButton(text=BTN_CONTACT, request_contact=True)], [KeyboardButton(text=BTN_CANCEL)]])
