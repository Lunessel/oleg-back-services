from aiogram.fsm.state import State, StatesGroup


class OrderForm(StatesGroup):
    name = State()
    service = State()
    helpers_needed = State()
    helpers_count = State()
    address_from = State()
    address_to = State()
    date = State()
    time = State()
    phone = State()


class AdminService(StatesGroup):
    new_photo = State()
    new_title = State()
    new_items = State()
    edit_photo = State()
    edit_title = State()
    edit_items = State()


class AdminTariff(StatesGroup):
    value = State()
