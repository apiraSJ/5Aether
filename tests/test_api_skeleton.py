"""Tests for FastAPI Skeleton (API Contract v1.1).

Tests application startup, health endpoint, error handling,
security middleware, and basic routing.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aether.api.main import create_app
from aether.core.service_container import ServiceContainer


@pytest.fixture
def container() -> ServiceContainer:
    """Create a minimal service container for testing."""
    return ServiceContainer()


@pytest.fixture
def app(container: ServiceContainer):
    """Create FastAPI app with test container."""
    return create_app(container=container)


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app, base_url="http://localhost")


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_endpoint_exists(self, client: TestClient):
        """Health endpoint should exist and return 200."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_response_format(self, client: TestClient):
        """Health response should match expected format."""
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "aether-api"
        assert data["version"] == "1.0.0"

    def test_health_no_auth_required(self, client: TestClient):
        """Health endpoint should work without authentication."""
        response = client.get("/health")
        assert response.status_code == 200


class TestRootEndpoint:
    """Tests for the root endpoint."""

    def test_root_exists(self, client: TestClient):
        """Root endpoint should exist."""
        response = client.get("/")
        assert response.status_code == 200

    def test_root_contains_links(self, client: TestClient):
        """Root should contain links to docs and health."""
        data = client.get("/").json()
        assert "docs" in data
        assert "health" in data


class TestSecurityMiddleware:
    """Tests for local-only security middleware."""

    def _create_app(self):
        """Helper to create a fresh app instance."""
        from aether.api.main import create_app
        from aether.core.service_container import ServiceContainer
        container = ServiceContainer()
        return create_app(container=container)

    def test_localhost_allowed(self):
        """localhost should be allowed on protected endpoints."""
        app = self._create_app()
        client = TestClient(app, base_url="http://localhost")
        response = client.get("/api/v1/tasks")
        # Should not be 403 (might be 503/500 due to missing service, but not 403)
        assert response.status_code != 403

    def test_127_0_0_1_allowed(self):
        """127.0.0.1 should be allowed."""
        app = self._create_app()
        client = TestClient(app, base_url="http://127.0.0.1")
        response = client.get("/api/v1/tasks")
        assert response.status_code != 403

    def test_external_host_rejected(self):
        """External hosts should be rejected with 403 on protected endpoints."""
        app = self._create_app()
        external_client = TestClient(app, base_url="http://example.com")
        response = external_client.get("/api/v1/tasks")
        assert response.status_code == 403
        data = response.json()
        assert data["error"] == "forbidden"

    def test_0_0_0_0_rejected(self):
        """0.0.0.0 should be rejected."""
        app = self._create_app()
        zero_client = TestClient(app, base_url="http://0.0.0.0")
        response = zero_client.get("/api/v1/tasks")
        assert response.status_code == 403


class TestErrorHandling:
    """Tests for error handling and response format."""

    def test_404_not_found(self, client: TestClient):
        """Non-existent endpoints should return 404."""
        response = client.get("/api/v1/nonexistent")
        assert response.status_code == 404

    def test_error_response_format(self, client: TestClient):
        """Error responses should follow standard format."""
        response = client.get("/api/v1/nonexistent")
        data = response.json()
        assert "error" in data
        assert "message" in data
        # detail is optional
        assert "detail" in data


class TestAPIPrefix:
    """Tests for API version prefix."""

    def test_api_v1_prefix(self, client: TestClient):
        """All API routes should be under /api/v1."""
        # This test will pass once routes are registered
        response = client.get("/api/v1/tasks", headers={"Host": "localhost"})
        # Should not be 404 (route exists) - might be 400/500 due to missing service
        assert response.status_code != 404

    def test_no_routes_without_prefix(self, client: TestClient):
        """Routes should not be accessible without /api/v1 prefix."""
        response = client.get("/tasks", headers={"Host": "localhost"})
        assert response.status_code == 404


class TestDocumentationEndpoints:
    """Tests for OpenAPI documentation endpoints."""

    def test_docs_endpoint(self, client: TestClient):
        """Swagger UI should be available."""
        response = client.get("/docs")
        assert response.status_code == 200
        assert "swagger-ui" in response.text.lower()

    def test_redoc_endpoint(self, client: TestClient):
        """ReDoc should be available."""
        response = client.get("/redoc")
        assert response.status_code == 200

    def test_openapi_schema(self, client: TestClient):
        """OpenAPI JSON schema should be available."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"] == "Aether Mark-1 API"
        assert schema["info"]["version"] == "1.0.0"


class TestCORS:
    """Tests for CORS policy (should be disabled for MVP)."""

    def test_no_cors_headers(self, client: TestClient):
        """CORS headers should not be present in MVP."""
        response = client.options("/health", headers={"Origin": "http://example.com"})
        # No Access-Control-Allow-Origin header
        assert "access-control-allow-origin" not in response.headers


class TestAPIRoutesRegistered:
    """Tests that API routes are properly registered."""

    def test_tasks_routes_exist(self, client: TestClient):
        """Task routes should be registered under /api/v1."""
        # These will fail with 500/503 without ScheduleService, but not 404
        for method, path in [
            ("GET", "/api/v1/tasks"),
            ("POST", "/api/v1/tasks"),
            ("GET", "/api/v1/tasks/test-id"),
        ]:
            response = client.request(method, path, headers={"Host": "localhost"})
            assert response.status_code != 404, f"{method} {path} not found"

    def test_calendar_routes_exist(self, client: TestClient):
        """Calendar routes should be registered."""
        for method, path in [
            ("GET", "/api/v1/calendar/day?date=2026-10-20"),
            ("GET", "/api/v1/calendar/week?date=2026-10-20"),
            ("GET", "/api/v1/calendar/month?year=2026&month=10"),
        ]:
            response = client.request(method, path, headers={"Host": "localhost"})
            assert response.status_code != 404, f"{method} {path} not found"

    def test_evidence_endpoint_not_registered(self, client: TestClient):
        """Evidence endpoint should NOT be registered in Sprint 1."""
        # The route should not exist at all
        response = client.post(
            "/api/v1/tasks/test-id/evidence",
            headers={"Host": "localhost"},
            json={"source": "web", "source_ref": "test", "excerpt": "test"},
        )
        # Should be 404 (not found) since endpoint is excluded from Sprint 1
        assert response.status_code == 404