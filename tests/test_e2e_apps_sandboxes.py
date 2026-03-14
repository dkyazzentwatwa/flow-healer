from __future__ import annotations

import http.client
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
E2E_APPS = ROOT / "e2e-apps"


def test_all_demo_app_sandboxes_exist() -> None:
    expected = {
        "node-next": [
            "package.json",
            "app/layout.js",
            "app/page.js",
            "app/api/todos/route.js",
            "lib/todo-service.js",
            "tests/todo-service.test.js",
        ],
        "python-fastapi": [
            "pyproject.toml",
            "app/api.py",
            "app/service.py",
            "app/repository.py",
            "tests/test_domain_service.py",
            "tests/test_api_contract.py",
        ],
        "prosper-chat": [
            "package.json",
            "src/main.tsx",
            "src/App.tsx",
            "supabase/config.toml",
            "supabase/assertions/manifest.json",
            "supabase/assertions/schema_core.sql",
            "supabase/functions/chat-widget/index.ts",
            "supabase/migrations/20260301190615_15638062-0f7f-4cc7-96f5-79466e4cb26b.sql",
            "scripts/healer_validate.sh",
        ],
        "ruby-rails-web": [
            "Gemfile",
            "server.rb",
            "config/routes.rb",
            "app/controllers/health_controller.rb",
            "app/controllers/sessions_controller.rb",
            "app/controllers/dashboard_controller.rb",
            "scripts/fixture_driver.rb",
            "spec/requests/health_spec.rb",
        ],
        "java-spring-web": [
            "build.gradle",
            "gradlew",
            "settings.gradle",
            "src/main/resources/application.properties",
            "src/main/java/example/Application.java",
            "src/main/java/example/web/HealthController.java",
            "src/main/java/example/web/LoginController.java",
            "src/main/java/example/web/DashboardController.java",
            "src/main/java/example/web/ResponsePlan.java",
            "scripts/fixture_driver.py",
            "src/test/java/example/web/HealthControllerTest.java",
        ],
    }

    for sandbox, required_files in expected.items():
        base = E2E_APPS / sandbox
        assert base.is_dir(), f"missing demo app sandbox: {sandbox}"
        for relative in required_files:
            assert (base / relative).exists(), f"{sandbox} missing {relative}"


def _request_reference_app(
    *,
    port: int,
    method: str,
    path: str,
    body: str = "",
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], str]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    payload = body.encode("utf-8") if body else None
    connection.request(method, path, body=payload, headers=headers or {})
    response = connection.getresponse()
    response_body = response.read().decode("utf-8")
    response_headers = {
        "-".join(part.capitalize() for part in key.split("-")): value
        for key, value in response.getheaders()
    }
    connection.close()
    return response.status, response_headers, response_body


def _format_reference_app_timeout(
    *,
    port: int,
    timeout_seconds: float,
    app_name: str,
    process: subprocess.Popen[str] | None,
) -> str:
    message = f"{app_name} on port {port} did not become ready within {timeout_seconds:.1f}s"
    if process is None:
        return message

    return_code = process.poll()
    if return_code is None:
        return message

    output = ""
    if process.stdout is not None:
        output = process.stdout.read().strip()
    if output:
        return f"{message}; process exited with code {return_code}; output:\n{output}"
    return f"{message}; process exited with code {return_code}"


def _wait_for_reference_app(
    port: int,
    *,
    timeout_seconds: float = 5.0,
    process: subprocess.Popen[str] | None = None,
    app_name: str = "reference app",
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            status, _headers, _body = _request_reference_app(port=port, method="GET", path="/healthz")
        except OSError:
            if process is not None and process.poll() is not None:
                break
            time.sleep(0.1)
            continue
        if status == 200:
            return
        time.sleep(0.1)
    raise AssertionError(
        _format_reference_app_timeout(
            port=port,
            timeout_seconds=timeout_seconds,
            app_name=app_name,
            process=process,
        )
    )


def test_wait_for_reference_app_reports_process_output_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeProcess:
        def __init__(self) -> None:
            self.stdout = io.StringIO("Boot failed: missing dependency\n")

        def poll(self) -> int | None:
            return 1

    monotonic_values = iter([0.0, 0.05, 0.2])

    monkeypatch.setattr(time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        f"{__name__}._request_reference_app",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("connection refused")),
    )

    with pytest.raises(AssertionError, match="Boot failed: missing dependency") as excinfo:
        _wait_for_reference_app(43210, timeout_seconds=0.1, process=_FakeProcess(), app_name="ruby reference app")

    assert "ruby reference app" in str(excinfo.value)


def _reserve_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_ruby_reference_app_serves_health_and_cookie_session() -> None:
    app_root = E2E_APPS / "ruby-rails-web"
    env = os.environ.copy()
    env["HOST"] = "127.0.0.1"
    port = _reserve_local_port()
    env["PORT"] = str(port)
    process = subprocess.Popen(
        ["ruby", "server.rb"],
        cwd=app_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_reference_app(
            port,
            timeout_seconds=10.0,
            process=process,
            app_name="ruby reference app",
        )

        status, _headers, body = _request_reference_app(port=port, method="GET", path="/healthz")
        assert status == 200
        assert json.loads(body)["status"] == "ok"

        status, headers, _body = _request_reference_app(port=port, method="GET", path="/dashboard")
        assert status == 302
        assert headers["Location"].endswith("/login")

        login_body = "email=seeded-admin%40example.com&password=demo-password"
        status, headers, _body = _request_reference_app(
            port=port,
            method="POST",
            path="/login",
            body=login_body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert status == 302
        assert headers["Location"].endswith("/dashboard")
        assert "healer_session=" in headers["Set-Cookie"]

        status, _headers, body = _request_reference_app(
            port=port,
            method="GET",
            path="/dashboard",
            headers={"Cookie": headers["Set-Cookie"]},
        )
        assert status == 200
        assert "seeded-admin@example.com" in body
        assert "Seeded alerts are ready." in body
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)


def test_java_reference_app_serves_health_and_cookie_session() -> None:
    app_root = E2E_APPS / "java-spring-web"
    env = os.environ.copy()
    env["HOST"] = "127.0.0.1"
    port = _reserve_local_port()
    env["PORT"] = str(port)
    java_bin = Path("/opt/homebrew/opt/openjdk/bin")
    if java_bin.is_dir():
        env["PATH"] = f"{java_bin}:{env.get('PATH', '')}"
        env["JAVA_HOME"] = "/opt/homebrew/opt/openjdk"
    process = subprocess.Popen(
        ["./gradlew", "bootRun"],
        cwd=app_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_reference_app(
            port,
            timeout_seconds=10.0,
            process=process,
            app_name="java reference app",
        )

        status, _headers, body = _request_reference_app(port=port, method="GET", path="/healthz")
        assert status == 200
        assert json.loads(body)["status"] == "ok"

        status, headers, _body = _request_reference_app(port=port, method="GET", path="/dashboard")
        assert status == 302
        assert headers["Location"].endswith("/login")

        login_body = "email=seeded-admin%40example.com"
        status, headers, _body = _request_reference_app(
            port=port,
            method="POST",
            path="/login",
            body=login_body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert status == 302
        assert headers["Location"].endswith("/dashboard")
        assert "healer_session=seeded-admin@example.com" in headers["Set-Cookie"]

        status, _headers, body = _request_reference_app(
            port=port,
            method="GET",
            path="/dashboard",
            headers={"Cookie": headers["Set-Cookie"]},
        )
        assert status == 200
        assert "seeded-admin@example.com" in body
        assert "Seeded alerts are ready." in body
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)


@pytest.mark.parametrize(
    ("command", "script_path", "default_origin"),
    [
        (["ruby"], E2E_APPS / "ruby-rails-web" / "scripts" / "fixture_driver.rb", "http://127.0.0.1:3101"),
        ([sys.executable], E2E_APPS / "java-spring-web" / "scripts" / "fixture_driver.py", "http://127.0.0.1:3201"),
    ],
)
def test_reference_app_fixture_drivers_normalize_entry_url_to_origin(
    tmp_path: Path,
    command: list[str],
    script_path: Path,
    default_origin: str,
) -> None:
    output_path = tmp_path / "storage-state.json"
    subprocess.run(
        [*command, str(script_path), "auth-state", "seeded-admin", str(output_path), default_origin + "/login?via=test"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    state = json.loads(output_path.read_text(encoding="utf-8"))
    assert state["origins"][0]["origin"] == default_origin
