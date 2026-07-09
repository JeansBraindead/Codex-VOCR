from __future__ import annotations

import os

from dotenv import load_dotenv


def configured_model() -> str | None:
    load_dotenv()
    return os.getenv("OPENAI_MODEL") or None


def configured_base_url() -> str | None:
    load_dotenv()
    return os.getenv("OPENAI_BASE_URL") or None


def configured_provider() -> str:
    return "local-openai-compatible" if configured_base_url() else "openai"


def live_model_config() -> dict[str, str | None]:
    return {
        "provider": configured_provider(),
        "model": configured_model(),
        "base_url": configured_base_url(),
    }
