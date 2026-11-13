import json
import uuid
from datetime import UTC, datetime

import pytest

from ks_platform.events import Envelope, new_event


def _event() -> Envelope:
    return new_event(
        "catalog.variant.price_changed.v1",
        "catalog",
        {"variant_id": "abc", "new_price_cents": 1990},
        correlation_id="req-1",
    )


def test_new_event_fills_metadata():
    event = _event()
    assert event.version == 1
    assert event.id.version == 7
    assert event.producer == "catalog"
    assert event.correlation_id == "req-1"
    assert event.causation_id is None
    assert event.occurred_at.tzinfo is not None
    assert abs((datetime.now(UTC) - event.occurred_at).total_seconds()) < 5


def test_new_event_version_comes_from_type_suffix():
    assert new_event("x.y.z.v1", "p", {}).version == 1
    assert new_event("x.y.z.v12", "p", {}).version == 12


def test_new_event_without_version_suffix_is_rejected():
    with pytest.raises(ValueError, match="versão"):
        new_event("x.y.z", "p", {})


def test_new_event_ids_are_unique_and_ordered():
    ids = [new_event("x.y.v1", "p", {}).id for _ in range(50)]
    assert len(set(ids)) == 50
    assert ids == sorted(ids)


def test_json_roundtrip():
    event = _event()
    raw = event.to_json()
    assert isinstance(raw, bytes)
    assert Envelope.from_json(raw) == event


def test_json_uses_spec_field_names():
    body = json.loads(_event().to_json())
    assert set(body) == {
        "id",
        "type",
        "version",
        "occurred_at",
        "correlation_id",
        "causation_id",
        "producer",
        "data",
    }
    uuid.UUID(body["id"])
    datetime.fromisoformat(body["occurred_at"])


@pytest.mark.parametrize("raw", [b"{not json", b"\xff\xfe", b"[]", b"{}", b'"texto"'])
def test_from_json_rejects_garbage(raw):
    with pytest.raises(ValueError):
        Envelope.from_json(raw)


_MISSING = object()


def _mutated(key: str, value: object) -> bytes:
    body = json.loads(_event().to_json())
    if value is _MISSING:
        del body[key]
    else:
        body[key] = value
    return json.dumps(body).encode()


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("id", _MISSING),
        ("data", _MISSING),
        ("producer", _MISSING),
        ("id", "nao-e-uuid"),
        ("version", "1"),
        ("version", True),
        ("version", 0),
        ("type", ""),
        ("occurred_at", "ontem"),
        ("occurred_at", "2026-11-13T10:00:00"),
        ("data", []),
        ("correlation_id", 5),
    ],
)
def test_from_json_rejects_missing_or_wrong_fields(key, value):
    with pytest.raises(ValueError):
        Envelope.from_json(_mutated(key, value))
