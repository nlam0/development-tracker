"""Pure tests for the digest window boundary -- no network or DB.

Regression cover for a real production/local discrepancy: the same digest
reported 20 new permits from a local uvicorn (Eastern) and 16 from the
Vercel function (UTC), against the same database. The boundary was
`date.today()`, which resolves in whatever timezone the process happens to
run in, so the two environments computed different window start dates and
the permits dated on the boundary day fell in or out accordingly.

The window is anchored to the current date in New York because
`permits.event_date` holds NYC calendar dates -- so these assert the
anchor is NYC, not merely "not local".
"""

import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from api.routers.stats import WINDOW_DAYS, window_start

NYC = ZoneInfo("America/New_York")


@pytest.fixture
def process_timezone():
    """Run a test body under a given TZ, restoring the original after.

    Mutates process-global state (time.tzset), so it always restores --
    otherwise it would leak into unrelated tests via date.today().
    """
    original = os.environ.get("TZ")

    def _set(tz: str):
        os.environ["TZ"] = tz
        time.tzset()

    yield _set

    if original is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = original
    time.tzset()


@pytest.mark.parametrize("window_days", WINDOW_DAYS)
def test_window_start_is_nyc_today_minus_window(window_days):
    assert window_start(window_days) == datetime.now(NYC).date() - timedelta(days=window_days)


@pytest.mark.parametrize("tz", ["UTC", "America/New_York", "Asia/Tokyo", "America/Los_Angeles"])
def test_window_start_does_not_depend_on_the_process_timezone(tz, process_timezone):
    """The bug: a UTC server and an Eastern server disagreed on the window."""
    expected = datetime.now(NYC).date() - timedelta(days=7)
    process_timezone(tz)
    assert window_start(7) == expected


def test_window_start_is_not_naive_local_date(process_timezone):
    """Under a timezone whose date differs from New York's, the naive
    `date.today()` this replaced would diverge -- assert we don't."""
    from datetime import date

    process_timezone("Asia/Tokyo")
    # Tokyo is far enough ahead that its date differs from NYC's for most
    # of the day; when it does, the old implementation was wrong.
    if date.today() != datetime.now(NYC).date():
        assert window_start(7) != date.today() - timedelta(days=7)
    assert window_start(7) == datetime.now(NYC).date() - timedelta(days=7)
