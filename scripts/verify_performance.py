#!/usr/bin/env python3
"""Create financial evidence for an existing performance database."""

import argparse
from pathlib import Path

from payment_quality_lab.performance.profiles import available_profiles
from payment_quality_lab.performance.runner import validate_run_id
from payment_quality_lab.performance.verifier import verify_database, write_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database_url")
    parser.add_argument("run_id", type=validate_run_id)
    parser.add_argument("profile", choices=available_profiles())
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    report = verify_database(
        arguments.database_url,
        arguments.run_id,
        arguments.profile,
    )
    write_report(report, arguments.output)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
