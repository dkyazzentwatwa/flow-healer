from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .healer_task_spec import HealerTaskSpec
from .language_strategies import get_strategy

if TYPE_CHECKING:
    from .healer_runner import HealerRunner, ResolvedExecution
    from .protocols import ConnectorProtocol
    from .store import SQLiteStore


_DEFAULT_PREFLIGHT_TTL_SECONDS = 900
_CONNECTOR_PROBE_TTL_SECONDS = 300
_SUPPORTED_SANDBOXES: tuple[tuple[str, str], ...] = (
    ("python", "e2e-smoke/python"),
    ("node", "e2e-smoke/node"),
    ("swift", "e2e-smoke/swift"),
)


@dataclass(slots=True, frozen=True)
class PreflightReport:
    language: str
    execution_root: str
    gate_mode: str
    status: str
    failure_class: str
    summary: str
    output_tail: str
    checked_at: str
    test_summary: dict[str, object]

    def to_state_value(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=True, sort_keys=True)

    @classmethod
    def from_state_value(cls, raw: str | None) -> "PreflightReport | None":
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        return cls(
            language=str(data.get("language") or ""),
            execution_root=str(data.get("execution_root") or ""),
            gate_mode=str(data.get("gate_mode") or ""),
            status=str(data.get("status") or ""),
            failure_class=str(data.get("failure_class") or ""),
            summary=str(data.get("summary") or ""),
            output_tail=str(data.get("output_tail") or ""),
            checked_at=str(data.get("checked_at") or ""),
            test_summary=dict(data.get("test_summary") or {}),
        )


def preflight_cache_key(*, gate_mode: str, language: str) -> str:
    return f"healer_preflight:{gate_mode.strip()}:{language.strip()}"


def list_cached_preflight_reports(*, store: SQLiteStore, gate_mode: str) -> list[PreflightReport]:
    reports: list[PreflightReport] = []
    for language, execution_root in _SUPPORTED_SANDBOXES:
        report = PreflightReport.from_state_value(
            store.get_state(preflight_cache_key(gate_mode=gate_mode, language=language))
        )
        if report is not None:
            reports.append(report)
            continue
        reports.append(
            PreflightReport(
                language=language,
                execution_root=execution_root,
                gate_mode=gate_mode,
                status="missing",
                failure_class="not_checked",
                summary="Preflight has not been run for this language yet.",
                output_tail="",
                checked_at="",
                test_summary={},
            )
        )
    return reports


class HealerPreflight:
    def __init__(
        self,
        *,
        store: SQLiteStore,
        runner: HealerRunner,
        repo_path: Path,
        ttl_seconds: int = _DEFAULT_PREFLIGHT_TTL_SECONDS,
    ) -> None:
        self.store = store
        self.runner = runner
        self.repo_path = Path(repo_path).expanduser().resolve()
        self.ttl_seconds = max(60, int(ttl_seconds))
        # Cache for connector probe results: connector_class_name → (ok, reason, checked_at)
        self._connector_probe_cache: dict[str, tuple[bool, str, datetime]] = {}

    def probe_connector(self, connector: ConnectorProtocol) -> tuple[bool, str]:
        """Quickly verify the connector is available before invoking it for an issue.

        Result is cached per connector class for _CONNECTOR_PROBE_TTL_SECONDS to avoid
        repeated overhead. Returns (available, failure_reason).
        """
        connector_name = type(connector).__name__
        now = datetime.now(UTC)
        cached = self._connector_probe_cache.get(connector_name)
        if cached is not None:
            ok, reason, checked_at = cached
            age = (now - checked_at).total_seconds()
            if age < _CONNECTOR_PROBE_TTL_SECONDS:
                return ok, reason
        try:
            connector.ensure_started()
        except Exception as exc:
            reason = f"connector.ensure_started() raised: {exc}"
            self._connector_probe_cache[connector_name] = (False, reason, now)
            return False, reason
        # Check health_snapshot if available
        snapshot_fn = getattr(connector, "health_snapshot", None)
        if callable(snapshot_fn):
            try:
                snapshot = snapshot_fn()
                availability = str(snapshot.get("availability") or "").lower()
                if availability == "unavailable":
                    reason = str(snapshot.get("availability_reason") or "connector reported unavailable")
                    self._connector_probe_cache[connector_name] = (False, reason, now)
                    return False, reason
            except Exception:
                pass
        self._connector_probe_cache[connector_name] = (True, "", now)
        return True, ""

    def refresh_all(self, *, force: bool = False) -> list[PreflightReport]:
        reports: list[PreflightReport] = []
        for language, execution_root in _SUPPORTED_SANDBOXES:
            reports.append(
                self.ensure_language_ready(
                    language=language,
                    execution_root=execution_root,
                    force=force,
                )
            )
        return reports

    def ensure_language_ready(
        self,
        *,
        language: str,
        execution_root: str,
        force: bool = False,
    ) -> PreflightReport:
        cached = self.get_cached_report(language=language)
        if not force and cached is not None and not self._is_stale(cached):
            return cached
        report = self._run_preflight(language=language, execution_root=execution_root)
        self.store.set_state(
            preflight_cache_key(gate_mode=self.runner.test_gate_mode, language=language),
            report.to_state_value(),
        )
        return report

    def get_cached_report(self, *, language: str) -> PreflightReport | None:
        return PreflightReport.from_state_value(
            self.store.get_state(preflight_cache_key(gate_mode=self.runner.test_gate_mode, language=language))
        )

    def _is_stale(self, report: PreflightReport) -> bool:
        checked = _parse_store_timestamp(report.checked_at)
        if checked is None:
            return True
        age = (datetime.now(UTC) - checked).total_seconds()
        return age >= self.ttl_seconds

    def _run_preflight(self, *, language: str, execution_root: str) -> PreflightReport:
        sandbox_path = self.repo_path / execution_root
        checked_at = _now_store_timestamp()
        strategy = get_strategy(language)
        if not sandbox_path.is_dir():
            return PreflightReport(
                language=language,
                execution_root=execution_root,
                gate_mode=self.runner.test_gate_mode,
                status="missing",
                failure_class="sandbox_missing",
                summary=f"Sandbox path is missing: {execution_root}",
                output_tail="",
                checked_at=checked_at,
                test_summary={},
            )
        if self.runner.test_gate_mode == "docker_only" and not strategy.supports_docker:
            return PreflightReport(
                language=language,
                execution_root=execution_root,
                gate_mode=self.runner.test_gate_mode,
                status="failed",
                failure_class="unsupported_gate_mode",
                summary=(
                    f"Preflight does not support docker_only for {language}; "
                    "use local_only or local_then_docker."
                ),
                output_tail="(docker gate unsupported for this language)",
                checked_at=checked_at,
                test_summary={},
            )
        if self.runner.test_gate_mode != "local_only" and strategy.supports_docker and shutil.which("docker") is None:
            return PreflightReport(
                language=language,
                execution_root=execution_root,
                gate_mode=self.runner.test_gate_mode,
                status="failed",
                failure_class="docker_unavailable",
                summary="Docker is required for the configured gate mode but was not found in PATH.",
                output_tail="",
                checked_at=checked_at,
                test_summary={},
            )

        task_spec = HealerTaskSpec(
            task_kind="build",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_only",
            validation_profile="code_change",
            language=language,
            language_source="preflight",
            execution_root=execution_root,
            validation_commands=(),
        )
        try:
            with tempfile.TemporaryDirectory(prefix="flow-healer-preflight-") as temp_root:
                temp_workspace = Path(temp_root)
                sandbox_dest = temp_workspace / execution_root
                sandbox_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(sandbox_path, sandbox_dest, dirs_exist_ok=True)
                summary = self.runner.validate_workspace(
                    temp_workspace,
                    task_spec=task_spec,
                    targeted_tests=[],
                    mode=self.runner.test_gate_mode,
                    local_gate_policy=self.runner.local_gate_policy,
                )
        except Exception as exc:
            return PreflightReport(
                language=language,
                execution_root=execution_root,
                gate_mode=self.runner.test_gate_mode,
                status="failed",
                failure_class="preflight_exception",
                summary=f"Preflight execution failed: {exc}",
                output_tail=str(exc),
                checked_at=checked_at,
                test_summary={},
            )

        failed_tests = int(summary.get("failed_tests", 0))
        output_tail = _best_output_tail(summary)
        if failed_tests > 0:
            if not _has_environment_gate_failure(summary):
                return PreflightReport(
                    language=language,
                    execution_root=execution_root,
                    gate_mode=self.runner.test_gate_mode,
                    status="ready",
                    failure_class="",
                    summary=(
                        f"Preflight toolchain check passed for {language} in {execution_root}; "
                        f"baseline tests currently fail (mode={self.runner.test_gate_mode}, failed_tests={failed_tests})."
                    ),
                    output_tail=output_tail,
                    checked_at=checked_at,
                    test_summary=summary,
                )
            return PreflightReport(
                language=language,
                execution_root=execution_root,
                gate_mode=self.runner.test_gate_mode,
                status="failed",
                failure_class="validation_failed",
                summary=(
                    f"Preflight validation failed for {language} in {execution_root} "
                    f"(mode={self.runner.test_gate_mode}, failed_tests={failed_tests})."
                ),
                output_tail=output_tail,
                checked_at=checked_at,
                test_summary=summary,
            )

        return PreflightReport(
            language=language,
            execution_root=execution_root,
            gate_mode=self.runner.test_gate_mode,
            status="ready",
            failure_class="",
            summary=f"Preflight passed for {language} in {execution_root}.",
            output_tail=output_tail,
            checked_at=checked_at,
            test_summary=summary,
        )


def execution_root_for_language(language: str) -> str:
    wanted = str(language or "").strip()
    for candidate_language, execution_root in _SUPPORTED_SANDBOXES:
        if candidate_language == wanted:
            return execution_root
    return ""


def preflight_report_to_test_summary(report: PreflightReport) -> dict[str, object]:
    summary = dict(report.test_summary)
    summary.setdefault("mode", report.gate_mode)
    summary["preflight_status"] = report.status
    summary["preflight_failure_class"] = report.failure_class
    summary["preflight_summary"] = report.summary
    summary["preflight_output_tail"] = report.output_tail
    summary["execution_root"] = report.execution_root
    summary["language_effective"] = report.language
    return summary


def _best_output_tail(summary: dict[str, object]) -> str:
    preferred_keys = (
        "docker_full_output_tail",
        "docker_targeted_output_tail",
        "local_full_output_tail",
        "local_targeted_output_tail",
    )
    for key in preferred_keys:
        value = str(summary.get(key) or "").strip()
        if value:
            return value[-2000:]
    return ""


def _has_environment_gate_failure(summary: dict[str, object]) -> bool:
    infra_reasons = {
        "tool_missing",
        "docker_unsupported_for_language",
        "local_only_requires_local_gate",
        "no_local_test_command",
    }
    for runner in ("local", "docker"):
        status = str(summary.get(f"{runner}_full_status") or "").strip().lower()
        reason = str(summary.get(f"{runner}_full_reason") or "").strip().lower()
        if status != "failed":
            continue
        if reason in infra_reasons:
            return True
        if reason:
            return True
    return False


def _parse_store_timestamp(raw: str) -> datetime | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _now_store_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
