"""
Tests for Error Resilience & Fallback Handling
"""

import pytest
from backend.services.article_extractor import ArticleExtractor
from backend.core.exceptions import ArticleExtractionError
from backend.services.embedding_service import EmbeddingService
from backend.services.vector_service import VectorSearchService


def test_article_extractor_invalid_url():
    """Verify that an invalid or non-http URL raises clean ArticleExtractionError"""
    extractor = ArticleExtractor(timeout=2)
    with pytest.raises(ArticleExtractionError) as exc_info:
        extractor.extract("not_a_valid_url")
    assert "Invalid URL format" in str(exc_info.value)


def test_embedding_and_vector_search():
    """Verify that FastEmbed embedding and vector search work seamlessly in memory"""
    emb_service = EmbeddingService()
    vector = emb_service.embed_text("India launches new space mission")
    assert len(vector) == 384

    vector_service = VectorSearchService(emb_service)
    session_id = "test-session-123"

    articles = [
        {
            "article_id": "art1",
            "title": "ISRO Launches New Satellite",
            "content": "Indian Space Research Organisation successfully launched satellite from Sriharikota.",
            "source_name": "The Hindu",
            "domain": "thehindu.com",
            "url": "https://thehindu.com/isro-launch",
            "published_at": "2026-08-30",
            "credibility_tier": "ESTABLISHED_NEWS_ORGANIZATION",
            "credibility_label": "Established News Organization",
            "search_provider": "newsapi"
        }
    ]

    indexed_count = vector_service.index_evidence(session_id, articles)
    assert indexed_count == 1

    retrieved = vector_service.retrieve_relevant_evidence("ISRO satellite launch", session_id, top_k=2)
    assert len(retrieved) == 1
    assert retrieved[0]["source_name"] == "The Hindu"
    assert retrieved[0]["relevance_score"] > 0.0


def test_vector_search_ranks_before_truncation_and_releases_request_index():
    from unittest.mock import Mock

    embeddings = Mock()
    embeddings.embed_text.return_value = [1.0, 0.0]
    embeddings.embed_batch.side_effect = [
        [[1.0, 0.0], [0.9, 0.4]],  # Headline ordering in the first pass.
        [[0.6, 0.8], [1.0, 0.0]],  # Evidence ordering in the second pass.
    ]
    service = VectorSearchService(embeddings)
    articles = [{"title": "First headline"}, {"title": "Second headline"}]
    results = service.search("ranking-check", articles, "Example claim", top_k=1)

    assert results[0]["title"] == "Second headline"
    assert service.retrieve_relevant_evidence("Example claim", "ranking-check") == []


def test_article_fetch_checks_each_redirect_before_connecting(monkeypatch):
    from unittest.mock import Mock

    import socket
    import urllib3

    pool = Mock()
    pool.urlopen.return_value.get_redirect_location.return_value = "https://second.example/article"
    open_connection = Mock(return_value=pool)

    def resolve(host, port, **kwargs):
        address = "93.184.215.14" if host == "first.example" else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(urllib3, "HTTPSConnectionPool", open_connection)

    with pytest.raises(ArticleExtractionError, match="public web server"):
        ArticleExtractor().extract("https://first.example/article")

    open_connection.assert_called_once()
    assert open_connection.call_args.args == ("93.184.215.14",)
    assert open_connection.call_args.kwargs["server_hostname"] == "first.example"
    assert pool.urlopen.call_args.kwargs["headers"]["Host"] == "first.example"
    pool.urlopen.return_value.close.assert_called_once()
    pool.close.assert_called_once()


def test_article_extraction_parses_fetched_html(monkeypatch):
    extractor = ArticleExtractor()
    content = "The town council unanimously voted to approve the library after residents spoke at a public meeting."
    html = f"<html><head><title>Council approves library</title></head><body><article><p>{content}</p><p>{content}</p></article></body></html>"
    monkeypatch.setattr(extractor, "_download", lambda url: ("https://www.example.com/report", html.encode()))

    article = extractor.extract("https://example.com/old-link")

    assert article.title == "Council approves library"
    assert article.publisher == "example.com"
    assert article.url == "https://www.example.com/report"
    assert content in article.content
