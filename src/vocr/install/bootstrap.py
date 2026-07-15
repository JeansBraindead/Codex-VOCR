from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from vocr.codex.config import write_mcp_config
from vocr.graph.graphify import GraphStore
from vocr.memory.ledger import MemoryLedger


REPO_URL = "https://github.com/JeansBraindead/Codex-VOCR.git"
MIN_PYTHON = (3, 11)
Runner = Callable[..., subprocess.CompletedProcess[str]]


class BootstrapError(RuntimeError):
    """Human-readable bootstrap failure."""


@dataclass(frozen=True)
class BootstrapStep:
    name: str
    status: str
    message: str


@dataclass
class BootstrapResult:
    repo_root: Path
    steps: list[BootstrapStep] = field(default_factory=list)

    def add(self, name: str, status: str, message: str) -> None:
        self.steps.append(BootstrapStep(name=name, status=status, message=message))


def is_vocr_repo(path: Path) -> bool:
    return (path / "pyproject.toml").exists() and (path / "src" / "vocr").is_dir()


def find_repo_root(start: Path) -> Path | None:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if is_vocr_repo(candidate):
            return candidate
    return None


def venv_python(repo_root: Path) -> Path:
    if os.name == "nt":
        return repo_root / ".venv" / "Scripts" / "python.exe"
    return repo_root / ".venv" / "bin" / "python"


def graph_is_stale(repo_root: Path, graph_path: Path) -> bool:
    if not graph_path.exists():
        return True
    graph_mtime = graph_path.stat().st_mtime
    candidates = [repo_root / "pyproject.toml", repo_root / "README.md", repo_root / "src", repo_root / "tests"]
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_mtime > graph_mtime:
            return True
        if candidate.is_dir():
            for child in candidate.rglob("*"):
                if child.is_file() and child.stat().st_mtime > graph_mtime:
                    return True
    return False


class Bootstrapper:
    def __init__(
        self,
        start_path: Path | str = ".",
        *,
        runner: Runner | None = None,
        which: Callable[[str], str | None] = shutil.which,
        python_version: tuple[int, int, int] | tuple[int, int] = sys.version_info[:3],
    ) -> None:
        self.start_path = Path(start_path).resolve()
        self.runner = runner or subprocess.run
        self.which = which
        self.python_version = python_version

    def bootstrap(
        self,
        *,
        run_tests: bool = False,
        write_scripts: bool = False,
        allow_install: bool = True,
    ) -> BootstrapResult:
        repo_root = self._require_repo_root()
        result = BootstrapResult(repo_root=repo_root)
        self._check_python(result)
        self._check_git(result)
        self._ensure_env_file(result, repo_root)
        python_path = self._ensure_venv(result, repo_root)
        if allow_install:
            self._ensure_editable_install(result, repo_root, python_path)
        else:
            result.add("install", "skipped", "Editable install was not requested.")
        self._ensure_setup(result, repo_root)
        self._ensure_graph(result, repo_root)
        if write_scripts:
            self.write_windows_scripts(repo_root)
            result.add("scripts", "changed", "Windows start scripts written.")
        else:
            result.add("scripts", "skipped", "Use --write-scripts to generate Windows start scripts.")
        if run_tests:
            self._run_smoke_tests(result, repo_root, python_path)
        else:
            result.add("tests", "skipped", "Smoke tests skipped. Use --tests to run them.")
        return result

    def prepare_start(self) -> BootstrapResult:
        repo_root = self._require_repo_root()
        result = BootstrapResult(repo_root=repo_root)
        self._check_python(result)
        self._check_git(result)
        self._ensure_env_file(result, repo_root)
        self._ensure_setup(result, repo_root)
        self._ensure_graph(result, repo_root)
        return result

    def _require_repo_root(self) -> Path:
        repo_root = find_repo_root(self.start_path)
        if repo_root is None:
            raise BootstrapError(
                "Hier liegt kein VOCR-Repo. Wechsle in den geklonten Codex-VOCR-Ordner "
                "oder klone zuerst das Repo:\n"
                f"git clone {REPO_URL} Codex-VOCR\n"
                "cd Codex-VOCR"
            )
        return repo_root

    def _check_python(self, result: BootstrapResult) -> None:
        if tuple(self.python_version[:2]) < MIN_PYTHON:
            raise BootstrapError(
                "Python ist zu alt. VOCR braucht Python 3.11 oder neuer. "
                "Installiere Python 3.11+ und starte den Bootstrap erneut."
            )
        result.add("python", "ok", f"Python {self.python_version[0]}.{self.python_version[1]} detected.")

    def _check_git(self, result: BootstrapResult) -> None:
        if self.which("git") is None:
            raise BootstrapError(
                "Git wurde nicht gefunden. Installiere Git fuer Windows und starte danach erneut: "
                "https://git-scm.com/download/win"
            )
        result.add("git", "ok", "Git is available.")

    def _ensure_env_file(self, result: BootstrapResult, repo_root: Path) -> None:
        env_path = repo_root / ".env"
        example = repo_root / ".env.example"
        if env_path.exists():
            result.add("env", "ok", ".env exists and was not overwritten.")
            return
        if example.exists():
            env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
            result.add("env", "changed", ".env created from .env.example without adding secrets.")
            return
        result.add("env", "warn", ".env.example is missing; .env was not created.")

    def _ensure_venv(self, result: BootstrapResult, repo_root: Path) -> Path:
        python_path = venv_python(repo_root)
        if python_path.exists():
            result.add("venv", "ok", ".venv exists and will be reused.")
            return python_path
        completed = self._run([sys.executable, "-m", "venv", ".venv"], cwd=repo_root)
        if completed.returncode != 0:
            raise BootstrapError(
                "Die virtuelle Umgebung konnte nicht angelegt werden. "
                f"Details: {(completed.stderr or completed.stdout).strip()}"
            )
        result.add("venv", "changed", ".venv created.")
        return python_path

    def _ensure_editable_install(self, result: BootstrapResult, repo_root: Path, python_path: Path) -> None:
        if not (repo_root / "pyproject.toml").exists():
            raise BootstrapError(
                "Vor pip install -e . wurde kein pyproject.toml gefunden. "
                "VOCR installiert nicht stillschweigend im falschen Ordner."
            )
        probe = self._run([str(python_path), "-c", "import vocr"], cwd=repo_root)
        if probe.returncode == 0:
            result.add("install", "ok", "VOCR is already importable in .venv.")
            return
        completed = self._run([str(python_path), "-m", "pip", "install", "-e", "."], cwd=repo_root)
        if completed.returncode != 0:
            raise BootstrapError(
                "VOCR konnte nicht in .venv installiert werden. "
                f"Details: {(completed.stderr or completed.stdout).strip()}"
            )
        result.add("install", "changed", "Editable install completed with pip install -e .")

    def _ensure_setup(self, result: BootstrapResult, repo_root: Path) -> None:
        vocr_home = repo_root / ".vocr"
        ledger = MemoryLedger(vocr_home)
        existed = ledger.path.exists()
        ledger.init()
        write_mcp_config(vocr_home / "codex-mcp.json")
        result.add("setup", "ok" if existed else "changed", ".vocr workspace is initialized.")

    def _ensure_graph(self, result: BootstrapResult, repo_root: Path) -> None:
        store = GraphStore(repo_root / ".vocr")
        if graph_is_stale(repo_root, store.path):
            graph = store.refresh(repo_root)
            result.add("graphify", "changed", f"Graphify refreshed with {len(graph.nodes)} files.")
            return
        result.add("graphify", "ok", "Graphify index is current.")

    def _run_smoke_tests(self, result: BootstrapResult, repo_root: Path, python_path: Path) -> None:
        commands: list[list[str]] = [
            [str(python_path), "-m", "compileall", "src", "tests"],
            [str(python_path), "-m", "unittest", "discover", "-s", "tests"],
        ]
        env = dict(os.environ)
        env["PYTHONPATH"] = "src"
        for command in commands:
            completed = self._run(command, cwd=repo_root, env=env)
            if completed.returncode != 0:
                raise BootstrapError(
                    "Smoke-Test fehlgeschlagen: "
                    f"{' '.join(command)}\n{(completed.stderr or completed.stdout).strip()}"
                )
        result.add("tests", "ok", "compileall and unittest smoke tests passed.")

    def write_windows_scripts(self, repo_root: Path) -> None:
        install_script = repo_root / "install-vocr.ps1"
        start_script = repo_root / "start-vocr.ps1"
        bat_script = repo_root / "Start-VOCR.bat"
        bootstrap_line = "python -m vocr.main bootstrap --no-start --write-scripts"
        start_line = "python -m vocr.main start"
        ps_header = (
            "$ErrorActionPreference = 'Stop'\n"
            f"Set-Location -LiteralPath '{repo_root}'\n"
            "if (-not (Test-Path .venv)) { python -m venv .venv }\n"
            ". .\\.venv\\Scripts\\Activate.ps1\n"
        )
        install_script.write_text(ps_header + "python -m pip install -e .\n" + bootstrap_line + "\n", encoding="utf-8")
        start_script.write_text(ps_header + "python -m pip install -e .\n" + bootstrap_line + "\n" + start_line + "\n", encoding="utf-8")
        bat_script.write_text(
            "@echo off\r\n"
            f"cd /d \"{repo_root}\"\r\n"
            "if not exist .venv\\Scripts\\python.exe python -m venv .venv\r\n"
            ".venv\\Scripts\\python.exe -m pip install -e .\r\n"
            ".venv\\Scripts\\python.exe -m vocr.main bootstrap --no-start\r\n"
            ".venv\\Scripts\\python.exe -m vocr.main start\r\n",
            encoding="utf-8",
        )

    def _run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return self.runner(
            list(command),
            cwd=str(cwd),
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
