from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from .config import AppConfig
from .service import FlowHealerService
from .store import SQLiteStore

DATASET_ORDER = (
    "issues",
    "attempts",
    "events",
    "runtime_status",
    "control_commands",
    "summary_metrics",
)


def default_export_dir(config: AppConfig) -> Path:
    return config.state_root_path() / "exports" / datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def write_telemetry_exports(
    *,
    service: FlowHealerService,
    repo_name: str | None,
    output_dir: Path,
    formats: tuple[str, ...] = ("csv", "jsonl"),
) -> list[Path]:
    normalized_formats = tuple(dict.fromkeys(_normalize_formats(formats)))
    output_dir.mkdir(parents=True, exist_ok=True)

    datasets = collect_telemetry_datasets(service=service, repo_name=repo_name)
    written: list[Path] = []
    for dataset_name in DATASET_ORDER:
        rows = datasets[dataset_name]
        if "csv" in normalized_formats:
            target = output_dir / "csv" / f"{dataset_name}.csv"
            _write_csv(target, rows)
            written.append(target)
        if "jsonl" in normalized_formats:
            target = output_dir / "jsonl" / f"{dataset_name}.jsonl"
            _write_jsonl(target, rows)
            written.append(target)
    return written


def collect_telemetry_datasets(
    *,
    service: FlowHealerService,
    repo_name: str | None,
) -> dict[str, list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    runtime_status: list[dict[str, Any]] = []

    for repo in service.config.select_repos(repo_name):
        store = SQLiteStore(service.config.repo_db_path(repo.repo_name))
        store.bootstrap()
        try:
            issues.extend(_annotate_repo_name(store.list_healer_issues(limit=5000), repo.repo_name))
            attempts.extend(_annotate_repo_name(store.list_recent_healer_attempts(limit=10_000), repo.repo_name))
            events.extend(_annotate_repo_name(store.list_healer_events(limit=10_000), repo.repo_name))
            runtime_row = dict(store.get_runtime_status() or {})
            runtime_row.setdefault("repo_name", repo.repo_name)
            runtime_status.append(runtime_row)
        finally:
            store.close()

    return {
        "issues": issues,
        "attempts": attempts,
        "events": events,
        "runtime_status": runtime_status,
        "control_commands": [dict(row) for row in service.control_command_rows(repo_name, limit=10_000)],
        "summary_metrics": [dict(row) for row in service.status_rows(repo_name, force_refresh=True)],
    }


def _annotate_repo_name(rows: Iterable[dict[str, Any]], repo_name: str) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item.setdefault("repo_name", repo_name)
        annotated.append(item)
    return annotated


def _normalize_formats(formats: tuple[str, ...]) -> list[str]:
    normalized: list[str] = []
    for item in formats:
        for value in str(item or "").split(","):
            candidate = value.strip().lower()
            if candidate in {"csv", "jsonl"}:
                normalized.append(candidate)
    return normalized or ["csv", "jsonl"]


def _flatten_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _flatten_value(row.get(field)) for field in fieldnames})


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=True, default=str))
            handle.write("\n")
