"""
Seeds the item catalog and a starting set of scrape sources on first boot.
Source URLs/keywords are carried over as data from
github.com/BT-Rajan/knpc-dashboard (main branch) config.py — see the
SOURCE_URLS / *_KEYWORDS constants in app/config.py for provenance.

Idempotent: only fills in sources for an item that currently has none, so
it never overwrites or duplicates anything an admin has since configured
by hand via the admin panel.
"""
import re

from app.db import SessionLocal
from app.models import Item, Source, ScrapeSetting, EmailTemplate
from app.config import (
    SEED_CATALOG, DEFAULT_SCRAPE_FREQUENCY_MINUTES,
    SOURCE_URLS, YAHOO_TICKERS,
    DUBAI_KEYWORDS, KEC_KEYWORDS, BRENT_KEYWORDS, WTI_KEYWORDS, OMAN_KEYWORDS,
    EIA_PRODUCT_SERIES,
)
from app.eia_client import series_data_url as eia_series_data_url

YAHOO_JSON_PATH = "chart.result.0.meta.regularMarketPrice"
OILPRICE_NEWS_SELECTOR = 'a[href*="oilprice.com"]'


def _keyword_regex(keywords: list[str], window: int = 350) -> str:
    """Case-insensitive: keyword, then (within `window` chars, tags and
    all) the first decimal number that looks like a price. Mirrors the
    old app's 'find keyword, then nearest plausible number' approach,
    expressed as a single regex against the raw response body."""
    alternation = "|".join(re.escape(k) for k in keywords)
    return rf"(?i)(?:{alternation})[\s\S]{{0,{window}}}?(\d{{2,4}}\.\d{{1,2}})"


def _add_source(db, item, name, url, source_type, value_selector, priority, news_selector=None):
    db.add(Source(
        item_id=item.id, name=name, url=url, source_type=source_type,
        value_selector=value_selector, news_selector=news_selector, priority=priority,
    ))


def _seed_sources_for_item(db, item):
    code = item.code

    if code in YAHOO_TICKERS:
        for i, ticker in enumerate(YAHOO_TICKERS[code], start=1):
            _add_source(
                db, item, f"Yahoo Finance ({ticker})",
                SOURCE_URLS["yahoo_chart"].format(symbol=ticker),
                "json_path", YAHOO_JSON_PATH, priority=i,
            )
        next_priority = len(YAHOO_TICKERS[code]) + 1
        fallback_keywords = {"BRENT": BRENT_KEYWORDS, "WTI": WTI_KEYWORDS, "OMAN": OMAN_KEYWORDS}[code]
        _add_source(
            db, item, "OilPrice.com (fallback)", SOURCE_URLS["oilprice_charts"],
            "regex", _keyword_regex(fallback_keywords), priority=next_priority,
            news_selector=OILPRICE_NEWS_SELECTOR,
        )
        return

    if code == "KEC":
        _add_source(
            db, item, "KPC Official", SOURCE_URLS["kpc_oil_prices"],
            "regex", r"(?i)KEC[\s\S]{0,400}?(\d{2,3}\.\d{1,2})", priority=1,
        )
        _add_source(
            db, item, "OilPrice.com (fallback)", SOURCE_URLS["oilprice_charts"],
            "regex", _keyword_regex(KEC_KEYWORDS), priority=2,
            news_selector=OILPRICE_NEWS_SELECTOR,
        )
        return

    if code == "DUBAI":
        chain = ["tradingeconomics_energy", "oilprice_charts", "investing_commodities"]
        for i, src_key in enumerate(chain, start=1):
            _add_source(
                db, item, src_key.replace("_", " ").title(), SOURCE_URLS[src_key],
                "regex", _keyword_regex(DUBAI_KEYWORDS), priority=i,
                news_selector=OILPRICE_NEWS_SELECTOR if src_key == "oilprice_charts" else None,
            )
        return

    if code in EIA_PRODUCT_SERIES:
        series_id = EIA_PRODUCT_SERIES[code]["series"]
        _add_source(
            db, item, "EIA Open Data (petroleum/pri/spt)",
            eia_series_data_url(series_id),
            "eia_api", series_id, priority=1,
        )
        # Same public-page fallback the crude benchmarks use, keyed off the
        # product's own name -- keeps a second source in the chain if the
        # EIA API is briefly unreachable, consistent with every other item.
        _add_source(
            db, item, "OilPrice.com (fallback)", SOURCE_URLS["oilprice_charts"],
            "regex", _keyword_regex([item.name.split(" (")[0]]), priority=2,
            news_selector=OILPRICE_NEWS_SELECTOR,
        )
        return


def _seed_email_templates(db):
    defaults = [
        (
            "Quarterly Report",
            "{{quarter}} {{year}} KNPC Market Intelligence Report",
            "<p>Dear {{recipient_name}},</p>"
            "<p>Please find attached the {{quarter}} {{year}} Market Intelligence Report "
            "for the Marketing Operations Group.</p>"
            "<p>Regards,<br>KNPC Market Intelligence Dashboard</p>",
        ),
        (
            "Price Alert",
            "KNPC Price Alert: {{item_name}}",
            "<p>Dear {{recipient_name}},</p>"
            "<p>{{item_name}} moved to {{price}} {{unit}} ({{change_pct}}% change).</p>"
            "<p>Regards,<br>KNPC Market Intelligence Dashboard</p>",
        ),
    ]
    for name, subject, body_html in defaults:
        if not db.query(EmailTemplate).filter(EmailTemplate.name == name).first():
            db.add(EmailTemplate(name=name, subject=subject, body_html=body_html))


def seed():
    db = SessionLocal()
    try:
        if not db.query(ScrapeSetting).first():
            db.add(ScrapeSetting(frequency_minutes=DEFAULT_SCRAPE_FREQUENCY_MINUTES))

        _seed_email_templates(db)

        for category, items in SEED_CATALOG.items():
            for spec in items:
                item = db.query(Item).filter(Item.code == spec["code"]).first()
                if not item:
                    item = Item(code=spec["code"], name=spec["name"], category=category, unit=spec["unit"])
                    db.add(item)
                    db.flush()

                has_sources = db.query(Source).filter(Source.item_id == item.id).first() is not None
                if not has_sources:
                    _seed_sources_for_item(db, item)

        db.commit()
    finally:
        db.close()
