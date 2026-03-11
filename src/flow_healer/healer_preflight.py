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
    from .healer_runner import HealerRunner
    from .protocols import ConnectorProtocol
    from .store import SQLiteStore


_DEFAULT_PREFLIGHT_TTL_SECONDS = 900
_CONNECTOR_PROBE_TTL_SECONDS = 300
_SUPPORTED_SANDBOXES: tuple[tuple[str, str, str], ...] = (
    ("python", "generic", "e2e-smoke/python"),
    ("node", "generic", "e2e-smoke/node"),
    ("node", "next", "e2e-smoke/js-next"),
    ("node", "vue_vite", "e2e-smoke/js-vue-vite"),
    ("node", "nuxt", "e2e-smoke/js-nuxt"),
    ("node", "angular", "e2e-smoke/js-angular"),
    ("node", "sveltekit", "e2e-smoke/js-sveltekit"),
    ("node", "express", "e2e-smoke/js-express"),
    ("node", "nest", "e2e-smoke/js-nest"),
    ("node", "remix", "e2e-smoke/js-remix"),
    ("node", "astro", "e2e-smoke/js-astro"),
    ("node", "solidstart", "e2e-smoke/js-solidstart"),
    ("node", "qwik", "e2e-smoke/js-qwik"),
    ("node", "hono", "e2e-smoke/js-hono"),
    ("node", "koa", "e2e-smoke/js-koa"),
    ("node", "adonis", "e2e-smoke/js-adonis"),
    ("node", "redwoodsdk", "e2e-smoke/js-redwoodsdk"),
    ("node", "lit", "e2e-smoke/js-lit"),
    ("node", "alpine_vite", "e2e-smoke/js-alpine-vite"),
    ("python", "fastapi", "e2e-smoke/py-fastapi"),
    ("python", "django", "e2e-smoke/py-django"),
    ("python", "flask", "e2e-smoke/py-flask"),
    ("python", "pandas", "e2e-smoke/py-data-pandas"),
    ("python", "sklearn", "e2e-smoke/py-ml-sklearn"),
    ("node", "next", "e2e-apps/node-next"),
    ("python", "fastapi", "e2e-apps/python-fastapi"),
    ("node", "next", "e2e-apps/prosper-chat"),
    ("python", "fastapi", "e2e-apps/nobi-owl-trader"),
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


def preflight_cache_key(*, gate_mode: str, language: str, execution_root: str = "") -> str:
    normalized_root = execution_root.strip().replace(":", "_") or "_repo"
    return f"healer_preflight:{gate_mode.strip()}:{language.strip()}:{normalized_root}"


def list_cached_preflight_reports(*, store: SQLiteStore, gate_mode: str) -> list[PreflightReport]:
    reports: list[PreflightReport] = []
    for language, _framework, execution_root in _SUPPORTED_SANDBOXES:
        report = PreflightReport.from_state_value(
            store.get_state(
                preflight_cache_key(
                    gate_mode=gate_mode,
                    language=language,
                    execution_root=execution_root,
                )
            )
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
        self._connector_probe_cache: dict[str, tuple[bool, str, datetime]] = {}
        self._browser_probe_cache: dict[str, tuple[bool, str, datetime]] = {}

    def probe_connector(self, connector: ConnectorProtocol) -> tuple[bool, str]:
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
        snapshot_fn = getattr(connector, "health_snapshot", None)
        if callable(snapshot_fn):
            try:
                snapshot = snapshot_fn()
                available = snapshot.get("available")
                if available is False:
                    reason = str(snapshot.get("availability_reason") or "connector reported unavailable")
                    self._connector_probe_cache[connector_name] = (False, reason, now)
                    return False, reason
                availability = str(snapshot.get("availability") or "").lower()
                if availability == "unavailable":
                    reason = str(snapshot.get("availability_reason") or "connector reported unavailable")
                    self._connector_probe_cache[connector_name] = (False, reason, now)
                    return False, reason
            except Exception:
                pass
        self._connector_probe_cache[connector_name] = (True, "", now)
        return True, ""

    def probe_browser_runtime(self, browser_harness: object) -> tuple[bool, str]:
        harness_name = type(browser_harness).__name__
        now = datetime.now(UTC)
        cached = self._browser_probe_cache.get(harness_name)
        if cached is not None:
            ok, reason, checked_at = cached
            age = (now - checked_at).total_seconds()
            if age < _CONNECTOR_PROBE_TTL_SECONDS:
                return ok, reason

        check_fn = getattr(browser_harness, "check_runtime_available", None)
        if not callable(check_fn):
            reason = "browser harness does not expose check_runtime_available()"
            self._browser_probe_cache[harness_name] = (False, reason, now)
            return False, reason
        try:
            ok, reason = check_fn()
        except Exception as exc:
            reason = f"browser_harness.check_runtime_available() raised: {exc}"
            self._browser_probe_cache[harness_name] = (False, reason, now)
            return False, reason
        self._browser_probe_cache[harness_name] = (bool(ok), str(reason or ""), now)
        return bool(ok), str(reason or "")

    def refresh_all(self, *, force: bool = False) -> list[PreflightReport]:
        reports: list[PreflightReport] = []
        for language, framework, execution_root in _SUPPORTED_SANDBOXES:
            reports.append(
                self.ensure_language_ready(
                    language=language,
                    framework=framework,
                    execution_root=execution_root,
                    force=force,
                )
            )
        return reports

    def ensure_language_ready(
        self,
        *,
        language: str,
        framework: str = "",
        execution_root: str,
        force: bool = False,
    ) -> PreflightReport:
        cached = self.get_cached_report(language=language, execution_root=execution_root)
        if not force and cached is not None and not self._is_stale(cached):
            return cached
        report = self._run_preflight(language=language, framework=framework, execution_root=execution_root)
        self.store.set_state(
            preflight_cache_key(
                gate_mode=self.runner.test_gate_mode,
                language=language,
                execution_root=execution_root,
            ),
            report.to_state_value(),
        )
        return report

    def get_cached_report(self, *, language: str, execution_root: str) -> PreflightReport | None:
        return PreflightReport.from_state_value(
            self.store.get_state(
                preflight_cache_key(
                    gate_mode=self.runner.test_gate_mode,
                    language=language,
                    execution_root=execution_root,
                )
            )
        )

    def _is_stale(self, report: PreflightReport) -> bool:
        checked = _parse_store_timestamp(report.checked_at)
        if checked is None:
            return True
        age = (datetime.now(UTC) - checked).total_seconds()
        return age >= self.ttl_seconds

    def _run_preflight(self, *, language: str, framework: str, execution_root: str) -> PreflightReport:
        sandbox_path = self.repo_path / execution_root
        checked_at = _now_store_timestamp()
        strategy = get_strategy(language, framework=framework)
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

        manager_probe = _probe_node_toolchain(sandbox_path)
        if manager_probe["required_tool"] and not manager_probe["tool_available"]:
            return PreflightReport(
                language=language,
                execution_root=execution_root,
                gate_mode=self.runner.test_gate_mode,
                status="failed",
                failure_class="tool_missing",
                summary=(
                    f"Preflight requires `{manager_probe['required_tool']}` for {execution_root} "
                    "but it is not available in PATH."
                ),
                output_tail="",
                checked_at=checked_at,
                test_summary={"toolchain": manager_probe},
            )

        monorepo_probe = _probe_monorepo_layout(sandbox_path)

        task_spec = HealerTaskSpec(
            task_kind="build",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_only",
            validation_profile="code_change",
            language=language,
            language_source="preflight",
            framework=framework,
            framework_source="preflight",
            execution_root=execution_root,
            validation_commands=_preflight_validation_commands(
                execution_root=execution_root,
                language=language,
                framework=framework,
            ),
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
                summary=f"Preflight crashed for {language} in {execution_root}: {exc}",
                output_tail=str(exc)[-2000:],
                checked_at=checked_at,
                test_summary={
                    "toolchain": manager_probe,
                    "monorepo": monorepo_probe,
                },
            )

        output_tail = _best_output_tail(summary)
        if _has_environment_gate_failure(summary):
            failure_class = str(
                summary.get("local_full_reason")
                or summary.get("docker_full_reason")
                or "preflight_failed"
            )
            return PreflightReport(
                language=language,
                execution_root=execution_root,
                gate_mode=self.runner.test_gate_mode,
                status="failed",
                failure_class=failure_class,
                summary=(
                    f"Preflight validation failed for {language} in {execution_root} "
                    f"(reason={failure_class})."
                ),
                output_tail=output_tail,
                checked_at=checked_at,
                test_summary={
                    **summary,
                    "toolchain": manager_probe,
                    "monorepo": monorepo_probe,
                },
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
            test_summary={
                **summary,
                "toolchain": manager_probe,
                "monorepo": monorepo_probe,
            },
        )


def execution_root_for_language(language: str) -> str:
    wanted = str(language or "").strip()
    for candidate_language, _framework, execution_root in _SUPPORTED_SANDBOXES:
        if candidate_language == wanted:
            return execution_root
    return ""


def _preflight_validation_commands(*, execution_root: str, language: str, framework: str = "") -> tuple[str, ...]:
    normalized_root = str(execution_root or "").strip().strip("/")
    if normalized_root == "e2e-apps/prosper-chat":
        return (f"cd {normalized_root} && ./scripts/healer_validate.sh full",)
    if language == "python":
        return (f"cd {normalized_root} && pytest -q",) if normalized_root else ()
    if language == "node":
        return (f"cd {normalized_root} && npm test -- --passWithNoTests",) if normalized_root else ()
    return ()


def preflight_report_to_test_summary(report: PreflightReport) -> dict[str, object]:
    summary = dict(report.test_summary)
    summary.setdefault("mode", report.gate_mode)
    readiness = preflight_readiness_assessment(report)
    summary["preflight_status"] = report.status
    summary["preflight_failure_class"] = report.failure_class
    summary["preflight_summary"] = report.summary
    summary["preflight_output_tail"] = report.output_tail
    summary["preflight_readiness_score"] = readiness["score"]
    summary["preflight_readiness_class"] = readiness["class"]
    summary["preflight_recommendation"] = readiness["recommendation"]
    summary["execution_root"] = report.execution_root
    summary["language_effective"] = report.language
    return summary


def preflight_readiness_assessment(report: PreflightReport) -> dict[str, object]:
    status = str(report.status or "").strip().lower()
    failure_class = str(report.failure_class or "").strip().lower()
    blockers: list[str] = []
    if failure_class:
        blockers.append(failure_class)
    elif status == "missing":
        blockers.append("not_checked")

    if status == "ready":
        return {
            "score": 100,
            "class": "ready",
            "blocking": False,
            "recommendation": "ready_for_issue_execution",
            "blockers": blockers,
        }
    if status == "missing":
        return {
            "score": 35,
            "class": "unknown",
            "blocking": False,
            "recommendation": "run_preflight_refresh",
            "blockers": blockers,
        }
    if failure_class in {"tool_missing", "docker_unavailable", "unsupported_gate_mode"}:
        recommendation = "repair_environment"
    elif failure_class == "sandbox_missing":
        recommendation = "restore_sandbox_path"
    else:
        recommendation = "inspect_preflight_failure"
    return {
        "score": 0,
        "class": "blocked",
        "blocking": True,
        "recommendation": recommendation,
        "blockers": blockers or ["preflight_failed"],
    }


def summarize_preflight_readiness(reports: list[PreflightReport]) -> dict[str, object]:
    if not reports:
        return {
            "total": 0,
            "ready": 0,
            "blocked": 0,
            "unknown": 0,
            "overall_score": 0,
            "overall_class": "unknown",
            "blocking_execution_roots": [],
        }
    assessments = [(report, preflight_readiness_assessment(report)) for report in reports]
    ready = sum(1 for _report, assessment in assessments if assessment["class"] == "ready")
    blocked = sum(1 for _report, assessment in assessments if bool(assessment["blocking"]))
    unknown = sum(1 for _report, assessment in assessments if assessment["class"] == "unknown")
    average_score = int(
        round(
            sum(int(assessment["score"]) for _report, assessment in assessments)
            / max(1, len(assessments))
        )
    )
    if blocked > 0:
        overall_class = "blocked"
    elif unknown > 0:
        overall_class = "degraded"
    else:
        overall_class = "ready"
    blocking_execution_roots = [
        report.execution_root
        for report, assessment in assessments
        if bool(assessment["blocking"])
    ][:12]
    return {
        "total": len(assessments),
        "ready": ready,
        "blocked": blocked,
        "unknown": unknown,
        "overall_score": average_score,
        "overall_class": overall_class,
        "blocking_execution_roots": blocking_execution_roots,
    }


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


def _probe_node_toolchain(sandbox_path: Path) -> dict[str, object]:
    required_tool = ""
    package_json = sandbox_path / "package.json"
    if (sandbox_path / "pnpm-lock.yaml").exists():
        required_tool = "pnpm"
    elif (sandbox_path / "yarn.lock").exists():
        required_tool = "yarn"
    elif (sandbox_path / "bun.lockb").exists() or (sandbox_path / "bun.lock").exists():
        required_tool = "bun"
    elif package_json.exists():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            manager = str(data.get("packageManager") or "").strip().lower()
            if manager.startswith("pnpm@"):
                required_tool = "pnpm"
            elif manager.startswith("yarn@"):
                required_tool = "yarn"
            elif manager.startswith("bun@"):
                required_tool = "bun"
        except Exception:
            pass
    return {
        "required_tool": required_tool,
        "tool_available": bool(shutil.which(required_tool)) if required_tool else True,
    }


def _probe_monorepo_layout(sandbox_path: Path) -> dict[str, object]:
    markers = ("pnpm-workspace.yaml", "nx.json", "turbo.json")
    package_json = sandbox_path / "package.json"
    workspace_markers = [name for name in markers if (sandbox_path / name).exists()]
    if package_json.exists():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            if isinstance(data.get("workspaces"), list):
                workspace_markers.append("package.json#workspaces")
        except Exception:
            pass
    return {
        "invalid": False,
        "reason": "",
        "workspace_markers": sorted(set(workspace_markers)),
    }
