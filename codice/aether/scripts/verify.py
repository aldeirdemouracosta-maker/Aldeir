"""Offline verification with observed results and explicit BLOCKED dependencies."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aether.evidence import EvidenceRecorder


def main() -> int:
    recorder = EvidenceRecorder(ROOT, "Verify local skills, indexing, cache and evidence")
    compile_code = (
        "import pathlib,py_compile,tomllib; root=pathlib.Path('.'); "
        "sources=[*root.joinpath('aether').rglob('*.py'),"
        "*root.joinpath('tests').glob('*.py'),*root.joinpath('scripts').glob('*.py')]; "
        "[py_compile.compile(str(p),doraise=True) for p in sources]; "
        "tomllib.loads(root.joinpath('pyproject.toml').read_text(encoding='utf-8')); "
        "print(f'Compiled {len(sources)} Python files; TOML parsed')"
    )
    commands = [
        (None, [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
        ("pytest", [sys.executable, "-m", "pytest", "-q"]),
        ("mypy", [sys.executable, "-m", "mypy", "aether"]),
        ("ruff", [sys.executable, "-m", "ruff", "check", "aether", "tests", "scripts"]),
        (None, [sys.executable, "-c", compile_code]),
    ]
    failed = False
    for module, command in commands:
        if module and importlib.util.find_spec(module) is None:
            recorder.record(artifact=".", phase="verification", command=command,
                executed=False, exit_code=None, duration_seconds=0,
                limitations=[f"Dependency unavailable: {module}; no installation performed"])
            continue
        started = time.perf_counter()
        try:
            result = subprocess.run(command, check=False, cwd=ROOT, shell=False, capture_output=True,
                                    text=True, errors="replace", timeout=60)
        except subprocess.TimeoutExpired:
            recorder.record(artifact=".", phase="verification", command=command,
                executed=True, exit_code=None, duration_seconds=time.perf_counter() - started,
                limitations=["Verification exceeded 60s; only direct process terminated"])
            failed = True
        else:
            recorder.record(artifact=".", phase="verification", command=command,
                executed=True, exit_code=result.returncode,
                duration_seconds=time.perf_counter() - started,
                output=result.stdout + result.stderr,
                limitations=["Real Ollama inference and end-to-end indexing are not exercised",
                             "Consult test output for skipped checks"] if module in {None, "pytest"} else [])
            failed |= result.returncode != 0
    paths = recorder.export()
    print(recorder.summary())
    print("Evidence:", *paths)
    # BLOCKED dependencies are incomplete gates, even if executable checks pass.
    return 1 if failed or any(r.status == "BLOCKED" for r in recorder.records) else 0


if __name__ == "__main__":
    raise SystemExit(main())
