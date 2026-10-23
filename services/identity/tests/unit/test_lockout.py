from datetime import UTC, datetime, timedelta

from identity.domain.lockout import (
    LOCK_DURATION,
    MAX_FAILURES,
    LoginState,
    is_locked,
    register_failure,
    register_success,
)

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def _fail(times: int) -> LoginState:
    state = LoginState(failed_logins=0, locked_until=None)
    for _ in range(times):
        state = register_failure(state, NOW)
    return state


def test_constants() -> None:
    assert MAX_FAILURES == 5
    assert LOCK_DURATION == timedelta(minutes=15)


def test_four_failures_do_not_lock() -> None:
    state = _fail(4)
    assert state.failed_logins == 4
    assert is_locked(state, NOW) is False


def test_fifth_failure_locks_and_resets_counter() -> None:
    state = _fail(5)
    assert is_locked(state, NOW) is True
    assert state.locked_until == NOW + LOCK_DURATION
    assert state.failed_logins == 0


def test_lock_expires_after_fifteen_minutes() -> None:
    state = _fail(5)
    assert is_locked(state, NOW + timedelta(minutes=15, seconds=1)) is False


def test_success_clears_state() -> None:
    state = register_success(_fail(3))
    assert state == LoginState(failed_logins=0, locked_until=None)
