"""Static checks for frozen headers and leading columns on fund tables."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_on_exchange_table_freezes_header_and_code_column():
    page = _source("frontend/price-change.html")
    market = _source("frontend/etf-market.html")
    css = _source("frontend/css/app.css")

    assert 'class="transfer-table-wrap etf-freeze-scroll"' in page
    assert 'class="transfer-table-wrap etf-freeze-scroll"' in market
    assert ".etf-freeze-scroll" in css
    assert "border-collapse: separate" in css
    assert "#etfTable thead th" in css
    assert "top: 0" in css
    assert "#etfTable tbody td:nth-child(1):not([colspan])" in css
    assert "#etfTable thead th:nth-child(1)" in css
    assert "function fitEtfFreezePane()" in _source("frontend/js/etf-market.js")


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
