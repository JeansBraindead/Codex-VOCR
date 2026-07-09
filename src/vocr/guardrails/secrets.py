from __future__ import annotations

import math
import re

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


def scan_diff_for_secrets(diff_text: str) -> SecretScanResult:
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

    return SecretScanResult(findings=_dedupe_findings(findings))


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
