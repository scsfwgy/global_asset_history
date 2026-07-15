"""Fixtures for API route integration tests."""

import pytest

from app import app as flask_app


@pytest.fixture
def client():
    """Flask test client."""
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def isolate_stats_files(monkeypatch, tmp_path):
    """Keep visit/unique-user fallback files out of shared /tmp during tests."""
    import app as app_module

    monkeypatch.setattr(app_module, "_COUNTER_PATH", tmp_path / "visit_count.json")
    monkeypatch.setattr(app_module, "_UNIQUE_VISITS_PATH", tmp_path / "unique_visits.json")
