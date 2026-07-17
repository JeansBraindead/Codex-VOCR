from __future__ import annotations

import json
import math
import os
import subprocess
import re
from pathlib import Path
from shutil import which

from vocr.models import SecretFinding, SecretScanResult


KEYWORD_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|credential|private[_-]?key)\b\s*[:=]\s*['\"]?[^'\"\s]{8,}"
)
KNOWN_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "OpenAI-style API key"),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"), "GitHub-style token"),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "Private key material"),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
]
HIGH_ENTROPY_RE = re.compile(r"['\"]?([A-Za-z0-9+/=_-]{32,})['\"]?")


def scan_diff_for_secrets(diff_text: str, *, repo_root: Path | str | None = None) -> SecretScanResult:
    findings: list[SecretFinding] = []
    current_path: str | None = None
    new_line = 0

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("+++ b/"):
            current_path = raw_line[6:].strip()
            new_line = 0
            continue
        if raw_line.startswith("@@"):
            new_line = _parse_new_line(raw_line)
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            line = raw_line[1:]
            line_no = new_line or None
            findings.extend(_scan_added_line(line, current_path, line_no))
            if new_line:
                new_line += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            continue
        elif new_line:
            new_line += 1

    scanners = ["vocr-minimal"]
    if repo_root is not None:
        gitleaks_findings = run_gitleaks_scan(Path(repo_root))
        if gitleaks_findings is not None:
            scanners.append("gitleaks")
            findings.extend(gitleaks_findings)

    return SecretScanResult(findings=_dedupe_findings(findings), scanners=scanners)


def run_gitleaks_scan(repo_root: Path) -> list[SecretFinding] | None:
    if which("gitleaks") is None:
        return None
    try:
        result = subprocess.run(
            _gitleaks_command(repo_root),
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return [
            SecretFinding(
                rule_id="gitleaks_timeout",
                summary=f"gitleaks did not complete cleanly ({exc}); review scanner output locally.",
                severity="medium",
            )
        ]
    output = result.stdout.strip()
    if result.returncode == 0:
        return []
    if result.returncode not in {1, 2} or not output:
        return [
            SecretFinding(
                rule_id="gitleaks_error",
                summary="gitleaks failed to scan cleanly; review scanner output locally.",
                severity="medium",
            )
        ]
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return [
            SecretFinding(
                rule_id="gitleaks_unparseable",
                summary="gitleaks returned unparseable output; review scanner output locally.",
                severity="medium",
            )
        ]
    findings: list[SecretFinding] = []
    for item in payload if isinstance(payload, list) else []:
        findings.append(
            SecretFinding(
                rule_id=str(item.get("RuleID") or item.get("Rule") or "gitleaks"),
                path=item.get("File"),
                line=item.get("StartLine"),
                summary="gitleaks detected a potential secret in the diff or repository.",
            )
        )
    return findings


def _gitleaks_command(repo_root: Path) -> list[str]:
    command = [
        "gitleaks",
        "detect",
        "--no-banner",
        "--redact",
        "--source",
        str(repo_root),
        "--report-format",
        "json",
    ]
    config = os.getenv("VOCR_GITLEAKS_CONFIG")
    if config is None and (repo_root / ".gitleaks.toml").exists():
        config = str(repo_root / ".gitleaks.toml")
    if config:
        command.extend(["--config", config])

    baseline = os.getenv("VOCR_GITLEAKS_BASELINE")
    if baseline is None and (repo_root / ".gitleaks-baseline.json").exists():
        baseline = str(repo_root / ".gitleaks-baseline.json")
    if baseline:
        command.extend(["--baseline-path", baseline])
    return command


def _scan_added_line(line: str, path: str | None, line_no: int | None) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    if KEYWORD_RE.search(line):
        findings.append(
            SecretFinding(
                rule_id="keyword_assignment",
                path=path,
                line=line_no,
                summary="Potential secret assignment in added line.",
            )
        )
    for rule_id, pattern, summary in KNOWN_PATTERNS:
        if pattern.search(line):
            findings.append(
                SecretFinding(
                    rule_id=rule_id,
                    path=path,
                    line=line_no,
                    summary=f"Potential secret detected: {summary}.",
                )
            )
    for match in HIGH_ENTROPY_RE.finditer(line):
        candidate = match.group(1)
        if _entropy(candidate) >= 4.2 and _looks_secret_adjacent(line):
            findings.append(
                SecretFinding(
                    rule_id="high_entropy_value",
                    path=path,
                    line=line_no,
                    summary="Potential high-entropy secret value in added line.",
                    severity="medium",
                )
            )
            break
    return findings


def _parse_new_line(hunk_header: str) -> int:
    match = re.search(r"\+(\d+)", hunk_header)
    return int(match.group(1)) if match else 0


def _entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {char: value.count(char) for char in set(value)}
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _looks_secret_adjacent(line: str) -> bool:
    lowered = line.lower()
    return any(term in lowered for term in ["key", "token", "secret", "password", "credential"])


def _dedupe_findings(findings: list[SecretFinding]) -> list[SecretFinding]:
    seen: set[tuple[str, str | None, int | None]] = set()
    unique: list[SecretFinding] = []
    for finding in findings:
        key = (finding.rule_id, finding.path, finding.line)
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return unique
