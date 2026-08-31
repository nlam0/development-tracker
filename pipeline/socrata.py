"""Shared Socrata client: app-token auth, deterministic paging, retry with backoff.

Every pipeline/sources/*.py adapter fetches through this rather than calling
requests directly, so paging and retry behavior stay consistent (Risk R9:
$offset paging over a dataset written concurrently can skip or duplicate
rows unless every page is ordered on a stable key).
"""

import time
from collections.abc import Iterator

import requests

BASE_URL = "https://data.cityofnewyork.us/resource"
PAGE_SIZE = 1000
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 2


class SocrataError(RuntimeError):
    pass


def fetch_all(
    dataset_id: str,
    *,
    select: str,
    order: str,
    where: str | None = None,
    app_token: str | None = None,
    page_size: int = PAGE_SIZE,
) -> Iterator[dict]:
    """Yield every row matching the query, paging deterministically.

    `order` must reference a stable, sufficiently unique key so pagination
    is deterministic even if the underlying dataset is being written to.
    """
    headers = {"X-App-Token": app_token} if app_token else {}
    offset = 0
    while True:
        params = {
            "$select": select,
            "$order": order,
            "$limit": page_size,
            "$offset": offset,
        }
        if where:
            params["$where"] = where
        page = _get_with_retry(dataset_id, params, headers)
        if not page:
            return
        yield from page
        if len(page) < page_size:
            return
        offset += page_size


def _get_with_retry(dataset_id: str, params: dict, headers: dict) -> list[dict]:
    url = f"{BASE_URL}/{dataset_id}.json"
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise SocrataError(f"{resp.status_code} from {dataset_id}: {resp.text[:200]}")
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, SocrataError) as exc:
            last_error = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(BACKOFF_BASE_SECONDS * (2**attempt))
    raise SocrataError(f"exhausted retries fetching {dataset_id}") from last_error
