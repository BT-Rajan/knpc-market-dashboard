"""
Client for the EIA (U.S. Energy Information Administration) Open Data API v2
-- https://www.eia.gov/opendata/browser/petroleum/pri/spt

Used for the four "Products" catalog items (Conventional Gasoline, ULSD,
Kerosene-Type Jet Fuel, Propane), sourced from EIA's daily petroleum spot
price series instead of the old scrape-and-regex fallback chain.

Design notes:
- The series IDs in EIA_PRODUCT_SERIES (config.py) are EIA's own published
  codes for these exact product/location pairs (e.g. RWTC = WTI Cushing is
  the same style of ID, just for crude). They're stable and rarely change,
  but if EIA ever retires/renames one, a hardcoded ID would silently start
  failing. So fetch_latest_value() self-heals: if the configured series ID
  returns no rows, it falls back to resolve_series_id(), which searches
  EIA's own series metadata for the best name match on product + location
  keywords and logs the ID it found -- so a bad hardcoded value degrades to
  "slower + logged" instead of "broken".
- The API key is read from app.config.EIA_API_KEY (env var), never stored
  in the Source.url the way scrape URLs are -- it's injected onto the
  request at fetch time so it never lands in the admin-visible sources
  table or scrape logs.
"""
import logging
from typing import Optional
from urllib.parse import urlencode, urlparse, parse_qs

import requests

from app.config import EIA_API_KEY, EIA_API_BASE_URL, EIA_SCRAPE_REQUEST_TIMEOUT

logger = logging.getLogger("knpc.eia")


class EiaError(Exception):
    pass


def _get(path: str, params: dict) -> dict:
    if not EIA_API_KEY:
        raise EiaError(
            "EIA_API_KEY is not configured (set it in backend/.env). "
            "Get a free key at https://www.eia.gov/opendata/register.php"
        )
    url = f"{EIA_API_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    query = {"api_key": EIA_API_KEY, **params}
    resp = requests.get(url, params=query, timeout=EIA_SCRAPE_REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def series_data_url(series_id: str) -> str:
    """Build a (key-less) EIA data endpoint URL for a given series, for
    storage in Source.url. The api_key is intentionally NOT included here --
    fetch_source_response() injects it at request time, so it never appears
    in the admin-visible sources table or scrape logs."""
    params = {
        "frequency": "daily",
        "data[0]": "value",
        "facets[series][]": series_id,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "offset": 0,
        "length": 1,
    }
    return f"{EIA_API_BASE_URL.rstrip('/')}/petroleum/pri/spt/data/?{urlencode(params)}"


def fetch_source_response(url: str) -> requests.Response:
    """Fetch a Source.url built by series_data_url(), injecting the API key
    at request time. Used by scraper/runner.py for source_type == 'eia_api'."""
    if not EIA_API_KEY:
        raise EiaError(
            "EIA_API_KEY is not configured (set it in backend/.env). "
            "Get a free key at https://www.eia.gov/opendata/register.php"
        )
    sep = "&" if "?" in url else "?"
    resp = requests.get(f"{url}{sep}api_key={EIA_API_KEY}", timeout=EIA_SCRAPE_REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp


def _latest_value_for_series(series_id: str) -> Optional[float]:
    data = _get(
        "petroleum/pri/spt/data/",
        {
            "frequency": "daily",
            "data[0]": "value",
            "facets[series][]": series_id,
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "offset": 0,
            "length": 1,
        },
    )
    rows = data.get("response", {}).get("data", [])
    if not rows:
        return None
    raw = rows[0].get("value")
    if raw is None or raw == "":
        return None
    return float(raw)


def resolve_series_id(product_keyword: str, location_keyword: str) -> Optional[str]:
    """Search EIA's own series metadata for the daily spot-price series whose
    name best matches both a product keyword (e.g. 'conventional gasoline')
    and a location keyword (e.g. 'gulf coast'). Used as a fallback when a
    hardcoded series ID stops returning data (EIA renames/retires a code)."""
    try:
        data = _get("petroleum/pri/spt/facet/series", {})
    except Exception as exc:
        logger.warning("EIA series metadata lookup failed: %s", exc)
        return None

    facets = data.get("response", {}).get("facets", [])
    product_kw = product_keyword.lower()
    location_kw = location_keyword.lower()

    best_id, best_score = None, 0
    for f in facets:
        name = (f.get("name") or "").lower()
        if "daily" not in name and "spot" not in name and True:
            pass  # this route is spot-price-only already; no extra filter needed
        score = 0
        if product_kw in name:
            score += 2
        if location_kw in name:
            score += 2
        if score > best_score:
            best_score, best_id = score, f.get("id")

    if best_id:
        logger.info(
            "EIA series resolved by name match: '%s' + '%s' -> %s",
            product_keyword, location_keyword, best_id,
        )
    return best_id


def fetch_latest_value(series_id: str, product_keyword: str = "", location_keyword: str = "") -> float:
    """Latest daily spot price for series_id. Falls back to a name-based
    metadata search if the configured series_id returns nothing and keywords
    were supplied."""
    value = _latest_value_for_series(series_id)
    if value is not None:
        return value

    if not (product_keyword and location_keyword):
        raise EiaError(f"No EIA series data for '{series_id}'")

    logger.warning(
        "EIA series '%s' returned no data -- attempting to re-resolve by name "
        "('%s' / '%s'). If this keeps happening, update EIA_PRODUCT_SERIES "
        "in config.py with the ID logged below.",
        series_id, product_keyword, location_keyword,
    )
    resolved_id = resolve_series_id(product_keyword, location_keyword)
    if not resolved_id:
        raise EiaError(f"No EIA series data for '{series_id}' and no name-match fallback found")

    value = _latest_value_for_series(resolved_id)
    if value is None:
        raise EiaError(f"Resolved EIA series '{resolved_id}' also returned no data")
    return value


def fetch_price_from_source_url(url: str, fallback_query: Optional[tuple] = None) -> float:
    """Entry point used by scraper/runner.py for source_type == 'eia_api'.
    Reads the series ID straight out of the Source.url's facets[series][]
    query param (so admins can repoint a source at a different EIA series
    from the admin panel like any other source), and falls back to
    resolve_series_id() using fallback_query = (product_keyword,
    location_keyword) if that series comes back empty."""
    series_ids = parse_qs(urlparse(url).query).get("facets[series][]")
    if not series_ids:
        raise EiaError(f"Source URL has no facets[series][] param: {url}")
    series_id = series_ids[0]
    product_kw, location_kw = fallback_query if fallback_query else ("", "")
    return fetch_latest_value(series_id, product_kw, location_kw)
