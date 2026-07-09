from __future__ import annotations

from agents import Agent

from vocr.agents.common import configured_model


def build_security_agent() -> Agent:
    return Agent(
        name="Security Specialist",
        model=configured_model(),
        instructions=(
            "Review secret handling, permissions, dependency risk, and privacy concerns. "
            "Use targeted graph context and avoid exposing secrets."
        ),
    )
