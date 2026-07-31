from datetime import datetime, date
import logging

from sqlalchemy.orm import Session
from bs4 import BeautifulSoup

from app.models import Item, Source, PriceHistory, NewsItem, ScrapeLog
from app.scraper.base import fetch, extract_value, extract_news, ScrapeError
from app.config import SOURCE_URLS, SCRAPE_USER_AGENT, SCRAPE_REQUEST_TIMEOUT
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


def collect_general_market_news(db: Session, limit: int = 10):
    """Item-independent news sweep (item_id=NULL), mirroring the old app's
    global news feed -- separate from any per-item price scraping so it
    always runs regardless of which price sources succeed or fail."""
    try:
        headers = {"User-Agent": SCRAPE_USER_AGENT}
        resp = requests.get(OILPRICE_NEWS_URL, headers=headers, timeout=SCRAPE_REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        count = 0
        for a in soup.find_all("a", href=True):
            title = a.get_text(" ", strip=True)
            href = a["href"]
            if len(title) < 35 or "click here" in title.lower() or "oilprice.com" not in href:
                continue
            if href.startswith("/"):
                href = "https://oilprice.com" + href
            _save_news(db, None, title, href, "OilPrice")
            count += 1
            if count >= limit:
                break
        db.commit()
        _log(db, None, "OilPrice (general)", "success", f"logged={count}")
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
