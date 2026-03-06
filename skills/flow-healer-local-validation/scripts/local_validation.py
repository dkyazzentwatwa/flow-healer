#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def _run(cmd: list[str], *, cwd: Path) -> dict[str, Any]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
    )
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return {
        "cmd": cmd,
        "exit_code": proc.returncode,
        "output_tail": output[-2000:],
    }


def main() -> int:
    parser_cmd = [
        ".venv/bin/python",
        "-m",
        "flow_healer.cli",
        "--config",
        "config.example.yaml",
        "scan",
        "--repo",
        "demo",
        "--dry-run",
    ]
    repo_root = Path.cwd()
    checks = [_run(["pytest", "-q"], cwd=repo_root)]
    if (repo_root / ".venv" / "bin" / "python").exists() and (repo_root / ".flow-healer-smoke-config.yaml").exists():
        checks.append(
            _run(
                [
                    ".venv/bin/python",
                    "-m",
                    "flow_healer.cli",
                    "--config",
                    ".flow-healer-smoke-config.yaml",
                    "scan",
                    "--dry-run",
                ],
                cwd=repo_root,
            )
        )
    else:
        checks.append(
            {
                "cmd": parser_cmd,
                "exit_code": 0,
                "output_tail": "Skipped scan check because .flow-healer-smoke-config.yaml is not present.",
            }
        )
    report = {
        "repo_root": str(repo_root),
        "checks": checks,
    }
    print(json.dumps(report, indent=2))
    return 0 if all(int(entry["exit_code"]) == 0 for entry in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
