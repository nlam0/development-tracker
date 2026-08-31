"""Date parsing shared by adapters whose date fields aren't proper dates.

DOB NOW's Socrata `calendar_date` fields arrive as ISO datetime strings
(e.g. "2025-08-14T00:00:00.000"); DOB legacy's are `text` in MM/DD/YYYY
(Risk R5) and will need their own parser here when M8 builds that adapter.
"""

from datetime import date, datetime


def parse_iso_date(value: str | None) -> date | None:
    """Parse a Socrata calendar_date string ("YYYY-MM-DDTHH:MM:SS.mmm") to a date."""
    if not value:
        return None
    return datetime.fromisoformat(value).date()
