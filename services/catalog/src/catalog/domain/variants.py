from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class NewVariant:
    sku: str
    color_code: str
    size_code: str


def generate_variant_grid(
    product_id: UUID,
    colors: list[str],
    sizes: list[str],
    existing: set[tuple[str, str]],
) -> list[NewVariant]:
    suffix = product_id.hex[-6:].upper()
    seen = set(existing)
    grid: list[NewVariant] = []
    for color in colors:
        for size in sizes:
            if (color, size) in seen:
                continue
            seen.add((color, size))
            grid.append(NewVariant(f"KS-{suffix}-{color}-{size}", color, size))
    return grid
