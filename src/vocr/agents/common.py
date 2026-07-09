from __future__ import annotations

import os

from dotenv import load_dotenv


def configured_model() -> str | None:
    load_dotenv()
    return os.getenv("OPENAI_MODEL") or None
