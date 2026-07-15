from __future__ import annotations

from pathlib import Path


MODEL_KEYS = {"OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY", "LMSTUDIO_API_KEY"}
WORKER_KEYS = {"VOCR_CODEX_PROFILE", "VOCR_CODEX_COMMAND", "VOCR_CODEX_UNSANDBOXED"}


def read_env_file(path: Path | str = ".env") -> dict[str, str]:
    target = Path(path)
    if not target.exists():
        return {}
    values: dict[str, str] = {}
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def update_env_file(updates: dict[str, str | None], path: Path | str = ".env") -> None:
    target = Path(path)
    existing_lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    seen: set[str] = set()
    lines: list[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            lines.append(line)
            continue
        key, _ = stripped.split("=", 1)
        key = key.strip()
        if key in updates:
            seen.add(key)
            value = updates[key]
            if value is not None:
                lines.append(f"{key}={value}")
            continue
        lines.append(line)

    for key, value in updates.items():
        if key not in seen and value is not None:
            lines.append(f"{key}={value}")

    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def redact_env(values: dict[str, str]) -> dict[str, str]:
    redacted = dict(values)
    if redacted.get("OPENAI_API_KEY"):
        redacted["OPENAI_API_KEY"] = "[set]"
    if redacted.get("LMSTUDIO_API_KEY"):
        redacted["LMSTUDIO_API_KEY"] = "[set]"
    return redacted


def provider_from_env(values: dict[str, str]) -> str:
    if values.get("OPENAI_BASE_URL"):
        return "local-openai-compatible"
    if values.get("OPENAI_API_KEY"):
        return "openai"
    return "not configured"
