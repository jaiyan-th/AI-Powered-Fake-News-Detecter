"""
Pytest Fixtures and Mock Providers for News Verification Test Suite
"""

import pytest
from sqlalchemy import create_engine
from backend.db import database
from backend.services.article_extractor import ExtractedArticle
from backend.schemas.verification import ClaimInfo, EvidenceSource, StanceEnum


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    from backend.main import rate_limiter
    rate_limiter.clear()
    yield
    rate_limiter.clear()


@pytest.fixture(autouse=True)
def test_database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setitem(database.SessionLocal.kw, "bind", engine)
    database.init_db()
    yield
    engine.dispose()


@pytest.fixture
def mock_extracted_article():
    return ExtractedArticle(
        url="https://reuters.com/world/example-news-story",
        title="India Announces Landmark Solar Energy Expansion",
        content="The government of India has officially announced a $5 billion solar energy expansion plan today in New Delhi.",
        publisher="reuters.com",
        published_date="2026-08-30T10:00:00Z"
    )


@pytest.fixture
def sample_claim_info():
    return ClaimInfo(
        primary_claim="India announced a $5 billion solar energy expansion plan.",
        secondary_claims=["The initiative was announced in New Delhi."],
        entities=["India", "New Delhi", "Solar Energy"],
        timeframe="2026-08-30"
    )


@pytest.fixture
def sample_evidence_sources():
    return [
        EvidenceSource(
            source_name="Reuters",
            domain="reuters.com",
            title="India Details $5B Solar Plan",
            url="https://reuters.com/solar-plan",
            published_at="2026-08-30T11:00:00Z",
            stance=StanceEnum.SUPPORT,
            relevance_score=0.94,
            evidence_snippet="The government announced $5B in solar funding.",
            credibility_tier="WIRE_AND_PRIMARY_AGENCY",
            search_provider="newsapi"
        ),
        EvidenceSource(
            source_name="The Hindu",
            domain="thehindu.com",
            title="Cabinet Approves Solar Mission Outlay",
            url="https://thehindu.com/solar-outlay",
            published_at="2026-08-30T12:00:00Z",
            stance=StanceEnum.SUPPORT,
            relevance_score=0.89,
            evidence_snippet="The cabinet cleared the multi-billion solar rollout.",
            credibility_tier="ESTABLISHED_NEWS_ORGANIZATION",
            search_provider="serpapi"
        )
    ]
