import re

from app.services import media


def test_is_local():
    assert media.is_local("services/a.jpg") is True
    assert media.is_local("https://images.unsplash.com/x") is False
    assert media.is_local("http://example.com/x.jpg") is False


def test_new_image_name_is_unique_and_under_services():
    first, second = media.new_image_name(), media.new_image_name()
    assert re.fullmatch(r"services/[0-9a-f]{32}\.jpg", first)
    assert first != second


def test_public_url():
    assert media.public_url("http://api.test/", "services/a.jpg") == "http://api.test/media/services/a.jpg"
    assert media.public_url("http://api.test", "https://cdn/x.jpg") == "https://cdn/x.jpg"


def test_delete_image_removes_local_file(tmp_path):
    target = media.image_path(tmp_path, "services/a.jpg")
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x")

    media.delete_image(tmp_path, "services/a.jpg")

    assert not target.exists()


def test_delete_image_ignores_urls_and_missing_files(tmp_path):
    media.delete_image(tmp_path, "https://cdn/x.jpg")
    media.delete_image(tmp_path, "services/missing.jpg")
