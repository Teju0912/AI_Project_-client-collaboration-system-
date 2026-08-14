import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))


def test_document_chunk_model_exists():
    import models

    assert hasattr(models, "DocumentChunk")


def test_normalize_supabase_url_removes_rest_v1_suffix():
    from routers.documents import _normalize_supabase_url

    assert _normalize_supabase_url("https://example.supabase.co/rest/v1/") == "https://example.supabase.co"
    assert _normalize_supabase_url("https://example.supabase.co") == "https://example.supabase.co"


def test_requirement_analysis_document_fk_uses_set_null():
    import models

    fk = next(iter(models.RequirementAnalysis.__table__.c.document_id.foreign_keys))
    assert fk.ondelete == "SET NULL"
