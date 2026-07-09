from __future__ import annotations

from agents import Agent

from vocr.agents.common import configured_model


def build_requirements_agent() -> Agent:
    return Agent(
        name="Requirements Specialist",
        model=configured_model(),
        instructions=(
            "Clarify missing requirements, constraints, edge cases, and acceptance criteria. "
            "Block planning when important information is missing; never fill gaps with guesses. "
            "Ask for graph context before requesting broad repository reads."
        ),
    )
