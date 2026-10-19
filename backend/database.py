"""PostgreSQL connection configuration shared by the API and migrations."""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError("Set DATABASE_URL in .env before starting the API. See README.md.")
if make_url(database_url).drivername != "postgresql+psycopg":
    raise RuntimeError("This project requires PostgreSQL with the psycopg driver.")

engine = create_engine(database_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_session():
    with SessionLocal() as session:
        yield session
