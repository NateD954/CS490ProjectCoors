"""The load balancer checks /health to decide whether the backend is running."""

from fastapi.testclient import TestClient

from app import main


def test_health_check_answers_without_a_login():
    response = TestClient(main.app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
