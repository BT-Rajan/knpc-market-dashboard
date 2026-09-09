"""
Monthly market brief generation.

Two modes:
  - "data_only":   a simple one-month price recap -- benchmark/product tables
                    and charts, computed straight from PriceHistory. No AI,
                    no single "lead story" -- there's no data-only equivalent
                    of a news-driven brief.
  - "ai_enhanced":  a single-topic intelligence brief modeled on a real
                    analyst brief -- picks the month's single most relevant
                    story from this system's own collected & categorized
                    news, fetches that article's actual text (not just its
                    headline), and asks the AI to extract Key Figures only if
                    the article states them, then write Background / Reading
                    the Market / Implications / Recommendation grounded in
                    that fetched text. No figure is ever invented -- a figure
                    with no article support is left out, not guessed.
"""
import json
import logging
import re
from datetime import datetime, date
from pathlib import Path
from io import BytesIO

from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from sqlalchemy.orm import Session

from app.models import NewsItem
from app.config import MOG_DIVISION_NAME, REPORTS_DIR
from app.article_fetch import fetch_article_text
from app.report_generator import (
    GOLD, DARK, GREY, MONTH_ABBR,
    CRUDE_CODES, PRODUCT_CODES,
    _heading, _add_table, _footnote, _add_chart, _item_names,
    _ai_or_none, _no_ai_note,
    get_month_date_range, get_benchmark_stats, get_product_stats,
    _news_for_period,
)
from app.report_charts import line_chart

logger = logging.getLogger("knpc.reports")


def _pick_lead_story(db: Session, start: date, end: date) -> NewsItem | None:
    """Picks the single most market-relevant general (item-independent)
    headline collected this month, from real collected news only."""
    candidates = _news_for_period(db, start, end, categories=["Crude", "Products", "EV & Renewables", "Other Commodities"], limit=30)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    numbered = "\n".join(f"{i}. {n.headline}" for i, n in enumerate(candidates))
    reply = _ai_or_none(
        db,
        f"Below is a numbered list of headlines collected this month. Reply with ONLY the number "
        f"of the single headline most likely to be the month's biggest, most market-moving story "
        f"for an oil & gas market intelligence brief. No other text.\n\n{numbered}",
    )
    if reply:
        match = re.search(r"\d+", reply)
        if match:
            idx = int(match.group())
            if 0 <= idx < len(candidates):
                return candidates[idx]
    return candidates[0]  # most recent, as a deterministic fallback


def _extract_key_figures(db: Session, article_text: str) -> list[dict]:
    """Only pulls figures the article text actually states. Returns [] on any
    failure or if the article states nothing extractable -- never invents."""
    if not article_text:
        return []
    prompt = (
        "From the article text below, list every concrete market figure it states "
        "(a price, a rate, a percentage, a volume, a count -- with its unit). "
        "Return ONLY strict JSON, no markdown fences: "
        '[{"metric": "...", "reading": "...", "context": "..."}, ...]. '
        "Only include a figure if the text actually states it. If none, return [].\n\n"
        f"Article text:\n{article_text}"
    )
    reply = _ai_or_none(db, prompt)
    if not reply:
        return []
    try:
        cleaned = re.sub(r"^```(json)?|```$", "", reply.strip(), flags=re.MULTILINE).strip()
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return [row for row in parsed if isinstance(row, dict) and row.get("metric") and row.get("reading")]
    except Exception as exc:
        logger.warning("Key figures extraction: could not parse AI response: %s", exc)
    return []


def generate_monthly_report(
    db: Session, year: int, month: int,
    generated_by: str = "MOG Analyst", mode: str = "data_only",
) -> bytes:
    start, end = get_month_date_range(year, month)
    period_label = f"{MONTH_ABBR[month]} {year}"
    ai = mode == "ai_enhanced"

    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)

    if ai:
        lead = _pick_lead_story(db, start, end)
        article_text = fetch_article_text(lead.url) if lead else None
        title_text = None
        if lead:
            title_text = _ai_or_none(
                db,
                f'Headline: "{lead.headline}"\n\nWrite a short (5-9 word) title for a market brief '
                f"about this story, in the style of a headline, not a question. Return only the title.",
            )
        title_text = title_text or (lead.headline if lead else f"{period_label} Market Brief")

        title = doc.add_paragraph()
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = title.add_run(title_text)
        run.bold, run.font.size, run.font.color.rgb = True, Pt(20), DARK

        subtitle = doc.add_paragraph()
        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = subtitle.add_run(f"{MOG_DIVISION_NAME} - Monthly Market Brief - {period_label}")
        run.font.size, run.font.color.rgb = Pt(12), GOLD

        meta = doc.add_paragraph()
        meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = meta.add_run(f"Generated {datetime.now().strftime('%d %B %Y')}  |  Prepared by {generated_by}  |  Mode: AI-enhanced")
        run.font.size, run.font.color.rgb = Pt(9), GREY
        doc.add_paragraph()

        _heading(doc, "1. Issue Background", level=1)
        if lead:
            background_prompt = (
                f"Write 2-3 short paragraphs of background for a market brief on this story.\n\n"
                f"Headline: {lead.headline}\n\n"
                f"Article text:\n{article_text or '(article text unavailable -- use only the headline)'}\n\n"
                f"Ground every claim in the article text above. If the article text is unavailable, "
                f"say only what the headline itself supports."
            )
            doc.add_paragraph(_ai_or_none(db, background_prompt) or (lead.headline + " " + _no_ai_note()))
        else:
            doc.add_paragraph("No general market news was collected for this month, so no single lead story could be identified.")

        figures = _extract_key_figures(db, article_text) if article_text else []
        _heading(doc, "2. Key Figures", level=1)
        if figures:
            _add_table(
                doc, ["Metric", "Reading", "Context"],
                [[f.get("metric", ""), f.get("reading", ""), f.get("context", "")] for f in figures],
                header_shade="1C3F5F",
            )
            _footnote(doc, f"Figures extracted only where stated in the source article ({lead.source or lead.url}).")
        else:
            doc.add_paragraph(
                "No article text was available to extract figures from." if not article_text
                else "The source article did not state figures suitable for a Key Figures table."
            )
        doc.add_paragraph()

        _heading(doc, "3. Analytics", level=1)
        b_stats = get_benchmark_stats(db, start, end)
        brent = next((s for s in b_stats if s["code"] == "BRENT"), None)
        if brent:
            x_labels = [d.strftime("%d %b") for d, _ in brent["series"]]
            png = line_chart(
                "Brent crude - price path this month", x_labels,
                {"Brent": [p for _, p in brent["series"]]}, "US$/bbl",
                footnote="Daily price points tracked this month.",
            )
            _add_chart(doc, png)
        if article_text:
            reading_prompt = (
                f"From the article text below, write 3-4 bullet points (one sentence each) under the "
                f"heading 'Reading the market' -- what an analyst should take away. Ground every point "
                f"in the text; do not introduce outside facts.\n\n{article_text}"
            )
            text = _ai_or_none(db, reading_prompt)
            if text:
                _heading(doc, "Reading the market", level=2)
                for line in text.splitlines():
                    line = line.lstrip("-* ").strip()
                    if line:
                        doc.add_paragraph(line, style="List Bullet")
        doc.add_paragraph()

        _heading(doc, "Implications", level=1)
        if article_text:
            impl_prompt = (
                f"From the article text below, write short implications for an oil & gas company, "
                f"bucketed by time horizon. Format exactly as:\n"
                f"NEAR-TERM: <one sentence>\nMEDIUM-TERM: <one sentence>\n"
                f"Ground both in the article text; if the text doesn't support one horizon, write "
                f"'Insufficient information' for that line.\n\n{article_text}"
            )
            text = _ai_or_none(db, impl_prompt)
            if text:
                for line in text.splitlines():
                    line = line.strip()
                    if line:
                        doc.add_paragraph(line, style="List Bullet")
            else:
                doc.add_paragraph(_no_ai_note())
        else:
            doc.add_paragraph("No article text was available to draw implications from.")
        doc.add_paragraph()

        _heading(doc, "Recommendation", level=1)
        if article_text:
            rec_prompt = (
                f"From the article text below, write one short recommendation paragraph (40-70 words) "
                f"for how the reader should respond. Ground it in the text; do not introduce outside facts.\n\n{article_text}"
            )
            doc.add_paragraph(_ai_or_none(db, rec_prompt) or _no_ai_note())
        else:
            doc.add_paragraph("No article text was available to base a recommendation on.")

        _heading(doc, "A Note on the Numbers", level=1)
        doc.add_paragraph(
            "This brief's lead story and Key Figures are drawn only from an article this system's own "
            "news feed collected and could fetch the text of; a figure with no textual support in that "
            "article was left out rather than estimated. The price chart is computed directly from "
            "prices this system has tracked. This brief is not independently fact-checked beyond what "
            "the cited article states."
        )

    else:
        title = doc.add_paragraph()
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = title.add_run(f"{period_label} Price Recap")
        run.bold, run.font.size, run.font.color.rgb = True, Pt(22), DARK

        subtitle = doc.add_paragraph()
        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = subtitle.add_run(MOG_DIVISION_NAME)
        run.font.size, run.font.color.rgb = Pt(12), GOLD

        meta = doc.add_paragraph()
        meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = meta.add_run(f"Generated {datetime.now().strftime('%d %B %Y')}  |  Prepared by {generated_by}  |  Mode: Data only")
        run.font.size, run.font.color.rgb = Pt(9), GREY
        doc.add_paragraph()

        b_stats = get_benchmark_stats(db, start, end)
        _heading(doc, "Crude Benchmarks", level=1)
        if b_stats:
            _add_table(
                doc, ["Benchmark", "Open", "Close", "High", "Low", "Average", "Change %"],
                [[s["name"], s["open"], s["close"], s["high"], s["low"], s["avg"], f"{s['change_pct']:+.2f}%"] for s in b_stats],
                header_shade="1C3F5F",
            )
            names = _item_names(db, CRUDE_CODES)
            x_labels = [d.strftime("%d %b") for d, _ in b_stats[0]["series"]]
            by_code = {s["code"]: dict(s["series"]) for s in b_stats}
            common_dates = sorted(set.intersection(*[set(d for d, _ in s["series"]) for s in b_stats]))
            png = line_chart(
                f"Crude benchmarks - {period_label}", [d.strftime("%d %b") for d in common_dates],
                {names.get(s["code"], s["name"]): [by_code[s["code"]][d] for d in common_dates] for s in b_stats},
                "US$/bbl", footnote="Daily price points tracked this month.",
            )
            _add_chart(doc, png)
        else:
            doc.add_paragraph("No data available for this month.")
        doc.add_paragraph()

        p_stats = get_product_stats(db, start, end)
        _heading(doc, "Refined Products", level=1)
        if p_stats:
            _add_table(
                doc, ["Product", "Open", "Close", "High", "Low", "Average", "Change %", "Weekly readings"],
                [[s["name"], s["open"], s["close"], s["high"], s["low"], s["avg"], f"{s['change_pct']:+.2f}%", s["readings"]] for s in p_stats],
                header_shade="1C3F5F",
            )
        else:
            doc.add_paragraph("No data available for this month.")

    output = BytesIO()
    doc.save(output)
    output.seek(0)
    return output.getvalue()


def save_monthly_report(db: Session, year: int, month: int, generated_by: str = "MOG Analyst", mode: str = "data_only") -> Path:
    report_bytes = generate_monthly_report(db, year, month, generated_by, mode)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"monthly_{year}-{month:02d}_{mode}_{timestamp}.docx"
    filepath = REPORTS_DIR / filename
    with open(filepath, "wb") as f:
        f.write(report_bytes)
    return filepath
