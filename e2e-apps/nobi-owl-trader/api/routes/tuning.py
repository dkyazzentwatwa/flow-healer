import os
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/tuning", tags=["Tuning"])

PID_FILE = Path("/tmp/nobibot-tune.pid")
LOG_FILE = Path("/tmp/nobibot-tune.log")


class TuningRunRequest(BaseModel):
    auto_apply: bool = Field(default=True)
    all_symbols: bool = Field(default=True)
    skip_download: bool = Field(default=False)
    fast: bool = Field(default=False)
    focus_symbols: str | None = Field(default=None, description="Comma-separated list")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except ValueError:
        return None


def read_log_tail(limit: int = 200) -> str:
    if not LOG_FILE.exists():
        return ""
    try:
        with LOG_FILE.open("r") as handle:
            lines = handle.readlines()
        return "".join(lines[-limit:])
    except OSError:
        return ""


@router.post("/run")
def run_tuning(payload: TuningRunRequest):
    current_pid = read_pid()
    if current_pid and is_running(current_pid):
        raise HTTPException(status_code=409, detail="Tuning is already running.")

    root = repo_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)

    if payload.auto_apply:
        env["AUTO_APPLY"] = "1"
    if payload.all_symbols:
        env["ALL_SYMBOLS"] = "1"
    if payload.skip_download:
        env["SKIP_DOWNLOAD"] = "1"
    if payload.fast:
        env["FAST"] = "1"
    if payload.focus_symbols:
        env["FOCUS_SYMBOLS"] = payload.focus_symbols

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("w") as log_file:
        process = subprocess.Popen(
            [sys.executable, "scripts/tune_automation_rules.py"],
            cwd=str(root),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )

    PID_FILE.write_text(str(process.pid))
    return {
        "status": "started",
        "pid": process.pid,
        "log_file": str(LOG_FILE),
        "started_at": utc_now(),
    }


@router.get("/status")
def tuning_status():
    pid = read_pid()
    running = bool(pid and is_running(pid))
    return {
        "running": running,
        "pid": pid,
        "log_tail": read_log_tail(),
        "log_file": str(LOG_FILE),
        "checked_at": utc_now(),
    }
