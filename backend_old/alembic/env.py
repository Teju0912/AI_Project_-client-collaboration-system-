import sys
import os
from dotenv import load_dotenv
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Backend folder ko path mein add karo taaki models.py import ho sake
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Base  # yahan apna models.py se Base import karo

load_dotenv()  # .env file load karo

config = context.config

# Yahi line important hai — DATABASE_URL ko alembic config mein set karo
db_url = os.getenv("DATABASE_URL")
if db_url:
    db_url = db_url.replace("%", "%%")
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata  # ab Base properly imported hai

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()