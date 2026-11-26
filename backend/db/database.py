"""
Database Engine & Session Management using SQLAlchemy
"""

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.core.config import settings

database_path = settings.DATABASE_DIR / "news_verification.db"
DATABASE_URL = URL.create("sqlite", database=str(database_path))

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=settings.DEBUG,
    hide_parameters=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db_session():
    """Dependency generator for FastAPI routes"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all database tables on startup"""
    import backend.db.models  # Ensure models are imported
    database_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
