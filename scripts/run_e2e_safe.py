"""Bootstrap PostgreSQL and run E2E in one process (reduces Windows Docker port race)."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
DB = "postgresql+asyncpg://aegis:aegis@127.0.0.1:5433/aegis"


def _migrate() -> bool:
    env = {**dict(__import__("os").environ), "DATABASE_URL": DB, "SECRET_KEY": "dev-secret-change-me"}
    proc = subprocess.run(
        [str(PY), "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode == 0


def _reset_once() -> bool:
    env = {**dict(__import__("os").environ), "DATABASE_URL": DB, "SECRET_KEY": "dev-secret-change-me"}
    proc = subprocess.run(
        [str(PY), str(BACKEND / "scripts" / "_e2e_reset.py")],
        cwd=str(BACKEND),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode == 0


def main() -> int:
    subprocess.run(["docker", "compose", "up", "-d", "postgres"], cwd=str(ROOT), check=False)
    for _ in range(60):
        if _migrate():
            break
        time.sleep(1)
    else:
        print("postgres migrate never succeeded", file=sys.stderr)
        return 1
    if not _reset_once():
        print("telemetry reset failed", file=sys.stderr)
        return 1
    sys.path.insert(0, str(ROOT))
    import e2e

    e2e.main(skip_reset=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
