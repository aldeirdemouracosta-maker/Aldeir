"""Local, inert skills. Discovery reads only bounded YAML frontmatter."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import textwrap
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any

NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
VERSION = re.compile(r"\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?\Z")


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str


@dataclass(frozen=True)
class LoadedSkill:
    metadata: SkillMetadata
    version: str
    instructions: str
    manifest: dict[str, Any]


class SkillError(ValueError):
    pass


class SkillLoader:
    def __init__(self, project_root: Path, *, max_bytes: int = 65536,
                 max_skills: int = 100):
        self.root = project_root.resolve()
        self.base = self.root / ".aether" / "skills"
        self.max_bytes = max_bytes
        self.max_skills = max_skills
        self.errors: dict[str, str] = {}
        if not 1024 <= max_bytes <= 1048576 or not 1 <= max_skills <= 1000:
            raise SkillError("Invalid skill limits")

    def _folder(self, name: str) -> Path:
        if len(name) > 64 or not NAME.fullmatch(name):
            raise SkillError("Invalid skill name")
        folder = self.base / name
        for path in (self.root / ".aether", self.base, folder):
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise SkillError("Skill directories cannot be links or junctions")
        if not folder.resolve().is_relative_to(self.root) or not folder.is_dir():
            raise SkillError("Skill folder missing or outside project")
        return folder

    def resource(self, name: str, reference: str) -> Path:
        folder = self._folder(name)
        # Check both path syntaxes, even on a different host OS.
        if (not reference or "\x00" in reference or reference.startswith(("/", "\\"))
                or re.search(r"(?:^|[/\\])\.\.(?:[/\\]|$)", reference)
                or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", reference)):
            raise SkillError("Reference outside skill folder")
        candidate = folder / reference.replace("\\", "/")
        if not candidate.resolve().is_relative_to(folder.resolve()):
            raise SkillError("Reference escapes skill folder")
        for path in [candidate, *candidate.parents]:
            if path == folder.parent:
                break
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise SkillError("Skill references cannot be links or junctions")
        if not candidate.is_file():
            raise SkillError(f"Missing skill resource: {reference}")
        return candidate

    def _frontmatter(self, folder: Path) -> tuple[SkillMetadata, int]:
        path = self.resource(folder.name, "SKILL.md")
        if path.stat().st_size > self.max_bytes:
            raise SkillError("SKILL.md exceeds size limit")
        lines: list[str] = []
        consumed = 0
        with path.open("rb") as stream:
            if stream.readline(256).strip() != b"---":
                raise SkillError("Missing YAML frontmatter")
            while True:
                raw = stream.readline(2049)
                consumed += len(raw)
                if not raw or consumed > 4096 or len(raw) > 2048:
                    raise SkillError("Invalid or oversized frontmatter")
                if raw.strip() == b"---":
                    offset = stream.tell()
                    break
                lines.append(raw.decode("utf-8"))
        # Restricted YAML string mapping, deliberately excluding tags, aliases,
        # nesting and implicit boolean/numeric coercion. No runtime dependency.
        data: dict[str, str] = {}
        position = 0
        while position < len(lines):
            line = lines[position]
            position += 1
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            match = re.fullmatch(r"(name|description):[ \t]+([^\r\n]+)[\r\n]*", line)
            if not match or match[1] in data:
                raise SkillError("Frontmatter supports unique name/description strings only")
            key, value = match.groups()
            if value in {"|", "|-", ">", ">-"}:
                block = []
                while position < len(lines) and (lines[position].startswith((" ", "\t"))
                                                or not lines[position].strip()):
                    block.append(lines[position])
                    position += 1
                value = textwrap.dedent("".join(block)).strip()
                if match[2].startswith(">"):
                    value = " ".join(value.splitlines())
            elif value.startswith('"'):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError as exc:
                    raise SkillError("Invalid quoted YAML string") from exc
            elif value.startswith("'"):
                if not value.endswith("'"):
                    raise SkillError("Invalid quoted YAML string")
                value = value[1:-1].replace("''", "'")
            elif (value[0] in "!&*[{>|" or ": " in value or " #" in value
                  or value.lower() in {"true", "false", "null", "~"}
                  or value.isnumeric()):
                raise SkillError("Unsupported YAML value; quote strings")
            if not isinstance(value, str) or not value.strip():
                raise SkillError("Empty frontmatter field")
            data[key] = value.strip()
        if set(data) != {"name", "description"} or data["name"] != folder.name:
            raise SkillError("Frontmatter name must match folder and include description")
        if len(data["description"]) > 1024:
            raise SkillError("Description exceeds size limit")
        return SkillMetadata(**data), offset

    def discover(self) -> list[SkillMetadata]:
        self.errors = {}
        if not self.base.exists():
            return []
        # Validate base before enumeration; never follow a linked skills root.
        for path in (self.root / ".aether", self.base):
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise SkillError("Skills root cannot be a link")
        result = []
        entries = sorted(islice(self.base.iterdir(), self.max_skills + 1), key=lambda p: p.name)
        if len(entries) > self.max_skills:
            raise SkillError("Too many skill folders")
        for entry in entries:
            try:
                result.append(self._frontmatter(self._folder(entry.name))[0])
            except (OSError, ValueError, UnicodeError) as exc:
                self.errors[entry.name] = str(exc)
        return result

    def load(self, name: str, available_tools: set[str], *, allow_network: bool = False,
             platform: str | None = None) -> LoadedSkill:
        folder = self._folder(name)
        metadata, offset = self._frontmatter(folder)
        manifest_path = self.resource(name, "aether.json")
        if manifest_path.stat().st_size > 8192:
            raise SkillError("Oversized skill manifest")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        required = {"version", "required_tools", "os", "network"}
        if (not isinstance(manifest, dict) or not required <= manifest.keys()
                or set(manifest) - required - {"required_executables", "resources"}):
            raise SkillError("Invalid manifest; permissions cannot be declared by skills")
        version = manifest["version"]
        if not isinstance(version, str) or not VERSION.fullmatch(version):
            raise SkillError("Invalid skill version")
        for key in ("required_tools", "os", "required_executables", "resources"):
            values = manifest.get(key, [])
            if (not isinstance(values, list) or len(values) > 64
                    or any(not isinstance(value, str) or not value for value in values)):
                raise SkillError(f"Invalid manifest field: {key}")
        if type(manifest["network"]) is not bool:
            raise SkillError("network must be boolean")
        if any(not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", executable)
               for executable in manifest.get("required_executables", [])):
            raise SkillError("Executable dependencies must be names, not paths")
        if not manifest["os"] or set(manifest["os"]) - {"windows", "linux", "darwin"}:
            raise SkillError("Invalid OS compatibility")
        system = platform or ("windows" if sys.platform == "win32" else sys.platform)
        if system not in manifest["os"]:
            raise SkillError(f"Unsupported OS: {system}")
        missing = set(manifest["required_tools"]) - available_tools
        missing.update(exe for exe in manifest.get("required_executables", [])
                       if shutil.which(exe) is None)
        if missing:
            raise SkillError("Missing dependencies: " + ", ".join(sorted(missing)))
        if manifest["network"] and not allow_network:
            raise SkillError("Skill needs network; current permissions do not allow it")
        count = total = 0
        for parent, dirs, files in os.walk(folder, followlinks=False):
            for filename in [*dirs, *files]:
                path = Path(parent) / filename
                if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                    raise SkillError("Links are not allowed in skills")
                count += 1
                if path.is_file():
                    total += path.stat().st_size
                if count > 256 or total > 4 * self.max_bytes:
                    raise SkillError("Skill resources exceed size limit")
        with self.resource(name, "SKILL.md").open("rb") as stream:
            stream.seek(offset)
            instructions = stream.read(self.max_bytes + 1).decode("utf-8")
        if (not instructions.strip() or "\x00" in instructions
                or len(instructions.encode()) > self.max_bytes):
            raise SkillError("Empty or oversized skill instructions")
        references = re.findall(r"\[[^\]]*\]\(([^)]+)\)", instructions)
        references += [value for value in re.findall(r"`([^`\n]+)`", instructions)
                       if "/" in value or "\\" in value]
        if re.search(r"(?:^|\s)(?:\.\.[/\\]|[a-zA-Z]:[/\\]|/[^\s])", instructions):
            raise SkillError("Instructions reference paths outside skill")
        for reference in [*manifest.get("resources", []), *references]:
            if not reference.startswith("#"):
                self.resource(name, reference.split("#", 1)[0])
        return LoadedSkill(metadata, version, instructions, manifest)
