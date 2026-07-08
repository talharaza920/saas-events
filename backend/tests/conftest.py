"""Shared fixtures for the platform-era tests. In-memory SQLite, fully offline.

`admin_emails` is EMPTY here so the only platform admin is the bare dev token
(sub "dev") — ordinary `<token>:<email>` users have exactly the access their
membership rows grant, which is what the authz tests need to pin down.
Pre-platform test files define their own same-named fixtures, which shadow
these (pytest resolves the nearest fixture), so nothing there changes.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.db import Base, get_db
from app.main import app
from tests.helpers import DEV_TOKEN


def _settings(**overrides) -> Settings:
    base = dict(
        environment="development",
        dev_admin_token=DEV_TOKEN,
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="sb_publishable_test",
        admin_emails="",
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def make_client(db_session):
    def _make(**setting_overrides) -> TestClient:
        s = _settings(**setting_overrides)
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[get_settings] = lambda: s
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


@pytest.fixture
def client(make_client):
    return make_client()
