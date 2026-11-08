"""Thin OpenAI-compatible chat client for OpenRouter."""

from __future__ import annotations

import re
import time
from typing import Any

import httpx

from config import API_KEY, BASE_URL, MODEL


def clean_text(text: str) -> str:
    text = re.sub(r"<details[^>]*?>.*?</details>", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"</?summary[^>]*>", "", text)
    return text.strip()


def chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.0,
    timeout: float = 45.0,
) -> str:
    if not API_KEY:
        raise RuntimeError("LLM_API_KEY در settings.env تنظیم نشده است.")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "KRS Invoice ChatBot",
    }
    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    for attempt in range(4):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(BASE_URL, headers=headers, json=payload)
            if resp.status_code in (429, 502, 503, 504) and attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                raise RuntimeError(f"OpenRouter {resp.status_code}: {resp.text[:500]}")
            data = resp.json()
            break
        except httpx.TransportError:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))

    content = data["choices"][0]["message"]["content"]
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        content = "".join(parts)
    return clean_text(str(content or ""))


def extract_sql(text: str) -> str:
    """Pull SQL out of optional markdown fences / chatter."""
    cleaned = clean_text(text)
    fence = re.search(r"```(?:sql)?\s*([\s\S]*?)```", cleaned, flags=re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    lines = cleaned.splitlines()
    for i, line in enumerate(lines):
        if re.match(
            r"^\s*(WITH|SELECT|INSERT|UPDATE|DELETE)\b",
            line,
            flags=re.IGNORECASE,
        ):
            return "\n".join(lines[i:]).strip()
    return cleaned.strip()
