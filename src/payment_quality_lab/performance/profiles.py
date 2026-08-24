"""Reviewed workload definitions shared by the runner and financial verifier."""

from dataclasses import dataclass

JPY_AMOUNT = 2_500
USD_AMOUNT = 1_099


@dataclass(frozen=True)
class ExpectedPayment:
    """One payment effect expected from a performance profile."""

    phase: str
    index: int
    approved: bool = True

    @property
    def currency(self) -> str:
        return "JPY" if self.index % 2 == 0 else "USD"

    @property
    def amount(self) -> int:
        return JPY_AMOUNT if self.currency == "JPY" else USD_AMOUNT


def available_profiles() -> tuple[str, ...]:
    """Return stable command-line profile names."""
    return ("smoke", "authorization", "retrieval", "idempotent-burst", "mixed")


def expected_payments(profile: str) -> tuple[ExpectedPayment, ...]:
    """Return the exact persistent effects expected after one profile."""
    if profile == "smoke":
        return tuple(
            ExpectedPayment("load", index, approved=index < 4) for index in range(5)
        )
    if profile == "authorization":
        return tuple(ExpectedPayment("warmup", index) for index in range(5)) + tuple(
            ExpectedPayment("load", index) for index in range(150)
        )
    if profile == "retrieval":
        return tuple(ExpectedPayment("setup", index) for index in range(20))
    if profile == "idempotent-burst":
        return (ExpectedPayment("setup", 0),)
    if profile == "mixed":
        return tuple(ExpectedPayment("setup", index) for index in range(20)) + tuple(
            ExpectedPayment("load", index) for index in range(120)
        )
    raise ValueError(f"Unknown performance profile: {profile}")


def reference(run_id: str, profile: str, payment: ExpectedPayment) -> str:
    """Build the non-sensitive merchant reference used by k6."""
    return f"perf-{run_id}-{profile}-{payment.phase}-{payment.index}"


def idempotency_key(run_id: str, profile: str, payment: ExpectedPayment) -> str:
    """Build the synthetic key pattern used by k6 without exposing actual evidence."""
    return f"perf-{run_id}-{profile}-{payment.phase}-{payment.index}-key"

