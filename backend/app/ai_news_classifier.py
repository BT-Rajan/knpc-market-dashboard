"""Groups scraped oilprice.com headline URLs into 'general' market news vs
a specific tracked item, via DeepSeek, instead of local keyword-guessing.
Classification is a nice-to-have -- collection itself must never depend on
it succeeding, so every failure mode here falls back to 'general'."""
import json
import logging
import re

import requests

from app.config import DEEPSEEK_API_URL, DEEPSEEK_MODEL

logger = logging.getLogger("knpc.ai_news")


def classify_urls(urls: list[str], item_names: list[str], api_key: str) -> tuple[dict, str]:
    """Returns (grouping, status). grouping is {"general": [...], "items":
    {name: [...]}}. status is "ok", "no_api_key" (nothing configured under
    Admin -> AI Settings), or "error: <detail>" (the call/parse failed) --
    callers should log this so 'everything landed in general' has a visible
    reason instead of looking identical to a real classification.
    Only the URLs are sent to the model -- no scraped article text/titles --
    since the URL slug alone is normally enough to tell what an oilprice.com
    piece is about."""
    fallback = {"general": list(urls), "items": {}}
    if not urls:
        return fallback, "ok"
    if not api_key:
        return fallback, "no_api_key"

    prompt = (
        "You will be given a JSON array of oilprice.com article URLs. "
        "Classify each one as either general oil/energy market news, or as "
        "specifically about one of these tracked items (judge the topic from "
        "the URL slug): " + ", ".join(item_names) + ".\n\n"
        "Return ONLY strict JSON, no markdown fences, no commentary, in exactly "
        "this shape:\n"
        '{"general": ["<url>", ...], "items": {"<item name>": ["<url>", ...]}}\n\n'
        "Every URL from the input must appear exactly once in the output, either "
        "in general or under exactly one item name (use the item names exactly "
        "as given above). If unsure, put it in general.\n\n"
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
        if not isinstance(parsed, dict) or "general" not in parsed or "items" not in parsed:
            raise ValueError(f"unexpected shape: {parsed!r}")
        return parsed, "ok"
    except Exception as exc:
        logger.warning("DeepSeek news classification failed, defaulting to general: %s", exc)
        return fallback, f"error: {exc}"
