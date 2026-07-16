"""Operational logging contracts for startup and API requests."""

import logging
import re

import app as app_module


def test_api_request_has_request_id_and_sanitized_structured_log(client, caplog):
    caplog.set_level(logging.INFO, logger="app")

    response = client.get("/api/health?token=must-not-be-logged")

    request_id = response.headers["X-Request-ID"]
    assert re.fullmatch(r"[0-9a-f]{12}", request_id)
    messages = [record.getMessage() for record in caplog.records]
    request_logs = [message for message in messages if "event=http_request" in message]
    assert any(
        f"request_id={request_id}" in message
        and "operation=health" in message
        and "method=GET" in message
        and "path=/api/health" in message
        and "status=200" in message
        and "duration_ms=" in message
        and "response_bytes=" in message
        for message in request_logs
    )
    assert all("must-not-be-logged" not in message for message in messages)


def test_request_log_path_redacts_private_wish_id():
    assert app_module._request_log_path("/api/wishes/private-id/reply") == "/api/wishes/:id/reply"
