"""
SkladBase — детермінований резолв магазину для card/crypto білінгу (Стадія 5b).

WayForPay (`orderReference`) і NOWPayments (`order_id`) не несуть структурованих
метаданих, як Stars-інвойс (payload). Тому кодуємо shop_id+plan_code+period
безпосередньо в рядок-референс, який провайдер повертає назад у вебхуку.
Підпис провайдера лишається межею довіри — ref лише визначає, ЯКОМУ магазину
зарахувати вже підтверджений платіж, а не підміняє перевірку підпису.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass

_SEPARATOR = "."
_VALID_PERIODS = ("month", "year")


class RefError(Exception):
    """Невалідний або нерозбірливий ref — викликач логує і ігнорує вебхук."""


@dataclass(frozen=True)
class ParsedRef:
    shop_id: int
    plan_code: str
    period: str


def build_ref(shop_id: int, plan_code: str, period: str) -> str:
    """`plan_code`/`period` не містять `.` (коди планів і "month"/"year"),
    тож роздільник безпечний. `nonce` лише для унікальності референсу між
    повторними чекаутами одного й того ж плану."""
    if period not in _VALID_PERIODS:
        raise RefError(f"невалідний period: {period!r}")
    nonce = secrets.token_hex(4)
    return _SEPARATOR.join((str(shop_id), plan_code, period, nonce))


def parse_ref(ref: str) -> ParsedRef:
    parts = ref.split(_SEPARATOR)
    if len(parts) != 4:
        raise RefError(f"невалідний формат ref: {ref!r}")

    shop_id_raw, plan_code, period, _nonce = parts
    try:
        shop_id = int(shop_id_raw)
    except ValueError as exc:
        raise RefError(f"невалідний shop_id у ref: {ref!r}") from exc

    if period not in _VALID_PERIODS:
        raise RefError(f"невалідний period у ref: {ref!r}")
    if not plan_code:
        raise RefError(f"відсутній plan_code у ref: {ref!r}")

    return ParsedRef(shop_id=shop_id, plan_code=plan_code, period=period)
