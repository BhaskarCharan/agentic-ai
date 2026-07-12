"""Contract tests for the integrations routes.

Use a fake `IntegrationService` via FastAPI's `dependency_overrides` instead
of a real one - these must never call the actual Composio API (no API key
needed in CI, and no risk of creating real auth configs/connections against
someone's real account just by running the test suite).
"""

from app.api.dependencies import get_integration_service
from app.main import app
from app.services.integration_service import IntegrationStatus


class _FakeIntegrationService:
    async def list_statuses(self) -> list[IntegrationStatus]:
        return [
            IntegrationStatus(toolkit="gmail", connected=False),
            IntegrationStatus(
                toolkit="linkedin",
                connected=True,
                connected_since="2026-01-01T00:00:00Z",
                label="Jane Doe",
            ),
        ]

    async def initiate_connection(self, toolkit: str) -> str:
        if toolkit not in ("gmail", "linkedin"):
            raise ValueError(f"Unsupported toolkit: {toolkit!r}")
        return f"https://connect.composio.dev/link/fake-{toolkit}"

    async def disconnect(self, toolkit: str) -> None:
        if toolkit not in ("gmail", "linkedin"):
            raise ValueError(f"Unsupported toolkit: {toolkit!r}")


def _use_fake_integration_service():
    app.dependency_overrides[get_integration_service] = _FakeIntegrationService
    return app.dependency_overrides.pop


async def test_list_integrations_reports_status(client):
    pop_override = _use_fake_integration_service()
    try:
        resp = await client.get("/api/integrations")
        assert resp.status_code == 200
        body = resp.json()
        assert {
            "toolkit": "gmail",
            "connected": False,
            "connected_since": None,
            "label": None,
        } in body
        assert any(
            item["toolkit"] == "linkedin"
            and item["connected"]
            and item["connected_since"]
            and item["label"] == "Jane Doe"
            for item in body
        )
    finally:
        pop_override(get_integration_service, None)


async def test_connect_unknown_toolkit_404s(client):
    pop_override = _use_fake_integration_service()
    try:
        resp = await client.post("/api/integrations/not-a-real-toolkit/connect")
        assert resp.status_code == 404
    finally:
        pop_override(get_integration_service, None)


async def test_connect_known_toolkit_returns_redirect_url(client):
    pop_override = _use_fake_integration_service()
    try:
        resp = await client.post("/api/integrations/gmail/connect")
        assert resp.status_code == 200
        assert resp.json()["redirect_url"] == "https://connect.composio.dev/link/fake-gmail"
    finally:
        pop_override(get_integration_service, None)


async def test_disconnect_known_toolkit_returns_204(client):
    pop_override = _use_fake_integration_service()
    try:
        resp = await client.delete("/api/integrations/linkedin")
        assert resp.status_code == 204
    finally:
        pop_override(get_integration_service, None)


async def test_disconnect_unknown_toolkit_404s(client):
    pop_override = _use_fake_integration_service()
    try:
        resp = await client.delete("/api/integrations/not-a-real-toolkit")
        assert resp.status_code == 404
    finally:
        pop_override(get_integration_service, None)
