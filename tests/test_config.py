from app.config import Settings, get_settings


def test_admin_ids_parsed_from_comma_separated_string():
    assert get_settings().admin_ids == [11, 22]


def test_admin_ids_empty_string_gives_empty_list(monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "")
    assert Settings().admin_ids == []


def test_leads_chat_id_is_int():
    assert get_settings().leads_chat_id == -1001
