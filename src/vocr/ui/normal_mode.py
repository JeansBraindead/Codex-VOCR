from __future__ import annotations

import base64
import json
import re
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from vocr.codex.mcp_client import CodexMcpClient
from vocr.config.env_file import read_env_file, update_env_file
from vocr.git.worktrees import GitWorktreeError, GitWorktreeManager
from vocr.graph.graphify import GraphStore
from vocr.guardrails.scope_guard import ScopeGuard
from vocr.memory.ledger import MemoryLedger
from vocr.models import (
    LedgerEventType,
    NormalModePhase,
    NormalModeStatus,
    PermissionGrant,
    PermissionMode,
    ProjectIntake,
    VocrTask,
)
from vocr.orchestration.readiness import parse_request_sections
from vocr.orchestration.worker_advisor import WorkerParallelismAdvisor
from vocr.orchestration.workflow import create_vision, dispatch_task, organize_slice


REQUIRED_TOPICS: tuple[tuple[str, str, str], ...] = (
    ("goal", "Ziel", "Was soll am Ende konkret funktionieren, und fuer wen?"),
    ("workspace", "Arbeitsbereich", "Welche Projektbereiche darf ich anfassen? Nenne bitte Pfade, Module oder klare Grenzen."),
    (
        "acceptance_criteria",
        "Akzeptanzkriterien",
        "Woran erkennst du eindeutig, dass das Ergebnis fertig ist? Bitte als pruefbare Punkte.",
    ),
    ("verification", "Verifikation", "Wie soll ich pruefen, dass es funktioniert? Zum Beispiel Tests, Syntax-Check oder manueller Ablauf."),
    ("non_goals", "Nicht-Ziele", "Was soll ich ausdruecklich nicht tun oder nicht veraendern?"),
    (
        "execution_bounds",
        "Ausfuehrung",
        "Soll ich nach deiner Freigabe nur planen oder bis zur Pruefung vorbereiten? Veroeffentlichen bleibt immer manuell.",
    ),
)

CLARIFICATION_ID_PATTERN = re.compile(r"\bclarify-[A-Za-z0-9_-]+\b")
EXPERT_ANSWER_COMMAND_PATTERN = re.compile(r"`?vocr\s+answer\b[^`\n]*`?", re.IGNORECASE)
CLARIFICATION_TERM_PATTERN = re.compile(r"\bClarification-?IDs?\b|\bClarification ID\b", re.IGNORECASE)
NORMAL_MODE_SURFACE = "tkinter-gui"
NORMAL_MODE_SURFACE_CONSTRAINTS = (
    "no_cloud_dependency",
    "no_frontend_buildchain",
    "no_extra_runtime_dependency",
    "single_textbox_dialog",
    "status_panel_only",
)


def normal_mode_surface_decision() -> dict[str, object]:
    return {
        "selected": NORMAL_MODE_SURFACE,
        "fallback": "console",
        "constraints": list(NORMAL_MODE_SURFACE_CONSTRAINTS),
        "why": [
            "Python stdlib keeps the MVP local-first and install-light.",
            "A quiet textbox plus status panel matches the normal user flow.",
            "The controller stays testable without rendering the GUI.",
        ],
        "deferred": [
            "Textual/TUI when terminal polish becomes more important than zero dependencies.",
            "Local web GUI when browser delivery is worth adding a server surface.",
        ],
    }


@dataclass(frozen=True)
class NormalModeResponse:
    message: str
    status: NormalModeStatus
    phase: NormalModePhase
    prepared_tasks: int = 0
    prepared_worktrees: int = 0


@dataclass(frozen=True)
class IntakeProposal:
    understood_goal: str
    intake: ProjectIntake


class NormalModeUiError(RuntimeError):
    """Raised when the local dialog window cannot be opened."""


class NormalModeController:
    def __init__(
        self,
        repo_root: str | Path = ".",
        vocr_home: str | Path | None = None,
        session_permission: PermissionGrant | None = None,
        on_activity: Callable[[str], None] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.ledger = MemoryLedger(Path(vocr_home) if vocr_home else self.repo_root / ".vocr")
        self.graph_store = GraphStore(self.ledger.root)
        self.session_permission = session_permission
        self.phase = NormalModePhase.welcome
        self.intake = ProjectIntake()
        self.pending_proposal: IntakeProposal | None = None
        self.active_topic: str | None = None
        self.history: list[str] = []
        self.prepared_task_count = 0
        self.prepared_worktree_count = 0
        self.on_activity = on_activity

    def _activity(self, message: str) -> None:
        if self.on_activity:
            self.on_activity(message)

    def opening_message(self) -> NormalModeResponse:
        if self.session_permission:
            permission_note = (
                "\n\nWARNUNG: Approve-all ist fuer diese Session aktiv. Ich ueberspringe interne "
                "Worker-Permission-Nachfragen, aber Review, Secret-Scan und Promote-Gates bleiben aktiv."
            )
        elif self.ledger.active_permission("global"):
            permission_note = (
                "\n\nWARNUNG: Ein persistenter Approve-all-Grant ist im VOCR-Ledger aktiv. "
                "Review, Secret-Scan und Promote-Gates bleiben aktiv."
            )
        else:
            permission_note = (
                "\n\nOption fuer bewusst unbeaufsichtigtes Arbeiten: Starte mit "
                "`vocr start --dangerously-skip-permissions`, um Worker-Permissions fuer diese Session zu erlauben. "
                "Das gilt nur fuer die aktuelle Session, ist riskanter und aendert nicht die Review- oder Promote-Gates."
            )
        return NormalModeResponse(
            message=self._normal_mode_text(
                "Ich bin der Visionaer. Sag mir frei, was du bauen oder aendern willst. "
                "Ich frage gezielt nach, bis Ziel, Grenzen und Pruefung belastbar sind."
                + permission_note
            ),
            status=self.status(),
            phase=self.phase,
        )

    def receive(self, user_text: str) -> NormalModeResponse:
        text = user_text.strip()
        if not text:
            return self._response("Schreib mir kurz, was du erreichen willst. Ein Satz reicht fuer den Start.")

        if self.phase == NormalModePhase.confirmation:
            return self._handle_confirmation_gate(text)

        if self.phase == NormalModePhase.prepared:
            return self._response(
                "Die Arbeit ist vorbereitet. Fuer weitere Aenderungen starte bitte eine neue Beschreibung im Visionaer.",
                prepared_tasks=self.prepared_task_count,
                prepared_worktrees=self.prepared_worktree_count,
            )

        if self._looks_like_new_goal(text):
            self._reset_intake()
            self.history.append(text)
            self._merge_user_text(text)
            self.pending_proposal = self._build_proposal()
            self.phase = NormalModePhase.intake
            self.active_topic = "workspace"
            return self._response("Ich starte dafuer einen neuen Intake.\n\n" + self._proposal_message())

        if self.pending_proposal is not None:
            return self._handle_pending_proposal(text)

        self.history.append(text)
        self._merge_user_text(text)
        if self._should_offer_proposal(text):
            self.pending_proposal = self._build_proposal()
            self.phase = NormalModePhase.intake
            self.active_topic = "workspace"
            return self._response(self._proposal_message())

        missing = self._missing_topics()
        if missing:
            topic, label, question = self._next_missing_question(missing[0])
            self.active_topic = topic
            self.phase = NormalModePhase.intake
            return self._response(self._question_message(label, question, topic))

        self.phase = NormalModePhase.confirmation
        self.active_topic = None
        return self._response(self._confirmation_message())

    def status(self) -> NormalModeStatus:
        completed = 6 - len(self._missing_topics())
        next_step = (
            "Freigabe einholen"
            if completed == 6
            else self._label_for(self.active_topic or self._missing_topics()[0])
        )
        return NormalModeStatus(
            goal=self._normal_mode_text(self.intake.goal) or "Noch nicht geklaert",
            workspace=self._normal_mode_text(self.intake.workspace) or "Noch nicht geklaert",
            acceptance_criteria=self._normal_mode_text(self.intake.acceptance_criteria) or "Noch nicht geklaert",
            verification=self._normal_mode_text(self.intake.verification) or "Noch nicht geklaert",
            non_goals=self._normal_mode_text(self.intake.non_goals) or "Noch nicht geklaert",
            execution_bounds=self._normal_mode_text(self.intake.execution_bounds) or "Noch nicht geklaert",
            readiness=f"{completed}/6 geklaert",
            current_step=next_step,
            environment_hint=self._environment_hint(),
        )

    def _merge_user_text(self, text: str) -> None:
        sections = parse_request_sections(text)
        mapping = {
            "ziel": "goal",
            "arbeitsbereich": "workspace",
            "akzeptanz": "acceptance_criteria",
            "verifikation": "verification",
            "nicht_ziele": "non_goals",
            "ausfuehrung": "execution_bounds",
        }
        for section, field_name in mapping.items():
            value = sections.get(section, "").strip()
            if value:
                setattr(self.intake, field_name, self._normalize_field(field_name, value))

        if not sections:
            self._fill_next_missing(text)

    def _merge_sectioned_or_execution_text(self, text: str) -> None:
        sections = parse_request_sections(text)
        if sections:
            self._merge_user_text(text)
            return
        execution = self._normalize_execution_bounds(text)
        if execution:
            self.intake.execution_bounds = execution

    def _fill_next_missing(self, text: str) -> None:
        for field_name, _, _ in REQUIRED_TOPICS:
            if field_name == "goal":
                if not self._topic_is_complete("goal"):
                    self.intake.goal = text
                    return
                continue
            if not getattr(self.intake, field_name):
                setattr(self.intake, field_name, self._normalize_field(field_name, text))
                return

    def _apply_change_request(self, text: str) -> NormalModeResponse:
        if self._is_negative_confirmation(text):
            return self._response(
                "Alles klar. Sag mir bitte, was ich an der Zusammenfassung aendern soll. "
                "Du kannst auch schreiben: Ziel: ..., Arbeitsbereich: ..., Akzeptanz: ..., Verifikation: ..., "
                "Nicht-Ziele: ..., Ausfuehrung: ..."
            )
        before = self.intake.model_copy()
        self._apply_natural_corrections(text)
        self._merge_sectioned_or_execution_text(text)
        if self.intake == before:
            return self._response(
                "Ich habe daraus noch keine klare Aenderung erkannt. Bitte nenne das Feld mit: "
                "Ziel, Arbeitsbereich, Akzeptanz, Verifikation, Nicht-Ziele oder Ausfuehrung."
            )
        missing = self._missing_topics()
        if missing:
            self.phase = NormalModePhase.intake
            topic, label, question = self._next_missing_question(missing[0])
            self.active_topic = topic
            return self._response(self._question_message(label, question, topic))
        self.active_topic = None
        return self._response(self._confirmation_message())

    def _handle_confirmation_gate(self, text: str) -> NormalModeResponse:
        if not self._confirms_gate(text):
            return self._apply_change_request(text)
        before = self.intake.model_copy()
        self._apply_natural_corrections(text)
        self._merge_sectioned_or_execution_text(text)
        ack = self._correction_ack(text) if self.intake != before else ""
        result = self._prepare_confirmed_intake()
        if not ack:
            return result
        return NormalModeResponse(
            message=self._normal_mode_text(ack + result.message),
            status=result.status,
            phase=result.phase,
            prepared_tasks=result.prepared_tasks,
            prepared_worktrees=result.prepared_worktrees,
        )

    def _handle_pending_proposal(self, text: str) -> NormalModeResponse:
        proposal = self.pending_proposal
        if proposal is None:
            return self.receive(text)

        if self._rejects_proposal(text):
            self.pending_proposal = None
            self.active_topic = None
            return self._response("Alles klar. Dann schlage ich nichts vor. Sag mir bitte, wie du den Rahmen setzen willst.")

        if self._accepts_full_proposal(text):
            self._apply_proposal(proposal)
            self._merge_sectioned_or_execution_text(text)
            self.pending_proposal = None
            self.active_topic = None
            self.phase = NormalModePhase.confirmation
            return self._response(self._confirmation_message())

        topic = self.active_topic or self._missing_topics()[0]
        ack = self._apply_answer_to_topic(topic, text)
        return self._response(ack + self._next_intake_step_message())

    def _prepare_confirmed_intake(self) -> NormalModeResponse:
        self._activity("Ledger wird initialisiert.")
        self.ledger.init()
        self._activity("Repository-Graph wird aktualisiert.")
        self.graph_store.refresh(self.repo_root)
        self._activity("VisionSlice wird aus dem Intake erzeugt.")
        slice_item = create_vision(self._structured_request())
        self._activity(f"VisionSlice {slice_item.id} wird im Ledger gespeichert.")
        self.ledger.append(LedgerEventType.vision_created, slice_item)

        self._activity("Tasks werden aus dem VisionSlice organisiert.")
        tasks = organize_slice(slice_item, vocr_home=str(self.ledger.root))
        for task in tasks:
            self._activity(f"Task {task.id} wird gespeichert: {task.title}")
            self.ledger.append(LedgerEventType.task_created, task)
        worker_plan = self._worker_plan_message(tasks)

        prepare_worktree_requested = self._should_prepare_worktrees()
        prepared_worktrees = 0
        if prepare_worktree_requested:
            grant = PermissionGrant(
                mode=PermissionMode.approve_all,
                scope=slice_item.id,
                reason="User confirmed the normal Visionary flow.",
            )
            self.ledger.append(LedgerEventType.permission_granted, grant)
            self._activity("Worktree-Vorbereitung wurde angefordert.")
            prepared_worktrees = self._prepare_ready_worktrees(tasks)

        self.phase = NormalModePhase.prepared
        self.prepared_task_count = len(tasks)
        self.prepared_worktree_count = prepared_worktrees
        if prepared_worktrees:
            message = (
                "Bestaetigt. Ich habe die Arbeit in kleine, pruefbare Schritte zerlegt und die ersten "
                "getrennten Arbeitsbereiche vorbereitet. Es wurde nichts veroeffentlicht; die Pruefung bleibt der naechste Halt."
                f"\n\n{worker_plan}"
            )
        elif prepare_worktree_requested:
            message = (
                "Bestaetigt. Ich habe die Arbeit in kleine, pruefbare Schritte zerlegt. "
                "Ein getrennter Arbeitsbereich war gewuenscht, konnte hier aber nicht vorbereitet werden. "
                "Es wurde nichts veroeffentlicht; Review und Promote bleiben gesperrt."
                f"\n\n{worker_plan}"
            )
        else:
            message = (
                "Bestaetigt. Ich habe die Arbeit in kleine, pruefbare Schritte zerlegt. "
                "Es wurde noch kein Arbeitsbereich erzeugt, weil du nur Planung freigegeben hast."
                f"\n\n{worker_plan}"
            )
        return self._response(message, prepared_tasks=len(tasks), prepared_worktrees=prepared_worktrees)

    def _worker_plan_message(self, tasks: list[VocrTask]) -> str:
        return WorkerParallelismAdvisor(self.repo_root).message(tasks)

    def _prepare_ready_worktrees(self, tasks: list[VocrTask]) -> int:
        prepared = 0
        manager = GitWorktreeManager(self.repo_root)
        guard = ScopeGuard()
        for task in tasks:
            if task.dependencies:
                self._activity(f"Task {task.id} wartet auf Abhaengigkeiten und wird noch nicht vorbereitet.")
                continue
            try:
                self._activity(f"Arbeitsbereich fuer Task {task.id} wird angelegt.")
                dispatched = dispatch_task(self.ledger, manager, task.id)
                permission = self.session_permission or self.ledger.active_permission(dispatched.slice_id)
                self._activity(f"Worker-Handoff fuer Task {task.id} wird geschrieben.")
                CodexMcpClient().write_manifest(dispatched, permission=permission)
                self._activity(f"Scope-Policy fuer Task {task.id} wird geschrieben.")
                guard.write_worker_policy(dispatched)
                guard.write_worker_agents_file(dispatched)
                prepared += 1
            except (GitWorktreeError, ValueError) as exc:
                self._activity(f"Worktree-Vorbereitung fuer Task {task.id} uebersprungen: {exc}")
                self.ledger.append(
                    LedgerEventType.message,
                    {
                        "channel": "normal-mode",
                        "summary": "Worktree preparation skipped.",
                        "error": str(exc),
                        "task_id": task.id,
                    },
                )
        return prepared

    def _missing_topics(self) -> list[str]:
        return [field_name for field_name, _, _ in REQUIRED_TOPICS if not self._topic_is_complete(field_name)]

    def _topic_is_complete(self, field_name: str) -> bool:
        value = getattr(self.intake, field_name).strip()
        if not value:
            return False
        if field_name == "goal":
            return len(value.split()) >= 5
        if field_name == "execution_bounds":
            return bool(self._normalize_execution_bounds(value))
        return len(value) >= 4

    def _next_missing_question(self, field_name: str) -> tuple[str, str, str]:
        for topic, label, question in REQUIRED_TOPICS:
            if topic == field_name:
                return topic, label, question
        return field_name, field_name, "Was fehlt hier konkret?"

    def _question_message(self, label: str, question: str, topic: str) -> str:
        suggestion = ""
        if topic == "execution_bounds":
            suggestion = (
                "\nIch schlage vor: zuerst nur planen. Danach kannst du mir sagen, "
                "ob ich einen getrennten Arbeitsbereich vorbereiten soll."
            )
        elif topic == "workspace":
            suggestion = "\nVorschlag: nenne konkrete Pfade oder schreibe 'nur Dokumentation', 'nur Tests' usw."
        elif topic == "non_goals":
            suggestion = "\nVorschlag: nenne Dateien, Features oder Verhalten, das tabu bleibt."
        return f"{label} fehlt noch.\n{question}{suggestion}"

    def _next_intake_step_message(self) -> str:
        missing = self._missing_topics()
        if not missing:
            self.pending_proposal = None
            self.active_topic = None
            self.phase = NormalModePhase.confirmation
            return self._confirmation_message()
        self.phase = NormalModePhase.intake
        self.active_topic = missing[0]
        if self.pending_proposal is not None:
            return self._proposal_question(missing[0])
        topic, label, question = self._next_missing_question(missing[0])
        return self._question_message(label, question, topic)

    def _proposal_question(self, field_name: str) -> str:
        proposal = self.pending_proposal
        if proposal is None:
            topic, label, question = self._next_missing_question(field_name)
            return self._question_message(label, question, topic)
        label = self._label_for(field_name)
        value = getattr(proposal.intake, field_name)
        if field_name == "workspace":
            lead = "Naechster Punkt: Arbeitsbereich."
        elif field_name == "acceptance_criteria":
            lead = "Naechster Punkt: Akzeptanz."
        elif field_name == "verification":
            lead = "Naechster Punkt: Verifikation."
        elif field_name == "non_goals":
            lead = "Naechster Punkt: Nicht-Ziele und Risiken."
        elif field_name == "execution_bounds":
            lead = "Naechster Punkt: Ausfuehrungsgrenzen."
        else:
            lead = f"Naechster Punkt: {label}."
        return f"{lead}\nIch schlage vor:\n{self._bullets(value)}\n\nPasst das?"

    def _apply_answer_to_topic(self, field_name: str, text: str) -> str:
        if self._accepts_proposal(text):
            self._apply_proposal_field(field_name)
            return ""
        before = self.intake.model_copy()
        if field_name == "workspace" and self.pending_proposal is not None and self._contains_natural_correction(text):
            self._apply_proposal_field(field_name)
        self._apply_natural_corrections(text)
        sections = parse_request_sections(text)
        if sections:
            self._merge_user_text(text)
        elif field_name == "execution_bounds":
            execution = self._normalize_execution_bounds(text)
            if execution:
                self.intake.execution_bounds = execution
            else:
                self.intake.execution_bounds = text.strip()
        elif field_name == "workspace":
            if self.intake == before:
                self.intake.workspace = text.strip()
        elif field_name == "acceptance_criteria":
            self.intake.acceptance_criteria = text.strip()
        elif field_name == "verification":
            self.intake.verification = text.strip()
        elif field_name == "non_goals":
            if self.intake == before:
                self.intake.non_goals = text.strip()
        else:
            self._merge_user_text(text)
        return self._correction_ack(text)

    def _apply_proposal_field(self, field_name: str) -> None:
        if self.pending_proposal is None:
            return
        setattr(self.intake, field_name, getattr(self.pending_proposal.intake, field_name))

    def _reset_intake(self) -> None:
        self.intake = ProjectIntake()
        self.pending_proposal = None
        self.active_topic = None
        self.phase = NormalModePhase.welcome
        self.prepared_task_count = 0
        self.prepared_worktree_count = 0

    def _looks_like_new_goal(self, text: str) -> bool:
        if not self.intake.goal or self.phase == NormalModePhase.prepared:
            return False
        lowered = text.lower().strip()
        if any(term in lowered for term in ["neues ziel", "anderes ziel", "neuer intake", "starte neu"]):
            return True
        if self.active_topic == "goal":
            return False
        return lowered.startswith(("ich will ", "ich moechte ", "ich mochte ", "baue ", "mach "))

    def _should_offer_proposal(self, text: str) -> bool:
        if self.pending_proposal is not None:
            return False
        if not self._topic_is_complete("goal"):
            return False
        sections = parse_request_sections(text)
        explicit_detail = any(
            sections.get(section)
            for section in ["arbeitsbereich", "akzeptanz", "verifikation", "nicht_ziele", "ausfuehrung"]
        )
        if explicit_detail:
            return False
        return not any(
            getattr(self.intake, field_name)
            for field_name in ["workspace", "acceptance_criteria", "verification", "non_goals", "execution_bounds"]
        )

    def _build_proposal(self) -> IntakeProposal:
        goal = self.intake.goal
        lowered = goal.lower()
        understood_goal = f"Du willst: {goal}"
        workspace = "betroffene App- und Testbereiche nach bestaetigtem Scope"
        acceptance = (
            "Der beschriebene Wunsch ist umgesetzt; Verhalten ist pruefbar; "
            "keine nicht bestaetigten Nebenbereiche werden veraendert"
        )
        non_goals = "keine Review-, Promote- oder Worker-Sandboxing-Aenderungen ohne eigene Freigabe"
        execution = "Erst planen; danach optional getrennten Arbeitsbereich vorbereiten; nie automatisch veroeffentlichen"

        if any(
            term in lowered
            for term in ["startshell", "start shell", "startseite", "startoberflaeche", "startmodus", "vocr start"]
        ):
            understood_goal = "Du willst einen einfacheren Einstieg fuer normale VOCR-Nutzer."
            workspace = "src/vocr/cli/app.py; neue Start-/Dialog-Komponente unter src/vocr/ui; tests; optional README/docs"
            acceptance = (
                "User kann vocr start ausfuehren; danach oeffnet sich ein normaler Visionaer-Dialog; "
                "User sieht keine technischen Rueckfrage-Codes; der bestehende Expert-CLI-Flow bleibt erhalten"
            )
            non_goals = "keine Aenderungen an Review, Promote oder Worker-Sandboxing; keine automatische Veroeffentlichung"
        elif any(term in lowered for term in ["clarification", "rueckfrage", "ruckfrage", "dialog", "ux", "visionaer"]):
            understood_goal = "Du willst den Rueckfrage- und Dialogfluss benutzerfreundlicher machen."
            workspace = "src/vocr/ui; src/vocr/cli; passende Tests; optional README/docs"
            acceptance = (
                "Der User kann natuerlichsprachlich bestaetigen oder korrigieren; "
                "der Visionaer schlaegt den naechsten sinnvollen Schritt vor; "
                "interne technische Aktionen werden nicht als primaere UI-Steuerung gezeigt"
            )
        elif any(term in lowered for term in ["readme", "doku", "dokumentation", "installation", "testanleitung"]):
            understood_goal = "Du willst die VOCR-Dokumentation fuer Installation, Tests oder Nutzung schaerfen."
            workspace = "README.md und docs"
            acceptance = "Die Anleitung beschreibt Setup und Testablauf nachvollziehbar; keine Secrets werden dokumentiert"
            non_goals = "keine Code-Aenderungen ohne eigene Freigabe"
            execution = "Zuerst planen; Dokumentationsaenderungen erst nach Bestaetigung vorbereiten"
        elif any(term in lowered for term in ["graph", "graphify", "token", "context"]):
            understood_goal = "Du willst VOCRs Kontextauswahl tokenaermer und zielgenauer machen."
            workspace = "src/vocr/graph, src/vocr/orchestration und passende Tests"
            acceptance = "Context-Auswahl wird tokenaermer; Ranking bleibt deterministisch; Tests decken das Verhalten ab"
        elif any(term in lowered for term in ["review", "promote", "scope", "secret"]):
            understood_goal = "Du willst VOCRs Sicherheits- oder Review-Grenzen verbessern."
            workspace = "src/vocr/orchestration, src/vocr/guardrails, src/vocr/cli und passende Tests"
            acceptance = "Gate-Regeln bleiben hart; riskante Aenderungen werden blockiert; Tests decken den Pfad ab"

        return IntakeProposal(
            understood_goal=understood_goal,
            intake=ProjectIntake(
                goal=goal,
                workspace=workspace,
                acceptance_criteria=acceptance,
                verification="python -m compileall src tests; python -m unittest discover -s tests",
                non_goals=non_goals,
                execution_bounds=execution,
            ),
        )

    def _proposal_message(self) -> str:
        proposal = self.pending_proposal
        if proposal is None:
            return "Ich habe noch keinen belastbaren Vorschlag. Sag mir bitte den gewuenschten Arbeitsbereich."
        intake = proposal.intake
        return (
            f"Ich verstehe: {proposal.understood_goal}\n\n"
            "Ich schlage diesen Rahmen vor:\n\n"
            "Vermutlich passende Bereiche:\n"
            f"{self._bullets(intake.workspace)}\n\n"
            "Ich schlage als Akzeptanz vor:\n"
            f"{self._bullets(intake.acceptance_criteria)}\n\n"
            "Verifikation:\n"
            f"{self._bullets(intake.verification)}\n\n"
            "Nicht-Ziele und Risiken:\n"
            f"{self._bullets(intake.non_goals)}\n\n"
            "Ausfuehrungsgrenzen:\n"
            f"{self._bullets(intake.execution_bounds)}\n\n"
            "Du kannst den ganzen Rahmen mit 'alles passt' uebernehmen oder Punkt fuer Punkt korrigieren.\n\n"
            + self._proposal_question(self.active_topic or "workspace")
        )

    def _apply_proposal(self, proposal: IntakeProposal) -> None:
        for field_name in ["workspace", "acceptance_criteria", "verification", "non_goals", "execution_bounds"]:
            if not getattr(self.intake, field_name):
                setattr(self.intake, field_name, getattr(proposal.intake, field_name))

    def _bullets(self, text: str) -> str:
        items = [item.strip(" .") for item in text.replace("\n", ";").split(";") if item.strip(" .")]
        return "\n".join(f"- {item}" for item in items)

    def _accepts_proposal(self, text: str) -> bool:
        lowered = text.lower()
        return lowered.strip(" .,!") in {"passt", "ja", "ok", "okay", "verwenden", "klingt gut", "so machen"}

    def _accepts_full_proposal(self, text: str) -> bool:
        lowered = text.lower()
        return any(term in lowered for term in ["alles passt", "ganzer rahmen passt", "kompletten rahmen", "alles so"])

    def _rejects_proposal(self, text: str) -> bool:
        lowered = text.lower().strip()
        return lowered in {"nein", "no", "anders", "nicht so", "stopp", "stop"} or lowered.startswith("nein,")

    def _contains_natural_correction(self, text: str) -> bool:
        lowered = text.lower()
        return any(
            term in lowered
            for term in [
                "aber",
                "ohne",
                "keine",
                "nicht",
                "statt",
                "nur",
                "ziel:",
                "arbeitsbereich:",
                "akzeptanz:",
                "verifikation:",
                "nicht-ziele:",
                "ausfuehrung:",
            ]
        )

    def _apply_natural_corrections(self, text: str) -> None:
        lowered = text.lower()
        if any(term in lowered for term in ["keine docs", "ohne docs", "keine doku", "ohne doku", "keine dokumentation"]):
            self._append_non_goal("keine Dokumentationsaenderungen")
            self._remove_workspace_terms(["README/docs", "README.md", "README/", "docs", "Dokumentation"])
        if any(
            term in lowered
            for term in ["nimm docs doch mit rein", "docs doch mit rein", "docs mit rein", "doku mit rein", "readme mit rein"]
        ):
            self._append_workspace("README/docs")
            self._remove_non_goal("keine Dokumentationsaenderungen")
        if "nur tests" in lowered:
            self.intake.workspace = "Tests"
            self._append_non_goal("keine Produktcode-Aenderungen")
        if any(term in lowered for term in ["keine cli", "ohne cli"]):
            self._append_non_goal("keine CLI-Aenderungen")
            self._remove_workspace_terms(["src/vocr/cli"])
        if any(term in lowered for term in ["nicht mergen", "nichts mergen", "nicht promoten", "nichts promoten"]):
            self._append_non_goal("kein automatischer Promote/Merge")
        execution = self._normalize_execution_bounds(text)
        if execution:
            self.intake.execution_bounds = execution

    def _correction_ack(self, text: str) -> str:
        lowered = text.lower()
        notes: list[str] = []
        if any(term in lowered for term in ["keine docs", "ohne docs", "keine doku", "ohne doku", "keine dokumentation"]):
            notes.append("Dokumentationsaenderungen sind ausgeschlossen.")
        if any(
            term in lowered
            for term in ["nimm docs doch mit rein", "docs doch mit rein", "docs mit rein", "doku mit rein", "readme mit rein"]
        ):
            notes.append("Arbeitsbereich erweitert um README/docs.")
        if "nur tests" in lowered:
            notes.append("Ich begrenze den Rahmen auf Tests.")
        if any(term in lowered for term in ["keine cli", "ohne cli"]):
            notes.append("CLI-Aenderungen sind ausgeschlossen.")
        if any(term in lowered for term in ["nicht mergen", "nichts mergen", "nicht promoten", "nichts promoten"]):
            notes.append("Automatischer Promote/Merge ist ausgeschlossen.")
        if self._normalize_execution_bounds(text):
            if self._should_prepare_worktrees():
                notes.append("Ich bereite hoechstens einen getrennten Arbeitsbereich vor und merge nicht automatisch.")
            else:
                notes.append("Ich bleibe zuerst bei Planung ohne Arbeitsbereich.")
        if not notes:
            return ""
        return "Okay. " + " ".join(notes) + "\n\n"

    def _append_non_goal(self, item: str) -> None:
        existing = self.intake.non_goals.strip()
        if item.lower() in existing.lower():
            return
        self.intake.non_goals = f"{existing}; {item}" if existing else item

    def _append_workspace(self, item: str) -> None:
        existing = self.intake.workspace.strip()
        if item.lower() in existing.lower():
            return
        self.intake.workspace = f"{existing}; {item}" if existing else item

    def _remove_non_goal(self, item: str) -> None:
        parts = [part.strip() for part in self.intake.non_goals.split(";") if part.strip()]
        self.intake.non_goals = "; ".join(part for part in parts if part.lower() != item.lower())

    def _remove_workspace_terms(self, terms: list[str]) -> None:
        workspace = self.intake.workspace
        for term in terms:
            workspace = workspace.replace(term, "")
        self.intake.workspace = " ".join(workspace.replace(",,", ",").replace(" und  und ", " und ").split()).strip(" ,;")

    def _confirmation_message(self) -> str:
        return (
            "Ich habe jetzt genug Informationen.\n\n"
            "Zusammenfassung:\n\n"
            f"Ziel:\n{self._bullets(self.intake.goal)}\n\n"
            f"Arbeitsbereich:\n{self._bullets(self.intake.workspace)}\n\n"
            f"Akzeptanz:\n{self._bullets(self.intake.acceptance_criteria)}\n\n"
            f"Verifikation:\n{self._bullets(self.intake.verification)}\n\n"
            f"Nicht-Ziele:\n{self._bullets(self.intake.non_goals)}\n\n"
            f"Ausfuehrungsmodus:\n{self._bullets(self.intake.execution_bounds)}\n\n"
            "Ich werde intern:\n"
            f"{self._bullets(self._planned_internal_steps())}\n\n"
            "Sicherheitsgrenzen:\n"
            f"{self._bullets(self._safety_boundaries())}\n\n"
            "Soll ich so fortfahren? Du kannst z.B. schreiben: "
            "'Ja, Worktree vorbereiten, aber nichts mergen' oder 'Nein, aendere ...'."
        )

    def _status_summary(self) -> str:
        return "\n".join(
            [
                f"Ziel: {self.intake.goal}",
                f"Arbeitsbereich: {self.intake.workspace}",
                f"Akzeptanzkriterien: {self.intake.acceptance_criteria}",
                f"Verifikation: {self.intake.verification}",
                f"Nicht-Ziele: {self.intake.non_goals}",
                f"Ausfuehrungsgrenzen: {self.intake.execution_bounds}",
            ]
        )

    def _structured_request(self) -> str:
        return "\n".join(
            [
                f"Ziel: {self.intake.goal}",
                f"Arbeitsbereich: {self.intake.workspace}",
                f"Akzeptanz: {self.intake.acceptance_criteria}",
                f"Verifikation: {self.intake.verification}",
                f"Nicht-Ziele: {self.intake.non_goals}",
                f"Ausfuehrung: {self.intake.execution_bounds}; Review vor Promote.",
            ]
        )

    def _normalize_field(self, field_name: str, value: str) -> str:
        if field_name == "execution_bounds":
            normalized = self._normalize_execution_bounds(value)
            return normalized or value.strip()
        return value.strip()

    def _normalize_execution_bounds(self, value: str) -> str | None:
        lowered = value.lower().strip()
        choice = lowered.strip(" .,:;!?()[]{}")
        if choice in {"1", "a"} or any(
            term in lowered for term in ["nur planen", "plan-only", "erst planen", "planung"]
        ):
            return "Nur planen; keine Arbeitsbereiche ohne spaetere Freigabe."
        prepare_terms = ["bis zur pruefung", "bis zur prufung", "vorbereiten", "worktree", "arbeitsbereich", "go", "afk"]
        if choice in {"2", "b"} or any(term in lowered for term in prepare_terms):
            return "Bis zur Pruefung vorbereiten; keine Veroeffentlichung ohne akzeptierte Review."
        return None

    def _should_prepare_worktrees(self) -> bool:
        return self.intake.execution_bounds.lower().startswith("bis zur")

    def _is_confirmation(self, value: str) -> bool:
        return value.lower().strip() in {"bestaetigen", "bestatigen", "ja", "go", "freigeben", "start"}

    def _confirms_gate(self, value: str) -> bool:
        lowered = value.lower().strip()
        if self._is_confirmation(lowered):
            return True
        return lowered.startswith(
            (
                "ja,",
                "ja ",
                "passt,",
                "passt ",
                "bestaetige",
                "bestatige",
                "so fortfahren",
                "fahr fort",
                "mach weiter",
            )
        )

    def _planned_internal_steps(self) -> str:
        steps = [
            "einen VisionSlice anlegen",
            "kleine reviewbare Tasks erzeugen",
        ]
        if self._should_prepare_worktrees():
            steps.append("einen isolierten Arbeitsbereich vorbereiten")
            steps.append("den vorbereiteten Task dorthin dispatchen")
        else:
            steps.append("noch keinen Arbeitsbereich vorbereiten")
            steps.append("Dispatch pausieren")
        steps.append("Review-Gates aktiv lassen")
        steps.append("nichts mergen oder promoten")
        return "; ".join(steps)

    def _safety_boundaries(self) -> str:
        return "; ".join(
            [
                "kein automatischer Promote oder Merge",
                "Review-Gates bleiben aktiv",
                "Worktree-Isolation bleibt aktiv",
                "Scope-Grenzen bleiben aktiv",
                "Secret-Scanning bleibt aktiv",
                "Expert-CLI bleibt erhalten",
            ]
        )

    def _is_negative_confirmation(self, value: str) -> bool:
        return value.lower().strip() in {"nein", "no", "stop", "abbrechen", "aendern", "andern"}

    def _label_for(self, field_name: str) -> str:
        for topic, label, _ in REQUIRED_TOPICS:
            if topic == field_name:
                return label
        return "Klaerung"

    def _environment_hint(self) -> str:
        if self.phase == NormalModePhase.prepared:
            return "Vorbereitung abgeschlossen. Veroeffentlichung bleibt review-gesteuert."
        if self.phase == NormalModePhase.confirmation:
            return "Bereit fuer deine Freigabe. Noch nichts wurde erzeugt."
        return "Noch im Intake. VOCR erzeugt vor deiner Freigabe keine Tasks oder Arbeitsbereiche."

    def _response(
        self,
        message: str,
        *,
        prepared_tasks: int | None = None,
        prepared_worktrees: int | None = None,
    ) -> NormalModeResponse:
        return NormalModeResponse(
            message=self._normal_mode_text(message),
            status=self.status(),
            phase=self.phase,
            prepared_tasks=self.prepared_task_count if prepared_tasks is None else prepared_tasks,
            prepared_worktrees=self.prepared_worktree_count if prepared_worktrees is None else prepared_worktrees,
        )

    def _normal_mode_text(self, message: str) -> str:
        sanitized = CLARIFICATION_ID_PATTERN.sub("diese Rueckfrage", message)
        sanitized = EXPERT_ANSWER_COMMAND_PATTERN.sub("antworte einfach hier im Dialog", sanitized)
        sanitized = CLARIFICATION_TERM_PATTERN.sub("technische Rueckfrage-Codes", sanitized)
        return sanitized


def launch_console_mode(repo_root: str | Path = ".", session_permission: PermissionGrant | None = None) -> None:
    controller = NormalModeController(repo_root, session_permission=session_permission)
    opening = controller.opening_message()
    print(f"\nVisionaer: {opening.message}\n")
    while True:
        try:
            user_text = input("Du: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nVisionaer: Ich pausiere hier. Es wurde nichts ohne Freigabe gestartet.")
            return
        if user_text.lower() in {"exit", "quit", "ende"}:
            print("Visionaer: Alles klar, ich beende den Dialog.")
            return
        response = controller.receive(user_text)
        print(f"\nVisionaer: {response.message}\n")
        if response.phase == NormalModePhase.prepared:
            return


def open_expert_shell(repo_root: str | Path = ".") -> None:
    root = Path(repo_root).resolve()
    root_literal = str(root).replace("'", "''")
    command = (
        "Write-Host 'VOCR Expertmodus' -ForegroundColor Cyan; "
        "Write-Host 'Startpunkte: vocr --help, vocr doctor, vocr worker doctor, vocr beta --help'; "
        "Write-Host ''; "
        f"Set-Location -LiteralPath '{root_literal}'"
    )
    subprocess.Popen(["powershell", "-NoExit", "-Command", command], cwd=str(root))


def open_codex_login_shell(repo_root: str | Path = ".") -> None:
    root = Path(repo_root).resolve()
    root_literal = str(root).replace("'", "''")
    command = (
        "Write-Host 'VOCR Codex Login' -ForegroundColor Cyan; "
        "Write-Host 'Melde dich hier mit codex login an. Danach dieses Fenster schliessen und VOCR weiter nutzen.'; "
        "Write-Host ''; "
        f"Set-Location -LiteralPath '{root_literal}'; "
        "codex login"
    )
    subprocess.Popen(["powershell", "-NoExit", "-Command", command], cwd=str(root))


def codex_login_status(auth_path: Path | None = None) -> str:
    try:
        completed = subprocess.run(
            ["codex", "login", "status"],
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "ChatGPT/Codex: nicht verfuegbar"

    output = " ".join(part.strip() for part in [completed.stdout, completed.stderr] if part.strip())
    if completed.returncode != 0 or "logged in" not in output.lower():
        return "ChatGPT/Codex: nicht eingeloggt"

    identity = _codex_auth_identity(auth_path or (Path.home() / ".codex" / "auth.json"))
    if identity:
        return f"ChatGPT/Codex: eingeloggt via ChatGPT ({identity})"
    return "ChatGPT/Codex: eingeloggt via ChatGPT"


def _codex_auth_identity(auth_path: Path) -> str | None:
    try:
        data = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        return None
    for key in ("id_token", "access_token"):
        token = tokens.get(key)
        if not isinstance(token, str):
            continue
        payload = _decode_jwt_payload(token)
        profile = payload.get("https://api.openai.com/profile")
        if isinstance(profile, dict):
            identity = _format_identity(profile.get("name"), profile.get("email"))
            if identity:
                return identity
        identity = _format_identity(payload.get("name"), payload.get("email"))
        if identity:
            return identity
    return None


def _decode_jwt_payload(token: str) -> dict[str, object]:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        data = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _format_identity(name: object, email: object) -> str | None:
    clean_name = str(name).strip() if isinstance(name, str) and name.strip() else ""
    clean_email = str(email).strip() if isinstance(email, str) and email.strip() else ""
    if clean_name and clean_email:
        return f"{clean_name} / {clean_email}"
    return clean_name or clean_email or None


def model_auth_status(repo_root: str | Path = ".") -> str:
    values = read_env_file(Path(repo_root) / ".env")
    parts: list[str] = []
    if values.get("LMSTUDIO_API_KEY"):
        label = "LM Studio: Key gesetzt"
        if values.get("OPENAI_BASE_URL"):
            label += f", {values['OPENAI_BASE_URL']}"
        if values.get("OPENAI_MODEL"):
            label += f", Modell {values['OPENAI_MODEL']}"
        parts.append(label)
    elif values.get("OPENAI_API_KEY"):
        parts.append("Codex/OpenAI API-Key: gesetzt")
    else:
        parts.append("API-Key: nicht gesetzt")
    return " | ".join(parts)


def launch_normal_mode(repo_root: str | Path = ".", session_permission: PermissionGrant | None = None) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox, scrolledtext, simpledialog, ttk
    except Exception as exc:  # pragma: no cover - depends on local Python build
        raise NormalModeUiError(str(exc)) from exc

    controller_activity: dict[str, Callable[[str], None] | None] = {"handler": None}

    def controller_activity_sink(message: str) -> None:
        handler = controller_activity["handler"]
        if handler:
            handler(message)

    controller = NormalModeController(repo_root, session_permission=session_permission, on_activity=controller_activity_sink)
    root = tk.Tk()
    root.title("VOCR Visionaer")
    root.geometry("980x660")
    root.minsize(760, 520)

    try:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", padding=(12, 8))
        style.configure("TLabel", font=("Segoe UI", 10))
    except tk.TclError:
        pass

    root.columnconfigure(0, weight=3)
    root.columnconfigure(1, weight=1)
    root.rowconfigure(0, weight=1)
    root.rowconfigure(1, weight=0)

    notebook = ttk.Notebook(root)
    notebook.grid(row=0, column=0, sticky="nsew", padx=(14, 8), pady=(14, 8))

    dialog_tab = ttk.Frame(notebook)
    dialog_tab.columnconfigure(0, weight=1)
    dialog_tab.rowconfigure(0, weight=1)
    notebook.add(dialog_tab, text="Dialog")

    beta_tab = ttk.Frame(notebook, padding=(12, 12))
    beta_tab.columnconfigure(0, weight=1)
    beta_tab.rowconfigure(6, weight=1)
    notebook.add(beta_tab, text="Beta-Test")

    transcript = scrolledtext.ScrolledText(dialog_tab, wrap=tk.WORD, padx=12, pady=12, state=tk.DISABLED)
    transcript.grid(row=0, column=0, sticky="nsew")

    status_frame = ttk.Frame(root, padding=(10, 10))
    status_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 14), pady=(14, 8))
    status_frame.columnconfigure(0, weight=1)
    ttk.Label(status_frame, text="Projektstatus", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")
    activity_text = tk.StringVar(value="Bereit")
    auth_status_text = tk.StringVar(value="ChatGPT/Codex: nicht geprueft")
    ttk.Label(status_frame, textvariable=auth_status_text, wraplength=260).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    model_status_text = tk.StringVar(value=model_auth_status(controller.repo_root))
    ttk.Label(status_frame, textvariable=model_status_text, wraplength=260).grid(row=2, column=0, sticky="ew", pady=(4, 0))
    ttk.Label(status_frame, textvariable=activity_text, wraplength=260).grid(row=3, column=0, sticky="ew", pady=(6, 0))
    activity_progress = ttk.Progressbar(status_frame, mode="indeterminate")
    activity_progress.grid(row=4, column=0, sticky="ew", pady=(6, 8))
    status_text = scrolledtext.ScrolledText(status_frame, wrap=tk.WORD, width=34, height=13, padx=8, pady=8, state=tk.DISABLED)
    status_text.grid(row=5, column=0, sticky="nsew", pady=(0, 8))
    ttk.Label(status_frame, text="Aktivitaet", font=("Segoe UI", 10, "bold")).grid(row=6, column=0, sticky="w")
    activity_log = scrolledtext.ScrolledText(status_frame, wrap=tk.WORD, width=34, height=7, padx=8, pady=8, state=tk.DISABLED)
    activity_log.grid(row=7, column=0, sticky="nsew", pady=(6, 0))
    status_frame.rowconfigure(5, weight=2)
    status_frame.rowconfigure(7, weight=1)

    input_frame = ttk.Frame(root, padding=(14, 8, 14, 14))
    input_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
    input_frame.columnconfigure(0, weight=1)
    user_input = tk.Text(input_frame, height=4, wrap=tk.WORD, padx=10, pady=8)
    user_input.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    send_button = ttk.Button(input_frame, text="Senden")
    send_button.grid(row=0, column=1, sticky="ns")

    beta_tier = tk.StringVar(value="core")
    beta_only = tk.StringVar(value="")
    beta_allow_cloud = tk.BooleanVar(value=False)
    beta_json_only = tk.BooleanVar(value=False)
    beta_debug = tk.BooleanVar(value=False)
    beta_report_dir = tk.StringVar(value="beta_reports")
    beta_tag = tk.StringVar(value="")
    beta_max_cloud_tasks = tk.IntVar(value=3)

    ttk.Label(beta_tab, text="VOCR Beta-Pruefstand", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(
        beta_tab,
        text=(
            "Normaler sinnvollster Lauf: empfohlener Standardtest. "
            "Er nutzt Tier core, ist netzfrei, kostet kein Kontingent und prueft die zentralen VOCR-Sicherheits- und Workflow-Gates."
        ),
        wraplength=620,
    ).grid(row=1, column=0, sticky="ew", pady=(6, 12))

    beta_recommended = ttk.Frame(beta_tab, padding=(10, 10))
    beta_recommended.grid(row=2, column=0, sticky="ew", pady=(0, 10))
    beta_recommended.columnconfigure(0, weight=1)
    ttk.Label(beta_recommended, text="Empfohlen", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(
        beta_recommended,
        text=(
            "Fuehre diesen Test nach Installation, Updates oder eigenen Aenderungen aus. "
            "Nur wenn er rot ist oder du gezielt etwas pruefen willst, nutze die erweiterten Optionen darunter."
        ),
        wraplength=620,
    ).grid(row=1, column=0, sticky="ew", pady=(4, 8))
    beta_recommended_button = ttk.Button(beta_recommended, text="Empfohlenen Standardtest starten")
    beta_recommended_button.grid(row=2, column=0, sticky="w")

    beta_controls = ttk.Frame(beta_tab)
    beta_controls.grid(row=3, column=0, sticky="ew")
    beta_controls.columnconfigure(1, weight=1)
    ttk.Label(beta_controls, text="Tier").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
    ttk.Combobox(beta_controls, textvariable=beta_tier, values=("core", "local", "cloud", "all"), state="readonly", width=12).grid(row=0, column=1, sticky="w", pady=4)
    ttk.Label(beta_controls, text="Szenarien").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
    ttk.Entry(beta_controls, textvariable=beta_only).grid(row=1, column=1, sticky="ew", pady=4)
    ttk.Label(beta_controls, text="z.B. S03,S07; leer = Tier-Auswahl").grid(row=1, column=2, sticky="w", padx=(8, 0), pady=4)
    ttk.Label(beta_controls, text="Report-Ordner").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
    ttk.Entry(beta_controls, textvariable=beta_report_dir).grid(row=2, column=1, sticky="ew", pady=4)
    ttk.Label(beta_controls, text="Tag").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=4)
    ttk.Entry(beta_controls, textvariable=beta_tag).grid(row=3, column=1, sticky="ew", pady=4)
    ttk.Label(beta_controls, text="Max Cloud Tasks").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=4)
    ttk.Spinbox(beta_controls, from_=1, to=20, textvariable=beta_max_cloud_tasks, width=6).grid(row=4, column=1, sticky="w", pady=4)

    beta_checks = ttk.Frame(beta_tab)
    beta_checks.grid(row=4, column=0, sticky="ew", pady=(8, 0))
    ttk.Checkbutton(beta_checks, text="Cloud-Szenarien erlauben (kann Kontingent kosten)", variable=beta_allow_cloud).grid(row=0, column=0, sticky="w")
    ttk.Checkbutton(beta_checks, text="Nur JSON-Report schreiben", variable=beta_json_only).grid(row=1, column=0, sticky="w")
    ttk.Checkbutton(beta_checks, text="Debug-Details anzeigen", variable=beta_debug).grid(row=2, column=0, sticky="w")

    beta_buttons = ttk.Frame(beta_tab)
    beta_buttons.grid(row=5, column=0, sticky="ew", pady=(10, 8))
    beta_start_button = ttk.Button(beta_buttons, text="Erweiterten Beta-Test starten")
    beta_start_button.grid(row=0, column=0, sticky="w")
    beta_list_button = ttk.Button(beta_buttons, text="Szenarien anzeigen")
    beta_list_button.grid(row=0, column=1, sticky="w", padx=(8, 0))

    beta_result = scrolledtext.ScrolledText(beta_tab, wrap=tk.WORD, height=14, padx=8, pady=8, state=tk.DISABLED)
    beta_result.grid(row=6, column=0, sticky="nsew", pady=(8, 0))

    def append(sender: str, message: str) -> None:
        transcript.configure(state=tk.NORMAL)
        transcript.insert(tk.END, f"{sender}: {message}\n\n")
        transcript.see(tk.END)
        transcript.configure(state=tk.DISABLED)

    def log_activity(message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        activity_log.configure(state=tk.NORMAL)
        activity_log.insert(tk.END, f"[{stamp}] {message}\n")
        activity_log.see(tk.END)
        activity_log.configure(state=tk.DISABLED)

    def set_activity(message: str, *, busy: bool = False) -> None:
        activity_text.set(message)
        if busy:
            activity_progress.start(12)
        else:
            activity_progress.stop()

    def refresh_model_status() -> None:
        status = model_auth_status(controller.repo_root)
        model_status_text.set(status)
        log_activity(status)

    def refresh_codex_status() -> None:
        auth_status_text.set("ChatGPT/Codex: pruefe Status...")

        def worker() -> None:
            status = codex_login_status()
            root.after(0, lambda: auth_status_text.set(status))
            root.after(0, lambda: log_activity(status))

        threading.Thread(target=worker, daemon=True).start()

    def start_codex_login() -> None:
        auth_status_text.set("ChatGPT/Codex: Login laeuft...")
        log_activity("ChatGPT/Codex Login wurde manuell aus Optionen gestartet.")
        open_codex_login_shell(controller.repo_root)

        def poll() -> None:
            for _ in range(40):
                status = codex_login_status()
                root.after(0, lambda status=status: auth_status_text.set(status))
                if status.startswith("ChatGPT/Codex: eingeloggt"):
                    root.after(0, lambda status=status: log_activity(status))
                    return
                threading.Event().wait(3)
            root.after(0, lambda: log_activity("ChatGPT/Codex Login-Status wurde nicht automatisch bestaetigt."))

        threading.Thread(target=poll, daemon=True).start()

    def controller_activity_handler(message: str) -> None:
        set_activity(message, busy=True)
        log_activity(message)
        root.update_idletasks()

    controller_activity["handler"] = controller_activity_handler

    def beta_append(message: str, *, replace: bool = False) -> None:
        beta_result.configure(state=tk.NORMAL)
        if replace:
            beta_result.delete("1.0", tk.END)
        beta_result.insert(tk.END, message.rstrip() + "\n")
        beta_result.see(tk.END)
        beta_result.configure(state=tk.DISABLED)

    def show_beta_scenarios() -> None:
        from vocr.beta.scenarios import SCENARIOS

        lines = ["Verfuegbare Szenarien:", ""]
        for scenario in SCENARIOS.values():
            hard = "hard" if scenario.hard else "soft"
            lines.append(f"{scenario.id} [{scenario.tier}, {hard}] {scenario.title}")
        beta_append("\n".join(lines), replace=True)
        notebook.select(beta_tab)

    def start_beta_run(*, recommended: bool = False) -> None:
        tier = "core" if recommended else beta_tier.get()
        only = [] if recommended else [item.strip().upper() for item in beta_only.get().split(",") if item.strip()]
        allow_cloud = False if recommended else beta_allow_cloud.get()
        json_only = False if recommended else beta_json_only.get()
        show_debug = beta_debug.get()
        report_dir = "beta_reports" if recommended else (beta_report_dir.get().strip() or "beta_reports")
        tag = "recommended-core" if recommended else (beta_tag.get().strip() or None)
        max_cloud_tasks = 3
        if not recommended:
            try:
                max_cloud_tasks = max(1, int(beta_max_cloud_tasks.get()))
            except Exception:
                max_cloud_tasks = 3
        if tier in {"cloud", "all"} and not allow_cloud:
            messagebox.showwarning(
                "Beta-Test",
                "Cloud-Szenarien sind nicht erlaubt. Aktiviere die Checkbox, wenn du Cloud-Pfade wirklich laufen lassen willst.",
            )
            return
        beta_start_button.configure(state=tk.DISABLED)
        beta_recommended_button.configure(state=tk.DISABLED)
        set_activity("Beta-Test startet", busy=True)
        log_activity("Beta-Test gestartet.")
        beta_append(
            "\n".join(
                [
                    "Empfohlener Standardtest laeuft..." if recommended else "Beta-Test laeuft...",
                    "Dieser Lauf ist der normale sinnvolle Check: Tier core, keine Cloud, alle Core-Szenarien.",
                    "Wenn er gruen ist, ist der lokale VOCR-Kernzustand in Ordnung." if recommended else "Erweiterte Optionen sind aktiv.",
                    "",
                    f"Tier: {tier}",
                    f"Szenarien: {','.join(only) if only else 'alle fuer Tier'}",
                    f"Cloud erlaubt: {'ja' if allow_cloud else 'nein'}",
                    "",
                ]
            ),
            replace=True,
        )
        notebook.select(beta_tab)

        def worker() -> None:
            try:
                from vocr.beta.scenarios import SCENARIOS
                from vocr.beta.runner import run_beta

                def progress(event: str, payload: object) -> None:
                    if event == "selected":
                        scenarios = list(payload)  # type: ignore[arg-type]
                        root.after(0, lambda: beta_append(f"{len(scenarios)} Szenarien ausgewaehlt."))
                        root.after(0, lambda: log_activity(f"Beta-Auswahl: {len(scenarios)} Szenarien."))
                    elif event == "start":
                        scenario = payload
                        label = f"{scenario.id} {scenario.title}"  # type: ignore[attr-defined]
                        root.after(0, lambda label=label: set_activity(f"Beta laeuft: {label}", busy=True))
                        root.after(0, lambda label=label: beta_append(f"Starte {label} ..."))
                        root.after(0, lambda label=label: log_activity(f"Starte Szenario {label}."))
                    elif event == "finish":
                        item = payload
                        label = f"{item.id} {item.title}: {item.status} ({item.duration_s}s)"  # type: ignore[attr-defined]
                        root.after(0, lambda label=label: beta_append(f"Fertig {label}"))
                        root.after(0, lambda label=label: log_activity(f"Szenario fertig: {label}."))
                    elif event == "report":
                        root.after(0, lambda: log_activity("Beta-Reports werden geschrieben."))

                run = run_beta(
                    SCENARIOS.values(),
                    tier=tier,
                    only=only or None,
                    report_dir=controller.repo_root / report_dir,
                    allow_cloud=allow_cloud,
                    max_cloud_tasks=max_cloud_tasks,
                    json_only=json_only,
                    tag=tag,
                    on_progress=progress,
                )
                lines = [
                    f"Verdikt: {run.status.upper()}",
                    f"Exit-Code: {run.exit_code}",
                    "",
                    "Einordnung:",
                    "- Gruen: Standardtest bestanden; fuer normale Nutzung reicht das.",
                    "- Rot: Report oeffnen und die rot markierten Szenarien gezielt nacharbeiten.",
                    "- Cloud/local-live brauchst du nur fuer bewusste Spezialpruefungen.",
                    "",
                    "Szenarien:",
                ]
                for item in run.results:
                    lines.append(f"- {item.id} {item.title}: {item.status}")
                    if show_debug:
                        for item_step in item.steps:
                            detail = f" ({item_step.details})" if item_step.details else ""
                            lines.append(f"  - {item_step.name}: {item_step.status}{detail}")
                        for note in item.notes:
                            lines.append(f"  - note: {note.strip()}")
                if run.report_json:
                    lines.extend(["", f"JSON-Report: {run.report_json}"])
                if run.report_markdown:
                    lines.append(f"Markdown-Report: {run.report_markdown}")
            except Exception as exc:  # noqa: BLE001 - UI should surface failures.
                lines = ["Beta-Test konnte nicht abgeschlossen werden:", str(exc)]
                root.after(0, lambda exc=exc: log_activity(f"Beta-Test fehlgeschlagen: {exc}"))
            root.after(0, lambda: beta_append("\n".join(lines), replace=True))
            root.after(0, lambda: set_activity("Beta-Test abgeschlossen", busy=False))
            root.after(0, lambda: log_activity("Beta-Test abgeschlossen."))
            root.after(0, lambda: beta_start_button.configure(state=tk.NORMAL))
            root.after(0, lambda: beta_recommended_button.configure(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()

    def save_codex_api_key() -> None:
        api_key = simpledialog.askstring("Codex API-Key", "API-Key fuer Codex/OpenAI eingeben:", show="*", parent=root)
        if not api_key:
            return
        update_env_file({"OPENAI_API_KEY": api_key.strip()}, controller.repo_root / ".env")
        refresh_model_status()
        append("System", "Codex/OpenAI API-Key gespeichert. Standard bleibt codex login; der Key ist optional fuer Expert-Setups.")
        log_activity("Codex/OpenAI API-Key gespeichert.")
        messagebox.showinfo("VOCR Optionen", "Codex/OpenAI API-Key gespeichert.")

    def save_lmstudio_api_key() -> None:
        api_key = simpledialog.askstring("LM Studio API-Key", "LM-Studio-Key eingeben:", show="*", parent=root)
        if not api_key:
            return
        base_url = simpledialog.askstring(
            "LM Studio Base URL",
            "OpenAI-kompatible Base URL:",
            initialvalue="http://localhost:1234/v1",
            parent=root,
        )
        if not base_url:
            return
        model = simpledialog.askstring("LM Studio Modell", "Optionaler Modellname:", parent=root)
        updates: dict[str, str | None] = {
            "OPENAI_BASE_URL": base_url.rstrip("/"),
            "OPENAI_API_KEY": api_key.strip(),
            "LMSTUDIO_API_KEY": api_key.strip(),
        }
        if model and model.strip():
            updates["OPENAI_MODEL"] = model.strip()
        update_env_file(updates, controller.repo_root / ".env")
        refresh_model_status()
        summary = model_auth_status(controller.repo_root)
        append("System", "LM-Studio-Key gespeichert. Lokale Modellfunktionen nutzen jetzt die konfigurierte Base URL.")
        log_activity(summary)
        messagebox.showinfo("VOCR Optionen", f"LM-Studio-Key gespeichert.\n\n{summary}")

    menu = tk.Menu(root)
    options_menu = tk.Menu(menu, tearoff=0)
    options_menu.add_command(label="ChatGPT/Codex Login oeffnen", command=start_codex_login)
    options_menu.add_command(label="ChatGPT/Codex Login-Status aktualisieren", command=refresh_codex_status)
    options_menu.add_command(label="API-/Modellstatus aktualisieren", command=refresh_model_status)
    options_menu.add_command(label="Codex/OpenAI API-Key setzen", command=save_codex_api_key)
    options_menu.add_command(label="LM Studio API-Key setzen", command=save_lmstudio_api_key)
    menu.add_cascade(label="Optionen", menu=options_menu)
    expert_menu = tk.Menu(menu, tearoff=0)
    expert_menu.add_command(label="Expertmodus oeffnen", command=lambda: open_expert_shell(controller.repo_root))
    expert_menu.add_command(
        label="Expert-Hilfe anzeigen",
        command=lambda: append(
            "System",
            "Expertmodus: Nutze vocr --help, vocr doctor, vocr worker doctor oder vocr beta --help in der Shell.",
        ),
    )
    menu.add_cascade(label="Expertmodus", menu=expert_menu)
    root.config(menu=menu)

    def render_status(status: NormalModeStatus) -> None:
        lines = [
            f"Ziel\n{status.goal}",
            f"Arbeitsbereich\n{status.workspace}",
            f"Akzeptanzkriterien\n{status.acceptance_criteria}",
            f"Verifikation\n{status.verification}",
            f"Nicht-Ziele\n{status.non_goals}",
            f"Ausfuehrungsgrenzen\n{status.execution_bounds}",
            f"Readiness\n{status.readiness}",
            f"Aktueller Schritt\n{status.current_step}",
            f"Hinweis\n{status.environment_hint}",
        ]
        status_text.configure(state=tk.NORMAL)
        status_text.delete("1.0", tk.END)
        status_text.insert(tk.END, "\n\n".join(lines))
        status_text.configure(state=tk.DISABLED)

    def send(_: object | None = None) -> str:
        text = user_input.get("1.0", tk.END).strip()
        if not text:
            return "break"
        user_input.delete("1.0", tk.END)
        append("Du", text)
        set_activity("Visionaer verarbeitet deine Eingabe", busy=True)
        log_activity("Visionaer verarbeitet Eingabe.")
        root.update_idletasks()
        try:
            response = controller.receive(text)
        except Exception as exc:  # pragma: no cover - UI safety net
            response = NormalModeResponse(
                message=controller._normal_mode_text(f"Ich konnte den Schritt nicht vorbereiten: {exc}"),
                status=controller.status(),
                phase=controller.phase,
            )
        append("Visionaer", response.message)
        render_status(response.status)
        set_activity(f"Bereit: {response.status.current_step}", busy=False)
        log_activity(f"Visionaer-Schritt abgeschlossen: {response.status.current_step}.")
        return "break"

    send_button.configure(command=send)
    user_input.bind("<Control-Return>", send)
    beta_recommended_button.configure(command=lambda: start_beta_run(recommended=True))
    beta_start_button.configure(command=start_beta_run)
    beta_list_button.configure(command=show_beta_scenarios)

    opening = controller.opening_message()
    append("Visionaer", opening.message)
    render_status(opening.status)
    set_activity("Bereit: Ziel beschreiben oder Optionen oeffnen", busy=False)
    log_activity("Normalmode gestartet.")
    beta_append(
        "Bereit fuer einen Beta-Test.\n"
        "Normalfall: Empfohlenen Standardtest starten.\n"
        "Das ist Tier core, keine Cloud, alle Core-Szenarien, Report nach beta_reports.\n"
        "Erweiterte Optionen brauchst du nur fuer gezielte Szenarien oder bewusste Cloud-/Local-Pruefungen.",
        replace=True,
    )
    user_input.focus_set()

    try:
        root.mainloop()
    except tk.TclError as exc:  # pragma: no cover - depends on local display
        raise NormalModeUiError(str(exc)) from exc


__all__ = [
    "NORMAL_MODE_SURFACE",
    "NormalModeController",
    "NormalModeResponse",
    "NormalModeUiError",
    "launch_console_mode",
    "launch_normal_mode",
    "open_codex_login_shell",
    "open_expert_shell",
    "normal_mode_surface_decision",
]
