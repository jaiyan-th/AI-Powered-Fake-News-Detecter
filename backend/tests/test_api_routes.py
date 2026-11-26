"""
Tests for API Routes & Input Validation
"""

from io import BytesIO
from wsgiref.util import setup_testing_defaults

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_wsgi_health_endpoint():
    from wsgi import UniversalApp

    environ = {"PATH_INFO": "/api/v1/health", "wsgi.input": BytesIO()}
    setup_testing_defaults(environ)
    statuses = []

    def start_response(status, headers, exc_info=None):
        if exc_info:
            raise exc_info[1].with_traceback(exc_info[2])
        statuses.append(status)

    body = b"".join(UniversalApp(app)(environ, start_response))
    assert statuses == ["200 OK"]
    assert b'"application":"running"' in body


def test_health_endpoint():
    """Verify GET /api/v1/health returns 200 with structured status"""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["application"] == "running"
    assert "dependencies" in data
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
