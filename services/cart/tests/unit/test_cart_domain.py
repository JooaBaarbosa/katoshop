import pytest

from cart.domain.cart import (
    Cart,
    CartError,
    CartItem,
    Notice,
    add_item,
    apply_archived,
    apply_price_changed,
    apply_stock_changed,
    merge,
    set_quantity,
    totals,
)

LIMITS = {"max_lines": 50, "max_qty": 20}


def snap(
    variant_id: str = "v1",
    *,
    price: int = 1000,
    available: int = 10,
    quantity: int = 0,
    version: int = 1,
    unavailable: bool = False,
) -> CartItem:
    return CartItem(
        variant_id=variant_id,
        product_id="p1",
        product_slug="camiseta",
        name="Camiseta",
        color_code="PRETO",
        color_name="Preto",
        size_code="M",
        image_url=None,
        unit_price_cents=price,
        available=available,
        category_slug="camisetas",
        collection_slugs=[],
        quantity=quantity,
        variant_version=version,
        unavailable=unavailable,
    )


def cart(*items: CartItem, owner: str = "guest:a", coupon: str | None = None) -> Cart:
    return Cart(
        cart_id="c1",
        owner=owner,
        items={i.variant_id: i for i in items},
        coupon_code=coupon,
        version=0,
    )


def test_add_new_item() -> None:
    c = cart()
    add_item(c, snap(), 2, **LIMITS)
    assert c.items["v1"].quantity == 2


def test_add_sums_to_existing_and_refreshes_snapshot() -> None:
    c = cart(snap(quantity=2, price=1000, version=1))
    add_item(c, snap(price=1200, version=3, available=10), 3, **LIMITS)
    item = c.items["v1"]
    assert item.quantity == 5
    assert item.unit_price_cents == 1200
    assert item.variant_version == 3


def test_add_respects_available_when_summing() -> None:
    c = cart(snap(quantity=4, available=5))
    with pytest.raises(CartError) as exc:
        add_item(c, snap(available=5), 2, **LIMITS)
    assert exc.value.code == "cart.item.quantity_exceeds_stock"
    assert exc.value.extra == {"max": 5}
    assert c.items["v1"].quantity == 4


def test_add_over_limit() -> None:
    c = cart()
    with pytest.raises(CartError) as exc:
        add_item(c, snap(available=100), 21, **LIMITS)
    assert exc.value.code == "cart.item.quantity_limit"
    assert exc.value.extra == {"max": 20}


def test_add_sum_over_limit() -> None:
    c = cart(snap(quantity=15, available=100))
    with pytest.raises(CartError) as exc:
        add_item(c, snap(available=100), 6, **LIMITS)
    assert exc.value.code == "cart.item.quantity_limit"


def test_add_zero_quantity_rejected() -> None:
    with pytest.raises(CartError) as exc:
        add_item(cart(), snap(), 0, **LIMITS)
    assert exc.value.code == "cart.item.quantity_limit"


def test_add_too_many_lines() -> None:
    c = cart(*(snap(f"v{n}", quantity=1) for n in range(50)))
    with pytest.raises(CartError) as exc:
        add_item(c, snap("novo"), 1, **LIMITS)
    assert exc.value.code == "cart.cart.too_many_lines"
    add_item(c, snap("v0"), 1, **LIMITS)  # item existente não conta como linha nova
    assert c.items["v0"].quantity == 2


def test_add_unavailable_snapshot() -> None:
    with pytest.raises(CartError) as exc:
        add_item(cart(), snap(unavailable=True), 1, **LIMITS)
    assert exc.value.code == "cart.item.unavailable"
    with pytest.raises(CartError) as exc2:
        add_item(cart(), snap(available=0), 1, **LIMITS)
    assert exc2.value.code == "cart.item.unavailable"


def test_add_clears_notice() -> None:
    item = snap(quantity=1)
    item.notice = Notice("price_changed", 900, 1000, None)
    c = cart(item)
    add_item(c, snap(), 1, **LIMITS)
    assert c.items["v1"].notice is None


def test_set_quantity_updates_and_clears_notice() -> None:
    item = snap(quantity=2)
    item.notice = Notice("quantity_reduced", None, None, 2)
    c = cart(item)
    set_quantity(c, "v1", 5, max_qty=20)
    assert c.items["v1"].quantity == 5
    assert c.items["v1"].notice is None


def test_set_quantity_zero_removes() -> None:
    c = cart(snap(quantity=2))
    set_quantity(c, "v1", 0, max_qty=20)
    assert c.items == {}


def test_set_quantity_errors() -> None:
    c = cart(snap(quantity=2, available=5))
    with pytest.raises(CartError) as e1:
        set_quantity(c, "v1", 6, max_qty=20)
    assert e1.value.code == "cart.item.quantity_exceeds_stock"
    assert e1.value.extra == {"max": 5}
    with pytest.raises(CartError) as e2:
        set_quantity(c, "v1", 21, max_qty=20)
    assert e2.value.code == "cart.item.quantity_limit"
    with pytest.raises(CartError) as e3:
        set_quantity(c, "v1", -1, max_qty=20)
    assert e3.value.code == "cart.item.quantity_limit"
    with pytest.raises(CartError) as e4:
        set_quantity(c, "nope", 1, max_qty=20)
    assert e4.value.code == "cart.item.not_found"
    c.items["v1"].unavailable = True
    with pytest.raises(CartError) as e5:
        set_quantity(c, "v1", 1, max_qty=20)
    assert e5.value.code == "cart.item.unavailable"


def test_set_quantity_zero_missing_is_noop() -> None:
    c = cart()
    set_quantity(c, "nope", 0, max_qty=20)
    assert c.items == {}


def test_price_changed_sets_notice() -> None:
    item = snap(quantity=1, price=1000, version=1)
    assert apply_price_changed(item, 1500, 2) is True
    assert item.unit_price_cents == 1500
    assert item.variant_version == 2
    assert item.notice == Notice("price_changed", 1000, 1500, None)


def test_price_changed_stale_ignored() -> None:
    item = snap(quantity=1, price=1000, version=5)
    assert apply_price_changed(item, 1500, 5) is False
    assert apply_price_changed(item, 1500, 4) is False
    assert item.unit_price_cents == 1000
    assert item.notice is None


def test_price_changed_same_price_updates_version_only() -> None:
    item = snap(quantity=1, price=1000, version=1)
    assert apply_price_changed(item, 1000, 2) is True
    assert item.variant_version == 2
    assert item.notice is None


def test_price_changed_on_unavailable_keeps_unavailable_notice() -> None:
    item = snap(quantity=1, price=1000, version=1)
    apply_archived(item)
    assert apply_price_changed(item, 1100, 2) is True
    assert item.unit_price_cents == 1100
    assert item.unavailable is True
    assert item.notice == Notice("unavailable")


def test_stock_below_quantity_reduces() -> None:
    item = snap(quantity=5, available=10, version=1)
    assert apply_stock_changed(item, 3, 2) is True
    assert item.quantity == 3
    assert item.available == 3
    assert item.notice == Notice("quantity_reduced", None, None, 3)
    assert item.unavailable is False


def test_stock_zero_marks_unavailable_keeping_quantity() -> None:
    item = snap(quantity=2, version=1)
    assert apply_stock_changed(item, 0, 2) is True
    assert item.unavailable is True
    assert item.quantity == 2
    assert item.notice == Notice("unavailable")


def test_stock_returns_resets_quantity_without_notice() -> None:
    item = snap(quantity=2, version=1)
    apply_stock_changed(item, 0, 2)
    assert apply_stock_changed(item, 8, 3) is True
    assert item.unavailable is False
    assert item.quantity == 1
    assert item.notice is None
    assert item.available == 8


def test_stock_enough_only_updates_available() -> None:
    item = snap(quantity=2, available=10, version=1)
    assert apply_stock_changed(item, 7, 2) is True
    assert (item.available, item.quantity, item.notice) == (7, 2, None)


def test_stock_stale_ignored() -> None:
    item = snap(quantity=2, version=4)
    assert apply_stock_changed(item, 0, 3) is False
    assert item.unavailable is False
    assert item.available == 10


def test_archived_marks_unavailable_always() -> None:
    item = snap(quantity=2, version=9)
    assert apply_archived(item) is True
    assert item.unavailable is True
    assert item.notice == Notice("unavailable")
    assert item.quantity == 2


def test_merge_sums_caps_and_reports() -> None:
    account = cart(snap("v1", quantity=4, available=5), snap("v2", quantity=1), owner="user:u")
    guest = cart(snap("v1", quantity=3, available=5), snap("v3", quantity=2))
    reduced = merge(account, guest, **LIMITS).reduced
    assert reduced == ["v1"]
    assert account.items["v1"].quantity == 5
    assert account.items["v1"].notice == Notice("quantity_reduced", None, None, 5)
    assert account.items["v2"].quantity == 1
    assert account.items["v3"].quantity == 2


def test_merge_sum_without_reduction() -> None:
    account = cart(snap(quantity=2), owner="user:u")
    guest = cart(snap(quantity=3))
    assert merge(account, guest, **LIMITS).reduced == []
    assert account.items["v1"].quantity == 5
    assert account.items["v1"].notice is None


def test_merge_caps_at_max_qty() -> None:
    account = cart(snap(quantity=15, available=100), owner="user:u")
    guest = cart(snap(quantity=10, available=100))
    assert merge(account, guest, **LIMITS).reduced == ["v1"]
    assert account.items["v1"].quantity == 20


def test_merge_uses_fresher_snapshot() -> None:
    account = cart(snap(quantity=1, price=1000, version=1), owner="user:u")
    guest = cart(snap(quantity=1, price=1300, version=4))
    merge(account, guest, **LIMITS)
    assert account.items["v1"].unit_price_cents == 1300
    assert account.items["v1"].variant_version == 4


def test_merge_respects_max_lines() -> None:
    account = cart(*(snap(f"a{n}", quantity=1) for n in range(2)), owner="user:u")
    guest = cart(snap("g1", quantity=1), snap("g2", quantity=1))
    result = merge(account, guest, max_lines=3, max_qty=20)
    assert "g1" in account.items
    assert "g2" not in account.items
    assert result.dropped == ["g2"]
    assert result.reduced == []


def test_merge_new_item_over_max_qty_is_capped() -> None:
    account = cart(owner="user:u")
    guest = cart(snap(quantity=25, available=100))
    assert merge(account, guest, **LIMITS).reduced == ["v1"]
    assert account.items["v1"].quantity == 20


def test_merge_unavailable_guest_item_is_carried_with_flag() -> None:
    account = cart(owner="user:u")
    guest_item = snap(quantity=1)
    apply_archived(guest_item)
    merge(account, cart(guest_item), **LIMITS)
    assert account.items["v1"].unavailable is True


def test_merge_keeps_account_item_when_unavailable() -> None:
    gone = snap(quantity=2)
    apply_archived(gone)
    account = cart(gone, owner="user:u")
    assert merge(account, cart(snap(quantity=1)), **LIMITS).reduced == []
    assert account.items["v1"].unavailable is True
    assert account.items["v1"].quantity == 2


def test_merge_coupon_rules() -> None:
    a = cart(owner="user:u", coupon="CONTA10")
    assert merge(a, cart(coupon="VISIT10"), **LIMITS).reduced == []
    assert a.coupon_code == "VISIT10"
    b = cart(owner="user:u", coupon="CONTA10")
    merge(b, cart(coupon=None), **LIMITS)
    assert b.coupon_code == "CONTA10"


def test_totals_ignore_unavailable_and_block_checkout() -> None:
    gone = snap("v2", quantity=1, price=500)
    apply_archived(gone)
    c = cart(snap("v1", quantity=2, price=1000), gone)
    assert totals(c) == (2000, True)


def test_totals_no_block_when_all_available_or_empty() -> None:
    assert totals(cart(snap(quantity=3, price=100))) == (300, False)
    assert totals(cart()) == (0, False)


def test_archived_is_sticky_against_later_stock_event() -> None:
    item = snap(quantity=2, version=1)
    apply_archived(item)
    assert apply_stock_changed(item, 9, 2) is True
    assert item.unavailable is True
    assert item.archived is True
    assert item.quantity == 2
    assert item.notice == Notice("unavailable")
    assert item.available == 9


def test_stock_then_archived_stays_unavailable() -> None:
    item = snap(quantity=2, version=1)
    apply_stock_changed(item, 9, 2)
    apply_archived(item)
    assert apply_stock_changed(item, 0, 3) is True
    assert apply_stock_changed(item, 9, 4) is True
    assert item.unavailable is True
    assert item.archived is True


def test_archived_price_change_is_silent_and_sticky() -> None:
    item = snap(quantity=1, price=1000, version=1)
    apply_archived(item)
    apply_price_changed(item, 1200, 2)
    assert item.unit_price_cents == 1200
    assert item.unavailable is True
    assert item.notice == Notice("unavailable")


def test_add_after_archive_with_active_snapshot_clears_flags() -> None:
    item = snap(quantity=3, version=1)
    apply_archived(item)
    c = cart(item)
    add_item(c, snap(version=5, available=10), 2, **LIMITS)
    new = c.items["v1"]
    assert (new.quantity, new.unavailable, new.archived, new.notice) == (2, False, False, None)


def test_add_on_unavailable_line_ignores_stale_quantity() -> None:
    item = snap(quantity=20, available=10)
    apply_stock_changed(item, 0, 2)
    c = cart(item)
    add_item(c, snap(version=3, available=10), 1, **LIMITS)
    assert c.items["v1"].quantity == 1
    assert c.items["v1"].unavailable is False


def test_stock_return_after_price_change_while_unavailable_warns_price() -> None:
    item = snap(quantity=2, price=1000, version=1)
    apply_stock_changed(item, 0, 2)
    apply_price_changed(item, 1100, 3)
    apply_price_changed(item, 1300, 4)
    assert item.notice == Notice("unavailable")
    apply_stock_changed(item, 5, 5)
    assert item.unavailable is False
    assert item.quantity == 1
    assert item.notice == Notice("price_changed", 1000, 1300, None)


def test_stock_return_after_price_back_to_seen_has_no_notice() -> None:
    item = snap(quantity=2, price=1000, version=1)
    apply_stock_changed(item, 0, 2)
    apply_price_changed(item, 1100, 3)
    apply_price_changed(item, 1000, 4)
    apply_stock_changed(item, 5, 5)
    assert item.notice is None


def test_merge_unavailable_picks_fresher_snapshot() -> None:
    old_gone = snap(quantity=2, version=1)
    apply_stock_changed(old_gone, 0, 2)
    account = cart(old_gone, owner="user:u")
    fresh_ok = snap(quantity=1, version=7, available=10)
    result = merge(account, cart(fresh_ok), **LIMITS)
    assert result.reduced == []
    assert account.items["v1"].unavailable is False
    assert account.items["v1"].variant_version == 7


def test_merge_archived_account_beats_older_guest() -> None:
    gone = snap(quantity=2, version=5)
    apply_archived(gone)
    account = cart(gone, owner="user:u")
    merge(account, cart(snap(quantity=1, version=2)), **LIMITS)
    assert account.items["v1"].archived is True
    assert account.items["v1"].quantity == 2


def test_merge_processes_available_guest_lines_first_and_reports_dropped() -> None:
    account = cart(snap("a1", quantity=1), owner="user:u")
    gone = snap("g1", quantity=1)
    apply_archived(gone)
    guest = cart(gone, snap("g2", quantity=1))
    result = merge(account, guest, max_lines=2, max_qty=20)
    assert set(account.items) == {"a1", "g2"}
    assert result.dropped == ["g1"]


def test_merge_keeps_unacked_notice() -> None:
    a = snap(quantity=1, version=2)
    a.notice = Notice("price_changed", 900, 1000, None)
    account = cart(a, owner="user:u")
    merge(account, cart(snap(quantity=1, version=1)), **LIMITS)
    assert account.items["v1"].notice == Notice("price_changed", 900, 1000, None)
    assert account.items["v1"].quantity == 2


def test_set_quantity_requires_max_qty_keyword() -> None:
    with pytest.raises(TypeError):
        set_quantity(cart(snap(quantity=1)), "v1", 2)  # type: ignore[call-arg]  # pyright: ignore[reportCallIssue]
