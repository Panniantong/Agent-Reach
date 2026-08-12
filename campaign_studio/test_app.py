"""Fast local contract checks that never contact OpenAI."""

from fastapi.testclient import TestClient

from campaign_studio.app import _image_count, app

client = TestClient(app)


def test_health_and_frontend() -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert "Campaign Concept Studio" in client.get("/").text


def test_invalid_brief_is_rejected() -> None:
    response = client.post("/api/campaigns", json={})
    assert response.status_code == 422


def test_missing_server_key_is_safe(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post(
        "/api/campaigns",
        json={
            "campaign_brief": "Launch a thoughtful new product to a focused audience.",
            "audience": "Creative teams",
            "product": "A planning tool",
            "tone": "Warm",
            "channels": ["Web"],
        },
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "OPENAI_API_KEY is not configured on the server."}


def test_image_count_is_safe_and_clamped(monkeypatch) -> None:
    monkeypatch.setenv("CAMPAIGN_IMAGE_COUNT", "not-a-number")
    assert _image_count() == 2
    monkeypatch.setenv("CAMPAIGN_IMAGE_COUNT", "99")
    assert _image_count() == 3
    monkeypatch.setenv("CAMPAIGN_IMAGE_COUNT", "0")
    assert _image_count() == 1
