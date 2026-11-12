import uuid
from datetime import datetime
from typing import Annotated

import email_validator
from pydantic import AfterValidator, BaseModel, StringConstraints

from identity.application.auth_service import TokenPair
from identity.application.ports import UserRecord

# limite alto o bastante para frases-senha, baixo o bastante para não virar vetor de DoS no Argon2
Password = Annotated[str, StringConstraints(max_length=256)]
# sem caracteres de controle: NUL quebraria o INSERT no Postgres (SQLSTATE 22021)
Name = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=120, pattern=r"^[^\x00-\x1f\x7f]*$"
    ),
]

# Os endereços demo usam katoshop.localhost (R14). O email-validator recusa nomes de uso
# especial mesmo com globally_deliverable=False; a lista é o ajuste documentado da lib.
if "localhost" in email_validator.SPECIAL_USE_DOMAIN_NAMES:
    email_validator.SPECIAL_USE_DOMAIN_NAMES.remove("localhost")


def _validate_email(value: str) -> str:
    """Só sintaxe (sem DNS); devolve a forma normalizada. Caixa fica com o serviço."""
    try:
        result = email_validator.validate_email(
            value.strip(), check_deliverability=False, globally_deliverable=False
        )
    except email_validator.EmailNotValidError as exc:
        raise ValueError(f"value is not a valid email address: {exc}") from exc
    return result.normalized


EmailAddress = Annotated[str, StringConstraints(max_length=320), AfterValidator(_validate_email)]


class RegisterIn(BaseModel):
    email: EmailAddress
    password: Password
    name: Name


class LoginIn(BaseModel):
    email: EmailAddress
    password: Password


class RefreshIn(BaseModel):
    refresh_token: Annotated[str, StringConstraints(min_length=1, max_length=512)]


class MePatchIn(BaseModel):
    name: Name | None = None
    email: EmailAddress | None = None
    new_password: Password | None = None
    current_password: Password | None = None


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    kind: str
    roles: list[str]

    @classmethod
    def from_record(cls, user: UserRecord) -> UserOut:
        return cls(id=user.id, email=user.email, name=user.name, kind=user.kind, roles=user.roles)


class TokenPairOut(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    refresh_expires_at: datetime
    user: UserOut

    @classmethod
    def from_pair(cls, pair: TokenPair) -> TokenPairOut:
        return cls(
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
            expires_in=pair.expires_in,
            refresh_expires_at=pair.refresh_expires_at,
            user=UserOut.from_record(pair.user),
        )
