from __future__ import annotations

from agents import Agent, Runner
from dotenv import load_dotenv

from vocr.agents.common import configured_base_url, configured_model
from vocr.agents.architect import build_architect_agent
from vocr.agents.backend import build_backend_agent
from vocr.agents.docs import build_docs_agent
from vocr.agents.frontend import build_frontend_agent
from vocr.agents.organizer import build_organizer_agent
from vocr.agents.qa import build_qa_agent
from vocr.agents.requirements import build_requirements_agent
from vocr.agents.security import build_security_agent
from vocr.models import TaskPlan, VisionSlice


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
