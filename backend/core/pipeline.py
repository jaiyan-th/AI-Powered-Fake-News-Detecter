"""
Verification Pipeline Orchestrator
Coordinates all pipeline stages: Article Extraction -> Claim Extraction -> Search ->
Normalization & Deduplication -> Vector Embedding & Semantic Retrieval -> Stance Analysis -> Verdict Synthesis.
"""

import asyncio
import time
import uuid
import logging
from typing import List
from starlette.concurrency import run_in_threadpool
from backend.schemas.verification import (
    VerificationRequest, VerificationResponse, PipelineStage
)
from backend.services.article_extractor import ArticleExtractor
from backend.services.claim_extractor import ClaimExtractor
from backend.services.query_generator import QueryGenerator
from backend.services.newsapi_service import NewsAPIService
from backend.services.serpapi_service import SerpAPIService
from backend.services.source_normalizer import SourceNormalizer
from backend.services.vector_service import VectorSearchService
from backend.services.evidence_analyzer import EvidenceAnalyzer
from backend.services.verdict_generator import VerdictGenerator
from backend.core.config import settings

logger = logging.getLogger("news_verification.pipeline")


class VerificationPipeline:
    def __init__(
        self,
        article_extractor: ArticleExtractor,
        claim_extractor: ClaimExtractor,
        query_generator: QueryGenerator,
        newsapi_service: NewsAPIService,
        serpapi_service: SerpAPIService,
        source_normalizer: SourceNormalizer,
        vector_service: VectorSearchService,
        evidence_analyzer: EvidenceAnalyzer,
        verdict_generator: VerdictGenerator
    ):
        self.article_extractor = article_extractor
        self.claim_extractor = claim_extractor
        self.query_generator = query_generator
        self.newsapi_service = newsapi_service
        self.serpapi_service = serpapi_service
        self.source_normalizer = source_normalizer
        self.vector_service = vector_service
        self.evidence_analyzer = evidence_analyzer
        self.verdict_generator = verdict_generator

    async def verify(self, request: VerificationRequest) -> VerificationResponse:
        verification_id = str(uuid.uuid4())
        pipeline_start = time.perf_counter()
        pipeline_stages: List[PipelineStage] = []

        logger.info(f"[{verification_id}] Starting news verification pipeline. (type={'URL' if request.url else 'TEXT'})")

        # STAGE 1: Content Extraction / Ingestion
        t0 = time.perf_counter()
        extracted_article = None

        if request.url:
            extracted_article = await run_in_threadpool(self.article_extractor.extract, request.url)
            raw_text = extracted_article.content.replace('\u202f', ' ').replace('\xa0', ' ')
            article_title = extracted_article.title.replace('\u202f', ' ').replace('\xa0', ' ')
            stage_duration = round((time.perf_counter() - t0) * 1000, 2)
            pipeline_stages.append(PipelineStage(
                stage="article_extraction",
                status="COMPLETED",
                duration_ms=stage_duration,
                details={"verification_id": verification_id, "title": article_title, "chars": len(raw_text)}
            ))
        else:
            raw_text = request.text.replace('\u202f', ' ').replace('\xa0', ' ')
            article_title = raw_text.split("\n")[0][:120]
            stage_duration = round((time.perf_counter() - t0) * 1000, 2)
            pipeline_stages.append(PipelineStage(
                stage="text_ingestion",
                status="COMPLETED",
                duration_ms=stage_duration,
                details={"verification_id": verification_id, "chars": len(raw_text)}
            ))

        # STAGE 2: Claim Extraction (Groq)
        t0 = time.perf_counter()
        claim_info = await run_in_threadpool(self.claim_extractor.extract_claims, raw_text, title=article_title)
        stage_duration = round((time.perf_counter() - t0) * 1000, 2)
        pipeline_stages.append(PipelineStage(
            stage="claim_extraction",
            status="COMPLETED",
            duration_ms=stage_duration,
            details={"primary_claim": claim_info.primary_claim, "entities": claim_info.entities}
        ))

        # STAGE 3: Universal Search Query Generation (Groq / Instant Cached)
        t0 = time.perf_counter()
        cached = getattr(claim_info, "_cached_queries", None)
        queries = cached or await run_in_threadpool(self.query_generator.generate_queries, claim_info)
        search_queries = [q.strip() for q in queries if q and len(q.strip()) >= 3]

        stage_duration = round((time.perf_counter() - t0) * 1000, 2)
        pipeline_stages.append(PipelineStage(
            stage="query_generation",
            status="COMPLETED",
            duration_ms=stage_duration,
            details={"generated_queries": search_queries}
        ))

        # STAGE 4: Multi-Provider Concurrent Search (Google News + NewsAPI)
        t0 = time.perf_counter()
        raw_articles = []
        failed_providers = []

        newsapi_res, serpapi_res = await asyncio.gather(
            self.newsapi_service.search(search_queries),
            self.serpapi_service.search_google_news(search_queries),
            return_exceptions=True
        )

        for provider, result in (("NewsAPI", newsapi_res), ("Google News", serpapi_res)):
            if isinstance(result, list):
                raw_articles.extend(result)
            else:
                failed_providers.append(provider)
                logger.warning("%s search failed (%s)", provider, type(result).__name__)

        stage_duration = round((time.perf_counter() - t0) * 1000, 2)
        pipeline_stages.append(PipelineStage(
            stage="multi_source_search",
            status="DEGRADED" if failed_providers else "COMPLETED",
            duration_ms=stage_duration,
            details={"raw_sources_found": len(raw_articles), "failed_providers": failed_providers}
        ))

        # STAGE 5: Normalization & Deduplication
        t0 = time.perf_counter()
        submitted_urls = (request.url, extracted_article.url) if extracted_article else ()
        normalized_articles = self.source_normalizer.normalize_and_deduplicate(
            raw_articles, excluded_urls=submitted_urls
        )
        stage_duration = round((time.perf_counter() - t0) * 1000, 2)
        pipeline_stages.append(PipelineStage(
            stage="normalization_and_deduplication",
            status="COMPLETED",
            duration_ms=stage_duration,
            details={"unique_articles": len(normalized_articles)}
        ))

        # STAGE 6: Semantic Vector Indexing & Retrieval
        t0 = time.perf_counter()
        retrieved_evidence = await run_in_threadpool(
            self.vector_service.search, verification_id, normalized_articles,
            claim_info.primary_claim, settings.TOP_K_EVIDENCE
        )
        stage_duration = round((time.perf_counter() - t0) * 1000, 2)
        pipeline_stages.append(PipelineStage(
            stage="semantic_vector_retrieval",
            status="COMPLETED",
            duration_ms=stage_duration,
            details={"top_k_retrieved": len(retrieved_evidence)}
        ))

        # STAGE 7: Evidence Stance Analysis (Groq)
        t0 = time.perf_counter()
        analyzed_sources = await run_in_threadpool(
            self.evidence_analyzer.analyze_evidence_sources, claim_info, retrieved_evidence
        )
        stage_duration = round((time.perf_counter() - t0) * 1000, 2)
        pipeline_stages.append(PipelineStage(
            stage="evidence_stance_analysis",
            status="COMPLETED",
            duration_ms=stage_duration,
            details={"analyzed_count": len(analyzed_sources)}
        ))

        # STAGE 8: Verdict Synthesis & Explanation (Groq)
        t0 = time.perf_counter()
        total_time_ms = round((time.perf_counter() - pipeline_start) * 1000, 2)

        verdict_response = await run_in_threadpool(
            self.verdict_generator.synthesize_verdict,
            claim_info=claim_info,
            analyzed_sources=analyzed_sources,
            pipeline_stages=pipeline_stages,
            processing_time_ms=total_time_ms
        )

        stage_duration = round((time.perf_counter() - t0) * 1000, 2)
        pipeline_stages.append(PipelineStage(
            stage="verdict_synthesis",
            status="COMPLETED",
            duration_ms=stage_duration,
            details={"verdict": verdict_response.verdict.value, "confidence": verdict_response.confidence}
        ))

        verdict_response.pipeline_stages = pipeline_stages
        if failed_providers:
            verdict_response.limitations.append(
                f"Search failed for {', '.join(failed_providers)} during this verification."
            )

        # Update final elapsed time
        verdict_response.processing_time_ms = round((time.perf_counter() - pipeline_start) * 1000, 2)
        logger.info(
            f"[{verification_id}] Completed verification: verdict={verdict_response.verdict.value} "
            f"confidence={verdict_response.confidence}% ({verdict_response.processing_time_ms}ms)"
        )
        return verdict_response
