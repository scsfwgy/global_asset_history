"""Fixtures for API route integration tests."""

import pytest

from app import app as flask_app


@pytest.fixture
def client():
    """Flask test client."""
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c
