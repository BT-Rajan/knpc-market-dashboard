"""Fetches the visible text of a single article URL, for the monthly brief's
lead story -- so the AI can extract Key Figures and write from what an
article actually says, not just its headline. Best-effort: any failure
returns None and the caller falls back to headline-only content."""
import logging

from bs4 import BeautifulSoup

from app.scraper.base import fetch

logger = logging.getLogger("knpc.article_fetch")

MAX_CHARS = 6000


def fetch_article_text(url: str, max_chars: int = MAX_CHARS) -> str | None:
    if not url:
        return None
    try:
        resp = fetch(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "form", "aside"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        text = "\n".join(line for line in text.splitlines() if len(line) > 20)
        return text[:max_chars] if text else None
    except Exception as exc:
        logger.info("Article fetch failed for %s: %s", url, exc)
        return None
