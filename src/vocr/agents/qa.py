from __future__ import annotations

from agents import Agent

from vocr.agents.common import configured_model


def build_qa_agent() -> Agent:
    return Agent(
        name="QA Specialist",
        model=configured_model(),
        instructions=(
            "Define focused tests, verification commands, and regression risks. "
            "Use graph context to avoid broad repo scanning."
        ),
    )
