from __future__ import annotations

from agents import Agent

from vocr.agents.common import configured_model


def build_tweak_agent() -> Agent:
    return Agent(
        name="VOCR Tweak Agent",
        model=configured_model(),
        instructions=(
            "Handle only small, low-risk changes. Escalate anything broad or risky "
            "back to Vision and Organize. Use targeted context only."
        ),
    )
