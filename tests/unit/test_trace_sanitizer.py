"""Checks for safe-to-publish browser failure artifacts."""

import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile


def test_trace_sanitizer_removes_test_controls(tmp_path: Path) -> None:
    trace_path = tmp_path / "failure.zip"
    with ZipFile(trace_path, "w") as trace:
        trace.writestr(
            "trace.network",
            (
                b"tok_approved tok_declined "
                b"tok_declined_insufficient_funds "
                b"tok_declined_verification after_commit before_commit"
            ),
        )

    subprocess.run(
        [sys.executable, "scripts/sanitize_trace.py", str(trace_path)],
        check=True,
    )

    with ZipFile(trace_path) as trace:
        content = trace.read("trace.network")
    assert b"tok_approved" not in content
    assert b"tok_declined" not in content
    assert b"insufficient_funds" not in content
    assert b"verification" not in content
    assert b"after_commit" not in content
    assert b"before_commit" not in content
    assert b"synthetic_ok" in content
    assert b"synthetic_no" in content
    assert b"test_control" in content
