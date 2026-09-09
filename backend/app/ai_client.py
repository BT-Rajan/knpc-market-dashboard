"""Shared text-completion client for DeepSeek/Claude. Used anywhere the app
asks an LLM to synthesize text -- the Ask AI panel, news classification, and
report narrative generation. Every caller is responsible for grounding its
prompt in real collected data (prices, headlines, fetched article text) --
this module only makes the call and raises on failure so callers can decide
how to fall back."""
import requests

from app.config import DEEPSEEK_API_URL, DEEPSEEK_MODEL, CLAUDE_API_URL, CLAUDE_MODEL


def ask_deepseek(prompt: str, api_key: str, system: str = None) -> str:
    if not api_key:
        raise RuntimeError("DeepSeek API key is not configured (Admin -> AI Settings)")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = requests.post(
        DEEPSEEK_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": DEEPSEEK_MODEL, "messages": messages, "temperature": 0.3},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def ask_claude(prompt: str, api_key: str, system: str = None, max_tokens: int = 1500) -> str:
    if not api_key:
        raise RuntimeError("Claude API key is not configured (Admin -> AI Settings)")
    body = {
        "model": CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system
    resp = requests.post(
        CLAUDE_API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=60,
    )
    resp.raise_for_status()
    blocks = resp.json().get("content", [])
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


def ask_ai(provider: str, prompt: str, api_key: str, system: str = None) -> str:
    if provider == "claude":
        return ask_claude(prompt, api_key, system=system)
    return ask_deepseek(prompt, api_key, system=system)
