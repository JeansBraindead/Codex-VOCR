from __future__ import annotations

from agents import Agent

from vocr.agents.common import configured_model


def build_docs_agent() -> Agent:
    return Agent(
        name="Docs Specialist",
        model=configured_model(),
        instructions=(
            "Identify setup, usage, limitation, and next-step documentation needs. "
            "Use graph context before broad documentation reads."
        ),
    )
