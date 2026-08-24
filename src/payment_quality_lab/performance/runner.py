"""Safe local orchestration for k6 and the financial verifier."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from payment_quality_lab.performance.profiles import available_profiles
from payment_quality_lab.performance.verifier import verify_database, write_report

PINNED_K6_VERSION = "v2.0.0"
RUN_ID_PATTERN = re.compile(r"^[a-z0-9]{8,24}$")
FORBIDDEN_EVIDENCE = (
    "Idempotency-Key",
    "payment_method_token",
    "tok_approved",
    "tok_declined",
    "-key",
    "whsec_",
    "sqlite:///",
    "PAYMENT_LAB_DATABASE_URL",
    "X-Payment-Lab-Failure",
)


@dataclass(frozen=True)
class RunResult:
    """Overall harness decision and retained evidence location."""

    passed: bool
    profile: str
    run_id: str
    evidence_directory: Path
    k6_exit_code: int
    verifier_passed: bool
    evidence_passed: bool


def validate_run_id(run_id: str) -> str:
    """Reject values that could expose paths or create unsafe filenames."""
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run ID must contain 8-24 lowercase letters or digits")
    return run_id


def find_available_port() -> int:
    """Ask the operating system for one loopback port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def require_k6(binary: str) -> str:
    """Require the reviewed k6 release for comparable behavior."""
    resolved = shutil.which(binary)
    if resolved is None:
        raise RuntimeError(
            "k6 was not found. Install the pinned v2.0.0 release before running."
        )
    result = subprocess.run(
        [resolved, "version"],
        check=False,
        capture_output=True,
        text=True,
    )
    version_output = f"{result.stdout}\n{result.stderr}"
    expected_version = rf"\bk6 {re.escape(PINNED_K6_VERSION)}(?:\s|\()"
    if result.returncode != 0 or re.search(expected_version, version_output) is None:
        raise RuntimeError(f"performance runs require k6 {PINNED_K6_VERSION}")
    return resolved


def wait_for_health(base_url: str, timeout_seconds: float = 15.0) -> None:
    """Wait for the isolated server without sending load prematurely."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{base_url}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            time.sleep(0.1)
    raise RuntimeError("isolated application did not become healthy")


def stop_process(process: subprocess.Popen[bytes]) -> None:
    """Stop the child application, escalating only after a bounded wait."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def validate_evidence(
    summary_path: Path,
    verifier_path: Path,
    *,
    run_id: str,
    profile: str,
) -> bool:
    """Reject missing, mismatched, malformed, or unsafe retained reports."""
    try:
        documents = [
            json.loads(summary_path.read_text(encoding="utf-8")),
            json.loads(verifier_path.read_text(encoding="utf-8")),
        ]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    if any(
        document.get("run_id") != run_id or document.get("profile") != profile
        for document in documents
    ):
        return False
    retained_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (summary_path, verifier_path)
    )
    forbidden_values = (
        *FORBIDDEN_EVIDENCE,
        str(Path.home()),
        socket.gethostname(),
        tempfile.gettempdir(),
    )
    return not any(forbidden in retained_text for forbidden in forbidden_values)


def run_profile(
    profile: str,
    *,
    run_id: str,
    k6_binary: str = "k6",
    reports_root: Path = Path("reports/performance"),
    force_threshold_failure: bool = False,
) -> RunResult:
    """Run one isolated profile and preserve both forms of evidence."""
    if profile not in available_profiles():
        raise ValueError(f"Unknown performance profile: {profile}")
    validate_run_id(run_id)
    resolved_k6 = require_k6(k6_binary)
    repository_root = Path(__file__).resolve().parents[3]
    script_path = repository_root / "tests" / "performance" / "payment_api.js"
    evidence_directory = (reports_root / run_id / profile).resolve()
    evidence_directory.mkdir(parents=True, exist_ok=False)
    summary_path = evidence_directory / "k6-summary.json"
    verifier_path = evidence_directory / "financial-verification.json"

    k6_exit_code = 1
    verifier_passed = False
    evidence_passed = False
    server: subprocess.Popen[bytes] | None = None
    with tempfile.TemporaryDirectory(prefix="payment-lab-performance-") as temporary:
        database_path = Path(temporary) / "performance.db"
        database_url = f"sqlite:///{database_path}"
        port = find_available_port()
        base_url = f"http://127.0.0.1:{port}"
        server_environment = os.environ.copy()
        server_environment["PAYMENT_LAB_DATABASE_URL"] = database_url
        try:
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "payment_quality_lab.main:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--log-level",
                    "warning",
                ],
                cwd=repository_root,
                env=server_environment,
            )
            wait_for_health(base_url)
            k6_environment = os.environ.copy()
            k6_environment.update(
                {
                    "BASE_URL": base_url,
                    "PROFILE": profile,
                    "RUN_ID": run_id,
                    "SUMMARY_PATH": summary_path.name,
                    "FORCE_THRESHOLD_FAILURE": (
                        "true" if force_threshold_failure else "false"
                    ),
                }
            )
            k6_result = subprocess.run(
                [resolved_k6, "run", "--quiet", "--no-color", str(script_path)],
                cwd=evidence_directory,
                env=k6_environment,
                check=False,
            )
            k6_exit_code = k6_result.returncode

            report = verify_database(database_url, run_id, profile)
            write_report(report, verifier_path)
            verifier_passed = report.passed
            evidence_passed = validate_evidence(
                summary_path,
                verifier_path,
                run_id=run_id,
                profile=profile,
            )
        finally:
            if server is not None:
                stop_process(server)

    return RunResult(
        passed=k6_exit_code == 0 and verifier_passed and evidence_passed,
        profile=profile,
        run_id=run_id,
        evidence_directory=evidence_directory,
        k6_exit_code=k6_exit_code,
        verifier_passed=verifier_passed,
        evidence_passed=evidence_passed,
    )


def _default_run_id() -> str:
    return time.strftime("%Y%m%d%H%M%S", time.gmtime())


def main() -> int:
    """Parse the local runner command and return a release-gate exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=available_profiles())
    parser.add_argument("--run-id", default=_default_run_id())
    parser.add_argument("--k6-binary", default="k6")
    parser.add_argument(
        "--force-threshold-failure",
        action="store_true",
        help="Harness test only: prove a failed threshold blocks the run.",
    )
    arguments = parser.parse_args()
    result = run_profile(
        arguments.profile,
        run_id=arguments.run_id,
        k6_binary=arguments.k6_binary,
        force_threshold_failure=arguments.force_threshold_failure,
    )
    decision = "PASS" if result.passed else "FAIL"
    print(
        f"Performance gate: {decision}; profile={result.profile}; "
        f"run_id={result.run_id}; k6_exit={result.k6_exit_code}; "
        f"financial_verifier={result.verifier_passed}; "
        f"evidence={result.evidence_passed}"
    )
    print(
        "Evidence: "
        f"reports/performance/{result.run_id}/{result.profile}/ "
        "(local generated artifact)"
    )
    return 0 if result.passed else 1
