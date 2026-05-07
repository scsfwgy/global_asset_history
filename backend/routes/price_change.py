"""
Yearly price change API blueprint.
"""
import logging

from flask import Blueprint, jsonify, request

from service.price_change.price_change_service import (
    fetch_yearly_returns,
    fetch_monthly_returns,
    fetch_monthly_returns_batch,
    get_presets,
    get_color_range,
)

logger = logging.getLogger(__name__)

price_change_bp = Blueprint("price_change", __name__, url_prefix="/api/price-change")


@price_change_bp.route("/config", methods=["GET"])
def config():
    """Return presets and other config for the frontend."""
    presets_dict = get_presets()
    # Return as list to preserve insertion order (Flask's jsonify sorts keys by default)
    presets_list = [
        {"key": k, "label": v["label"], "symbols": v["symbols"]}
        for k, v in presets_dict.items()
    ]
    color_range = get_color_range()
    return jsonify({"presets": presets_list, "color_range": color_range})


@price_change_bp.route("/yearly", methods=["POST"])
def get_yearly_returns():
    """Return yearly returns for given symbols.

    Request body:
        {"symbols": [{"symbol": "AAPL", "type": "stock"}, ...]}

    Returns:
        {"years": [...], "data": {"SYMBOL": {"year": pct, ...}, ...}}
    """
    body = request.get_json(silent=True) or {}
    symbols = body.get("symbols", [])

    if not symbols:
        return jsonify({"error": "symbols list is required"}), 400

    try:
        result = fetch_yearly_returns(symbols)
        return jsonify(result)
    except Exception as e:
        logger.exception("Failed to fetch yearly returns: %s", e)
        return jsonify({"error": str(e)}), 500


@price_change_bp.route("/monthly", methods=["POST"])
def get_monthly_returns():
    """Return monthly returns for a symbol in a given year.

    Request body:
        {"symbol": "AAPL", "type": "stock", "year": 2024}

    Returns:
        {"symbol": "AAPL", "year": 2024, "months": [{"month": 1, "return": 5.2}, ...]}
    """
    body = request.get_json(silent=True) or {}
    symbol = body.get("symbol", "").strip().upper()
    asset_type = body.get("type", "stock").strip().lower()
    year = body.get("year")

    if not symbol or not year:
        return jsonify({"error": "symbol and year are required"}), 400

    try:
        year = int(year)
    except (ValueError, TypeError):
        return jsonify({"error": "year must be an integer"}), 400

    try:
        months = fetch_monthly_returns(symbol, asset_type, year)
        return jsonify({"symbol": symbol, "type": asset_type, "year": year, "months": months})
    except Exception as e:
        logger.exception("Failed to fetch monthly returns: %s", e)
        return jsonify({"error": str(e)}), 500


@price_change_bp.route("/monthly-batch", methods=["POST"])
def get_monthly_returns_batch():
    """Return monthly returns for multiple symbols in a given year.

    Request body:
        {"symbols": [{"symbol": "AAPL", "type": "stock"}, ...], "year": 2025}

    Returns:
        {"year": 2025, "data": {"AAPL": [{"month": 1, "return": 5.2}, ...], ...}}
    """
    body = request.get_json(silent=True) or {}
    symbols = body.get("symbols", [])
    year = body.get("year")

    if not symbols or not year:
        return jsonify({"error": "symbols and year are required"}), 400

    try:
        year = int(year)
    except (ValueError, TypeError):
        return jsonify({"error": "year must be an integer"}), 400

    try:
        result = fetch_monthly_returns_batch(symbols, year)
        return jsonify({"year": year, "data": result})
    except Exception as e:
        logger.exception("Failed to fetch monthly returns batch: %s", e)
        return jsonify({"error": str(e)}), 500
