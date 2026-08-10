"""Shared building blocks for every schema family.

`Money`, `PhoneNumber` and `Password` are annotated types rather than per-field
validators or serialisers. Attaching the behaviour to the type means a field
cannot opt out of it by omission: a money field typed `Money` cannot be
serialised as a JSON float, and a phone typed `PhoneNumber` cannot skip
normalisation.
"""

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    PlainSerializer,
    model_validator,
)
from pydantic.functional_validators import AfterValidator, BeforeValidator

# Uzbek mobile numbers: +998 followed by exactly nine digits.
E164_UZ = re.compile(r"^\+998\d{9}$")

TWO_PLACES = Decimal("0.01")


def _money_to_str(value: Decimal) -> str:
    """Two decimal places, as a string.

    JSON has one numeric type and it is a binary float. Serialising money as a
    number means the client parses 45000.00 into something that may not compare
    equal to itself after a round trip, which is how totals drift by a tiyin.
    """
    return str(value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP))


Money = Annotated[Decimal, PlainSerializer(_money_to_str, return_type=str)]


def _normalise_phone(value: Any) -> Any:
    """Strip formatting, add the country code, then insist on E.164.

    Accepts the shapes a person actually types — `90 123 45 67`,
    `+998 90 123-45-67`, `998901234567` — and rejects everything else rather than
    storing a number that cannot receive an SMS.
    """
    if not isinstance(value, str):
        return value

    digits = re.sub(r"[\s\-()]", "", value.strip())
    if digits.startswith("00"):
        digits = f"+{digits[2:]}"
    if not digits.startswith("+"):
        if digits.startswith("998"):
            digits = f"+{digits}"
        elif len(digits) == 9:
            digits = f"+998{digits}"
    return digits


def _check_phone(value: str) -> str:
    if not E164_UZ.match(value):
        raise ValueError("Telefon raqami +998XXXXXXXXX ko'rinishida bo'lishi kerak")
    return value


PhoneNumber = Annotated[str, BeforeValidator(_normalise_phone), AfterValidator(_check_phone)]


PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


def _check_password(value: str) -> str:
    """Length only, with our own message.

    `Field(min_length=...)` would enforce the same rule but report it in English,
    and this string reaches the user.
    """
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Parol kamida {PASSWORD_MIN_LENGTH} ta belgidan iborat bo'lishi kerak")
    if len(value) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Parol {PASSWORD_MAX_LENGTH} ta belgidan uzun bo'lmasligi kerak")
    return value


Password = Annotated[str, AfterValidator(_check_password)]


# `from_attributes` is what lets a service hand an ORM object or a repository
# dataclass straight to `model_validate`.
class ReadSchema(BaseModel):
    """Barcha javob sxemalari uchun asos."""

    model_config = ConfigDict(from_attributes=True)


class UpdateSchema(BaseModel):
    """Barcha tahrirlash sxemalari uchun asos.

    Har bir maydon ixtiyoriy. Bo'sh so'rov 422 qaytaradi — jimgina hech narsa
    o'zgartirmaslik o'rniga.
    """

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _reject_empty_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Kamida bitta maydon yuborilishi kerak")
        return self
