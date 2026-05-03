"""Tests for deterministic credit risk Excel-model engine and LLM guardrails."""

from __future__ import annotations

import unittest
from datetime import date, timedelta

from app.services import credit_risk_agent_service as cra
from app.services.credit_risk_excel_model import DealInputs, ParsedParams, compute_deal_scoring, load_workbook_structures


def _hist_ok(n: int = 6) -> list[dict]:
    base = date(2025, 1, 1)
    out = []
    for i in range(n):
        due = base + timedelta(days=30 * i)
        paid = due + timedelta(days=2)
        out.append(
            {
                "invoice_amount": 100_000 + i * 1000,
                "due_date": due.isoformat(),
                "paid_date": paid.isoformat(),
            }
        )
    return out


def _deal(
    rating: str = "BBB",
    *,
    dispute: bool = False,
    mismatch: bool = False,
    portfolio: float = 5_000_000,
    anc_exposure: float = 600_000,
    sup_exposure: float = 20_000,
    invoice: float = 200_000,
    hist: list | None = None,
) -> DealInputs:
    return DealInputs(
        anchor="Anchor s.r.o.",
        supplier="Supplier s.r.o.",
        receivable_status="Faktura",
        deal_id="D-1",
        invoice_amount=invoice,
        due_date=date(2026, 6, 30),
        data_mismatch=mismatch,
        dispute=dispute,
        anchor_rating=rating,
        existing_supplier_exposure=sup_exposure,
        existing_anchor_exposure=anc_exposure,
        total_portfolio_exposure=portfolio,
        historical_transactions=hist or _hist_ok(),
        reference_date=date(2026, 5, 1),
    )


class TestRatingGates(unittest.TestCase):
    def test_aaa_gate_ok_clean_deal(self):
        r = compute_deal_scoring(_deal("AAA"))
        self.assertEqual(r["rating_gate"], "OK")

    def test_investment_grade_ratings_gate_ok(self):
        for rt in ("AA", "A", "BBB"):
            with self.subTest(rating=rt):
                self.assertEqual(compute_deal_scoring(_deal(rt))["rating_gate"], "OK")

    def test_bb_gate_manual(self):
        r = compute_deal_scoring(_deal("BB"))
        self.assertEqual(r["rating_gate"], "MANUAL")

    def test_nr_gate_manual(self):
        r = compute_deal_scoring(_deal("NR"))
        self.assertEqual(r["rating_gate"], "MANUAL")

    def test_b_gate_stop(self):
        r = compute_deal_scoring(_deal("B"))
        self.assertEqual(r["rating_gate"], "STOP")

    def test_ccc_gate_stop(self):
        r = compute_deal_scoring(_deal("CCC"))
        self.assertEqual(r["rating_gate"], "STOP")


class TestBehaviorFlags(unittest.TestCase):
    def test_dispute_forces_stop(self):
        r = compute_deal_scoring(_deal("AAA", dispute=True))
        self.assertEqual(r["rating_gate"], "STOP")

    def test_mismatch_forces_manual_minimum(self):
        r = compute_deal_scoring(_deal("AAA", mismatch=True))
        self.assertEqual(r["rating_gate"], "MANUAL")


class TestConcentration(unittest.TestCase):
    def test_red_flag_high_anchor_share(self):
        r = compute_deal_scoring(
            _deal("AAA", portfolio=400_000, anc_exposure=50_000, sup_exposure=10_000, invoice=350_000)
        )
        self.assertEqual(r["concentration_flag"], "RED FLAG")


class TestDeterminism(unittest.TestCase):
    def test_repeatable_score(self):
        d = _deal()
        a = compute_deal_scoring(d)
        b = compute_deal_scoring(d)
        self.assertEqual(a["total_score"], b["total_score"])
        self.assertEqual(a["risk_band"], b["risk_band"])


class TestLLMGuardrails(unittest.TestCase):
    def test_guardrails_block_approve_on_stop(self):
        mr = {"rating_gate": "STOP", "risk_band": "D", "concentration_flag": "GREEN"}
        interp = {"recommendation": "Approve", "risk_grade": "A", "key_risks": []}
        out = cra.enforce_llm_guardrails(mr, interp)
        self.assertEqual(out["recommendation"], "Reject")

    def test_guardrails_manual_review_red_flag(self):
        mr = {"rating_gate": "OK", "risk_band": "A", "concentration_flag": "RED FLAG"}
        interp = {"recommendation": "Approve", "risk_grade": "A", "key_risks": []}
        out = cra.enforce_llm_guardrails(mr, interp)
        self.assertEqual(out["recommendation"], "Human review required")


class TestWorkbookFallback(unittest.TestCase):
    def test_load_non_xlsx_returns_defaults(self):
        params, catalog = load_workbook_structures(__file__)  # not an xlsx → defaults
        self.assertIsInstance(params, ParsedParams)
        self.assertIn("AAA", catalog)


if __name__ == "__main__":
    unittest.main()
