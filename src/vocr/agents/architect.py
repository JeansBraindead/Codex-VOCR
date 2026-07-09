from __future__ import annotations

from agents import Agent

from vocr.agents.common import configured_model


def build_architect_agent() -> Agent:
    return Agent(
        name="Architect Specialist",
        model=configured_model(),
        instructions=(
            "Suggest simple architecture boundaries and sequencing for a small task. "
            "Use Graphify context to stay token-efficient."
        ),
    )
