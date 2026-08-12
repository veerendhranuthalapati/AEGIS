"""Start backend + mock API with reliable log redirection (Windows dev helper)."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
MOCK = ROOT / "attack_lab" / "targets" / "mock_api"
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
LOG_DIR = Path(os.environ.get("TEMP", "/tmp")) / "aegis_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _start(name: str, cwd: Path, args: list[str], env: dict | None = None) -> None:
    out = (LOG_DIR / f"{name}.out.log").open("w", encoding="utf-8", buffering=1)
    err = (LOG_DIR / f"{name}.err.log").open("w", encoding="utf-8", buffering=1)
    merged = dict(os.environ)
    merged["PYTHONUNBUFFERED"] = "1"
    if env:
        merged.update(env)
    subprocess.Popen(
        args,
        cwd=str(cwd),
        stdout=out,
        stderr=err,
        env=merged,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    print(f"started {name}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dev"
    if cmd in ("dev", "backend"):
        _start(
            "backend",
            BACKEND,
            [str(PY), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
            {
                "AEGIS_IN_PROCESS_WORKER": "true",
                "UPSTREAM_BASE_URL": "http://127.0.0.1:8100",
            },
        )
    if cmd in ("dev", "mock"):
        _start(
            "mock",
            MOCK,
            [str(PY), "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8100"],
        )
    if cmd == "dev":
        time.sleep(8)
        print(f"logs in {LOG_DIR}")
