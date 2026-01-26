"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient

from src.api.server import create_app
from src.config import ApiConfig


@pytest.fixture
def client():
    """Create test client."""
    config = ApiConfig(host="127.0.0.1", port=8080)
    app = create_app(config)
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_ok(self, client):
        """Health check should return status ok."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert data["data"]["status"] == "ok"
        assert "version" in data["data"]


class TestTokenEndpoint:
    """Tests for /token/{address} endpoint."""

    def test_invalid_address_returns_400(self, client):
        """Invalid address should return 400."""
        response = client.get("/token/invalid")
        assert response.status_code == 400

    def test_valid_address_format_accepted(self, client):
        """Valid address format should be accepted."""
        # This will return 404 since no database, but should not be 400
        response = client.get("/token/So11111111111111111111111111111111111111112")
        assert response.status_code in [200, 404]

    def test_short_address_returns_400(self, client):
        """Short address should return 400."""
        response = client.get("/token/abc123")
        assert response.status_code == 400


class TestScoreEndpoint:
    """Tests for /token/{address}/score endpoint."""

    def test_score_invalid_address(self, client):
        """Invalid address should return 400."""
        response = client.get("/token/invalid/score")
        assert response.status_code == 400


class TestRiskyTokensEndpoint:
    """Tests for /tokens/risky endpoint."""

    def test_risky_returns_list(self, client):
        """Should return data wrapper with list."""
        response = client.get("/tokens/risky")
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_risky_respects_limit(self, client):
        """Should respect limit parameter."""
        response = client.get("/tokens/risky?limit=5")
        assert response.status_code == 200

    def test_risky_rejects_invalid_limit(self, client):
        """Should reject invalid limit."""
        response = client.get("/tokens/risky?limit=0")
        assert response.status_code == 422  # Validation error

        response = client.get("/tokens/risky?limit=500")
        assert response.status_code == 422


class TestOpportunitiesEndpoint:
    """Tests for /tokens/opportunities endpoint."""

    def test_opportunities_returns_list(self, client):
        """Should return data wrapper with list."""
        response = client.get("/tokens/opportunities")
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)


class TestAlertsEndpoint:
    """Tests for /alerts endpoint."""

    def test_alerts_returns_list(self, client):
        """Should return data wrapper with list."""
        response = client.get("/alerts")
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_alerts_filter_by_type(self, client):
        """Should accept type filter."""
        response = client.get("/alerts?type=RUG_WARNING")
        assert response.status_code == 200

    def test_alerts_filter_by_token(self, client):
        """Should accept token filter with valid address."""
        response = client.get("/alerts?token=So11111111111111111111111111111111111111112")
        assert response.status_code == 200


class TestWatchlistEndpoints:
    """Tests for watchlist endpoints."""

    def test_add_to_watchlist(self, client):
        """Should add valid address to watchlist."""
        response = client.post("/watch/So11111111111111111111111111111111111111112")
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert data["data"]["added"] is True

    def test_add_invalid_address(self, client):
        """Should reject invalid address."""
        response = client.post("/watch/invalid")
        assert response.status_code == 400

    def test_remove_from_watchlist(self, client):
        """Should remove address from watchlist."""
        response = client.delete("/watch/So11111111111111111111111111111111111111112")
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert data["data"]["removed"] is True


class TestResponseFormat:
    """Tests for response format consistency."""

    def test_success_responses_have_data_wrapper(self, client):
        """All success responses should have data wrapper."""
        endpoints = [
            "/health",
            "/tokens/risky",
            "/tokens/opportunities",
            "/alerts",
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 200
            data = response.json()
            assert "data" in data, f"Missing data wrapper in {endpoint}"
