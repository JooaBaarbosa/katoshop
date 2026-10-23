from collections.abc import Awaitable

from identity.application import auth_service as codes
from identity.application.auth_service import AuthError
from ks_platform.errors import ProblemError

_STATUS = {
    codes.INVALID_CREDENTIALS: (401, "Credenciais inválidas"),
    codes.INVALID_REFRESH: (401, "Sessão inválida ou expirada"),
    codes.REFRESH_REUSED: (401, "Sessão encerrada por segurança"),
    codes.EMAIL_TAKEN: (409, "Email já cadastrado"),
    codes.WEAK_PASSWORD: (422, "Senha fraca"),
    codes.CURRENT_PASSWORD_REQUIRED: (422, "Senha atual obrigatória"),
}


def to_problem(error: AuthError, password_field: str = "body.password") -> ProblemError:  # noqa: S107
    status, title = _STATUS[error.code]
    errors = {password_field: error.violations} if error.code == codes.WEAK_PASSWORD else None
    return ProblemError(status, error.code, title, errors=errors)


async def mapped[T](call: Awaitable[T], password_field: str = "body.password") -> T:  # noqa: S107
    try:
        return await call
    except AuthError as exc:
        raise to_problem(exc, password_field) from exc
