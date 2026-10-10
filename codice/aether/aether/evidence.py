"""Observed execution evidence; no model-authored PASS assertions."""
from __future__ import annotations

import hashlib
import json
import math
import platform
import re
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

Status = Literal["PASS", "FAIL", "BLOCKED", "N/A"]


def redact(text: str) -> str:
    text = re.sub(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
                  "[REDACTED PRIVATE KEY]", text, flags=re.DOTALL)
    text = re.sub(r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?)(?:bearer|basic)\s+\S+",
                  r"\1[REDACTED]", text)
    text = re.sub(r"(?i)((?:api[_-]?key|token|password|secret(?:_access_key)?|authorization)"
                  r"[\"']?\s*[:=]\s*)"
                  r"[^\s,;]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(--(?:api-key|token|password|secret)\s+)\S+", r"\1[REDACTED]", text)
    text = re.sub(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,})\b",
                  "[REDACTED]", text)
    return re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", text)


def redact_command(command: list[str]) -> list[str]:
    result = []
    secret_next = False
    for argument in command:
        result.append("[REDACTED]" if secret_next else redact(argument))
        secret_next = argument.lower() in {"--api-key", "--token", "--password",
                                            "--secret", "--authorization"}
    return result


def redact_data(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_data(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class Evidence:
    task_id: str
    artifact: str
    phase: str
    command: list[str]
    status: Status
    executed: bool
    exit_code: int | None
    duration_seconds: float
    environment: dict[str, str]
    limitations: list[str]
    output: str = ""


class EvidenceRecorder:
    def __init__(self, root: Path, task: str, *, task_id: str | None = None):
        self.root = root.resolve()
        self.task_id = task_id or uuid.uuid4().hex
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", self.task_id):
            raise ValueError("Invalid task ID")
        self.task_sha256 = hashlib.sha256(task.encode()).hexdigest()
        self.started = time.time()
        self.records: list[Evidence] = []
        self.skills: list[dict[str, str]] = []
        self.outcome: dict[str, str] | None = None
        self.tool_events: list[dict[str, Any]] = []

    def record(self, *, artifact: str, phase: str, command: list[str], executed: bool,
               exit_code: int | None, duration_seconds: float, output: str = "",
               limitations: list[str] | None = None, applicable: bool = True) -> Evidence:
        path = (self.root / artifact).resolve()
        if type(executed) is not bool or type(applicable) is not bool:
            raise ValueError("Evidence execution flags must be boolean")
        if not path.is_relative_to(self.root):
            raise ValueError("Evidence artifact outside project")
        if phase not in {"before", "after", "verification"}:
            raise ValueError("Invalid evidence phase")
        if executed and not applicable:
            raise ValueError("Executed checks cannot be N/A")
        if (not math.isfinite(duration_seconds) or duration_seconds < 0
                or (not executed and exit_code is not None)
                or (exit_code is not None and type(exit_code) is not int)):
            raise ValueError("Invalid execution evidence")
        status: Status = ("N/A" if not applicable else "BLOCKED" if not executed
                          else "PASS" if exit_code == 0 else "FAIL")
        limitations = list(limitations or [])
        if executed and exit_code is None:
            limitations.append("Process started but no successful exit code was observed")
        item = Evidence(self.task_id, str(path.relative_to(self.root)), phase,
                        redact_command(command), status, executed, exit_code,
                        round(duration_seconds, 6), {"os": platform.platform(),
                        "python": sys.version.split()[0]}, [redact(s) for s in limitations],
                        redact(output)[:12000])
        self.records.append(item)
        return item

    def summary(self) -> str:
        lines = [f"Task {self.task_id}"]
        if self.outcome:
            lines.append(f"Task {self.outcome['status']} [{self.outcome['code']}]: "
                         + redact(self.outcome['reason']))
        lines.extend(f"Skill {skill['name']} v{skill['version']}" for skill in self.skills)
        lines.extend(f"{r.status} [{r.phase}] {r.artifact}: {' '.join(r.command)} "
                     f"(exit={r.exit_code}, {r.duration_seconds:.3f}s)"
                     + ("; " + "; ".join(r.limitations) if r.limitations else "")
                     for r in self.records)
        if not self.records:
            lines.append("BLOCKED: no execution evidence was recorded")
        for comparison in self.comparisons():
            lines.append(f"{comparison['result']}: {comparison['artifact']} "
                         f"{comparison['command']}")
        return "\n".join(lines)

    def comparisons(self) -> list[dict[str, str]]:
        before = {(r.artifact, tuple(r.command)): r for r in self.records if r.phase == "before"}
        result = []
        for after in self.records:
            if after.phase != "after":
                continue
            initial = before.get((after.artifact, tuple(after.command)))
            if initial is None:
                label = "NO_BASELINE"
            elif initial.environment != after.environment:
                label = "INCOMPARABLE"
            elif "BLOCKED" in {initial.status, after.status}:
                label = "BLOCKED"
            elif "N/A" in {initial.status, after.status}:
                label = "N/A"
            elif initial.status == "PASS" and after.status == "FAIL":
                label = "REGRESSION"
            elif initial.status == "FAIL" and after.status == "PASS":
                label = "RESOLVED"
            else:
                label = "UNCHANGED"
            result.append({"artifact": after.artifact, "command": " ".join(after.command),
                           "result": label})
        return result

    def export(self) -> tuple[Path, Path]:
        folder = (self.root / ".aether" / "evidence").resolve()
        if not folder.is_relative_to(self.root):
            raise ValueError("Evidence output outside project")
        folder.mkdir(parents=True, exist_ok=True)
        json_path = folder / f"{self.task_id}.json"
        text_path = folder / f"{self.task_id}.txt"
        for path in (json_path, text_path):
            if path.is_symlink() or not path.resolve().is_relative_to(folder):
                raise ValueError("Evidence output is linked")
        payload: dict[str, Any] = {"schema_version": 1, "task_id": self.task_id,
            "task_sha256": self.task_sha256, "started": self.started,
            "skills": self.skills, "records": [asdict(record) for record in self.records],
            "comparisons": self.comparisons(),
            "human_validation": None}
        payload["task_outcome"] = ({key: redact(value) for key, value in self.outcome.items()}
                                   if self.outcome else None)
        payload["tool_events"] = redact_data(self.tool_events)
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        text_path.write_text(self.summary(), encoding="utf-8")
        return json_path, text_path
