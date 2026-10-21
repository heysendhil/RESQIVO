from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def preflight(origin: str):
    return client.options(
        "/validate",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


def test_local_frontend_origin_is_allowed() -> None:
    response = preflight("http://localhost:3000")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_unlisted_origin_is_not_allowed() -> None:
    response = preflight("https://example.com")

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_simple_request_from_allowed_origin_gets_cors_header() -> None:
    response = client.get("/health", headers={"Origin": "http://127.0.0.1:3000"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
