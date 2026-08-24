"""Contract tests for reviewed performance workload metadata."""

import pytest

from payment_quality_lab.performance.profiles import (
    available_profiles,
    expected_payments,
    idempotency_key,
    reference,
)


@pytest.mark.parametrize(
    ("profile", "payments", "approved"),
    [
        ("smoke", 5, 4),
        ("authorization", 155, 155),
        ("retrieval", 20, 20),
        ("idempotent-burst", 1, 1),
        ("mixed", 140, 140),
    ],
)
def test_expected_effects_match_catalog(
    profile: str, payments: int, approved: int
) -> None:
    expected = expected_payments(profile)

    assert len(expected) == payments
    assert sum(item.approved for item in expected) == approved


def test_profile_names_are_stable() -> None:
    assert available_profiles() == (
        "smoke",
        "authorization",
        "retrieval",
        "idempotent-burst",
        "mixed",
    )


def test_synthetic_identifiers_are_bounded_and_unique() -> None:
    all_references = set()
    all_keys = set()
    for profile in available_profiles():
        for payment in expected_payments(profile):
            payment_reference = reference("20260823120000", profile, payment)
            key = idempotency_key("20260823120000", profile, payment)
            assert len(payment_reference) <= 64
            assert len(key) <= 128
            all_references.add(payment_reference)
            all_keys.add(key)

    assert len(all_references) == 321
    assert len(all_keys) == 321


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown performance profile"):
        expected_payments("stress")
