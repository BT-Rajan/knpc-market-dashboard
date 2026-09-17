import requests
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth import get_current_user
from app.schemas import AIAskRequest, AIAskResponse, AICredentialsOut
from app.services import (
    get_item_by_code_or_404,
    trend_fields,
    recent_news,
    resolve_ai_key,
    get_ai_credentials_row,
    build_market_overview_context,
)
from app.ai_client import ask_deepseek, ask_claude

router = APIRouter(prefix="/api/ai", tags=["ai"], dependencies=[Depends(get_current_user)])


@router.get("/providers", response_model=AICredentialsOut)
def get_provider_status(db: Session = Depends(get_db)):
    """Which providers currently have a key configured -- available to any
    signed-in user (not just admins) so the Ask-AI panel can default to,
    and label, a provider that's actually usable instead of guessing."""
    row = get_ai_credentials_row(db)
    return AICredentialsOut(
        deepseek_configured=bool(row.deepseek_api_key),
        claude_configured=bool(row.claude_api_key),
    )


def _build_context(db: Session, item_code: str | None) -> str:
    """Always includes a site-wide snapshot of every tracked crude benchmark
    and product plus recent general headlines, so the AI can answer
    anything about this system's crude/product content -- not only
    questions about a single item. If item_code is given (the person is
    focused on one item's page), a closer look at that item's own price and
    headlines is appended on top of the overview."""
    parts = [build_market_overview_context(db)]
    if item_code:
        item = get_item_by_code_or_404(db, item_code)
        fields = trend_fields(db, item.id)
        news = recent_news(db, item.id, limit=5)
        lines = [
            f"Focused item: {item.name} ({item.category}, {item.unit})",
            f"Current price: {fields['current_price']}, previous: {fields['previous_price']}, "
            f"daily change: {fields['daily_change']} ({fields['daily_change_pct']}%), as of {fields['as_of']}",
            "Recent headlines for this item:",
        ]
        lines += [f"- {n.headline}" for n in news] or ["- (none collected yet)"]
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _ask_deepseek(prompt: str, api_key: str) -> str:
    if not api_key:
        raise HTTPException(status_code=503, detail="DeepSeek API key is not configured. Add it under Admin -> AI Settings.")
    try:
        return ask_deepseek(prompt, api_key)
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"DeepSeek API error: {exc.response.status_code} {exc.response.text[:200]}")
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"DeepSeek request failed: {exc}")


def _ask_claude(prompt: str, api_key: str) -> str:
    if not api_key:
        raise HTTPException(status_code=503, detail="Claude API key is not configured. Add it under Admin -> AI Settings.")
    try:
        return ask_claude(prompt, api_key)
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Claude API error: {exc.response.status_code} {exc.response.text[:200]}")
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Claude request failed: {exc}")


@router.post("/ask", response_model=AIAskResponse)
def ask(body: AIAskRequest, db: Session = Depends(get_db)):
    context = _build_context(db, body.item_code)
    prompt = (
        f"You are a market intelligence assistant for a petroleum pricing dashboard.\n"
        f"{('Context:\\n' + context) if context else ''}\n\n"
        f"Question: {body.question}\n"
        f"Answer concisely, and note explicitly if the available data is insufficient."
    )

    if body.provider == "deepseek":
        answer = _ask_deepseek(prompt, resolve_ai_key(db, "deepseek"))
    elif body.provider == "claude":
        answer = _ask_claude(prompt, resolve_ai_key(db, "claude"))
    else:
        raise HTTPException(status_code=422, detail="provider must be 'deepseek' or 'claude'")

    return AIAskResponse(provider=body.provider, answer=answer)
