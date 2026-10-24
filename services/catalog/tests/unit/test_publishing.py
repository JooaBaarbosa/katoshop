from catalog.domain.publishing import PublishCheck, publish_blockers


def test_empty_product_has_two_blockers_in_order():
    assert publish_blockers(PublishCheck([], 0)) == ["no_active_variant", "no_image"]


def test_zero_price_blocks():
    assert publish_blockers(PublishCheck([0, 12900], 1)) == ["no_price"]


def test_ready_product_has_no_blockers():
    assert publish_blockers(PublishCheck([12900], 2)) == []


def test_no_price_check_without_variants():
    assert publish_blockers(PublishCheck([], 1)) == ["no_active_variant"]
