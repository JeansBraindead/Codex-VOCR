from __future__ import annotations

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from vocr.install.bootstrap import BootstrapError, Bootstrapper, find_repo_root, venv_python


def make_repo(root: Path) -> None:
    (root / "src" / "vocr").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname = 'vocr'\n", encoding="utf-8")
    (root / "src" / "vocr" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests" / "test_smoke.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")
    (root / ".env.example").write_text("VOCR_HOME=.vocr\nOPENAI_API_KEY=\n", encoding="utf-8")


class FakeRunner:
    def __init__(self, *, importable: bool = False) -> None:
        self.importable = importable
        self.commands: list[list[str]] = []

    def __call__(self, command, *, cwd, text, capture_output, check, env=None):
        del text, capture_output, check, env
        args = [str(item) for item in command]
        self.commands.append(args)
        repo_root = Path(cwd)
        if args[1:4] == ["-m", "venv", ".venv"]:
            python_path = venv_python(repo_root)
            python_path.parent.mkdir(parents=True, exist_ok=True)
            python_path.write_text("", encoding="utf-8")
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[-2:] == ["-c", "import vocr"]:
            return subprocess.CompletedProcess(args, 0 if self.importable else 1, "", "not importable")
        if args[-4:] == ["pip", "install", "-e", "."] or "pip" in args:
            self.importable = True
            return subprocess.CompletedProcess(args, 0, "installed", "")
        return subprocess.CompletedProcess(args, 0, "", "")


class BootstrapTests(unittest.TestCase):
    def test_find_repo_root_from_subdirectory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_repo(root)
            subdir = root / "src" / "vocr"

            self.assertEqual(find_repo_root(subdir), root)

    def test_missing_pyproject_gets_human_repo_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(BootstrapError) as raised:
                Bootstrapper(Path(tmp), runner=FakeRunner(), which=lambda _: "git").bootstrap()

        self.assertIn("Hier liegt kein VOCR-Repo", str(raised.exception))
        self.assertIn("git clone", str(raised.exception))

    def test_missing_git_gets_install_help(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_repo(root)

            with self.assertRaises(BootstrapError) as raised:
                Bootstrapper(root, runner=FakeRunner(), which=lambda _: None).bootstrap()

        self.assertIn("Git wurde nicht gefunden", str(raised.exception))

    def test_old_python_gets_clear_diagnosis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_repo(root)

            with self.assertRaises(BootstrapError) as raised:
                Bootstrapper(root, runner=FakeRunner(), which=lambda _: "git", python_version=(3, 10, 9)).bootstrap()

        self.assertIn("Python ist zu alt", str(raised.exception))

    def test_bootstrap_creates_venv_install_setup_graph_env_and_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_repo(root)
            runner = FakeRunner(importable=False)

            result = Bootstrapper(root, runner=runner, which=lambda _: "git").bootstrap(
                run_tests=True,
                write_scripts=True,
            )

            command_text = [" ".join(command) for command in runner.commands]
            self.assertTrue(any("-m venv .venv" in command for command in command_text))
            self.assertTrue(any("-m pip install -e ." in command for command in command_text))
            self.assertTrue(any("-m compileall src tests" in command for command in command_text))
            self.assertTrue(any("-m unittest discover -s tests" in command for command in command_text))
            self.assertTrue((result.repo_root / ".env").exists())
            self.assertTrue((result.repo_root / ".vocr" / "ledger.jsonl").exists())
            self.assertTrue((result.repo_root / ".vocr" / "graph.json").exists())
            self.assertTrue((result.repo_root / "install-vocr.ps1").exists())
            self.assertTrue((result.repo_root / "start-vocr.ps1").exists())
            self.assertTrue((result.repo_root / "Start-VOCR.bat").exists())
            self.assertIn("Pause-OnInteractiveError", (result.repo_root / "start-vocr.ps1").read_text(encoding="utf-8"))
            self.assertIn("pause", (result.repo_root / "Start-VOCR.bat").read_text(encoding="utf-8").lower())

    def test_bootstrap_does_not_overwrite_existing_windows_installer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_repo(root)
            installer = root / "install-vocr.ps1"
            installer.write_text("# existing winget-aware installer\n", encoding="utf-8")

            Bootstrapper(root, runner=FakeRunner(importable=True), which=lambda _: "git").bootstrap(
                write_scripts=True,
            )

            self.assertEqual(installer.read_text(encoding="utf-8"), "# existing winget-aware installer\n")
            self.assertTrue((root / "start-vocr.ps1").exists())
            self.assertTrue((root / "Start-VOCR.bat").exists())

    def test_bootstrap_does_not_overwrite_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_repo(root)
            (root / ".env").write_text("KEEP_ME=yes\n", encoding="utf-8")
            python_path = venv_python(root)
            python_path.parent.mkdir(parents=True, exist_ok=True)
            python_path.write_text("", encoding="utf-8")

            Bootstrapper(root, runner=FakeRunner(importable=True), which=lambda _: "git").bootstrap()

            self.assertEqual((root / ".env").read_text(encoding="utf-8"), "KEEP_ME=yes\n")

    def test_bootstrap_is_idempotent_with_existing_venv_install_setup_and_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_repo(root)
            python_path = venv_python(root)
            python_path.parent.mkdir(parents=True, exist_ok=True)
            python_path.write_text("", encoding="utf-8")
            first = Bootstrapper(root, runner=FakeRunner(importable=True), which=lambda _: "git").bootstrap()
            graph_path = first.repo_root / ".vocr" / "graph.json"
            future = time.time() + 1000
            os.utime(graph_path, (future, future))
            runner = FakeRunner(importable=True)

            Bootstrapper(root, runner=runner, which=lambda _: "git").bootstrap()

        command_text = [" ".join(command) for command in runner.commands]
        self.assertFalse(any("-m venv .venv" in command for command in command_text))
        self.assertFalse(any("-m pip install -e ." in command for command in command_text))


if __name__ == "__main__":
    unittest.main()
