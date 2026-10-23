import os

from alembic import context
from sqlalchemy import create_engine

from app import models  # noqa: F401  (enregistre les tables)
from app.db import Base

target_metadata = Base.metadata
URL = os.getenv("DATABASE_URL", "sqlite:///./transport.db")

with create_engine(URL).connect() as connection:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
