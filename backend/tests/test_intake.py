"""Custom intake: field specs, profile building, document parsing, extraction
normalization, and the prepare -> stream flow. LLM extraction itself is mocked
here; live extraction quality is scored by evals/eval_intake.py.
"""

from __future__ import annotations

import io
import json

import main
import pytest
from conftest import make_tool_completion
from fastapi.testclient import TestClient

import agents.intake as intake
from api.intake_fields import INTAKE_FIELDS, build_profile
from api.schemas import validate_company_profile

# ---------------------------------------------------------------------------
# Minimal one-page PDF builder (correct xref) for parser tests
# ---------------------------------------------------------------------------

def build_pdf(lines: list[str]) -> bytes:
    def esc(s: str) -> str:
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    content_parts = ["BT /F1 11 Tf 50 750 Td 14 TL"]
    for i, line in enumerate(lines):
        if i > 0:
            content_parts.append("T*")
        content_parts.append(f"({esc(line)}) Tj")
    content_parts.append("ET")
    stream = " ".join(content_parts).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode())
        out.write(obj)
        out.write(b"\nendobj\n")
    xref_pos = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return out.getvalue()


PDF_LINES = [
    "Acme Support Co - AI Deflection Proposal",
    "Annual ticket volume: 200,000 tickets",
    "Cost per ticket: $9.50",
    "Tier-1 share of tickets: 55%",
    "Claimed deflection rate across all tickets: 40%",
    "Initial build cost: $250,000",
    "Claimed annual inference budget: $30,000",
]

ACME_VALUES = {
    "company_name": "Acme Support Co",
    "annual_ticket_volume": 200_000,
    "cost_per_ticket_usd": 9.5,
    "tier1_ticket_share": 0.55,
    "claimed_deflection_rate_all_tickets": 0.4,
    "initial_build_cost_usd": 250_000,
    "annual_inference_budget_usd_claimed": 30_000,
}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv("VANTAGE_API_TOKEN", raising=False)
    main.limiter.enabled = False
    with TestClient(main.app, raise_server_exceptions=False) as c:
        yield c
    main.limiter.enabled = False


# ---------------------------------------------------------------------------
# Field specs + profile building
# ---------------------------------------------------------------------------

class TestFieldSpecs:
    def test_specs_cover_all_categories(self):
        assert set(INTAKE_FIELDS) == {"customer_support", "marketing", "maintenance"}

    def test_required_fields_satisfy_schema(self):
        """Filling exactly the required intake fields must produce a profile
        that passes the category's Pydantic schema — the two must never drift."""
        samples = {
            "customer_support": ACME_VALUES,
            "marketing": {
                "company_name": "X",
                "monthly_ad_spend_usd": 100_000,
                "current_conversion_rate": 0.02,
                "average_order_value_usd": 90,
                "claimed_conversion_lift_rate": 0.3,
                "initial_build_cost_usd": 150_000,
                "annual_inference_budget_usd_claimed": 9_000,
            },
            "maintenance": {
                "company_name": "Y",
                "current_annual_maintenance_spend_usd": 1_000_000,
                "annual_downtime_cost_usd": 2_000_000,
                "claimed_maintenance_spend_reduction_rate": 0.2,
                "initial_build_cost_usd": 300_000,
                "annual_inference_budget_usd_claimed": 15_000,
            },
        }
        for category_key, values in samples.items():
            profile = build_profile(category_key, values)
            validate_company_profile(category_key, profile)  # must not raise
            branch_field = INTAKE_FIELDS[category_key]["branch_field"]
            assert profile["unknown_fields"] == {branch_field: "unknown"}

    def test_build_profile_coerces_numeric_strings(self):
        profile = build_profile("customer_support", {**ACME_VALUES,
                                                     "annual_ticket_volume": "200000"})
        assert profile["current_operations"]["annual_ticket_volume"] == 200_000.0

    def test_build_profile_ignores_unknown_keys(self):
        profile = build_profile("customer_support", {**ACME_VALUES, "evil_key": "x"})
        assert "evil_key" not in profile
        assert "evil_key" not in profile["current_operations"]


# ---------------------------------------------------------------------------
# Document parsing + extraction normalization
# ---------------------------------------------------------------------------

class TestDocumentParsing:
    def test_pdf_text_extraction(self):
        text = intake.prepare_document_text("proposal.pdf", build_pdf(PDF_LINES))
        assert "Annual ticket volume: 200,000" in text
        assert "$250,000" in text

    def test_txt_passthrough(self):
        body = ("Annual maintenance spend is $1.2M. " * 10).encode()
        assert "maintenance spend" in intake.prepare_document_text("notes.txt", body)

    def test_thin_document_rejected(self):
        with pytest.raises(intake.DocumentTooThin):
            intake.prepare_document_text("empty.txt", b"too short")

    def test_oversized_text_capped(self):
        text = intake.prepare_document_text("big.txt", b"x" * 100_000)
        assert len(text) == intake.MAX_DOC_CHARS


class TestExtractionNormalization:
    def test_percent_rates_normalized_to_fractions(self):
        out = intake._normalize_extraction(
            {"category": "marketing", "claimed_conversion_lift_rate": 45,
             "current_conversion_rate": 0.02}
        )
        assert out["values"]["claimed_conversion_lift_rate"] == 0.45
        assert out["values"]["current_conversion_rate"] == 0.02

    def test_negative_and_garbage_values_dropped(self):
        out = intake._normalize_extraction(
            {"category": "customer_support", "annual_ticket_volume": -5,
             "cost_per_ticket_usd": "not-a-number"}
        )
        assert "annual_ticket_volume" not in out["values"]
        assert "cost_per_ticket_usd" not in out["values"]

    def test_missing_required_reported(self):
        out = intake._normalize_extraction(
            {"category": "customer_support", "company_name": "Acme"}
        )
        assert "annual_ticket_volume" in out["missing_required"]

    def test_unknown_category_defaults(self):
        out = intake._normalize_extraction({"category": "nonsense"})
        assert out["category_key"] == "customer_support"


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

def test_intake_fields_endpoint(client):
    data = client.get("/api/intake/fields").json()
    assert set(data) == {"customer_support", "marketing", "maintenance"}
    assert any(f["name"] == "annual_ticket_volume" for f in data["customer_support"]["fields"])


def test_extract_profile_endpoint_pdf(client, monkeypatch):
    def fake_chat_text(*, client=None, model, messages, max_tokens,
                       temperature=0.2, tools=None, tool_choice=None):
        # The document text must actually reach the model prompt.
        assert "Annual ticket volume: 200,000" in messages[0]["content"]
        return make_tool_completion(
            "emit_profile",
            {"category": "customer_support", "company_name": "Acme Support Co",
             "annual_ticket_volume": 200000, "cost_per_ticket_usd": 9.5,
             "tier1_ticket_share": 0.55,
             "claimed_deflection_rate_all_tickets": 0.4,
             "initial_build_cost_usd": 250000,
             "annual_inference_budget_usd_claimed": 30000},
        )

    monkeypatch.setattr(intake, "chat_text", fake_chat_text)
    monkeypatch.setattr(intake, "vultr_client", lambda: None)
    r = client.post(
        "/api/extract-profile",
        files={"file": ("proposal.pdf", build_pdf(PDF_LINES), "application/pdf")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["category_key"] == "customer_support"
    assert body["values"]["annual_ticket_volume"] == 200000
    assert body["missing_required"] == []


def test_extract_profile_rejects_thin_document(client):
    r = client.post("/api/extract-profile", files={"file": ("x.txt", b"hi", "text/plain")})
    assert r.status_code == 422


def test_prepare_validates_before_staging(client):
    r = client.post(
        "/api/run/prepare",
        json={"category": "customer_support", "values": {"company_name": "Acme"}},
    )
    assert r.status_code == 422
    assert "Invalid company profile" in r.json()["detail"]


def test_prepare_then_stream_runs_custom_profile(client, monkeypatch):
    captured: dict = {}

    def fake_run(category_key, company, emitter=None, cancel=None, parallel=True):
        captured["category"] = category_key
        captured["company"] = company
        emitter.emit("memo_ready", {"ok": True})
        return {"ok": True}

    monkeypatch.setattr(main, "run_pipeline", fake_run)
    r = client.post("/api/run/prepare",
                    json={"category": "customer_support", "values": ACME_VALUES})
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    with client.stream("GET", f"/api/run/stream?run_id={run_id}") as s:
        assert s.status_code == 200
        body = "".join(s.iter_text())
    assert "memo_ready" in body
    assert captured["category"] == "customer_support"
    assert captured["company"]["company_name"] == "Acme Support Co"
    assert captured["company"]["current_operations"]["annual_ticket_volume"] == 200_000.0
    assert captured["company"]["unknown_fields"] == {"hosting_architecture": "unknown"}


def test_run_id_is_single_use_and_unknown_404(client, monkeypatch):
    monkeypatch.setattr(
        main, "run_pipeline",
        lambda ck, c, emitter=None, cancel=None, parallel=True: emitter.emit("memo_ready", {}),
    )
    r = client.post("/api/run/prepare",
                    json={"category": "customer_support", "values": ACME_VALUES})
    run_id = r.json()["run_id"]
    with client.stream("GET", f"/api/run/stream?run_id={run_id}") as s:
        "".join(s.iter_text())
    # second use -> gone
    assert client.get(f"/api/run/stream?run_id={run_id}").status_code == 404
    assert client.get("/api/run/stream?run_id=nope").status_code == 404


def test_custom_run_produces_full_memo_with_mocked_providers(client, monkeypatch):
    """End-to-end offline: intake values -> prepare -> stream -> real pipeline
    (providers mocked) -> memo with deterministic numbers for the custom company."""
    from conftest import (
        EXPLANATION_TEXT,
        RECOMMENDATION_ARGS,
        VERDICTS_ONE_FLAGGED,
        fake_rerank,
    )

    def fake_chat_text(*, client=None, model, messages, max_tokens,
                       temperature=0.2, tools=None, tool_choice=None):
        names = [t["function"]["name"] for t in (tools or [])]
        if "validate_claims" in names:
            return make_tool_completion("validate_claims", {"verdicts": VERDICTS_ONE_FLAGGED})
        return make_tool_completion("emit_recommendation", RECOMMENDATION_ARGS)

    def fake_stream(*, model, messages, max_tokens, reasoning_budget, on_chunk=None):
        return EXPLANATION_TEXT

    monkeypatch.setattr("agents.retrieval.rerank", fake_rerank)
    monkeypatch.setattr("agents.retrieval.chat_text", fake_chat_text)
    monkeypatch.setattr("agents.retrieval.vultr_client", lambda: None)
    monkeypatch.setattr("agents.report.chat_text", fake_chat_text)
    monkeypatch.setattr("agents.report.vultr_client", lambda: None)
    monkeypatch.setattr("agents.explainability._stream_with_callback", fake_stream)

    r = client.post("/api/run/prepare",
                    json={"category": "customer_support", "values": ACME_VALUES})
    run_id = r.json()["run_id"]
    with client.stream("GET", f"/api/run/stream?run_id={run_id}") as s:
        events = [json.loads(line[5:]) for line in s.iter_lines()
                  if line.startswith("data:")]
    memo = next(e["data"] for e in events if e["event"] == "memo_ready")
    assert memo["meta"]["company_name"] == "Acme Support Co"
    assert len(memo["branches"]) == 2
    # Deterministic math ran on the custom numbers (not the demo company's).
    likely_roi = memo["branches"][0]["metrics"]["roi_3yr"]["likely"]
    assert likely_roi is not None and likely_roi != 5.686  # 5.686 = Meridian's value
