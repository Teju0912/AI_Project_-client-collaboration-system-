"""
reindex_all.py
One-time script: deletes every existing DocumentChunk (old 384-dim
MiniLM embeddings) and re-indexes every Document from scratch using the
new Gemini embeddings (768-dim).

Run this ONCE after:
  1. Updating rag_utils.py to use Gemini embeddings
  2. Updating models.py embedding column to Vector(768)
  3. Running `alembic upgrade head`
  4. Setting GEMINI_API_KEY in your .env

Usage (from your backend folder, with venv active):
    python reindex_all.py
"""

import sys
import time

from database import SessionLocal
import models
import rag_utils


def main():
    ok, msg = rag_utils.check_rag_dependencies()
    print(f"Dependency check: {msg}")
    if not ok:
        print("Fix the above issue before running this script. Aborting.")
        sys.exit(1)

    db = SessionLocal()
    try:
        # Step 1: wipe every existing chunk (old 384-dim embeddings —
        # incompatible with the new 768-dim column).
        deleted = db.query(models.DocumentChunk).delete(synchronize_session=False)
        db.commit()
        print(f"Deleted {deleted} old chunk(s).")

        # Step 2: reindex every document.
        documents = db.query(models.Document).all()
        total = len(documents)
        print(f"Found {total} document(s) to reindex.\n")

        success = 0
        failed = []

        for i, doc in enumerate(documents, start=1):
            print(f"[{i}/{total}] {doc.filename} ...", end=" ", flush=True)
            try:
                count = rag_utils.process_document_for_rag(
                    db,
                    doc.id,
                    doc.storage_path,
                    doc.organization_id,
                    doc.project_id,
                )
                if count > 0:
                    print(f"OK ({count} chunks)")
                    success += 1
                else:
                    print("SKIPPED (no extractable text / unsupported type)")
            except Exception as exc:
                print(f"FAILED ({type(exc).__name__}: {exc})")
                failed.append(doc.filename)
                db.rollback()

            # Small delay so we don't hammer the Gemini API rate limits.
            time.sleep(0.3)

        print("\n----- Summary -----")
        print(f"Reindexed successfully: {success}/{total}")
        if failed:
            print(f"Failed: {len(failed)} -> {', '.join(failed)}")
        else:
            print("No failures.")

    finally:
        db.close()


if __name__ == "__main__":
    main()