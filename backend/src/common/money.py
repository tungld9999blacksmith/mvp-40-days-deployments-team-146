"""VND amounts: computed as ``Decimal``, serialized as JSON numbers.

Specs show money as plain numbers (``"chargeableTotal": 1300000``); Pydantic would
otherwise emit ``Decimal`` as a string. Integral amounts become ``int`` so the
JSON never carries a spurious ``.00``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer


def _to_number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


Money = Annotated[Decimal, PlainSerializer(_to_number, return_type=int | float, when_used="json")]
