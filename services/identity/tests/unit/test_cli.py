import asyncio
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from identity import cli

CLI_PASSWORD = "Cobalto-Sereno-Mare-42"  # noqa: S105 (senha de teste)


def test_create_staff_cli_creates_admin(
    migrated_url: str,
    settings: object,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    key_path: Path = settings.signing_key_path  # pyright: ignore[reportAttributeAccessIssue]
    monkeypatch.setenv("IDENTITY_DATABASE_URL", migrated_url)
    monkeypatch.setenv("IDENTITY_SIGNING_KEY_PATH", str(key_path))

    async def reset() -> None:
        engine = create_async_engine(migrated_url)
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE users CASCADE"))
        await engine.dispose()

    async def roles() -> list[tuple[str, str]]:
        engine = create_async_engine(migrated_url)
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT u.email, r.key FROM users u JOIN user_roles ur ON ur.user_id = u.id "
                    "JOIN roles r ON r.id = ur.role_id"
                )
            )
            result = [(row[0], row[1]) for row in rows]
        await engine.dispose()
        return result

    asyncio.run(reset())
    code = cli.main(["create-staff", "--email", "Equipe@Example.com", "--password", CLI_PASSWORD])

    assert code == 0
    assert "equipe@example.com" in capsys.readouterr().out
    assert asyncio.run(roles()) == [("equipe@example.com", "admin")]
    # segunda execução com o mesmo email falha com mensagem clara
    again = cli.main(["create-staff", "--email", "equipe@example.com", "--password", CLI_PASSWORD])
    assert again == 1
    assert "identity.auth.email_taken" in capsys.readouterr().err
