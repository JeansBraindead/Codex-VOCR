from __future__ import annotations

import asyncio
import os
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from vocr.agents.runtime import create_live_task_plan, create_live_vision, live_agents_available
from vocr.bus.bus import MessageBus
from vocr.codex.mcp_client import CodexMcpClient
from vocr.git.worktrees import GitWorktreeError, GitWorktreeManager
from vocr.graph.graphify import GraphStore, RepoGraphBuilder
from vocr.guardrails.scope_guard import ScopeGuard
from vocr.memory.ledger import MemoryLedger, sanitize_payload
from vocr.models import (
    ClarificationSession,
    LedgerEventType,
    PermissionGrant,
    PermissionMode,
    ReviewDecision,
    TaskStatus,
)
from vocr.orchestration.workflow import (
    create_vision,
    dispatch_task,
    organize_slice,
    promote_task,
    review_task,
    render_task_template,
)
from vocr.orchestration.readiness import assess_request_readiness

app = typer.Typer(help="VOCR: Vision / Organize / Code / Review")
console = Console()


def safe_text(value: str) -> str:
    sanitized = sanitize_payload(value)
    return escape(sanitized if isinstance(sanitized, str) else str(sanitized))


def ledger() -> MemoryLedger:
    load_dotenv()
    return MemoryLedger(Path(os.getenv("VOCR_HOME", ".vocr")))


def graph_store() -> GraphStore:
    load_dotenv()
    return GraphStore(Path(os.getenv("VOCR_HOME", ".vocr")))


def refresh_graph() -> None:
    graph_store().save(RepoGraphBuilder(".").build())


def persist_tasks(store: MemoryLedger, tasks: list, *, print_tasks: bool = True) -> None:
    for task in tasks:
        store.append(LedgerEventType.task_created, task)
        if print_tasks:
            console.print(f"[green]Created task[/green] {task.id}: {task.title}")
            console.print(render_task_template(task))


def write_dispatch_handoff(store: MemoryLedger, task_id: str) -> None:
    task = dispatch_task(store, GitWorktreeManager(), task_id)
    MessageBus(store).publish("dispatch", "vocr", f"Task {task.id} dispatched to {task.worktree_path}")
    permission = store.active_permission(task.slice_id) or store.active_permission("global")
    manifest_path = CodexMcpClient().write_manifest(task, permission=permission)
    scope_path = ScopeGuard().write_worker_policy(task)
    console.print(f"[green]Dispatched[/green] {task.id} to {task.worktree_path}")
    if permission:
        console.print(f"[yellow]Permission mode:[/yellow] {permission.mode.value} ({permission.scope})")
    else:
        console.print("[yellow]Permission mode:[/yellow] ask_each_time")
    console.print(f"[cyan]Task manifest:[/cyan] {manifest_path}")
    console.print(f"[cyan]Scope policy:[/cyan] {scope_path}")
    console.print("Codex MCP execution is prepared but not implemented yet.")


def request_clarification(store: MemoryLedger, request: str) -> bool:
    readiness = assess_request_readiness(request)
    if readiness.ready:
        return False

    session = ClarificationSession(request=request, report=readiness)
    store.append(LedgerEventType.clarification_requested, session)
    console.print("[yellow]Der Visionaer braucht noch Informationen, bevor er loslegt.[/yellow]")
    console.print(f"Clarification ID: {session.id}")
    console.print(f"Readiness: {readiness.confidence:.0%}")
    for index, question in enumerate(readiness.questions, start=1):
        console.print(f"{index}. [bold]{safe_text(question.topic)}[/bold]: {safe_text(question.question)}")
        console.print(f"   Warum: {safe_text(question.why_needed)}")
    console.print(
        "\nAntworte mit `vocr answer "
        f"{session.id} \"<deine Details>\"`. VOCR legt bis dahin keine Tasks und keine Worktrees an."
    )
    return True


def run_vision_pipeline(
    request: str,
    *,
    go: bool,
    live_agent: bool,
    auto: bool,
    dispatch_workers: bool,
) -> None:
    store = ledger()
    store.init()
    if request_clarification(store, request):
        return

    if auto:
        refresh_graph()
        console.print("[green]Graphify complete[/green] Visionary will use token-efficient context.")

    item = create_vision(request)
    if live_agent and live_agents_available():
        try:
            item = asyncio.run(create_live_vision(request))
        except Exception as exc:
            console.print(f"[yellow]Live agent failed, using local fallback:[/yellow] {safe_text(str(exc))}")
    elif live_agent:
        console.print("[yellow]OPENAI_API_KEY is missing, using local fallback.[/yellow]")
    store.append(LedgerEventType.vision_created, item)
    if go:
        grant = PermissionGrant(mode=PermissionMode.approve_all, scope=item.id)
        store.append(LedgerEventType.permission_granted, grant)
    console.print(f"[green]Created slice[/green] {item.id}")
    console.print(f"Goal: {safe_text(item.goal)}")
    if go:
        console.print("[yellow]Approve-all is active for this slice.[/yellow]")

    if not auto:
        console.print("[yellow]Plan-only mode:[/yellow] run organize/dispatch manually if needed.")
        return

    tasks = organize_slice(item, vocr_home=str(store.root))
    if live_agent and live_agents_available():
        try:
            context_pack = graph_store().context_pack(query=item.goal, limit=12)
            plan = asyncio.run(create_live_task_plan(item, context_pack))
            tasks = plan.tasks or tasks
            for task in tasks:
                if not task.context_pack:
                    task.context_query = task.context_query or item.goal
                    task.context_pack = graph_store().context_pack(query=task.context_query, limit=12)
        except Exception as exc:
            console.print(f"[yellow]Live organizer failed, using local fallback:[/yellow] {safe_text(str(exc))}")

    persist_tasks(store, tasks)

    if go and dispatch_workers:
        for task in tasks:
            try:
                write_dispatch_handoff(store, task.id)
            except (GitWorktreeError, ValueError) as exc:
                console.print(f"[yellow]Dispatch skipped for {task.id}:[/yellow] {safe_text(str(exc))}")
    elif not go:
        console.print("[yellow]Dispatch paused:[/yellow] pass --go when the Visionary should continue unattended.")


@app.command()
def setup() -> None:
    store = ledger()
    store.init()
    GitWorktreeManager().worktree_root.mkdir(parents=True, exist_ok=True)
    store.append(LedgerEventType.setup, {"message": "VOCR workspace initialized."})
    console.print(f"[green]VOCR workspace initialized at {store.root}[/green]")


@app.command()
def graphify() -> None:
    graph = RepoGraphBuilder(".").build()
    store = graph_store()
    store.save(graph)
    console.print(f"[green]Graph written[/green] {store.path}")
    console.print(f"Files indexed: {len(graph.nodes)}")
    console.print(f"Edges indexed: {len(graph.edges)}")


@app.command("context")
def context(
    query: str | None = typer.Argument(
        None,
        help="Optional search terms for a smaller context pack.",
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum files in the brief."),
) -> None:
    store = graph_store()
    if not store.exists():
        raise typer.BadParameter("No graph found. Run 'vocr graphify' first.")
    console.print(store.context_pack(query=query, limit=limit))


@app.command()
def vision(
    request: str,
    go: bool = typer.Option(
        False,
        "--go",
        help="Give this slice approve-all permission for unattended VOCR execution.",
    ),
    live_agent: bool = typer.Option(
        False,
        "--live-agent",
        help="Use OpenAI Agents SDK when OPENAI_API_KEY is available.",
    ),
    auto: bool = typer.Option(
        True,
        "--auto/--plan-only",
        help="Let the Visionary orchestrate graphify and task creation automatically.",
    ),
    dispatch_workers: bool = typer.Option(
        True,
        "--dispatch/--no-dispatch",
        help="With --go, dispatch generated tasks to isolated worktrees.",
    ),
) -> None:
    run_vision_pipeline(
        request,
        go=go,
        live_agent=live_agent,
        auto=auto,
        dispatch_workers=dispatch_workers,
    )


@app.command()
def answer(
    clarification_id: str,
    details: str,
    go: bool = typer.Option(
        False,
        "--go",
        help="Give this clarified slice approve-all permission for unattended VOCR execution.",
    ),
    live_agent: bool = typer.Option(False, "--live-agent", help="Use OpenAI Agents SDK when available."),
    dispatch_workers: bool = typer.Option(True, "--dispatch/--no-dispatch"),
) -> None:
    store = ledger()
    session = store.get_clarification(clarification_id)
    if session is None:
        raise typer.BadParameter(f"Unknown clarification id: {clarification_id}")
    store.append(
        LedgerEventType.clarification_answered,
        {"session_id": clarification_id, "answer": details},
    )
    combined = "\n".join([session.request, *session.answers, details])
    run_vision_pipeline(
        combined,
        go=go,
        live_agent=live_agent,
        auto=True,
        dispatch_workers=dispatch_workers,
    )


@app.command("go")
def grant_go(
    scope: str = typer.Argument("global", help="Use 'global' or a slice id."),
    all_permissions: bool = typer.Option(
        False,
        "--all",
        help="Required explicit flag for approve-all unattended execution.",
    ),
    reason: str = typer.Option(
        "User approved unattended VOCR execution.",
        "--reason",
        help="Why this permission was granted.",
    ),
) -> None:
    if not all_permissions:
        raise typer.BadParameter("Use --all to explicitly grant approve-all permission.")
    grant = PermissionGrant(mode=PermissionMode.approve_all, scope=scope, reason=reason)
    ledger().append(LedgerEventType.permission_granted, grant)
    console.print(f"[green]Approve-all granted[/green] for scope: {scope}")


@app.command()
def organize(
    slice_id: str,
    live_agent: bool = typer.Option(
        False,
        "--live-agent",
        help="Use OpenAI Agents SDK for task planning when available.",
    ),
) -> None:
    store = ledger()
    slice_item = store.get_slice(slice_id)
    if slice_item is None:
        raise typer.BadParameter(f"Unknown slice id: {slice_id}")
    tasks = organize_slice(slice_item, vocr_home=str(store.root))
    if live_agent and live_agents_available():
        try:
            context_pack = graph_store().context_pack(query=slice_item.goal, limit=12)
            plan = asyncio.run(create_live_task_plan(slice_item, context_pack))
            tasks = plan.tasks or tasks
        except Exception as exc:
            console.print(f"[yellow]Live organizer failed, using local fallback:[/yellow] {safe_text(str(exc))}")
    elif live_agent:
        console.print("[yellow]OPENAI_API_KEY is missing, using local fallback.[/yellow]")
    for task in tasks:
        if not task.context_pack:
            task.context_query = task.context_query or slice_item.goal
            task.context_pack = graph_store().context_pack(query=task.context_query, limit=12)
    persist_tasks(store, tasks)


@app.command()
def dispatch(task_id: str) -> None:
    store = ledger()
    try:
        write_dispatch_handoff(store, task_id)
    except (GitWorktreeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command("run")
def run_worker(
    task_id: str,
    timeout_seconds: int = typer.Option(3600, "--timeout", help="Worker timeout in seconds."),
) -> None:
    store = ledger()
    task = store.get_task(task_id)
    if task is None:
        raise typer.BadParameter(f"Unknown task id: {task_id}")
    permission = store.active_permission(task.slice_id) or store.active_permission("global")
    try:
        result = CodexMcpClient().run_task(task, permission=permission, timeout_seconds=timeout_seconds)
    except (RuntimeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]Worker finished[/green] exit={result.exit_code}")
    if result.stdout:
        console.print(safe_text(result.stdout[-2000:]))
    if result.stderr:
        console.print(f"[yellow]{safe_text(result.stderr[-2000:])}[/yellow]")


@app.command()
def status() -> None:
    store = ledger()
    table = Table(title="VOCR Status")
    table.add_column("ID")
    table.add_column("Kind")
    table.add_column("Status")
    table.add_column("Title / Goal")
    for item in store.slices():
        table.add_row(item.id, "slice", "-", safe_text(item.goal))
    for task in store.tasks():
        table.add_row(task.id, "task", task.status.value, task.title)
    console.print(table)
    grants = store.permission_grants()
    if grants:
        permission_table = Table(title="VOCR Permissions")
        permission_table.add_column("Mode")
        permission_table.add_column("Scope")
        permission_table.add_column("Reason")
        for grant in grants:
            permission_table.add_row(grant.mode.value, grant.scope, safe_text(grant.reason))
        console.print(permission_table)


@app.command()
def review(
    task_id: str,
    decision: ReviewDecision | None = typer.Option(
        None,
        "--decision",
        "-d",
        help="Explicit manual review decision: accepted, needs_changes, or blocked.",
    ),
    summary: str | None = typer.Option(None, "--summary", "-s", help="Short review summary."),
) -> None:
    result = review_task(ledger(), task_id, decision=decision, summary=summary)
    color = "green" if result.decision == ReviewDecision.accepted else "yellow"
    console.print(f"[{color}]Review: {result.decision.value}[/{color}]")
    console.print(result.summary)
    for change in result.required_changes:
        console.print(f"- {change}")
    for test in result.test_results:
        console.print(f"[cyan]Check:[/cyan] {safe_text(test.command)} -> {test.status}")
        if test.output:
            console.print(safe_text(test.output))
    if result.git_status:
        console.print(f"[cyan]Git status:[/cyan] {safe_text(result.git_status)}")
    if result.diff_summary:
        console.print(f"[cyan]Diff summary:[/cyan] {safe_text(result.diff_summary)}")


@app.command()
def promote(task_id: str) -> None:
    store = ledger()
    task = store.get_task(task_id)
    if task is None:
        raise typer.BadParameter(f"Unknown task id: {task_id}")
    if task.status != TaskStatus.accepted:
        raise typer.BadParameter("Task must have an accepted review before promote.")
    try:
        promote_task(store, GitWorktreeManager(), task_id)
    except (GitWorktreeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]Promoted[/green] {task_id}")


@app.command()
def tweak(small_change: str) -> None:
    store = ledger()
    store.append(
        LedgerEventType.tweak_recorded,
        {
            "change": small_change,
            "rule": "Tweak is only for small, low-risk changes.",
        },
    )
    console.print("[green]Tweak recorded[/green]")
    console.print("Use normal code edits only if the change stays small and low-risk.")


@app.command()
def doctor() -> None:
    store = ledger()
    store.init()
    git_status = GitWorktreeManager().doctor()
    table = Table(title="VOCR Doctor")
    table.add_column("Check")
    table.add_column("Result")
    table.add_row("Ledger", str(store.path))
    table.add_row("Graph", str(graph_store().path if graph_store().exists() else "missing"))
    table.add_row("Git repository", git_status["git_repo"])
    table.add_row("Worktree root", git_status["worktree_root"])
    table.add_row("Approve-all grants", str(len(store.permission_grants())))
    table.add_row("Codex MCP", "adapter only; TODO")
    console.print(table)
