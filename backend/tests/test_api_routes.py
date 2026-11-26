"""
Tests for API Routes & Input Validation
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from backend.api.deps import get_db
from backend.core.config import Settings
from backend.main import app

client = TestClient(app)


def test_health_returns_503_when_database_schema_is_unavailable(monkeypatch):
    from sqlalchemy.orm import Session

    engine = create_engine("sqlite://")

    def unavailable_database():
        with Session(engine) as session:
            yield session

    monkeypatch.setitem(app.dependency_overrides, get_db, unavailable_database)
    try:
        response = client.get("/api/v1/health")
        assert response.status_code == 503
        assert response.json()["dependencies"]["database"]["status"] == "unavailable"
    finally:
        engine.dispose()


def test_production_requires_persistent_signing_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(ValidationError, match="explicit JWT_SECRET_KEY"):
        Settings(_env_file=None, PRODUCTION=True)
    settings = Settings(_env_file=None, PRODUCTION=True, JWT_SECRET_KEY="test-key-" * 5)
    assert settings.PRODUCTION


def test_health_endpoint():
    """Verify GET /api/v1/health returns 200 with structured status"""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["application"] == "running"
    assert "dependencies" in data
    assert data["dependencies"]["database"]["status"] == "operational"
    assert "groq_llm" in data["dependencies"]
    assert "news_api" in data["dependencies"]
    assert "vector_search_engine" in data["dependencies"]


def test_verify_validation_both_url_and_text():
    """Verify that providing both URL and text fails with 422 Unprocessable Entity"""
    payload = {
        "url": "https://reuters.com/article",
        "text": "Some text claim"
    }
    response = client.post("/api/v1/verify", json=payload)
    assert response.status_code == 422


def test_verify_validation_neither_url_nor_text():
    """Verify that providing neither URL nor text fails with 422"""
    payload = {
        "url": "",
        "text": ""
    }
    response = client.post("/api/v1/verify", json=payload)
    assert response.status_code == 422


def test_verify_empty_body():
    """Verify that sending empty JSON body fails with 422"""
    response = client.post("/api/v1/verify", json={})
    assert response.status_code == 422


@pytest.mark.parametrize("payload", [
    {"url": "file:///article"},
    {"url": "https://user:password@example.com/article"},
    {"text": "x" * 12001},
])
def test_verify_rejects_invalid_or_oversized_input(payload):
    assert client.post("/api/v1/verify", json=payload).status_code == 422


def test_verify_rejects_nonpublic_article():
    response = client.post("/api/v1/verify", json={"url": "http://127.0.0.1/news"})
    assert response.status_code == 422
    assert "public web server" in response.json()["message"]
