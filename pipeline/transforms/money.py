"""Cost-field parsing shared by adapters whose money fields arrive as text.

Risk R5: `estimated_job_costs` is `text` in DOB NOW. An unparseable value
must become NULL, never a guessed zero -- a zero would corrupt the research
digest's total-cost aggregate (PRD §7E) by silently understating spend
instead of admitting the figure is unknown.
"""

from decimal import Decimal, InvalidOperation


def parse_cost(value: str | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"unparseable cost: {value!r}") from exc
