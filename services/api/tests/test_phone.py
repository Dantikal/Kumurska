import pytest

from app.core.phone import mask_phone, normalize_phone


@pytest.mark.parametrize(
    "raw",
    ["+996555123456", "+996 555 123 456", "996555123456", "0555123456", "555-12-34-56"],
)
def test_normalize_phone(raw: str) -> None:
    assert normalize_phone(raw) == "+996555123456"


@pytest.mark.parametrize("raw", ["+7 999 123 45 67", "12345", "+996 555 12 34", "abc", ""])
def test_normalize_phone_rejects(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_phone(raw)


def test_mask_phone() -> None:
    assert mask_phone("+996555123456") == "+996 *** *** 456"
