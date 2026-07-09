from __future__ import annotations

from agents import Agent

from vocr.agents.common import configured_model


def build_frontend_agent() -> Agent:
    return Agent(
        name="Frontend Specialist",
        model=configured_model(),
        instructions=(
            "Review UI flow, states, accessibility, and frontend test implications. "
            "Start from graph context and then request only relevant files."
        ),
    )
