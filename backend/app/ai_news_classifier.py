"""Groups scraped oilprice.com headline URLs into a topic category or a
specific tracked item, via DeepSeek, instead of local keyword-guessing.
Classification is a nice-to-have -- collection itself must never depend on
it succeeding, so every failure mode here falls back to dumping everything
into the 'Other Commodities' category."""
import json
import logging
import re

import requests

from app.config import DEEPSEEK_API_URL, DEEPSEEK_MODEL

logger = logging.getLogger("knpc.ai_news")

NEWS_CATEGORIES = ["Crude", "Products", "EV & Renewables", "Other Commodities"]


def classify_urls(urls: list[str], item_names: list[str], api_key: str) -> tuple[dict, str]:
    """Returns (grouping, status). grouping is {"items": {name: [...]},
    "categories": {"Crude": [...], "Products": [...], "EV & Renewables": [...],
    "Other Commodities": [...]}}. status is "ok", "no_api_key" (nothing
    configured under Admin -> AI Settings), or "error: <detail>" (the
    call/parse failed) -- callers should log this so 'everything landed in
    Other Commodities' has a visible reason instead of looking identical to
    a real classification.
    Only the URLs are sent to the model -- no scraped article text/titles --
    since the URL slug alone is normally enough to tell what an oilprice.com
    piece is about."""
    fallback = {"items": {}, "categories": {"Other Commodities": list(urls)}}
    if not urls:
        return fallback, "ok"
    if not api_key:
        return fallback, "no_api_key"

    prompt = (
        "You will be given a JSON array of oilprice.com article URLs. "
        "Classify each one as specifically about one of these tracked items "
        "(judge the topic from the URL slug): " + ", ".join(item_names) + ". "
        "If it isn't about one of those specific tracked items, instead file it "
        "under exactly one of these topic categories: " + ", ".join(NEWS_CATEGORIES) + ". "
        "'Crude' is general crude-oil market news not about one specific tracked "
        "crude benchmark; 'Products' is general refined-product news not about one "
        "specific tracked product; 'EV & Renewables' is electric vehicles, batteries, "
        "solar, wind, or other clean-energy news; 'Other Commodities' is anything "
        "else energy/commodity related (gas, coal, metals, shipping, geopolitics, etc).\n\n"
        "Return ONLY strict JSON, no markdown fences, no commentary, in exactly "
        "this shape:\n"
        '{"items": {"<item name>": ["<url>", ...]}, '
        '"categories": {"Crude": ["<url>", ...], "Products": [...], '
        '"EV & Renewables": [...], "Other Commodities": [...]}}\n\n'
        "Every URL from the input must appear exactly once in the output, either "
        "under exactly one item name (use the item names exactly as given above) "
        "or under exactly one of the four category names above. If unsure between "
        "a category, use 'Other Commodities'.\n\n"
        f"URLs: {json.dumps(urls)}"
    )

    try:
        resp = requests.post(
            DEEPSEEK_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": "You output strict JSON only, nothing else."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        content = re.sub(r"^```(json)?|```$", "", content, flags=re.MULTILINE).strip()
        parsed = json.loads(content)
        if not isinstance(parsed, dict) or "categories" not in parsed or "items" not in parsed:
            raise ValueError(f"unexpected shape: {parsed!r}")
        return parsed, "ok"
    except Exception as exc:
        logger.warning("DeepSeek news classification failed, defaulting to general: %s", exc)
        return fallback, f"error: {exc}"
