import re

_KG_LOCAL_DIGITS = 9


def normalize_phone(raw: str) -> str:
    """Приводит номер Кыргызстана к виду +996XXXXXXXXX.

    Принимает варианты «+996 555 123 456», «996555123456», «0555123456», «555123456».
    Для всего остального бросает ValueError.
    """
    digits = re.sub(r"[\s\-()]", "", raw)
    if digits.startswith("+"):
        digits = digits[1:]
        if not digits.startswith("996"):
            raise ValueError("Поддерживаются только номера Кыргызстана (+996)")
    if not digits.isdigit():
        raise ValueError("Номер может содержать только цифры")

    if len(digits) == 3 + _KG_LOCAL_DIGITS and digits.startswith("996"):
        local = digits[3:]
    elif len(digits) == 1 + _KG_LOCAL_DIGITS and digits.startswith("0"):
        local = digits[1:]
    elif len(digits) == _KG_LOCAL_DIGITS:
        local = digits
    else:
        raise ValueError("Неверный формат номера, ожидается +996XXXXXXXXX")
    return f"+996{local}"


def mask_phone(phone: str) -> str:
    """+996555123456 → +996 *** *** 456"""
    return f"{phone[:4]} *** *** {phone[-3:]}"
