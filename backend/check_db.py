import os
from sqlalchemy import create_engine, text

url = os.getenv('DATABASE_URL')
print('DATABASE_URL present:', bool(url))
if url:
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            print(conn.execute(text('select current_database()')).scalar())
    except Exception as exc:
        print('DB connection failed:', exc)
