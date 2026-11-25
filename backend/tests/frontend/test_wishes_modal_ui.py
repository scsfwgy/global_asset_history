"""Checks for the compact Wish Wall trigger button and compose modal dialog."""

from pathlib import Path

from app import app as flask_app


ROOT = Path(__file__).resolve().parents[3]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_wish_wall_uses_button_and_modal_instead_of_inline_hero_banner():
    page = _source("frontend/price-change.html")
    script = _source("frontend/js/wishes.js")

    assert 'class="wish-hero"' not in page
    assert 'id="wishHeadline"' not in page
    assert 'id="wishOpenModalBtn"' in page
    assert 'id="wishComposeDialog"' in page
    assert 'id="wishDialogClose"' in page
    assert 'id="wishForm"' in page
    assert "function openWishDialog()" in script
    assert "function closeWishDialog()" in script
    assert "function ensureWishesLoaded()" in script
    assert "dialog.showModal()" in script
    assert "closeWishDialog();" in script


def test_wishes_route_keeps_modal_and_home_route_prunes_it():
    with flask_app.test_client() as client:
        wishes_res = client.get("/zh/wishes")
        assert wishes_res.status_code == 200
        wishes_html = wishes_res.get_data(as_text=True)
        assert 'id="wishOpenModalBtn"' in wishes_html
        assert 'id="wishComposeDialog"' in wishes_html
        assert 'class="wish-hero"' not in wishes_html

        home_res = client.get("/zh/heatmap")
        assert home_res.status_code == 200
        home_html = home_res.get_data(as_text=True)
        assert 'id="wishComposeDialog"' not in home_html
