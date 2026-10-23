import argparse
import asyncio
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from identity.adapters.repositories import (
    SessionScope,
    SqlRefreshTokenRepository,
    SqlUserRepository,
)
from identity.adapters.signing import load_signing_key
from identity.application.auth_service import AuthError, AuthService
from identity.settings import IdentitySettings
from ks_platform.db import make_engine, make_session_factory


async def _create_staff(settings: IdentitySettings, email: str, password: str, name: str) -> None:
    engine = make_engine(settings.database_url)
    try:
        scope = SessionScope(make_session_factory(engine))
        service = AuthService(
            SqlUserRepository(scope),
            SqlRefreshTokenRepository(scope),
            load_signing_key(settings.signing_key_path),
            lambda: datetime.now(UTC),
        )
        await service.create_staff(email, password, name)
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="identity.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    staff = commands.add_parser("create-staff", help="cria um usuário da equipe com papel admin")
    staff.add_argument("--email", required=True)
    staff.add_argument("--password", required=True)
    staff.add_argument("--name", default="Equipe")
    args = parser.parse_args(argv)

    settings = IdentitySettings()  # pyright: ignore[reportCallIssue]
    try:
        asyncio.run(_create_staff(settings, args.email, args.password, args.name))
    except AuthError as exc:
        detail = f"{exc.code}: {', '.join(exc.violations)}" if exc.violations else exc.code
        print(f"erro: {detail}", file=sys.stderr)  # noqa: T201
        return 1
    print(f"usuário staff criado: {args.email.strip().lower()}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
