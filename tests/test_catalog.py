from app.services import catalog


async def _make(session, *titles):
    return [await catalog.create_service(session, title=t, items=["a"], image=f"{t}.jpg") for t in titles]


async def _titles(session):
    return [s.title for s in await catalog.list_services(session)]


def test_parse_items_splits_lines_and_drops_blanks():
    assert catalog.parse_items("  one \n\n two\n   \nthree") == ["one", "two", "three"]
    assert catalog.parse_items("  \n ") == []


async def test_create_appends_to_the_end(session):
    await _make(session, "A", "B", "C")
    assert await _titles(session) == ["A", "B", "C"]


async def test_get_service(session):
    (a,) = await _make(session, "A")
    assert (await catalog.get_service(session, a.id)).title == "A"
    assert await catalog.get_service(session, 999) is None


async def test_update_changes_only_given_fields(session):
    (a,) = await _make(session, "A")

    updated = await catalog.update_service(session, a.id, items=["x", "y"])

    assert (updated.title, updated.items, updated.image) == ("A", ["x", "y"], "A.jpg")
    assert await catalog.update_service(session, 999, title="Z") is None


async def test_delete_returns_deleted_row(session):
    a, b = await _make(session, "A", "B")

    deleted = await catalog.delete_service(session, a.id)

    assert deleted.image == "A.jpg"
    assert await _titles(session) == ["B"]
    assert await catalog.delete_service(session, 999) is None


async def test_move_swaps_with_neighbour(session):
    a, b, c = await _make(session, "A", "B", "C")

    assert await catalog.move_service(session, c.id, -1) is True
    assert await _titles(session) == ["A", "C", "B"]

    assert await catalog.move_service(session, a.id, 1) is True
    assert await _titles(session) == ["C", "A", "B"]


async def test_move_at_edges_does_nothing(session):
    a, b = await _make(session, "A", "B")

    assert await catalog.move_service(session, a.id, -1) is False
    assert await catalog.move_service(session, b.id, 1) is False
    assert await catalog.move_service(session, 999, 1) is False
    assert await _titles(session) == ["A", "B"]


async def test_create_after_delete_still_goes_last(session):
    a, b = await _make(session, "A", "B")
    await catalog.delete_service(session, a.id)
    await _make(session, "C")
    assert await _titles(session) == ["B", "C"]
