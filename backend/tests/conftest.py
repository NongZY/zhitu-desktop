import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DB = Path(__file__).parent / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["JWT_SECRET_KEY"] = "test-only-secret-key-with-enough-entropy"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"


@pytest.fixture()
def client():
    from app.database import Base, engine
    from app.main import app

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def create_learner(client):
    def create(email: str, name: str = "测试学习者") -> dict[str, str]:
        password = "Learning123!"
        registration = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "name": name},
        )
        assert registration.status_code == 201, registration.text
        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert login.status_code == 200, login.text
        return {"Authorization": f"Bearer {login.json()['access_token']}"}

    return create
