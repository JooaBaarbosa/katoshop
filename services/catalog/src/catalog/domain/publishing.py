from dataclasses import dataclass


@dataclass(frozen=True)
class PublishCheck:
    active_variant_prices: list[int]
    image_count: int


def publish_blockers(c: PublishCheck) -> list[str]:
    blockers: list[str] = []
    if not c.active_variant_prices:
        blockers.append("no_active_variant")
    if c.image_count < 1:
        blockers.append("no_image")
    if any(price <= 0 for price in c.active_variant_prices):
        blockers.append("no_price")
    return blockers
