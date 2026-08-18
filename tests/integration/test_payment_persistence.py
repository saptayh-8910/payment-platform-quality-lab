"""Integration tests for transactions and persisted financial effects."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from payment_quality_lab.domain.payment import AuthorizationDecision, Currency
from payment_quality_lab.persistence.database import (
    Base,
    create_database_engine,
    create_session_factory,
)
from payment_quality_lab.persistence.models import (
    IdempotencyRecord,
    LedgerEntryRecord,
    PaymentRecord,
)
from payment_quality_lab.services.payments import (
    AuthorizationCommand,
    PaymentNotFoundError,
    authorize_payment,
    get_ledger_entries,
    get_payment,
)


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_database_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as database_session:
        yield database_session


def command(
    decision: AuthorizationDecision = AuthorizationDecision.APPROVE,
) -> AuthorizationCommand:
    return AuthorizationCommand(
        merchant_reference="integration-order",
        amount=1000,
        currency=Currency.USD,
        payment_method_token=decision,
    )


def count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_authorization_commits_payment_ledger_and_idempotency_atomically(
    session: Session,
) -> None:
    outcome = authorize_payment(
        session,
        command=command(),
        idempotency_key="integration-key-1",
    )

    assert outcome.replayed is False
    assert count(session, PaymentRecord) == 1
    assert count(session, LedgerEntryRecord) == 1
    assert count(session, IdempotencyRecord) == 1
    ledger = get_ledger_entries(session, outcome.payment.id)
    assert ledger[0].amount == outcome.payment.authorized_amount == 1000


def test_decline_commits_no_ledger_entry(session: Session) -> None:
    outcome = authorize_payment(
        session,
        command=command(AuthorizationDecision.DECLINE),
        idempotency_key="integration-key-2",
    )

    assert outcome.payment.status == "DECLINED"
    assert count(session, PaymentRecord) == 1
    assert count(session, LedgerEntryRecord) == 0
    assert count(session, IdempotencyRecord) == 1


def test_foreign_key_prevents_orphan_idempotency_record(session: Session) -> None:
    session.add(
        IdempotencyRecord(
            key="orphan-key",
            request_fingerprint="a" * 64,
            operation="AUTHORIZE",
            payment_id="pay_missing",
            created_at=datetime.now(UTC),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_missing_payment_raises_domain_facing_error(session: Session) -> None:
    with pytest.raises(PaymentNotFoundError, match="pay_unknown"):
        get_payment(session, "pay_unknown")
