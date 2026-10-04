import pytest

from app.services.phone import normalize_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+38 (067) 123-45-67", "+380671234567"),
        ("+380671234567", "+380671234567"),
        ("0671234567", "0671234567"),
        ("380671234567", "+380671234567"),
        ("067 123 45 67", "0671234567"),
    ],
)
def test_valid_numbers(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "12345", "+38067123456", "+3806712345678", "hello", "+1 202 555 0100"])
def test_invalid_numbers(raw):
    assert normalize_phone(raw) is None
