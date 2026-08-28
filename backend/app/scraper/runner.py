from datetime import datetime, date
import logging

from sqlalchemy.orm import Session
from bs4 import BeautifulSoup

from app.models import Item, Source, PriceHistory, NewsItem, ScrapeLog
from app.scraper.base import fetch, extract_value, extract_news, ScrapeError
from app.config import SOURCE_URLS, SCRAPE_USER_AGENT, SCRAPE_REQUEST_TIMEOUT, EIA_PRODUCT_SERIES
from app.ai_news_classifier import classify_urls
from app.services import resolve_ai_key
from app import eia_client
import requests

logger = logging.getLogger("knpc.scraper")


def _log(db: Session, item_code, source_name, status, message):
    db.add(ScrapeLog(item_code=item_code, source_name=source_name, status=status, message=message))
    logger.info("[%s] %s / %s: %s", status.upper(), item_code, source_name, message)


def _save_news(db: Session, item_id, headline: str, url: str, source_name: str):
    dup = (
        db.query(NewsItem)
        .filter(NewsItem.item_id == item_id, NewsItem.headline == headline)
        .first()
    )
    if not dup:
        db.add(NewsItem(item_id=item_id, headline=headline, url=url, source=source_name))


def _collect_news_for_item(db: Session, item: Item):
    """Try every active source's news_selector for this item, independent of
    which source (if any) currently wins the price. A fallback source is
    often the only one with a news_selector configured, so this must not be
    gated on the primary price source succeeding."""
    for source in item.sources:
        if not source.active or not source.news_selector:
            continue
        try:
            resp = fetch(source.url)
            for headline in extract_news(source, resp):
                _save_news(db, item.id, headline["headline"], headline["url"], source.name)
        except Exception as exc:
            logger.info("News fetch skipped for %s/%s: %s", item.code, source.name, exc)
            continue


def scrape_item(db: Session, item: Item) -> bool:
    """Try each active source for this item, in priority order, until one
    succeeds for price. Returns True on success, False if every source failed
    (failure is logged either way). News collection runs separately (see
    _collect_news_for_item) so a failed/missing price selector never blocks it."""
    sources = sorted(
        [s for s in item.sources if s.active],
        key=lambda s: s.priority,
    )
    if not sources:
        _log(db, item.code, None, "error", "No active sources configured")
        return False

    last_error = None
    price_ok = False
    for source in sources:
        try:
            if source.source_type == "eia_api":
                fallback_query = EIA_PRODUCT_SERIES.get(item.code, {}).get("query")
                price = eia_client.fetch_price_from_source_url(source.url, fallback_query)
            else:
                resp = fetch(source.url)
                price = extract_value(source, resp)

            today = date.today()
            existing = (
                db.query(PriceHistory)
                .filter(PriceHistory.item_id == item.id, PriceHistory.price_date == today)
                .first()
            )
            if existing:
                existing.price = price
                existing.source_id = source.id
                existing.collected_at = datetime.utcnow()
            else:
                db.add(PriceHistory(
                    item_id=item.id, source_id=source.id,
                    price_date=today, price=price,
                ))

            _log(db, item.code, source.name, "success", f"price={price}")
            db.commit()
            price_ok = True
            break

        except Exception as exc:  # noqa: BLE001 - we want to log & fall through
            last_error = str(exc)
            db.rollback()
            _log(db, item.code, source.name, "error", last_error)
            db.commit()
            continue

    if not price_ok:
        _log(db, item.code, None, "error", f"All sources failed. Last error: {last_error}")
        db.commit()

    _collect_news_for_item(db, item)
    db.commit()
    return price_ok


OILPRICE_NEWS_URL = SOURCE_URLS.get("oilprice_news", "https://oilprice.com/Latest-Energy-News/World-News/")


def collect_general_market_news(db: Session, limit: int = 20):
    """Item-independent news sweep -- fetches up to `limit` headline/url
    pairs from oilprice.com's latest news page (fewer if the page doesn't
    have that many), then asks DeepSeek to group each URL as 'general' or
    against one of the tracked items (only the URLs are sent, not the
    scraped titles/body). Falls back to filing everything as general if no
    DeepSeek key is configured or the classification call fails --
    collection itself never depends on the AI call succeeding."""
    try:
        headers = {"User-Agent": SCRAPE_USER_AGENT}
        resp = requests.get(OILPRICE_NEWS_URL, headers=headers, timeout=SCRAPE_REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        topics = []  # [{"title": ..., "url": ...}], de-duped, capped at `limit`
        seen_urls = set()
        for a in soup.find_all("a", href=True):
            title = a.get_text(" ", strip=True)
            href = a["href"]
            if len(title) < 35 or "click here" in title.lower() or "oilprice.com" not in href:
                continue
            if href.startswith("/"):
                href = "https://oilprice.com" + href
            if href in seen_urls:
                continue
            seen_urls.add(href)
            topics.append({"title": title, "url": href})
            if len(topics) >= limit:
                break

        if not topics:
            _log(db, None, "OilPrice (general)", "success", "logged=0 (no topics found on page)")
            db.commit()
            return 0

        items = db.query(Item).filter(Item.active == True).all()  # noqa: E712
        item_by_name = {i.name.strip().lower(): i for i in items}
        api_key = resolve_ai_key(db, "deepseek")

        grouping, classify_status = classify_urls([t["url"] for t in topics], [i.name for i in items], api_key)
        topic_by_url = {t["url"]: t for t in topics}

        count = 0
        item_matches = 0
        for url in grouping.get("general", []):
            topic = topic_by_url.get(url)
            if not topic:
                continue
            _save_news(db, None, topic["title"], topic["url"], "OilPrice")
            count += 1

        for item_name, urls in grouping.get("items", {}).items():
            item = item_by_name.get(str(item_name).strip().lower())
            for url in urls:
                topic = topic_by_url.get(url)
                if not topic:
                    continue
                # An item name the model invented/misspelled shouldn't drop
                # the headline -- file it as general instead of losing it.
                target_item_id = item.id if item else None
                if target_item_id:
                    item_matches += 1
                _save_news(db, target_item_id, topic["title"], topic["url"], "OilPrice")
                count += 1

        db.commit()
        if classify_status == "no_api_key":
            status_note = "no DeepSeek key configured (Admin -> AI Settings) -- filed all as general"
        elif classify_status == "ok":
            status_note = f"DeepSeek classified {item_matches} to a specific item, rest general"
        else:
            status_note = f"DeepSeek classification failed ({classify_status}) -- filed all as general"
        _log(db, None, "OilPrice (general)", "success", f"logged={count} of {len(topics)} topics fetched; {status_note}")
        return count
    except Exception as exc:
        db.rollback()
        _log(db, None, "OilPrice (general)", "error", str(exc))
        db.commit()
        return 0


def run_full_scrape(db: Session):
    items = db.query(Item).filter(Item.active == True).all()  # noqa: E712
    results = {}
    for item in items:
        results[item.code] = scrape_item(db, item)
    collect_general_market_news(db)
    return results
