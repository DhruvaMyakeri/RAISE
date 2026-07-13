"""API layer: auth gate, rate limiting, input validation, error sanitization.

Fully offline — the pipeline itself is mocked; only the FastAPI layer runs.
"""

from __future__ import annotations

import main
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    # Auth off, rate limiting off by default; individual tests re-enable.
    monkeypatch.delenv("VANTAGE_API_TOKEN", raising=False)
    main.limiter.enabled = False
    with TestClient(main.app, raise_server_exceptions=False) as c:
        yield c
    main.limiter.enabled = False


@pytest.fixture()
def no_pipeline(monkeypatch):
    """Fail loudly if any test in this module actually reaches the pipeline."""

    def _boom(*args, **kwargs):
        raise AssertionError("run_pipeline must not be called")

    monkeypatch.setattr(main, "run_pipeline", _boom)
    return _boom


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_companies_lists_three_demos(client):
    data = client.get("/api/companies").json()
    assert len(data) == 3
    assert {c["category_key"] for c in data} == {"customer_support", "marketing", "maintenance"}


def test_unknown_company_source_404(client):
    assert client.get("/api/companies/nope/source").status_code == 404


def test_unknown_benchmark_category_404(client):
    assert client.get("/api/benchmarks/nope").status_code == 404


def test_run_unknown_category_400(client, no_pipeline):
    r = client.post("/api/run", json={"category": "nope"})
    assert r.status_code == 400


def test_inline_company_missing_numeric_fields_422_before_llm(client, no_pipeline):
    r = client.post(
        "/api/run",
        json={
            "category": "customer_support",
            "company": {
                "project_category": "Customer Support AI",
                "current_operations": {"annual_ticket_volume": 1000},
                "proposed_project": {"initial_build_cost_usd": 100000},
            },
        },
    )
    assert r.status_code == 422
    assert "Invalid company profile" in r.json()["detail"]


def test_inline_company_absurd_values_rejected(client, no_pipeline):
    r = client.post(
        "/api/run",
        json={
            "category": "marketing",
            "company": {
                "project_category": "Marketing AI",
                "current_operations": {
                    "monthly_ad_spend_usd": 1000,
                    "current_conversion_rate": 5.0,  # >1: not a rate
                    "average_order_value_usd": 50,
                },
                "proposed_project": {
                    "name": "X",
                    "initial_build_cost_usd": 1000,
                    "annual_inference_budget_usd_claimed": 10,
                    "claimed_conversion_lift_rate": 0.3,
                },
            },
        },
    )
    assert r.status_code == 422


def test_valid_inline_company_reaches_pipeline(client, monkeypatch, meridian_company):
    monkeypatch.setattr(main, "run_pipeline", lambda *a, **k: {"ok": True})
    r = client.post(
        "/api/run",
        json={"category": "customer_support", "company": meridian_company},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_500_detail_is_generic(client, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("secret internal path D:\\keys\\vultr.txt")

    monkeypatch.setattr(main, "run_pipeline", _boom)
    r = client.post("/api/run", json={"category": "customer_support"})
    assert r.status_code == 500
    assert "secret" not in r.text
    assert "vultr" not in r.text.lower()
    assert r.json()["detail"] == "Pipeline run failed. See server logs for details."


class TestAuth:
    def test_run_requires_token_when_configured(self, client, monkeypatch, no_pipeline):
        monkeypatch.setenv("VANTAGE_API_TOKEN", "sekret-token")
        r = client.post("/api/run", json={"category": "customer_support"})
        assert r.status_code == 401

    def test_wrong_token_rejected(self, client, monkeypatch, no_pipeline):
        monkeypatch.setenv("VANTAGE_API_TOKEN", "sekret-token")
        r = client.post(
            "/api/run",
            json={"category": "customer_support"},
            headers={"Authorization": "Bearer wrong"},
        )
        assert r.status_code == 401

    def test_correct_token_accepted(self, client, monkeypatch):
        monkeypatch.setenv("VANTAGE_API_TOKEN", "sekret-token")
        monkeypatch.setattr(main, "run_pipeline", lambda *a, **k: {"ok": True})
        r = client.post(
            "/api/run",
            json={"category": "customer_support"},
            headers={"Authorization": "Bearer sekret-token"},
        )
        assert r.status_code == 200

    def test_sse_accepts_token_query_param(self, client, monkeypatch):
        monkeypatch.setenv("VANTAGE_API_TOKEN", "sekret-token")

        def fake_run(category_key, company, emitter=None, cancel=None, parallel=True):
            emitter.emit("memo_ready", {"stub": True})
            return {"stub": True}

        monkeypatch.setattr(main, "run_pipeline", fake_run)
        with client.stream(
            "GET",
            "/api/run/stream?category=customer_support&token=sekret-token",
        ) as r:
            assert r.status_code == 200
            body = "".join(r.iter_text())
        assert "memo_ready" in body

    def test_read_only_endpoints_stay_open(self, client, monkeypatch):
        monkeypatch.setenv("VANTAGE_API_TOKEN", "sekret-token")
        assert client.get("/api/companies").status_code == 200
        assert client.get("/health").status_code == 200


def test_early_access_register_and_dedupe(client, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "EARLY_ACCESS_FILE", tmp_path / "signups.jsonl")
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "_signup_emails", None)

    r1 = client.post("/api/early-access", json={"email": "A@Example.com"})
    assert r1.json()["status"] == "registered"
    r2 = client.post("/api/early-access", json={"email": "a@example.com"})
    assert r2.json()["status"] == "already_registered"
    assert (tmp_path / "signups.jsonl").read_text(encoding="utf-8").count("\n") == 1


def test_early_access_invalid_email_400(client):
    assert client.post("/api/early-access", json={"email": "not-an-email"}).status_code == 400


def test_rate_limit_fires(client, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "EARLY_ACCESS_FILE", tmp_path / "signups.jsonl")
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "_signup_emails", None)
    main.limiter.enabled = True
    try:
        statuses = [
            client.post("/api/early-access", json={"email": f"u{i}@example.com"}).status_code
            for i in range(8)
        ]
    finally:
        main.limiter.enabled = False
    assert 429 in statuses  # SIGNUP_RATE_LIMIT default 5/minute
