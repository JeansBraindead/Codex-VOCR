from __future__ import annotations

import json
from pathlib import Path
from shutil import which


def codex_available() -> bool:
    return which("codex") is not None


def codex_worker_command() -> str:
    return "codex exec -"


def codex_mcp_server_command() -> list[str]:
    return ["codex", "mcp-server"]


def build_mcp_config() -> dict:
    return {
        "mcpServers": {
            "codex": {
                "command": "codex",
                "args": ["mcp-server"],
                "transport": "stdio",
            }
        }
    }


def write_mcp_config(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build_mcp_config(), indent=2), encoding="utf-8")
    return target
