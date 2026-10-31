import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.database.models import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

URL = os.environ.get("MP_DATABASE_URL", "postgresql+psycopg://marketpulse:marketpulse@localhost:5432/marketpulse")
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(URL)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
