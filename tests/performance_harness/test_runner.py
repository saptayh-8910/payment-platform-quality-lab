"""Safety and failure-path tests for the local performance runner."""

import json
import socket
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from payment_quality_lab.performance import runner
from payment_quality_lab.performance.verifier import VerificationReport

RUN_ID = "20260823120000"


@pytest.mark.parametrize(
    "run_id",
    ["short", "UPPERCASE123", "../../escape", "contains-dash", "a" * 25],
)
def test_unsafe_run_id_is_rejected(run_id: str) -> None:
    with pytest.raises(ValueError, match="run ID"):
        runner.validate_run_id(run_id)


def test_available_port_is_loopback_bindable() -> None:
    assert 0 < runner.find_available_port() < 65_536


def test_require_k6_rejects_missing_or_wrong_version(monkeypatch) -> None:
    monkeypatch.setattr(runner.shutil, "which", lambda _binary: None)
    with pytest.raises(RuntimeError, match="not found"):
        runner.require_k6("k6")

    monkeypatch.setattr(runner.shutil, "which", lambda _binary: "/bin/k6")
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 0, stdout="k6 v1.8.0", stderr=""
        ),
    )
    with pytest.raises(RuntimeError, match=r"v2\.0\.0"):
        runner.require_k6("k6")


def write_evidence(path: Path, run_id: str = RUN_ID, profile: str = "smoke") -> None:
    path.write_text(
        json.dumps({"run_id": run_id, "profile": profile, "passed": True}),
        encoding="utf-8",
    )


def test_evidence_requires_two_matching_safe_documents(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    verifier = tmp_path / "verifier.json"
    write_evidence(summary)
    write_evidence(verifier)

    assert runner.validate_evidence(summary, verifier, run_id=RUN_ID, profile="smoke")

    write_evidence(verifier, profile="mixed")
    assert not runner.validate_evidence(
        summary, verifier, run_id=RUN_ID, profile="smoke"
    )

    verifier.write_text("not JSON", encoding="utf-8")
    assert not runner.validate_evidence(
        summary, verifier, run_id=RUN_ID, profile="smoke"
    )


@pytest.mark.parametrize(
    "sensitive_value",
    [
        "sqlite:///private.db",
        "perf-20260824000000-smoke-load-0-key",
        str(Path.home()),
        socket.gethostname(),
        tempfile.gettempdir(),
    ],
)
def test_evidence_rejects_sensitive_fields(
    tmp_path: Path, sensitive_value: str
) -> None:
    summary = tmp_path / "summary.json"
    verifier = tmp_path / "verifier.json"
    write_evidence(summary)
    verifier.write_text(
        json.dumps(
            {
                "run_id": RUN_ID,
                "profile": "smoke",
                "unsafe_value": sensitive_value,
            }
        ),
        encoding="utf-8",
    )

    assert not runner.validate_evidence(
        summary, verifier, run_id=RUN_ID, profile="smoke"
    )


def test_threshold_failure_still_runs_verifier_and_cleanup(
    tmp_path: Path, monkeypatch
) -> None:
    fake_server = Mock()
    fake_server.poll.return_value = None
    report = VerificationReport(1, RUN_ID, "smoke", True, (), {})
    run_calls = 0

    def fake_run(_args, **kwargs):
        nonlocal run_calls
        run_calls += 1
        if run_calls == 1:
            return subprocess.CompletedProcess([], 0, stdout="k6 v2.0.0", stderr="")
        write_evidence(Path(kwargs["cwd"]) / "k6-summary.json")
        return subprocess.CompletedProcess([], 99)

    monkeypatch.setattr(runner.shutil, "which", lambda _binary: "/bin/k6")
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(
        runner.subprocess,
        "Popen",
        lambda *_args, **_kwargs: fake_server,
    )
    monkeypatch.setattr(runner, "wait_for_health", lambda _base_url: None)
    monkeypatch.setattr(runner, "find_available_port", lambda: 8123)
    verifier = Mock(return_value=report)
    monkeypatch.setattr(runner, "verify_database", verifier)

    result = runner.run_profile(
        "smoke",
        run_id=RUN_ID,
        reports_root=tmp_path / "reports",
        force_threshold_failure=True,
    )

    assert not result.passed
    assert result.k6_exit_code == 99
    assert result.verifier_passed
    assert result.evidence_passed
    verifier.assert_called_once()
    fake_server.terminate.assert_called_once()
    fake_server.wait.assert_called_once_with(timeout=5)


def test_health_failure_prevents_load_and_still_cleans_up(
    tmp_path: Path, monkeypatch
) -> None:
    fake_server = Mock()
    fake_server.poll.return_value = None
    monkeypatch.setattr(runner.shutil, "which", lambda _binary: "/bin/k6")
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 0, stdout="k6 v2.0.0", stderr=""
        ),
    )
    monkeypatch.setattr(
        runner.subprocess,
        "Popen",
        lambda *_args, **_kwargs: fake_server,
    )
    monkeypatch.setattr(
        runner,
        "wait_for_health",
        lambda _base_url: (_ for _ in ()).throw(RuntimeError("not healthy")),
    )

    with pytest.raises(RuntimeError, match="not healthy"):
        runner.run_profile("smoke", run_id=RUN_ID, reports_root=tmp_path / "reports")

    fake_server.terminate.assert_called_once()


def test_stop_process_kills_child_that_does_not_terminate() -> None:
    process = Mock()
    process.poll.return_value = None
    process.wait.side_effect = [subprocess.TimeoutExpired("server", 5), 0]

    runner.stop_process(process)

    process.terminate.assert_called_once()
    process.kill.assert_called_once()
