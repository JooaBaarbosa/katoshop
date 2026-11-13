"""Outbox transacional: a linha entra na transação da mudança; o relay publica depois."""

import asyncio
import contextlib
import logging
import time
from datetime import UTC, datetime, timedelta

from opentelemetry import metrics
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    delete,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ks_platform.events import Envelope
from ks_platform.messaging import EventPublisher

logger = logging.getLogger("ks_platform.outbox")

_CLEANUP_EVERY_S = 60.0
_ALERT_ATTEMPTS = 10


def outbox_table(metadata: MetaData) -> Table:
    """Tabela `outbox`; cada serviço a inclui na própria migração Alembic."""
    return Table(
        "outbox",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True),
        Column("type", Text, nullable=False),
        Column("payload", JSONB, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("published_at", DateTime(timezone=True), nullable=True),
        Column("attempts", Integer, nullable=False, server_default=text("0")),
        Index(
            "ix_outbox_unpublished_created_at",
            "created_at",
            postgresql_where=text("published_at IS NULL"),
        ),
    )


async def add_event(session: AsyncSession, table: Table, event: Envelope) -> None:
    """Só faz o INSERT; quem chama controla a transação (a mesma da mudança de domínio)."""
    await session.execute(
        insert(table).values(id=event.id, type=event.type, payload=event.to_dict())
    )


class OutboxRelay:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        table: Table,
        publisher: EventPublisher,
        *,
        batch_size: int = 100,
        interval_s: float = 1.0,
        retention: timedelta = timedelta(days=7),
    ) -> None:
        self._session_factory = session_factory
        self._table = table
        self._publisher = publisher
        self._batch_size = batch_size
        self._interval_s = interval_s
        self._retention = retention
        self._last_cleanup: float | None = None
        self._backlog = metrics.get_meter("ks_platform.outbox").create_gauge(
            "outbox.backlog", unit="{row}", description="Linhas da outbox ainda não publicadas"
        )

    async def run_once(self) -> int:
        """Publica um lote em uma transação; para no primeiro erro. Devolve quantas publicou."""
        t = self._table
        published: list[object] = []
        async with self._session_factory() as session, session.begin():
            rows = (
                await session.execute(
                    select(t.c.id, t.c.type, t.c.payload)
                    .where(t.c.published_at.is_(None))
                    .order_by(t.c.created_at, t.c.id)
                    .limit(self._batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for row in rows:
                try:
                    await self._publisher.publish(Envelope.from_dict(row.payload), row.type)
                except Exception:
                    logger.warning(
                        "outbox: falha ao publicar evento %s (%s); lote interrompido",
                        row.id,
                        row.type,
                        exc_info=True,
                    )
                    attempts = await session.scalar(
                        update(t)
                        .where(t.c.id == row.id)
                        .values(attempts=t.c.attempts + 1)
                        .returning(t.c.attempts)
                    )
                    if attempts is not None and attempts >= _ALERT_ATTEMPTS:
                        logger.error(
                            "outbox: evento %s (%s) falhou %d vezes; a fila está travada",
                            row.id,
                            row.type,
                            attempts,
                        )
                    break
                published.append(row.id)
            if published:
                await session.execute(
                    update(t).where(t.c.id.in_(published)).values(published_at=func.now())
                )
        async with self._session_factory() as session, session.begin():
            now = time.monotonic()
            if self._last_cleanup is None or now - self._last_cleanup >= _CLEANUP_EVERY_S:
                cutoff = datetime.now(UTC) - self._retention
                await session.execute(delete(t).where(t.c.published_at < cutoff))
                self._last_cleanup = now
            backlog = await session.scalar(
                select(func.count()).select_from(t).where(t.c.published_at.is_(None))
            )
        self._backlog.set(backlog or 0)
        return len(published)

    async def run_forever(self, stop: asyncio.Event) -> None:
        """Roda até `stop`; lote cheio repete na hora, senão espera `interval_s`."""
        while not stop.is_set():
            count = 0
            try:
                count = await self.run_once()
            except Exception:
                logger.exception("outbox: iteração do relay falhou")
            if count >= self._batch_size:
                continue
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), self._interval_s)
