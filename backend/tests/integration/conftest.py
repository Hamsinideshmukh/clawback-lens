"""Integration tests run against a real PostgreSQL (DATABASE_URL), migrated
with Alembic once per session and truncated between tests."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.session import Base, engine

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip("PostgreSQL not available (set DATABASE_URL)")
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
def client() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def create_case(client: TestClient, reason_code: str = "4530", **overrides: str) -> dict:
    payload = {
        "transaction_id": "txn_1",
        "merchant_name": "Orbit Retail",
        "amount": "120.50",
        "reason_code": reason_code,
        **overrides,
    }
    response = client.post("/api/v1/cases", json=payload)
    assert response.status_code == 201, response.text
    return response.json()
