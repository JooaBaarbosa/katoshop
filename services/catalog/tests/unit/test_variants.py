import uuid

from catalog.domain.variants import NewVariant, generate_variant_grid

PID = uuid.UUID("01890000-0000-7000-8000-0000abcdef12")


def test_grid_skips_existing_and_keeps_order():
    grid = generate_variant_grid(PID, ["PRT", "BRC"], ["P", "M", "G"], {("PRT", "M")})
    assert len(grid) == 5
    assert grid[0] == NewVariant(sku="KS-CDEF12-PRT-P", color_code="PRT", size_code="P")
    assert [(v.color_code, v.size_code) for v in grid] == [
        ("PRT", "P"),
        ("PRT", "G"),
        ("BRC", "P"),
        ("BRC", "M"),
        ("BRC", "G"),
    ]


def test_grid_sku_uses_last_six_hex_uppercase():
    grid = generate_variant_grid(PID, ["PRT"], ["P"], set())
    assert grid[0].sku == "KS-CDEF12-PRT-P"


def test_grid_dedupes_repeated_inputs():
    grid = generate_variant_grid(PID, ["PRT", "PRT"], ["P", "P"], set())
    assert len(grid) == 1
