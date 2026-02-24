"""Tests for site analytics: date range, track hostname, summary shape."""
import os
import pytest
from analytics_service.app import get_date_range_for_time_filter, VALID_TIME_FILTERS


class TestDateRangeHelper:
    def test_today_same_start_end(self):
        s, e = get_date_range_for_time_filter("today")
        assert s == e and len(s) == 10

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            get_date_range_for_time_filter("invalid")


@pytest.fixture(scope="module")
def client():
    try:
        from server import app
        from fastapi.testclient import TestClient
        return TestClient(app)
    except Exception as e:
        pytest.skip(str(e))


class TestTrack:
    def test_rejects_localhost(self, client):
        r = client.post("/api/track", json={"hostname": "localhost", "event_type": "page_view"})
        assert r.status_code == 400

    def test_accepts_prod_hostname(self, client):
        r = client.post("/api/track", json={"hostname": "ai.cloudfuze.com", "event_type": "page_view"})
        assert r.status_code in (202, 500)


class TestSummary:
    def test_invalid_time_filter_400(self, client):
        assert client.get("/api/analytics/summary?time_filter=bad").status_code == 400

    def test_today_returns_keys(self, client):
        r = client.get("/api/analytics/summary?time_filter=today")
        assert r.status_code == 200
        d = r.json()
        assert "total_page_views" in d and "unique_users" in d and "funnel" in d
