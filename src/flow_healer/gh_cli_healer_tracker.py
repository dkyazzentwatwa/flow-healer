from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .healer_tracker import GitHubHealerTracker

logger = logging.getLogger("apple_flow.gh_cli_healer_tracker")

_DEFAULT_GH_API_TIMEOUT_SECONDS = 15


class GhCliHealerTracker(GitHubHealerTracker):
    """GitHub tracker transport that routes API calls through `gh api`."""

    def __init__(
        self,
        *,
        repo_path: Path,
        gh_command: str = "gh",
        request_timeout_seconds: int = _DEFAULT_GH_API_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(
            repo_path=repo_path,
            token="gh_cli_auth",
            request_timeout_seconds=request_timeout_seconds,
        )
        self.gh_command = str(gh_command or "gh").strip() or "gh"
        self.request_timeout_seconds = max(1, int(request_timeout_seconds))

    @property
    def enabled(self) -> bool:
        return bool(self.repo_slug and shutil.which(self.gh_command))

    def _request_json(self, path: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
        self._last_error_class = ""
        self._last_error_reason = ""
        method_upper = method.strip().upper() or "GET"
        started_at = time.monotonic()
        max_attempts = 3 if method_upper in {"POST", "PUT", "PATCH", "DELETE"} else 4

        for attempt in range(max_attempts):
            if method_upper in {"POST", "PUT", "PATCH", "DELETE"}:
                self._enforce_mutation_spacing()
            cmd = self._build_gh_api_command(path=path, method=method_upper, body=body)
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.request_timeout_seconds,
                input=self._gh_api_stdin(path=path, body=body),
            )
            stdout = str(proc.stdout or "")
            stderr = str(proc.stderr or "")
            status_code = self._extract_status_code(stderr=stderr)
            if proc.returncode == 0:
                payload = self._parse_success_payload(stdout=stdout)
                self._record_request_metric(
                    method=method_upper,
                    path=path,
                    status=str(status_code or 200),
                    started_at=started_at,
                )
                return payload

            reason = self._gh_error_reason(stderr=stderr, stdout=stdout, returncode=proc.returncode)
            if self._is_missing_label_delete_noop(
                method=method_upper,
                path=path,
                status_code=status_code,
                reason=reason,
            ):
                self._record_request_metric(
                    method=method_upper,
                    path=path,
                    status=str(status_code),
                    started_at=started_at,
                )
                return []
            if self._is_expected_artifact_publish_miss(
                method=method_upper,
                path=path,
                status_code=status_code,
            ):
                self._last_error_class = "github_api_error"
                self._last_error_reason = reason[:500]
                self._record_request_metric(
                    method=method_upper,
                    path=path,
                    status=str(status_code),
                    started_at=started_at,
                )
                return {}

            self._last_error_class = self._gh_error_class(status_code=status_code, reason=reason)
            self._last_error_reason = reason[:500]
            retryable = status_code in {403, 429, 500, 502, 503, 504}
            if retryable and attempt < (max_attempts - 1):
                self._record_request_metric(
                    method=method_upper,
                    path=path,
                    status=str(status_code or "gh_error"),
                    started_at=started_at,
                )
                delay = self._retry_delay_seconds(attempt=attempt, headers={})
                logger.warning(
                    "gh api %s %s failed (status=%s). Retrying in %.2fs (%d/%d).",
                    method_upper,
                    path,
                    status_code or "unknown",
                    delay,
                    attempt + 1,
                    max_attempts,
                )
                time.sleep(delay)
                started_at = time.monotonic()
                continue

            self._record_request_metric(
                method=method_upper,
                path=path,
                status=str(status_code or "gh_error"),
                started_at=started_at,
            )
            logger.warning("gh api %s %s failed: %s", method_upper, path, reason)
            return {}
        return {}

    def _build_gh_api_command(self, *, path: str, method: str, body: dict[str, Any] | None) -> list[str]:
        normalized_path = str(path or "").lstrip("/")
        if normalized_path == "graphql":
            cmd = [self.gh_command, "api", "graphql"]
            query = str((body or {}).get("query") or "")
            cmd.extend(["-f", f"query={query}"])
            variables = dict((body or {}).get("variables") or {})
            for key, value in variables.items():
                cmd.extend(["-F", f"{key}={self._render_graphql_variable(value)}"])
            return cmd

        cmd = [self.gh_command, "api", normalized_path]
        if method != "GET":
            cmd.extend(["--method", method])
        if body is not None:
            cmd.extend(["--input", "-"])
        return cmd

    @staticmethod
    def _gh_api_stdin(*, path: str, body: dict[str, Any] | None) -> str | None:
        if body is None or str(path or "").lstrip("/") == "graphql":
            return None
        return json.dumps(body)

    @staticmethod
    def _render_graphql_variable(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float, str)):
            return str(value)
        return json.dumps(value, sort_keys=True)

    @staticmethod
    def _parse_success_payload(*, stdout: str) -> Any:
        text = str(stdout or "").strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _extract_status_code(*, stderr: str) -> int:
        match = re.search(r"HTTP\s+(\d{3})", str(stderr or ""))
        if match is None:
            return 0
        try:
            return int(match.group(1))
        except ValueError:
            return 0

    @staticmethod
    def _gh_error_reason(*, stderr: str, stdout: str, returncode: int) -> str:
        stderr_text = str(stderr or "").strip()
        stdout_text = str(stdout or "").strip()
        if stderr_text and stdout_text:
            return f"{stderr_text} body={stdout_text[:280]}"
        if stderr_text:
            return stderr_text
        if stdout_text:
            return stdout_text[:280]
        return f"gh api exited with status {returncode}"

    @staticmethod
    def _gh_error_class(*, status_code: int, reason: str) -> str:
        lowered = str(reason or "").lower()
        if status_code in {401, 403} and ("login" in lowered or "token" in lowered or "auth" in lowered):
            return "github_auth_missing"
        if status_code == 429 or "rate limit" in lowered:
            return "github_rate_limited"
        if status_code:
            return "github_api_error"
        return "github_network_error"
