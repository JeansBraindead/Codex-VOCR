from __future__ import annotations

from agents import Agent

from vocr.agents.architect import build_architect_agent
from vocr.agents.backend import build_backend_agent
from vocr.agents.common import configured_model
from vocr.agents.docs import build_docs_agent
from vocr.agents.frontend import build_frontend_agent
from vocr.agents.organizer import build_organizer_agent
from vocr.agents.qa import build_qa_agent
from vocr.agents.requirements import build_requirements_agent
from vocr.agents.security import build_security_agent


def build_visionary_agent() -> Agent:
    organizer = build_organizer_agent()
    requirements = build_requirements_agent()
    architect = build_architect_agent()
    backend = build_backend_agent()
    frontend = build_frontend_agent()
    qa = build_qa_agent()
    security = build_security_agent()
    docs = build_docs_agent()

    return Agent(
        name="VOCR Visionary Agent",
        model=configured_model(),
        instructions=(
            "Hold the user goal, assumptions, non-goals, and acceptance criteria. "
            "If required information is missing, ask explicit clarification questions "
            "and do not invent details. "
            "Use specialist tools when useful. Do not dispatch work directly. "
            "Keep the vision concise and testable. For token efficiency, prefer "
            "the Graphify context brief before asking workers to inspect files."
        ),
        tools=[
            organizer.as_tool(
                tool_name="organizer_agent",
                tool_description="Split a vision into small VOCR tasks.",
            ),
            requirements.as_tool(
                tool_name="requirements_specialist",
                tool_description="Clarify requirements and acceptance criteria.",
            ),
            architect.as_tool(
                tool_name="architect_specialist",
                tool_description="Suggest simple architecture boundaries.",
            ),
            backend.as_tool(
                tool_name="backend_specialist",
                tool_description="Review backend concerns and tests.",
            ),
            frontend.as_tool(
                tool_name="frontend_specialist",
                tool_description="Review frontend concerns and tests.",
            ),
            qa.as_tool(
                tool_name="qa_specialist",
                tool_description="Suggest focused verification steps.",
            ),
            security.as_tool(
                tool_name="security_specialist",
                tool_description="Review secret, permission, and dependency risks.",
            ),
            docs.as_tool(
                tool_name="docs_specialist",
                tool_description="Review documentation needs.",
            ),
        ],
    )
