import pytest


@pytest.fixture()
def client():
    """API client with the lifespan running (demo seed) against a fresh in-memory store."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.services import container

    container.reset_for_tests()
    with TestClient(create_app()) as c:
        yield c
    container.reset_for_tests()
