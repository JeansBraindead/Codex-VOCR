from __future__ import annotations

import os

from agents import Agent, Runner
from dotenv import load_dotenv

from vocr.agents.common import configured_base_url, configured_model, configured_provider
from vocr.agents.architect import build_architect_agent
from vocr.agents.backend import build_backend_agent
from vocr.agents.docs import build_docs_agent
from vocr.agents.frontend import build_frontend_agent
from vocr.agents.organizer import build_organizer_agent
from vocr.agents.qa import build_qa_agent
from vocr.agents.requirements import build_requirements_agent
from vocr.agents.security import build_security_agent
from vocr.models import TaskPlan, VisionSlice


def _status_code_from_exception(exc: BaseException) -> int | None:
    for attr in ("status_code", "status", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    if isinstance(value, int):
        return value
    text = str(exc)
    return 401 if "401" in text else None


def diagnose_live_agent_error(
    exc: BaseException,
    *,
    provider: str | None = None,
    base_url: str | None = None,
) -> str:
    active_provider = provider or configured_provider()
    active_base_url = base_url if base_url is not None else configured_base_url()
    local_provider = active_provider == "local-openai-compatible" or bool(active_base_url)
    status_code = _status_code_from_exception(exc)

    if local_provider and status_code == 401:
        return (
            "LM Studio hat die Anfrage wegen API-Key/Auth abgelehnt. "
            "Vermutlich ist Auth im LM-Studio-Server aktiv oder der gesetzte Token ist ungueltig. "
            "Deaktiviere Auth im LM-Studio-Server oder setze einen gueltigen LM-Studio-API-Token. "
            "VOCR wertet das nicht als erfolgreiche Live-Agent-Ausfuehrung und nutzt den lokalen Fallback."
        )

    return f"Live-Agent-Ausfuehrung fehlgeschlagen. VOCR nutzt den lokalen Fallback. Ursache: {exc}"


def live_agents_available() -> bool:
    load_dotenv()
    return bool(os.getenv("OPENAI_API_KEY") or configured_base_url())


async def create_live_vision(request: str) -> VisionSlice:
    agent = Agent(
        name="VOCR Live Visionary",
        model=configured_model(),
        output_type=VisionSlice,
        instructions=(
            "Create a concise VOCR VisionSlice. Capture the goal, assumptions, "
            "and acceptance criteria. Do not include secrets. Keep it small."
        ),
        tools=[
            build_requirements_agent().as_tool(
                tool_name="requirements_specialist",
                tool_description="Clarify requirements and acceptance criteria.",
            ),
            build_architect_agent().as_tool(
                tool_name="architect_specialist",
                tool_description="Suggest simple architecture boundaries.",
            ),
            build_security_agent().as_tool(
                tool_name="security_specialist",
                tool_description="Review permission and secret-handling risks.",
            ),
        ],
    )
    result = await Runner.run(agent, request)
    return VisionSlice.model_validate(result.final_output)


async def create_live_task_plan(slice_item: VisionSlice, context_pack: str) -> TaskPlan:
    organizer = build_organizer_agent()
    agent = Agent(
        name="VOCR Live Organizer",
        model=configured_model(),
        output_type=TaskPlan,
        instructions=(
            "Create a tiny VOCR task plan from a VisionSlice. Every task must have "
            "scope, non-goals, acceptance criteria, tests, and a context query. "
            "Prefer one task unless the work is clearly separable."
        ),
        tools=[
            organizer.as_tool(
                tool_name="organizer_agent",
                tool_description="Split work into small reviewable tasks.",
            ),
            build_backend_agent().as_tool(
                tool_name="backend_specialist",
                tool_description="Review backend implications.",
            ),
            build_frontend_agent().as_tool(
                tool_name="frontend_specialist",
                tool_description="Review frontend implications.",
            ),
            build_qa_agent().as_tool(
                tool_name="qa_specialist",
                tool_description="Suggest verification steps.",
            ),
            build_docs_agent().as_tool(
                tool_name="docs_specialist",
                tool_description="Suggest documentation changes.",
            ),
        ],
    )
    prompt = (
        f"VisionSlice:\n{slice_item.model_dump_json(indent=2)}\n\n"
        f"Token-efficient repo context:\n{context_pack}"
    )
    result = await Runner.run(agent, prompt)
    return TaskPlan.model_validate(result.final_output)
