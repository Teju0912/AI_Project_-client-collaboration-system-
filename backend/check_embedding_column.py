from sqlalchemy import text
from database import engine

with engine.connect() as conn:
    result = conn.execute(text('''
        SELECT format_type(atttypid, atttypmod) AS column_type
        FROM pg_attribute
        WHERE attrelid = 'document_chunks'::regclass
          AND attname = 'embedding'
    '''))
    row = result.fetchone()
    if row:
        print(f"embedding column type: {row[0]}")
    else:
        print("Could not find the embedding column")
