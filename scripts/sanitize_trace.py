"""Remove test controls from a Playwright trace before CI publication."""

import os
import re
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

REPLACEMENTS = {
    b"tok_approved": b"synthetic_ok",
    b"tok_declined": b"synthetic_no",
    b"after_commit": b"test_control",
    b"before_commit": b"test_control_",
}
DETAILED_DECLINE_TOKEN = re.compile(rb"tok_declined(?:_[a-z_]+)?")


def sanitize_trace(trace_path: Path) -> None:
    """Replace synthetic token and failure-control values in every zip member."""
    temporary_path = trace_path.with_suffix(".sanitized.zip")
    with (
        ZipFile(trace_path, "r") as source,
        ZipFile(
            temporary_path,
            "w",
            compression=ZIP_DEFLATED,
        ) as destination,
    ):
        for member in source.infolist():
            data = source.read(member.filename)
            data = DETAILED_DECLINE_TOKEN.sub(b"synthetic_no", data)
            for unsafe, safe in REPLACEMENTS.items():
                data = data.replace(unsafe, safe)
            destination.writestr(member, data)
    os.replace(temporary_path, trace_path)


if __name__ == "__main__":
    sanitize_trace(Path(sys.argv[1]))
