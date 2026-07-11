from __future__ import annotations

import os

from agents import Agent, Runner
from dotenv import load_dotenv

from vocr.agents.common import configured_base_url, configured_model, configured_provider
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
        tools=[],
    )
    result = await Runner.run(agent, request)
    return VisionSlice.model_validate(result.final_output)


async def create_live_task_plan(slice_item: VisionSlice, context_pack: str) -> TaskPlan:
    agent = Agent(
        name="VOCR Live Organizer",
        model=configured_model(),
        output_type=TaskPlan,
        instructions=(
            "Create a tiny VOCR task plan from a VisionSlice. Every task must have "
            "scope, non-goals, acceptance criteria, tests, and a context query. "
            "Prefer one task unless the work is clearly separable."
        ),
        tools=[],
    )
    prompt = (
        f"VisionSlice:\n{slice_item.model_dump_json(indent=2)}\n\n"
        f"Token-efficient repo context:\n{context_pack}"
    )
    result = await Runner.run(agent, prompt)
    return TaskPlan.model_validate(result.final_output)
