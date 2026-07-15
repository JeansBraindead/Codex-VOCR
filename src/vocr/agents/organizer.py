from __future__ import annotations

from agents import Agent

from vocr.agents.common import configured_model


def build_organizer_agent() -> Agent:
    return Agent(
        name="VOCR Organizer Agent",
        model=configured_model(),
        instructions=(
            "Split a vision slice into small tasks. Every task needs scope, non-goals, "
            "acceptance criteria, and tests. Avoid broad implementation batches. "
            "Use Graphify context packs to choose a minimal file set."
        ),
    )
