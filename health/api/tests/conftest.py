"""Tests need a Postgres. Set HEALTH_TEST_PG_URL (default: local postgres on 5432,
db health_test). The database is dropped and recreated per session."""
from __future__ import annotations

import os

import psycopg
import pytest

TEST_URL = os.environ.get("HEALTH_TEST_PG_URL", "postgresql://postgres:postgres@localhost:5432/health_test")


def _dbname(url: str) -> str:
    return psycopg.conninfo.conninfo_to_dict(url)["dbname"]


def _admin_url(url: str) -> str:
    return psycopg.conninfo.make_conninfo(url, dbname="postgres")


@pytest.fixture(scope="session")
def pg_url() -> str:
    dbname = _dbname(TEST_URL)
    try:
        with psycopg.connect(_admin_url(TEST_URL), autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{dbname}"')
            c.execute(f'CREATE DATABASE "{dbname}"')
    except psycopg.OperationalError as e:
        pytest.skip(f"no test Postgres at {TEST_URL}: {e}")
    os.environ["HEALTH_PG_URL"] = TEST_URL
    os.environ.pop("HEALTH_APP_TOKEN", None)
    os.environ["HEALTH_DATA_DIR"] = os.environ.get("HEALTH_TEST_DATA_DIR", "/tmp/health-test-data")
    return TEST_URL


@pytest.fixture(scope="session")
def client(pg_url: str):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c
