import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, StringConstraints

from identity.application.auth_service import TokenPair
from identity.application.ports import UserRecord

# limite alto o bastante para frases-senha, baixo o bastante para não virar vetor de DoS no Argon2
Password = Annotated[str, StringConstraints(max_length=256)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class RegisterIn(BaseModel):
    email: EmailStr
    password: Password
    name: Name


class LoginIn(BaseModel):
    email: EmailStr
    password: Password


class RefreshIn(BaseModel):
    refresh_token: Annotated[str, StringConstraints(min_length=1, max_length=512)]


class MePatchIn(BaseModel):
    name: Name | None = None
    email: EmailStr | None = None
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
