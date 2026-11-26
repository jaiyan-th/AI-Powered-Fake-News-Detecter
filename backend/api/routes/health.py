"""
Health Check and Diagnostics Route Handler: GET /api/v1/health
"""

from datetime import datetime, timezone
import logging
from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from backend.schemas.health import HealthResponse
from backend.core.config import settings
from backend.db.models import User, VerificationHistory
from backend.services.groq_service import GroqService
from backend.services.newsapi_service import NewsAPIService
from backend.services.serpapi_service import SerpAPIService
from backend.services.vector_service import VectorSearchService
from backend.api.deps import (
    get_db, get_groq_service, get_newsapi_service, get_serpapi_service, get_vector_service
)

router = APIRouter(prefix="/api/v1", tags=["Health"])
logger = logging.getLogger(__name__)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System Health and Diagnostics",
    description="Returns status of the FastAPI backend application and its core services (Groq, NewsAPI, SerpAPI, Vector Search Engine)."
)
def check_system_health(
    response: Response,
    db: Session = Depends(get_db),
    groq_service: GroqService = Depends(get_groq_service),
    newsapi_service: NewsAPIService = Depends(get_newsapi_service),
    serpapi_service: SerpAPIService = Depends(get_serpapi_service),
    vector_service: VectorSearchService = Depends(get_vector_service)
) -> HealthResponse:
    groq_ok = groq_service.is_available()
    newsapi_ok = newsapi_service.is_configured()
    serpapi_ok = serpapi_service.is_configured()
    vector_ok = vector_service.is_available()

    try:
        db.execute(select(User.id).limit(1)).first()
        db.execute(select(VerificationHistory.id).limit(1)).first()
        database_ok = True
    except SQLAlchemyError:
        logger.exception("Database health check failed")
        database_ok = False
        response.status_code = 503

    overall_status = "healthy" if groq_ok and vector_ok else "degraded"
    if not database_ok:
        overall_status = "unavailable"

    dependencies = {
        "database": {"status": "operational" if database_ok else "unavailable"},
        "groq_llm": {
            "status": "operational" if groq_ok else "unconfigured_or_unavailable",
            "role": "Claim extraction, query generation, stance analysis, verdict synthesis"
        },
        "news_api": {
            "status": "operational" if newsapi_ok else "unconfigured",
            "role": "Real-time news retrieval"
        },
        "serp_api": {
            "status": "operational" if serpapi_ok else "unconfigured",
            "role": "Google News broad search"
        },
        "vector_search_engine": {
            "status": "operational" if vector_ok else "unavailable",
            "role": "In-memory semantic vector index & similarity retrieval"
        },
        "embedding_engine": {
            "status": "initialized_on_demand",
            "model": settings.EMBEDDING_MODEL,
            "dimension": settings.EMBEDDING_DIM
        }
    }

    return HealthResponse(
        status=overall_status,
        application="running",
        dependencies=dependencies,
        timestamp=datetime.now(timezone.utc).isoformat()
    )
