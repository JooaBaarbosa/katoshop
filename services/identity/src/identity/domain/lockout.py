from dataclasses import dataclass, replace
from datetime import datetime, timedelta

MAX_FAILURES = 5
LOCK_DURATION = timedelta(minutes=15)


@dataclass(frozen=True)
class LoginState:
    failed_logins: int
    locked_until: datetime | None


def is_locked(state: LoginState, now: datetime) -> bool:
    return state.locked_until is not None and now < state.locked_until


def register_failure(state: LoginState, now: datetime) -> LoginState:
    failures = state.failed_logins + 1
    if failures >= MAX_FAILURES:
        return LoginState(failed_logins=0, locked_until=now + LOCK_DURATION)
    return replace(state, failed_logins=failures)


def register_success(state: LoginState) -> LoginState:  # noqa: ARG001
    return LoginState(failed_logins=0, locked_until=None)
