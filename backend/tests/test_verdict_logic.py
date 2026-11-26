"""
Tests for Verdict Generation & Stance Aggregation Logic
"""

from unittest.mock import MagicMock
from backend.services.evidence_analyzer import EvidenceAnalyzer
from backend.services.verdict_generator import VerdictGenerator
from backend.schemas.verification import (
    ClaimInfo, EvidenceSource, StanceEnum, VerdictEnum
)


def test_zero_sources_returns_unverified():
    """Verify that when 0 sources are found, the verdict is decisively UNVERIFIED"""
    mock_groq = MagicMock()
    generator = VerdictGenerator(mock_groq)

    claim = ClaimInfo(primary_claim="Unknown rumor without any news coverage")
    response = generator.synthesize_verdict(
        claim_info=claim,
        analyzed_sources=[],
        pipeline_stages=[],
        processing_time_ms=150.0
    )

    assert response.verdict == VerdictEnum.UNVERIFIED
    assert response.confidence <= 50
    assert response.evidence_summary.total_sources_evaluated == 0
    assert "Insufficient" in response.summary


def test_rule_based_fallback_supporting_sources():
    """Verify that fallback rule synthesis correctly returns REAL when multiple sources support"""
    mock_groq = MagicMock()
    mock_groq.generate_json.side_effect = Exception("Groq timeout")
    generator = VerdictGenerator(mock_groq)

    claim = ClaimInfo(primary_claim="Government launched highway project")
    sources = [
        EvidenceSource(
            source_name="Reuters",
            domain="reuters.com",
            title="Highway project inaugurated",
            url="https://reuters.com/highway",
            stance=StanceEnum.SUPPORT,
            relevance_score=0.9,
            evidence_snippet="Project launched today."
        ),
        EvidenceSource(
            source_name="The Hindu",
            domain="thehindu.com",
            title="Prime Minister opens highway",
            url="https://thehindu.com/highway",
            stance=StanceEnum.SUPPORT,
            relevance_score=0.88,
            evidence_snippet="The highway is now open."
        )
    ]

    response = generator.synthesize_verdict(
        claim_info=claim,
        analyzed_sources=sources,
        pipeline_stages=[],
        processing_time_ms=200.0
    )

    assert response.verdict == VerdictEnum.REAL
    assert response.confidence >= 75
    assert response.evidence_summary.supporting == 2
    assert response.evidence_summary.contradicting == 0


def test_context_only_evidence_does_not_produce_definitive_verdict(sample_claim_info, sample_evidence_sources):
    from unittest.mock import Mock
    from backend.schemas.verification import StanceEnum

    groq = Mock()
    sources = [source.model_copy(update={"stance": StanceEnum.NEUTRAL}) for source in sample_evidence_sources]
    response = VerdictGenerator(groq).synthesize_verdict(sample_claim_info, sources, [], 0)

    assert response.verdict == VerdictEnum.UNVERIFIED
    assert response.evidence_summary.neutral == len(sources)
    groq.generate_json.assert_not_called()


def test_evidence_requires_a_quote_from_the_matching_source(sample_claim_info):
    groq = MagicMock()
    quote = "The cabinet approved the solar expansion."
    groq.generate_json.return_value = {"evaluations": [
        {"source_id": "invalid", "stance": "SUPPORT", "evidence_snippet": quote},
        {"source_id": 1, "stance": "SUPPORT", "evidence_snippet": quote},
        {"source_id": 2, "stance": "SUPPORT", "evidence_snippet": quote},
    ]}
    documents = [
        {"title": "Solar expansion approved", "content_snippet": quote},
        {"title": "Weather bulletin", "content_snippet": "Rain is expected."},
    ]

    first, second = EvidenceAnalyzer(groq).analyze_evidence_sources(sample_claim_info, documents)

    assert first.stance == StanceEnum.SUPPORT
    assert first.evidence_snippet == quote
    assert second.stance == StanceEnum.NEUTRAL
    assert second.evidence_snippet == "Rain is expected."


def test_same_domain_does_not_corroborate_a_real_verdict(sample_claim_info, sample_evidence_sources):
    groq = MagicMock()
    groq.generate_json.return_value = {"verdict": "REAL", "summary": "Confirmed."}
    first, second = sample_evidence_sources
    sources = [first, second.model_copy(update={"domain": f"www.{first.domain}"})]
    response = VerdictGenerator(groq).synthesize_verdict(sample_claim_info, sources, [], 0)

    assert response.verdict == VerdictEnum.UNVERIFIED
    assert "Confirmed." not in response.summary


def test_conflicting_evidence_stays_unverified_when_synthesis_fails(sample_claim_info, sample_evidence_sources):
    groq = MagicMock()
    groq.generate_json.side_effect = TimeoutError()
    first, second = sample_evidence_sources
    sources = [first, second.model_copy(update={"stance": StanceEnum.CONTRADICT})]
    response = VerdictGenerator(groq).synthesize_verdict(sample_claim_info, sources, [], 0)

    assert response.verdict == VerdictEnum.UNVERIFIED
