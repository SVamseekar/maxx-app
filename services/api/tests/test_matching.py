from maxx.matching import CATALOG, match_item
from maxx.scan import Item


def test_exact_variant_and_uncertain_confirmation():
    assert len(CATALOG) == 50
    exact = match_item(Item(title="Sony WH-1000XM5 Black", model="WH-1000XM5", variant="Black"))
    assert exact.candidates[0].product_key == "sony-wh1000xm5-black"
    assert not exact.requires_confirmation
    uncertain = match_item(Item(title="Sony headphones"))
    assert uncertain.requires_confirmation
    assert uncertain.confidence < 0.8


def test_variant_contradiction_cannot_be_auto_matched():
    result = match_item(Item(title="Sony WH-1000XM5 Silver", model="WH-1000XM5", variant="Silver"))
    assert result.candidates[0].product_key == "sony-wh1000xm5-silver"
    assert all(c.product_key != "sony-wh1000xm5-black" for c in result.candidates)
    assert match_item(Item(title="Unrecognised lamp")).requires_confirmation


def test_brand_in_title_excludes_other_brands():
    result = match_item(Item(title="Sony headphones"))
    assert result.candidates
    assert all(c.brand == "Sony" for c in result.candidates)
