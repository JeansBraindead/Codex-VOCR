from __future__ import annotations

import json

from vocr.models import CodexRunResult, VocrTask
from vocr.telemetry import estimate_tokens


class StubWorker:
    """Deterministic LLM-free worker for gate and telemetry evaluation."""

    def run(self, task: VocrTask, prompt: str) -> CodexRunResult:
        prompt_tokens = estimate_tokens(prompt)
        completion_tokens = 7
        return CodexRunResult(
            task_id=task.id,
            command=["vocr-stub-worker"],
            exit_code=0,
            stdout=json.dumps(
                {
                    "worker": "vocr-stub-worker",
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                    },
                }
            ),
        )
