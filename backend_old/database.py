"""
database.py
Creates the SQLAlchemy engine and session pointed at your Supabase Postgres
database. Every other file that needs the database imports from here.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env early (covers cwd-relative runs)
load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent

# Load .env from project root (parent of backend/), not only cwd — overrides
# the earlier load_dotenv() if a root-level .env exists.
load_dotenv(ROOT_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL:
    # NOTE: production/Supabase usage expects DATABASE_URL to be set, e.g.
    #   "DATABASE_URL is not set. Copy .env.example to .env and fill in your "
    #   "Supabase connection string (Project Settings -> Database -> Connection "
    #   "string -> URI)."
    # For local development we don't hard-fail; we fall back to SQLite instead.
    print("DATABASE_URL is missing. Falling back to a local SQLite database for development.")
    DATABASE_URL = f"sqlite:///{BASE_DIR / 'local_dev.db'}"

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    # pool_pre_ping avoids "connection has been closed" errors if Supabase's
    # free-tier database goes idle and needs to wake back up.
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

    # Register pgvector so VECTOR columns + cosine_distance work over psycopg2.
    try:
        from sqlalchemy import event
        from pgvector.psycopg2 import register_vector

        @event.listens_for(engine, "connect")
        def _register_pgvector(dbapi_connection, connection_record):  # noqa: ARG001
            register_vector(dbapi_connection)
    except Exception as exc:  # pragma: no cover
        print(f"pgvector register skipped: {exc}")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def initialize_database() -> None:
    # Ensure vector extension exists before create_all builds VECTOR columns.
    if not DATABASE_URL.startswith("sqlite"):
        try:
            from sqlalchemy import text

            with engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception as exc:  # pragma: no cover
            print(f"vector extension setup skipped: {exc}")

    # Import models so DocumentChunk / other tables register on Base.metadata.
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    if not DATABASE_URL.startswith("sqlite"):
        return
    try:
        from security import hash_password
        import models
        db = SessionLocal()
        try:
            if db.query(models.Organization).count() == 0:
                org = models.Organization(name="Local Organization")
                db.add(org)
                db.flush()
                admin_user = models.User(
                    organization_id=org.id,
                    name="Admin",
                    email="admin@example.com",
                    password_hash=hash_password("password123"),
                    role="admin",
                )
                db.add(admin_user)
                db.commit()
        finally:
            db.close()
    except Exception as exc:  # pragma: no cover - defensive guard
        print(f"Local database initialization warning: {exc}")


def get_db():
    """FastAPI dependency — yields a database session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()