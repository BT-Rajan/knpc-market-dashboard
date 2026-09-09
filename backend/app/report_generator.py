"""
Quarterly market report generation for MOG division.
Compiles price movements, product trends, and market developments into Word documents.

Two modes, chosen by the caller (the admin picks per-generation):
  - "data_only":   every figure comes straight from PriceHistory. No AI calls.
  - "ai_enhanced":  the data_only content, plus narrative sections synthesized
                     by an LLM from headlines this system has actually collected
                     (NewsItem) -- never from invented facts. Every AI call
                     degrades gracefully to a plain note if no AI key is
                     configured or the call fails; it never blocks generation.
"""
import logging
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path
from io import BytesIO

from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Item, PriceHistory, NewsItem
from app.config import QUARTER_MONTHS, MOG_DIVISION_NAME, REPORTS_DIR
from app.services import collapse_rows_to_weekly, resolve_ai_key
from app.ai_client import ask_ai
from app.report_charts import line_chart, grouped_bar_chart, signed_bar_chart

logger = logging.getLogger("knpc.reports")

GOLD = RGBColor(0xB8, 0x8A, 0x1E)
DARK = RGBColor(0x1A, 0x1F, 0x2B)
GREY = RGBColor(0x5A, 0x66, 0x78)
NAVY = RGBColor(0x1C, 0x3F, 0x5F)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

CRUDE_CODES = ["BRENT", "WTI", "OMAN", "DUBAI", "KEC"]
PRODUCT_CODES = ["GASOLINE_CONV_GC", "ULSD_GC", "JETKERO_GC", "PROPANE_MB"]
MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _item_names(db: Session, codes: list[str]) -> dict:
    return {i.code: i.name for i in db.query(Item).filter(Item.code.in_(codes)).all()}


def _short_label(name: str) -> str:
    """Chart legend label: the tracked item's full name minus its trailing
    "(location, grade)" parenthetical -- full name still appears in the table
    and heading right above the chart."""
    return name.split(" (")[0].strip()


# --------------------------------------------------------------------------
# Document helpers
# --------------------------------------------------------------------------

def _set_cell_text(cell, text, bold=False, color=None, size=10):
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run(str(text))
    run.bold = bold
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = color


def _shade_cell(cell, hex_color: str):
    shd = cell._tc.get_or_add_tcPr().makeelement(qn("w:shd"), {
        qn("w:val"): "clear", qn("w:color"): "auto", qn("w:fill"): hex_color,
    })
    cell._tc.get_or_add_tcPr().append(shd)


def _add_table(doc, headers, rows, header_shade: str = None):
    """Add a formatted table. header_shade (e.g. '1C3F5F') gives it the
    reference report's navy-header/white-text look; omitted keeps the
    plain default style."""
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Light Grid Accent 1" if not header_shade else "Table Grid"
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        _set_cell_text(cell, h, bold=True, color=WHITE if header_shade else GOLD)
        if header_shade:
            _shade_cell(cell, header_shade)
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            _set_cell_text(cells[i], "" if val is None else val)
    return table


def _heading(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        run.font.color.rgb = DARK
    return h


def _footnote(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.italic = True
    run.font.size = Pt(8)
    run.font.color.rgb = GREY
    return p


def _add_chart(doc, png_bytes: bytes, width_in: float = 6.2):
    doc.add_picture(BytesIO(png_bytes), width=Inches(width_in))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER


# --------------------------------------------------------------------------
# Date range helpers
# --------------------------------------------------------------------------

def get_quarter_date_range(year: int, quarter: str) -> tuple[date, date]:
    if quarter not in QUARTER_MONTHS:
        raise ValueError(f"Invalid quarter: {quarter}")
    start_month, end_month = QUARTER_MONTHS[quarter]
    start = date(year, start_month, 1)
    if end_month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, end_month + 1, 1) - timedelta(days=1)
    return start, end


def get_month_date_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = (date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)) - timedelta(days=1)
    return start, end


def _month_key(d: date) -> date:
    return d.replace(day=1)


def _iter_months(start: date, end: date):
    cur = _month_key(start)
    while cur <= end:
        yield cur
        cur = date(cur.year + 1, 1, 1) if cur.month == 12 else date(cur.year, cur.month + 1, 1)


def _month_label(d: date) -> str:
    return f"{MONTH_ABBR[d.month]}-{str(d.year)[2:]}"


# --------------------------------------------------------------------------
# Price stats (shared by both modes -- pure PriceHistory arithmetic)
# --------------------------------------------------------------------------

def _rows_for(db: Session, code: str, start: date, end: date):
    item = db.query(Item).filter(Item.code == code).first()
    if not item:
        return None, []
    rows = (
        db.query(PriceHistory)
        .filter(PriceHistory.item_id == item.id, PriceHistory.price_date >= start, PriceHistory.price_date <= end)
        .order_by(PriceHistory.price_date)
        .all()
    )
    return item, rows


def _stats_from_series(item, series: list[tuple[date, float]], readings: int) -> dict:
    dates_list = [d for d, _ in series]
    prices_list = [p for _, p in series]
    opening, closing = prices_list[0], prices_list[-1]
    high, low = max(prices_list), min(prices_list)
    change = closing - opening
    change_pct = (change / opening * 100) if opening else 0
    return {
        "code": item.code, "name": item.name, "unit": item.unit,
        "open": round(opening, 2), "close": round(closing, 2),
        "high": round(high, 2), "low": round(low, 2),
        "high_date": dates_list[prices_list.index(high)],
        "low_date": dates_list[prices_list.index(low)],
        "avg": round(sum(prices_list) / len(prices_list), 2),
        "change": round(change, 2), "change_pct": round(change_pct, 2),
        "readings": readings,
        "series": series,
    }


def get_benchmark_stats(db: Session, start: date, end: date) -> list[dict]:
    """Daily stats for each crude benchmark tracked over [start, end]."""
    stats = []
    for code in CRUDE_CODES:
        item, rows = _rows_for(db, code, start, end)
        if not item or not rows:
            continue
        series = [(r.price_date, r.price) for r in rows]
        stats.append(_stats_from_series(item, series, len(rows)))
    return stats


def get_product_stats(db: Session, start: date, end: date) -> list[dict]:
    """Weekly-collapsed stats for each product over [start, end] -- Products
    are only actually re-priced ~weekly, so this averages away the repeated
    daily scrape rows the same way the item page and price export do."""
    stats = []
    for code in PRODUCT_CODES:
        item, rows = _rows_for(db, code, start, end)
        if not item or not rows:
            continue
        series = collapse_rows_to_weekly(rows)
        if not series:
            continue
        stats.append(_stats_from_series(item, series, len(series)))
    return stats


def get_monthly_averages(db: Session, start: date, end: date, codes: list[str], weekly: bool = False):
    """{month_start: {code: avg_price}} for each code, only for months where
    every requested code has at least one reading (avoids misleading
    zero-height bars for a code with a data gap)."""
    per_code = {}
    for code in codes:
        item, rows = _rows_for(db, code, start, end)
        if not item:
            per_code[code] = {}
            continue
        series = collapse_rows_to_weekly(rows) if weekly else [(r.price_date, r.price) for r in rows]
        buckets = defaultdict(list)
        for d, p in series:
            buckets[_month_key(d)].append(p)
        per_code[code] = {m: sum(v) / len(v) for m, v in buckets.items()}

    months = [m for m in _iter_months(start, end) if all(m in per_code[c] for c in codes)]
    return months, per_code


def get_kec_differential(db: Session, start: date, end: date):
    """KEC's tracked price minus the Oman/Dubai average, for dates all three
    have a reading. This is an *implied* differential computed from tracked
    prices -- not KPC's officially published monthly OSP, which this system
    has no source for."""
    _, kec_rows = _rows_for(db, "KEC", start, end)
    _, oman_rows = _rows_for(db, "OMAN", start, end)
    _, dubai_rows = _rows_for(db, "DUBAI", start, end)
    kec = {r.price_date: r.price for r in kec_rows}
    oman = {r.price_date: r.price for r in oman_rows}
    dubai = {r.price_date: r.price for r in dubai_rows}
    common = sorted(set(kec) & set(oman) & set(dubai))
    daily = [(d, kec[d] - (oman[d] + dubai[d]) / 2) for d in common]

    buckets = defaultdict(list)
    for d, v in daily:
        buckets[_month_key(d)].append(v)
    monthly = [{"month": m, "diff": round(sum(v) / len(v), 2)} for m, v in sorted(buckets.items())]
    return daily, monthly


# --------------------------------------------------------------------------
# News (real, collected headlines -- the only grounding AI narrative gets)
# --------------------------------------------------------------------------

def _news_for_period(db: Session, start: date, end: date, item_codes: list[str] = None,
                      categories: list[str] = None, limit: int = 40) -> list[NewsItem]:
    q = db.query(NewsItem).filter(
        NewsItem.collected_at >= datetime.combine(start, datetime.min.time()),
        NewsItem.collected_at <= datetime.combine(end, datetime.max.time()),
    )
    conditions = []
    if item_codes:
        ids = [i.id for i in db.query(Item).filter(Item.code.in_(item_codes)).all()]
        if ids:
            conditions.append(NewsItem.item_id.in_(ids))
    if categories:
        conditions.append(NewsItem.category.in_(categories))
    if conditions:
        q = q.filter(or_(*conditions))
    return q.order_by(NewsItem.collected_at.desc()).limit(limit).all()


def get_period_news(db: Session, start: date, end: date, limit: int = 20) -> list[dict]:
    items = _news_for_period(db, start, end, limit=limit)
    return [
        {
            "headline": n.headline, "url": n.url, "source": n.source,
            "collected_at": n.collected_at.strftime("%d %b %Y") if n.collected_at else "Unknown",
        }
        for n in items
    ]


def _format_news_lines(items: list[NewsItem]) -> str:
    if not items:
        return "(none collected)"
    return "\n".join(f"- {n.headline} ({n.source or 'unknown source'}, "
                      f"{n.collected_at.strftime('%d %b') if n.collected_at else '?'})" for n in items)


# --------------------------------------------------------------------------
# AI narrative -- every prompt is grounded in real stats/headlines passed in.
# Returns None (never raises) if no key is configured or the call fails, so
# callers can fall back to a plain, honest note instead of blocking.
# --------------------------------------------------------------------------

def _ai_or_none(db: Session, prompt: str, system: str = None) -> str | None:
    system = system or (
        "You are a market intelligence analyst. Write only from the facts given to you. "
        "Never invent a price, a figure, or a cause for a price move that isn't stated in "
        "the input. If the input doesn't support a claim, say the data is insufficient "
        "rather than guessing."
    )
    for provider in ("deepseek", "claude"):
        key = resolve_ai_key(db, provider)
        if not key:
            continue
        try:
            return ask_ai(provider, prompt, key, system=system).strip()
        except Exception as exc:
            logger.warning("Report AI call failed via %s: %s", provider, exc)
    return None


def _no_ai_note() -> str:
    return "(AI narrative unavailable -- configure a DeepSeek or Claude key under Admin -> AI Settings to enable this section.)"


def build_executive_summary(db, period_label: str, b_stats, p_stats, news_items) -> str:
    if not b_stats:
        return f"No benchmark price readings were recorded for {period_label} at the time of generation."
    lines = [f"{s['name']}: {s['open']} -> {s['close']} ({s['change_pct']:+.2f}%)" for s in b_stats]
    prompt = (
        f"Write a single-paragraph executive summary (120-180 words) for a {period_label} oil market report.\n\n"
        f"Benchmark moves:\n" + "\n".join(lines) + "\n\n"
        f"Product moves:\n" + "\n".join(f"{s['name']}: {s['open']} -> {s['close']} ({s['change_pct']:+.2f}%)" for s in p_stats) + "\n\n"
        f"Headlines collected this period:\n{_format_news_lines(news_items)}\n\n"
        f"Ground every claim about *why* prices moved in the headlines above. If the headlines don't "
        f"explain a move, describe the move itself without asserting a cause."
    )
    return _ai_or_none(db, prompt) or (
        f"{max(b_stats, key=lambda s: s['change_pct'])['name']} was the strongest-performing tracked "
        f"benchmark this period; {min(b_stats, key=lambda s: s['change_pct'])['name']} was the weakest. "
        f"{len(news_items)} market developments were logged in the monitoring feed. " + _no_ai_note()
    )


def build_month_narrative(db, month_label: str, b_stats_month: dict, news_items: list[NewsItem]) -> str:
    moves = ", ".join(f"{code}: {vals.get('start', '?')} -> {vals.get('end', '?')}" for code, vals in b_stats_month.items())
    prompt = (
        f"Write one short paragraph (60-110 words) narrating crude benchmark movement in {month_label}.\n\n"
        f"Price moves this month: {moves}\n\n"
        f"Headlines collected this month:\n{_format_news_lines(news_items)}\n\n"
        f"Only attribute a price move to an event if a headline above actually supports it."
    )
    return _ai_or_none(db, prompt) or (
        f"{month_label}: {moves}. No market-moving headlines were collected this month." if not news_items
        else f"{month_label}: {moves}. " + _no_ai_note()
    )


def build_kec_narrative(db, monthly_diff: list[dict], news_items: list[NewsItem]) -> str:
    lines = ", ".join(f"{_month_label(m['month'])}: {m['diff']:+.2f}" for m in monthly_diff)
    prompt = (
        f"Write one short paragraph (60-100 words) on Kuwait Export Crude's implied pricing "
        f"differential to the Oman/Dubai average this period.\n\n"
        f"Implied differential by month (KEC price minus Oman/Dubai average, US$/bbl): {lines}\n\n"
        f"Headlines mentioning Kuwait or KEC:\n{_format_news_lines(news_items)}\n\n"
        f"This is a differential computed from tracked prices, not KPC's official published OSP -- "
        f"do not refer to it as an official selling price."
    )
    return _ai_or_none(db, prompt) or (f"Implied KEC-to-Oman/Dubai differential by month: {lines}. " + _no_ai_note())


def build_product_narrative(db, product_name: str, stat: dict, news_items: list[NewsItem]) -> str:
    prompt = (
        f"Write one short paragraph (50-90 words) on {product_name} price movement this period.\n\n"
        f"{product_name}: {stat['open']} -> {stat['close']} ({stat['change_pct']:+.2f}%), "
        f"high {stat['high']}, low {stat['low']}.\n\n"
        f"Headlines collected this period:\n{_format_news_lines(news_items)}\n\n"
        f"Only attribute the move to an event if a headline above supports it."
    )
    return _ai_or_none(db, prompt) or (
        f"{product_name} moved {stat['open']} -> {stat['close']} ({stat['change_pct']:+.2f}%). " + _no_ai_note()
    )


def build_market_drivers(db, news_items: list[NewsItem]) -> list[str]:
    if not news_items:
        return ["No market developments were collected in the monitoring feed for this period."]
    prompt = (
        f"From the headlines below, list the 4-6 biggest cross-cutting market themes for this period, "
        f"one per line, each a single sentence. Only state what the headlines actually support.\n\n"
        f"{_format_news_lines(news_items)}"
    )
    text = _ai_or_none(db, prompt)
    if not text:
        return [_no_ai_note()]
    return [line.lstrip("-* ").strip() for line in text.splitlines() if line.strip()]


def build_outlook_draft(db, news_items: list[NewsItem]) -> str | None:
    if not news_items:
        return None
    prompt = (
        f"From the headlines below, does any of them contain forward-looking commentary (an analyst "
        f"forecast, an expected future event, a stated outlook)? If yes, synthesize a short forward "
        f"outlook paragraph (60-100 words) grounded only in that commentary. If no headline contains "
        f"forward-looking commentary, respond with exactly: NONE\n\n"
        f"{_format_news_lines(news_items)}"
    )
    text = _ai_or_none(db, prompt)
    if not text or text.strip().upper() == "NONE":
        return None
    return text


def find_price_annotations(db, item_id: int, series: list[tuple[date, float]], max_annotations: int = 3):
    """Finds the largest day-over-day moves in `series` and, only where a real
    headline was collected within a day of the move, asks the AI for a short
    label built from that headline. A move with no matching headline gets no
    label -- never a guessed cause."""
    if len(series) < 2:
        return []
    moves = []
    for i in range(1, len(series)):
        _, p0 = series[i - 1]
        _, p1 = series[i]
        if p0:
            moves.append((abs((p1 - p0) / p0), i))
    moves.sort(reverse=True)

    annotations = []
    for _, idx in moves:
        if len(annotations) >= max_annotations:
            break
        d = series[idx][0]
        window = (datetime.combine(d - timedelta(days=1), datetime.min.time()),
                  datetime.combine(d + timedelta(days=1), datetime.max.time()))
        headline = (
            db.query(NewsItem)
            .filter(NewsItem.collected_at >= window[0], NewsItem.collected_at <= window[1])
            .filter(or_(NewsItem.item_id == item_id, NewsItem.category == "Crude"))
            .order_by(NewsItem.collected_at.desc())
            .first()
        )
        if not headline:
            continue
        label = _ai_or_none(
            db,
            f'Headline: "{headline.headline}"\n\nWrite a 2-5 word chart annotation label naming the '
            f'event this headline describes (e.g. "Ceasefire announced", "US strikes Iran"). '
            f"Return only the label -- no quotes, no trailing punctuation.",
        )
        if label:
            annotations.append({"index": idx, "text": label.strip().strip('"')})
    return annotations


NOTE_ON_THE_NUMBERS = (
    "This report's price statistics (open/close/high/low/average, by day for crude benchmarks and by "
    "week for refined products) are computed directly from prices this system has tracked over the "
    "period. The Kuwait Export Crude differential shown here is not KPC's officially published OSP -- "
    "this system has no source for that figure -- it is computed as KEC's tracked price minus the "
    "Oman/Dubai average for the same dates. Narrative sections are generated by AI strictly from "
    "headlines collected by this system's news monitoring feed over the period; they are not "
    "independently fact-checked beyond what the cited headlines state. For trading, hedging, or "
    "contractual purposes, consult a licensed Platts or Argus feed directly."
)


# --------------------------------------------------------------------------
# Quarterly report
# --------------------------------------------------------------------------

def generate_quarterly_report(
    db: Session,
    year: int,
    quarter: str,
    outlook_notes: str = "",
    generated_by: str = "MOG Analyst",
    mode: str = "data_only",
) -> bytes:
    start, end = get_quarter_date_range(year, quarter)
    period_label = f"{quarter} {year}"
    ai = mode == "ai_enhanced"

    b_stats = get_benchmark_stats(db, start, end)
    p_stats = get_product_stats(db, start, end)
    news_items = _news_for_period(db, start, end, limit=40) if ai else []

    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(f"{period_label} Market Intelligence Report")
    run.bold, run.font.size, run.font.color.rgb = True, Pt(24), DARK

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run(MOG_DIVISION_NAME)
    run.font.size, run.font.color.rgb = Pt(13), GOLD

    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = meta.add_run(
        f"Reporting period: {start.strftime('%d %B %Y')} - {end.strftime('%d %B %Y')}  |  "
        f"Generated {datetime.now().strftime('%d %B %Y')}  |  Prepared by {generated_by}  |  "
        f"Mode: {'AI-enhanced' if ai else 'Data only'}"
    )
    run.font.size, run.font.color.rgb = Pt(9), GREY
    doc.add_paragraph()

    # Executive Summary
    _heading(doc, "Executive Summary", level=1)
    if ai:
        doc.add_paragraph(build_executive_summary(db, period_label, b_stats, p_stats, news_items))
    elif b_stats:
        best = max(b_stats, key=lambda s: s["change_pct"])
        worst = min(b_stats, key=lambda s: s["change_pct"])
        doc.add_paragraph(
            f"During {period_label}, {best['name']} was the strongest-performing tracked benchmark "
            f"({best['change_pct']:+.2f}%), while {worst['name']} moved {worst['change_pct']:+.2f}%."
        )
    else:
        doc.add_paragraph(f"No benchmark price readings were recorded for {period_label} at the time of generation.")

    # Quarter at a Glance
    _heading(doc, "Quarter at a Glance", level=2)
    if b_stats:
        _add_table(
            doc,
            ["Benchmark", start.strftime("%d %b %Y"), "Period peak", "Period trough", end.strftime("%d %b %Y"), "Net change"],
            [[
                s["name"], s["open"],
                f"{s['high']} ({s['high_date'].strftime('%d %b')})",
                f"{s['low']} ({s['low_date'].strftime('%d %b')})",
                s["close"], f"{s['change_pct']:+.1f}%",
            ] for s in b_stats],
            header_shade="1C3F5F",
        )
        _footnote(doc, "Figures from tracked daily prices; peak/trough dates are when this system recorded that extreme.")
    else:
        doc.add_paragraph("No data available for this period.")
    doc.add_paragraph()

    # 1. Crude Benchmarks
    _heading(doc, "1. Crude Benchmarks", level=1)
    doc.add_paragraph(
        "Benchmark movement based on daily prices tracked by this system."
    )
    brent = next((s for s in b_stats if s["code"] == "BRENT"), None)
    wti = next((s for s in b_stats if s["code"] == "WTI"), None)
    if brent and wti:
        common_dates = sorted(set(d for d, _ in brent["series"]) & set(d for d, _ in wti["series"]))
        x_labels = [d.strftime("%d %b") for d in common_dates]
        brent_by_date = dict(brent["series"])
        wti_by_date = dict(wti["series"])
        annotations = []
        if ai:
            annotations = find_price_annotations(
                db, db.query(Item).filter(Item.code == "BRENT").first().id, [(d, brent_by_date[d]) for d in common_dates],
            )
        png = line_chart(
            "Brent and WTI crude - price path", x_labels,
            {"Brent": [brent_by_date[d] for d in common_dates], "WTI": [wti_by_date[d] for d in common_dates]},
            "US$/bbl", footnote="Daily price points tracked over the period.", annotations=annotations,
        )
        _add_chart(doc, png)
    if ai:
        for m in _iter_months(start, end):
            m_end = min(end, (date(m.year + 1, 1, 1) if m.month == 12 else date(m.year, m.month + 1, 1)) - timedelta(days=1))
            month_stats = {}
            for s in b_stats:
                month_series = [(d, p) for d, p in s["series"] if m <= d <= m_end]
                if month_series:
                    month_stats[s["code"]] = {"start": month_series[0][1], "end": month_series[-1][1]}
            month_news = _news_for_period(db, m, m_end, item_codes=CRUDE_CODES, categories=["Crude"], limit=15)
            _heading(doc, _month_label(m), level=2)
            doc.add_paragraph(build_month_narrative(db, m.strftime("%B %Y"), month_stats, month_news))
    months, per_code_avg = get_monthly_averages(db, start, end, CRUDE_CODES)
    if months:
        names = _item_names(db, CRUDE_CODES)
        _heading(doc, "Monthly average levels", level=2)
        png = grouped_bar_chart(
            "Crude benchmark monthly averages", [_month_label(m) for m in months],
            {names[code]: [round(per_code_avg[code][m], 2) for m in months] for code in CRUDE_CODES},
            "US$/bbl",
        )
        _add_chart(doc, png)
    doc.add_paragraph()

    # 2. Kuwait Export Crude
    _heading(doc, "2. Kuwait Export Crude (KEC)", level=1)
    daily_diff, monthly_diff = get_kec_differential(db, start, end)
    if monthly_diff:
        png = signed_bar_chart(
            "KEC implied differential to Oman/Dubai average", [_month_label(m["month"]) for m in monthly_diff],
            [m["diff"] for m in monthly_diff], "US$/bbl",
            footnote="Implied: KEC tracked price minus Oman/Dubai average -- not KPC's published OSP.",
        )
        _add_chart(doc, png)
        if ai:
            kec_news = _news_for_period(db, start, end, item_codes=["KEC"], limit=15)
            doc.add_paragraph(build_kec_narrative(db, monthly_diff, kec_news))
    else:
        doc.add_paragraph("Insufficient overlapping KEC/Oman/Dubai data to compute a differential for this period.")
    doc.add_paragraph()

    # 3. Refined Products
    _heading(doc, "3. Refined Products", level=1)
    doc.add_paragraph("Weekly price movement (repeated daily scrape rows collapsed to one reading per week).")
    if p_stats:
        _add_table(
            doc,
            ["Product", "Open", "Close", "High", "Low", "Average", "Change %", "Weekly readings"],
            [[s["name"], s["open"], s["close"], s["high"], s["low"], s["avg"], f"{s['change_pct']:+.2f}%", s["readings"]]
             for s in p_stats],
            header_shade="1C3F5F",
        )
        common_p_dates = sorted(set.union(*[set(d for d, _ in s["series"]) for s in p_stats]))
        x_labels = [d.strftime("%d %b") for d in common_p_dates]
        series_by_code = {s["code"]: dict(s["series"]) for s in p_stats}
        png = line_chart(
            "Refined products - weekly price path", x_labels,
            {_short_label(s["name"]): [series_by_code[s["code"]].get(d, float("nan")) for d in common_p_dates] for s in p_stats},
            p_stats[0]["unit"],
            footnote="Weekly readings; gaps mean no reading was recorded that week.",
        )
        _add_chart(doc, png)
        if ai:
            for i, s in enumerate(p_stats, start=1):
                prod_news = _news_for_period(db, start, end, item_codes=[s["code"]], categories=["Products"], limit=15)
                _heading(doc, f"3.{i} {s['name']}", level=2)
                doc.add_paragraph(build_product_narrative(db, s["name"], s, prod_news))
    else:
        doc.add_paragraph("No data available for this period.")
    doc.add_paragraph()

    if ai:
        _heading(doc, "4. Market Drivers Summary", level=1)
        for line in build_market_drivers(db, news_items):
            doc.add_paragraph(line, style="List Bullet")
        doc.add_paragraph()

    # Outlook
    section_num = "5" if ai else "4"
    draft = build_outlook_draft(db, news_items) if (ai and not outlook_notes.strip()) else None
    if outlook_notes.strip() or draft:
        _heading(doc, f"{section_num}. Outlook", level=1)
        if outlook_notes.strip():
            doc.add_paragraph(outlook_notes)
        elif draft:
            _footnote(doc, "AI draft, grounded in this period's collected news -- review before publishing.")
            doc.add_paragraph(draft)

    if ai:
        _heading(doc, "A Note on the Numbers", level=1)
        doc.add_paragraph(NOTE_ON_THE_NUMBERS)

    output = BytesIO()
    doc.save(output)
    output.seek(0)
    return output.getvalue()


def save_quarterly_report(
    db: Session, year: int, quarter: str,
    outlook_notes: str = "", generated_by: str = "MOG Analyst", mode: str = "data_only",
) -> Path:
    report_bytes = generate_quarterly_report(db, year, quarter, outlook_notes, generated_by, mode)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{quarter}_{year}_market_report_{mode}_{timestamp}.docx"
    filepath = REPORTS_DIR / filename
    with open(filepath, "wb") as f:
        f.write(report_bytes)
    return filepath


def list_generated_reports() -> list[Path]:
    return sorted(REPORTS_DIR.glob("*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
