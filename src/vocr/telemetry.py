from __future__ import annotations

import json
import re
from typing import Any

from vocr.models import TokenUsage


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text else 0


def extract_token_usage(text: str) -> TokenUsage | None:
    """Extract real token usage from JSON emitted by a worker, when present."""
    for item in _json_objects(text):
        usage = _usage_payload(item)
        if not usage:
            continue
        prompt = _int_value(usage, "prompt_tokens", "input_tokens")
        completion = _int_value(usage, "completion_tokens", "output_tokens")
        total = _int_value(usage, "total_tokens")
        if total is None and (prompt is not None or completion is not None):
            total = (prompt or 0) + (completion or 0)
        if total is not None:
            return TokenUsage(
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=total,
                source="actual",
            )
    return None


def estimated_token_usage(prompt_text: str, output_text: str) -> TokenUsage:
    prompt = estimate_tokens(prompt_text)
    completion = estimate_tokens(output_text)
    return TokenUsage(
        total_tokens=prompt + completion,
        prompt_tokens_estimate=prompt,
        completion_tokens_estimate=completion,
        source="estimated",
    )


def token_total(usage: TokenUsage) -> int:
    return usage.total_tokens or (usage.prompt_tokens_estimate or 0) + (
        usage.completion_tokens_estimate or 0
    )


def _usage_payload(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    usage = item.get("usage") or item.get("token_usage")
    if isinstance(usage, dict):
        return usage
    if any(key in item for key in ("prompt_tokens", "completion_tokens", "total_tokens")):
        return item
    return None


def _int_value(item: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _json_objects(text: str) -> list[Any]:
    items: list[Any] = []
    stripped = text.strip()
    if stripped:
        try:
            items.append(json.loads(stripped))
        except json.JSONDecodeError:
            pass
    for match in re.finditer(r"\{.*?\}", text, flags=re.DOTALL):
        try:
            items.append(json.loads(match.group(0)))
        except json.JSONDecodeError:
            continue
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items
