import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))


def test_document_chunk_model_exists():
    import models

    assert hasattr(models, "DocumentChunk")
