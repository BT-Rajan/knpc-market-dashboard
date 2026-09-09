from collections import defaultdict
from datetime import date, timedelta
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Item, PriceHistory, NewsItem, AICredentials, EmailCredentials
from app.config import DEEPSEEK_API_KEY, CLAUDE_API_KEY
from app.crypto import decrypt
from app.ai_news_classifier import NEWS_CATEGORIES


def get_item_by_code_or_404(db: Session, code: str) -> Item:
    item = db.query(Item).filter(Item.code == code.upper()).first()
    if not item:
        raise HTTPException(status_code=404, detail=f"Unknown item code '{code}'")
    return item


def collapse_rows_to_weekly(rows):
    """Groups PriceHistory rows by ISO week (key = week-ending Sunday) and
    averages each week's rows -- collapses the repeated daily scrape rows
    Products get between their actual ~weekly re-pricings. Returns
    [(week_end_date, avg_price), ...] ascending. Shared by the item-page
    weekly series, the price export, and the quarterly/monthly reports so
    every "weekly" product figure in the system is computed the same way."""
    buckets = defaultdict(list)
    for r in rows:
        week_end = r.price_date + timedelta(days=6 - r.price_date.weekday())
        buckets[week_end].append(r.price)
    return [(week_end, sum(prices) / len(prices)) for week_end, prices in sorted(buckets.items())]


def _current_month_rows(db: Session, item_id: int):
    today = date.today()
    start = today.replace(day=1)
    return (
        db.query(PriceHistory)
        .filter(PriceHistory.item_id == item_id, PriceHistory.price_date >= start, PriceHistory.price_date <= today)
        .order_by(PriceHistory.price_date.asc())
        .all()
    )


def monthly_daily_series(db: Session, item_id: int):
    """Daily prices for every day recorded so far in the current calendar month."""
    rows = _current_month_rows(db, item_id)
    return [{"price_date": r.price_date, "price": r.price} for r in rows]


def weekly_average_series(db: Session, item_id: int):
    """One point per week of the current calendar month, x-axis = end of that week (Sunday), value = average price that week."""
    rows = _current_month_rows(db, item_id)
    return [{"price_date": we, "price": p} for we, p in collapse_rows_to_weekly(rows)]


def _current_year_rows(db: Session, item_id: int):
    today = date.today()
    start = today.replace(month=1, day=1)
    return (
        db.query(PriceHistory)
        .filter(PriceHistory.item_id == item_id, PriceHistory.price_date >= start, PriceHistory.price_date <= today)
        .order_by(PriceHistory.price_date.asc())
        .all()
    )


def product_weekly_series(db: Session, item_id: int):
    """Products are only re-priced roughly once a week, so daily scrape rows repeat the
    last known value. One point per week recorded so far this year, x-axis = end of
    that week (Sunday), value = average of that week's rows (collapses the repeats)."""
    rows = _current_year_rows(db, item_id)
    return [{"price_date": we, "price": p} for we, p in collapse_rows_to_weekly(rows)]


def product_monthly_series(db: Session, item_id: int):
    """One point per calendar month recorded so far this year, x-axis = the month, value = average price that month."""
    rows = _current_year_rows(db, item_id)
    buckets = defaultdict(list)
    for r in rows:
        buckets[r.price_date.replace(day=1)].append(r.price)
    return [
        {"price_date": month_start, "price": sum(prices) / len(prices)}
        for month_start, prices in sorted(buckets.items())
    ]


def item_price_export_rows(db: Session, item: Item):
    """Full recorded price history for one item, shaped for the price export
    workbook: every recorded day for Crude items, or one row per week
    (week-ending date, averaged) for Products -- Products are only re-priced
    roughly once a week, so daily scrape rows just repeat the last known
    value, and exporting them as-is would show the same price many times
    over under a misleading 'daily' label."""
    rows = (
        db.query(PriceHistory)
        .filter(PriceHistory.item_id == item.id)
        .order_by(PriceHistory.price_date.asc())
        .all()
    )
    if item.category == "Products":
        return [{"date": we, "price": p} for we, p in collapse_rows_to_weekly(rows)]
    return [{"date": r.price_date, "price": r.price} for r in rows]


def latest_two_prices(db: Session, item_id: int):
    rows = (
        db.query(PriceHistory)
        .filter(PriceHistory.item_id == item_id)
        .order_by(PriceHistory.price_date.desc())
        .limit(2)
        .all()
    )
    current = rows[0] if len(rows) > 0 else None
    previous = rows[1] if len(rows) > 1 else None
    return current, previous


def trend_fields(db: Session, item_id: int):
    current, previous = latest_two_prices(db, item_id)
    if not current:
        return dict(current_price=None, previous_price=None, daily_change=None,
                    daily_change_pct=None, as_of=None)
    prev_price = previous.price if previous else None
    change = (current.price - prev_price) if prev_price is not None else None
    change_pct = (change / prev_price * 100) if change is not None and prev_price else None
    return dict(
        current_price=current.price,
        previous_price=prev_price,
        daily_change=round(change, 4) if change is not None else None,
        daily_change_pct=round(change_pct, 3) if change_pct is not None else None,
        as_of=current.price_date,
    )


def recent_news(db: Session, item_id: int, limit: int = 10):
    return (
        db.query(NewsItem)
        .filter(NewsItem.item_id == item_id)
        .order_by(NewsItem.collected_at.desc())
        .limit(limit)
        .all()
    )


def general_market_news_by_category(db: Session, limit_per_category: int = 20):
    """Item-independent headlines (item_id is NULL) -- the global news feed,
    separate from any single benchmark/product's page -- grouped into the
    fixed topic categories, most recent first within each. A row saved
    before categorization existed, or classified as something unrecognized,
    falls into 'Other Commodities' rather than being dropped."""
    rows = (
        db.query(NewsItem)
        .filter(NewsItem.item_id.is_(None))
        .order_by(NewsItem.collected_at.desc())
        .all()
    )
    buckets: dict = {cat: [] for cat in NEWS_CATEGORIES}
    for r in rows:
        cat = r.category if r.category in buckets else "Other Commodities"
        if len(buckets[cat]) < limit_per_category:
            buckets[cat].append(r)
    return [{"category": cat, "news": buckets[cat]} for cat in NEWS_CATEGORIES]


def get_ai_credentials_row(db: Session) -> AICredentials:
    row = db.query(AICredentials).first()
    if not row:
        row = AICredentials()
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def resolve_ai_key(db: Session, provider: str) -> str:
    """DB-entered key wins; falls back to the env-var default from config.py."""
    row = get_ai_credentials_row(db)
    if provider == "deepseek":
        return row.deepseek_api_key or DEEPSEEK_API_KEY
    if provider == "claude":
        return row.claude_api_key or CLAUDE_API_KEY
    return ""


def get_email_credentials_row(db: Session) -> EmailCredentials:
    row = db.query(EmailCredentials).first()
    if not row:
        row = EmailCredentials()
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def resolve_email_credentials(db: Session) -> tuple[str, str]:
    """Returns (gmail_address, gmail_app_password) with the password
    decrypted from storage. Empty strings if not configured."""
    row = get_email_credentials_row(db)
    address = row.gmail_address or ""
    password = decrypt(row.gmail_app_password_encrypted or "") if row.gmail_app_password_encrypted else ""
    return address, password
