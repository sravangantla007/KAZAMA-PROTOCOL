from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"
    assert "timestamp" in data


def test_mock_scenarios_endpoint():
    resp = client.get("/api/mock-scenarios")
    assert resp.status_code == 200
    data = resp.json()
    assert "scenarios" in data
    assert len(data["scenarios"]) >= 1
    assert data["scenarios"][0]["id"] == "scholarship_scenario"


def test_static_index_html():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "KAZAMA PROTOCOL" in resp.text
    assert "canvas-container" in resp.text


def test_static_css_and_js():
    resp_css = client.get("/css/style.css")
    assert resp_css.status_code == 200
    assert "--bg-space" in resp_css.text

    resp_scene = client.get("/js/scene.js")
    assert resp_scene.status_code == 200
    assert "NeuralSpaceScene" in resp_scene.text

    resp_app = client.get("/js/app.js")
    assert resp_app.status_code == 200
    assert "triggerAnalysis" in resp_app.text


def test_analyze_endpoint_mock_mode():
    payload = {
        "query": "What are the eligibility criteria and deadlines for NMES?",
        "decision": "Apply for scholarship as final year student",
        "urls": [],
        "files": [],
        "options": {
            "mock_mode": True,
            "mock_scenario": "scholarship_scenario",
            "include_debug": True,
        }
    }
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert len(data["sources"]) == 6
    assert data["synthesis"]["topic_summary"] is not None
    assert len(data["synthesis"]["facts"]) > 0
    assert data["decision_payload"] is not None
    assert data["decision_payload"]["decision_readiness"] in [
        "GO", "PROCEED_WITH_CAUTION", "VERIFY_FIRST", "STOP_DO_NOT_PROCEED"
    ]


def test_analyze_validation_error():
    # query too short (< 3 chars)
    payload = {
        "query": "x",
        "urls": [],
        "files": [],
    }
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 422
    data = resp.json()
    assert data["status"] == "error"
    assert data["error"]["code"] == "VALIDATION_ERROR"

