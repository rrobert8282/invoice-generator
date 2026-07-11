import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app
from app import models  # noqa: F401 -- registers models on Base.metadata


@pytest.fixture
def db_session():
    # Fresh in-memory SQLite DB per test, so tests never see each other's data.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    session = TestingSessionLocal()
    yield session
    session.close()

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def _register_and_login(raw_client: TestClient, email: str, password: str = "testpassword123") -> str:
    raw_client.post("/auth/register", json={"email": email, "password": password})
    response = raw_client.post("/auth/login", data={"username": email, "password": password})
    return response.json()["access_token"]


@pytest.fixture
def client(db_session):
    # Pre-authenticated as a default test user. This is the fixture nearly every
    # existing test uses, so making it carry a valid token by default means Phase
    # 1-5 tests didn't need to change at all when auth was added in Phase 6.
    raw_client = TestClient(app)
    token = _register_and_login(raw_client, "default@example.com")
    raw_client.headers.update({"Authorization": f"Bearer {token}"})
    return raw_client


@pytest.fixture
def unauthenticated_client(db_session):
    # Same DB (db_session already wired the override onto `app`), but no token --
    # for testing registration/login itself and rejection of unauthenticated requests.
    return TestClient(app)


@pytest.fixture
def second_user_client(db_session, client):
    # A second, differently-authenticated user against the SAME database as `client`,
    # for testing that users can't see or touch each other's data.
    raw_client = TestClient(app)
    token = _register_and_login(raw_client, "second@example.com")
    raw_client.headers.update({"Authorization": f"Bearer {token}"})
    return raw_client
