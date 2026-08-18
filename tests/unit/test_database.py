"""Unit tests for request-scoped transaction cleanup."""

from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from payment_quality_lab.persistence.database import session_scope


def test_session_scope_rolls_back_and_closes_after_error() -> None:
    session = Mock(spec=Session)
    factory = Mock(return_value=session)
    scope = session_scope(factory)

    assert next(scope) is session
    with pytest.raises(RuntimeError, match="database operation failed"):
        scope.throw(RuntimeError("database operation failed"))

    session.rollback.assert_called_once_with()
    session.close.assert_called_once_with()
