from __future__ import annotations

from agents import Agent

from vocr.agents.common import configured_model


def build_backend_agent() -> Agent:
    return Agent(
        name="Backend Specialist",
        model=configured_model(),
        instructions=(
            "Review backend API, validation, data flow, error handling, and tests. "
            "Start from graph context and then request only relevant files."
        ),
    )
