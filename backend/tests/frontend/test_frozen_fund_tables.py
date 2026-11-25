"""Static and route checks for frozen headers, leading columns, and scroll sizing on fund tables."""

from pathlib import Path

from app import app as flask_app


ROOT = Path(__file__).resolve().parents[3]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_on_exchange_table_freezes_header_and_code_column():
    page = _source("frontend/price-change.html")
    market = _source("frontend/etf-market.html")
    css = _source("frontend/css/app.css")
    script = _source("frontend/js/etf-market.js")

    assert 'class="transfer-table-wrap etf-freeze-scroll"' in page
    assert 'class="transfer-table-wrap etf-freeze-scroll"' in market
    assert ".etf-freeze-scroll" in css
    assert "border-collapse: separate" in css
    assert "#etfTable thead th" in css
    assert "top: 0" in css
    assert "#etfTable tbody td:nth-child(1):not([colspan])" in css
    assert "#etfTable thead th:nth-child(1)" in css
    assert "function fitEtfFreezePane()" in script
    assert "function handleEtfFreezeWheel(event)" in script
    assert "window.innerHeight - top" not in script


def test_off_exchange_table_freezes_header_and_first_two_columns():
    page = _source("frontend/price-change.html")
    css = _source("frontend/css/app.css")
    script = _source("frontend/js/qdii-funds.js")

    assert 'class="transfer-table-wrap qdii-freeze-scroll"' in page
    assert ".qdii-freeze-scroll" in css
    assert "--qdii-freeze-col1" in css
    assert "#qdiiFundsTable thead th:nth-child(1)" in css
    assert "#qdiiFundsTable tbody tr.qdii-fund-row td:nth-child(1)" in css
    assert "#qdiiFundsTable thead th:nth-child(2)" in css
    assert "#qdiiFundsTable tbody tr.qdii-fund-row td:nth-child(2)" in css
    assert "left: var(--qdii-freeze-col1)" in css
    assert "function syncQdiiFrozenColumns()" in script
    assert 'table.style.setProperty("--qdii-freeze-col1", next)' in script
    assert "syncQdiiFrozenColumns();" in script
    assert "function fitQdiiFreezePane()" in script


def test_qdii_freeze_pane_uses_viewport_height_and_mobile_layout():
    """Guard against shrinking the table via initial rect.top, which traps the guide below."""
    page = _source("frontend/price-change.html")
    css = _source("frontend/css/app.css")
    script = _source("frontend/js/qdii-funds.js")

    assert "window.innerHeight - top" not in script
    assert "viewportH - reserve" in script
    assert "function handleQdiiFreezeWheel(event)" in script
    assert 'addEventListener("wheel", handleQdiiFreezeWheel, { passive: false })' in script
    assert "max-height: calc(100dvh - 96px);" in css
    assert "max-height: calc(100dvh - 76px);" in css
    assert "#tab-qdii-funds .pc-monthly-header" in page
    assert ".qdii-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }" in page


def test_qdii_route_renders_table_and_guide():
    with flask_app.test_client() as client:
        res = client.get("/zh/qdii-funds")
        assert res.status_code == 200
        body = res.get_data(as_text=True)
        assert 'id="qdiiFundsTable"' in body
        assert 'id="qdiiFundsGuide"' in body
        assert "/js/qdii-funds.js" in body
