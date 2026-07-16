from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from vocr.beta.runner import ScenarioResult


def write_reports(
    results: list[ScenarioResult],
    report_dir: Path,
    *,
    json_only: bool = False,
    tag: str | None = None,
) -> tuple[Path, Path | None]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = f"beta_report_{tag}_{stamp}" if tag else f"beta_report_{stamp}"
    json_path = report_dir / f"{prefix}.json"
    md_path = None if json_only else report_dir / f"{prefix}.md"
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict(results),
        "results": [item.model_dump(mode="json") for item in results],
        "totals": totals(results),
    }
    previous = previous_json(report_dir, current=json_path, tag=tag)
    if previous:
        payload["trend"] = trend(previous, payload)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if md_path:
        md_path.write_text(render_markdown(payload), encoding="utf-8")
    return json_path, md_path


def verdict(results: list[ScenarioResult]) -> str:
    if any(item.hard and item.status == "failed" for item in results):
        return "DURCHGEFALLEN"
    return "BESTANDEN"


def totals(results: list[ScenarioResult]) -> dict[str, int]:
    return {
        "passed": sum(1 for item in results if item.status == "passed"),
        "failed": sum(1 for item in results if item.status == "failed"),
        "skipped": sum(1 for item in results if item.status == "skipped"),
        "hard_failed": sum(1 for item in results if item.hard and item.status == "failed"),
    }


def previous_json(report_dir: Path, *, current: Path, tag: str | None) -> dict | None:
    pattern = f"beta_report_{tag}_*.json" if tag else "beta_report_*.json"
    candidates = [path for path in sorted(report_dir.glob(pattern)) if path != current]
    if not candidates:
        return None
    try:
        return json.loads(candidates[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def trend(previous: dict, current: dict) -> dict[str, str]:
    before = {item["id"]: item["status"] for item in previous.get("results", [])}
    after = {item["id"]: item["status"] for item in current.get("results", [])}
    return {
        scenario_id: f"{before.get(scenario_id, 'new')} -> {status}"
        for scenario_id, status in sorted(after.items())
        if before.get(scenario_id) != status
    }


def render_markdown(payload: dict) -> str:
    lines = [
        "# VOCR Beta Report",
        "",
        f"Verdikt: **{payload['verdict']}**",
        "",
        "| Szenario | Hart | Status | Dauer |",
        "|---|---:|---|---:|",
    ]
    for item in payload["results"]:
        lines.append(
            f"| {item['id']} {item['title']} | {'ja' if item['hard'] else 'nein'} | "
            f"{item['status']} | {item['duration_s']:.2f}s |"
        )
    metric_lines: list[str] = []
    for item in payload["results"]:
        metrics = item.get("metrics") or {}
        if not metrics:
            continue
        metric_text = ", ".join(f"{key}={value}" for key, value in sorted(metrics.items()))
        metric_lines.append(f"- {item['id']}: {metric_text}")
    if metric_lines:
        lines.extend(["", "## Metrics", *metric_lines])
    if payload.get("trend"):
        lines.extend(["", "## Trend"])
        for key, value in payload["trend"].items():
            lines.append(f"- {key}: {value}")
    return "\n".join(lines) + "\n"
