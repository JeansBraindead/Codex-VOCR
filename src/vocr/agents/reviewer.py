from __future__ import annotations

from agents import Agent

from vocr.agents.common import configured_model


def build_reviewer_agent() -> Agent:
    return Agent(
        name="VOCR Reviewer Agent",
        model=configured_model(),
        instructions=(
            "Review task output and decide accepted, needs_changes, or blocked. "
            "Promotion is allowed only after accepted review. Prefer graph and diff "
            "summaries before broad file reads."
        ),
    )
