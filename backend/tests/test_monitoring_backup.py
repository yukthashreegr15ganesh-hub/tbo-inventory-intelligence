"""Telemetry & Monitoring Automation Test Suite.

Verifies:
1. /api/metrics telemetry dashboard payload
2. /api/health subsystem database connectivity & solver check
3. Resource tracking (CPU, RAM, Uptime)
4. Traffic counters (status codes, endpoint latencies)
5. Solver execution timing tracking
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from app import app
from pipeline.monitoring import (
    record_api_metric,
    record_optimization_metric,
    get_system_telemetry,
    check_database_health,
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_metrics_endpoint_schema(client):
    """Verify /api/metrics returns full system telemetry dashboard."""
    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    data = resp.json()

    # Core sections
    assert "uptime" in data
    assert "resources" in data
    assert "database" in data
    assert "models" in data
    assert "traffic" in data
    assert "optimizer_performance" in data
    assert "errors" in data

    # Sub-metrics
    assert data["database"]["status"] == "HEALTHY"
    assert data["models"]["solver"] == "HiGHS / PuLP MILP"
    assert "cpu_percent" in data["resources"]
    assert "memory_rss_mb" in data["resources"]


def test_health_check_database_probe(client):
    """Verify /api/health includes database connection status."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "HEALTHY"
    assert "database" in data
    assert data["database"]["status"] == "HEALTHY"
    assert data["database"]["latency_ms"] >= 0


def test_solver_telemetry_recording():
    """Verify record_optimization_metric appends solve timing data."""
    record_optimization_metric(1.45, 500000000.0, "OPTIMAL")
    telemetry = get_system_telemetry()
    opt_perf = telemetry["optimizer_performance"]
    assert opt_perf["total_solves"] > 0
    assert opt_perf["max_solve_seconds"] >= 1.45
