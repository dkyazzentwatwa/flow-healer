from pathlib import Path

from flow_healer.healer_runner import (
    _build_docker_test_script,
    _gate_runners_for_mode,
    _normalize_test_gate_mode,
    _run_test_gates,
)


def test_build_docker_test_script_bootstraps_pytest_and_package_install():
    script = _build_docker_test_script(["pytest", "-q", "tests/test_demo_math.py"])

    assert "python -m pip install --disable-pip-version-check -q pytest" in script
    assert "python -m pip install --disable-pip-version-check -q -e ." in script
    assert '"pytest" "-q" "tests/test_demo_math.py"' in script


def test_build_docker_test_script_skips_editable_install_when_no_python_project():
    script = _build_docker_test_script(["pytest", "-q"])

    assert "if [ -f pyproject.toml ] || [ -f setup.py ] || [ -f setup.cfg ]" in script
    assert script.endswith('"pytest" "-q"')


def test_normalize_test_gate_mode_defaults_to_local_then_docker():
    assert _normalize_test_gate_mode("") == "local_then_docker"
    assert _normalize_test_gate_mode("weird") == "local_then_docker"
    assert _normalize_test_gate_mode("local-then-docker") == "local_then_docker"


def test_gate_runners_for_mode_local_then_docker():
    assert [name for name, _ in _gate_runners_for_mode("local_then_docker")] == ["local", "docker"]


def test_run_test_gates_runs_local_then_docker(monkeypatch):
    calls: list[tuple[str, list[str]]] = []

    def fake_local(workspace: Path, command: list[str], timeout_seconds: int):
        calls.append(("local", command))
        return {"exit_code": 0, "output_tail": "local ok"}

    def fake_docker(workspace: Path, command: list[str], timeout_seconds: int):
        calls.append(("docker", command))
        return {"exit_code": 0, "output_tail": "docker ok"}

    monkeypatch.setattr("flow_healer.healer_runner._run_pytest_locally", fake_local)
    monkeypatch.setattr("flow_healer.healer_runner._run_pytest_in_docker", fake_docker)

    summary = _run_test_gates(
        Path("."),
        targeted_tests=["tests/test_demo.py"],
        timeout_seconds=30,
        mode="local_then_docker",
    )

    assert calls == [
        ("local", ["pytest", "-q", "tests/test_demo.py"]),
        ("docker", ["pytest", "-q", "tests/test_demo.py"]),
        ("local", ["pytest", "-q"]),
        ("docker", ["pytest", "-q"]),
    ]
    assert summary["local_targeted_exit_code"] == 0
    assert summary["docker_full_exit_code"] == 0
    assert summary["failed_tests"] == 0
