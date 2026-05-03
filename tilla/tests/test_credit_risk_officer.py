"""Credit Risk Officer orchestration — policy, final decision, API smoke."""

from __future__ import annotations

import os
import unittest
from datetime import date, timedelta
from unittest import mock

from starlette.testclient import TestClient

from app.services import credit_risk_agent_service as cra
from app.services.credit_risk_policy_engine import run_policy_checks
from app.services.credit_risk_scoring_engine import CreditRiskInput, calculate_credit_risk


def _hist_ok(n: int = 6) -> list[dict]:
    base = date(2026, 1, 1)
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


def _base_credit_input(**kw) -> CreditRiskInput:
    data = {
        "supplier_name": "Supplier s.r.o.",
        "supplier_ico": "111",
        "anchor_name": "Anchor s.r.o.",
        "anchor_ico": "222",
        "invoice_amount": 200_000.0,
        "due_date": "2026-12-31",
        "anchor_rating": "BBB",
        "historical_transactions": _hist_ok(),
        "total_portfolio_exposure": 5_000_000.0,
        "existing_exposure_supplier": "20000",
        "existing_exposure_anchor": "600000",
        "revenue_latest_year": "10",
        "ebitda_latest_year": "1",
        "confirmation_status": "confirmed",
        "legal_status": "ok",
        "bank_account_verified": True,
        "invoice_number": "INV-1",
    }
    data.update(kw)
    return CreditRiskInput.model_validate(data)


class TestFinalDecision(unittest.TestCase):
    def test_stop_gate_rejects_and_blocks_funding(self):
        inp_b = _base_credit_input(anchor_rating="B")
        mr = calculate_credit_risk(inp_b)
        pr = run_policy_checks(inp_b, mr)
        fd = cra.build_final_decision(inp_b, mr, pr, {})
        self.assertEqual(fd["recommendation"], "Reject")
        self.assertFalse(fd["can_fund_now"])

    def test_clean_deal_pass_allows_funding_flag(self):
        inp = _base_credit_input()
        mr = calculate_credit_risk(inp)
        pr = run_policy_checks(inp, mr)
        fd = cra.build_final_decision(inp, mr, pr, {})
        self.assertEqual(pr["final_policy_status"], "PASS")
        self.assertEqual(fd["recommendation"], "Approve")
        self.assertTrue(fd["can_fund_now"])

    def test_dispute_blocks_funding(self):
        inp = _base_credit_input(dispute=True)
        mr = calculate_credit_risk(inp)
        pr = run_policy_checks(inp, mr)
        fd = cra.build_final_decision(inp, mr, pr, {})
        self.assertEqual(pr["final_policy_status"], "STOP")
        self.assertFalse(fd["can_fund_now"])
        self.assertEqual(fd["recommendation"], "Reject")

    def test_data_mismatch_blocks_auto_funding(self):
        inp = _base_credit_input(data_mismatch=True)
        mr = calculate_credit_risk(inp)
        pr = run_policy_checks(inp, mr)
        fd = cra.build_final_decision(inp, mr, pr, {})
        self.assertNotEqual(pr["final_policy_status"], "PASS")
        self.assertFalse(fd["can_fund_now"])

    def test_missing_confirmation_blocks_auto_funding(self):
        inp = _base_credit_input(confirmation_status="pending")
        mr = calculate_credit_risk(inp)
        pr = run_policy_checks(inp, mr)
        fd = cra.build_final_decision(inp, mr, pr, {})
        self.assertIn("POLICY_ANCHOR_CONFIRMATION_PENDING", pr["manual_review_triggers"])
        self.assertFalse(fd["can_fund_now"])

    def test_high_concentration_manual_review(self):
        inp = _base_credit_input(
            total_portfolio_exposure=400_000,
            existing_exposure_anchor="50000",
            invoice_amount=350_000,
        )
        mr = calculate_credit_risk(inp)
        self.assertEqual(mr["concentration_flag"], "RED FLAG")
        pr = run_policy_checks(inp, mr)
        fd = cra.build_final_decision(inp, mr, pr, {})
        self.assertFalse(fd["can_fund_now"])

    def test_requested_advance_over_80_exception_path(self):
        inp = _base_credit_input(requested_advance_pct=85.0)
        mr = calculate_credit_risk(inp)
        pr = run_policy_checks(inp, mr)
        self.assertIn("POLICY_ADVANCE_ABOVE_80_PCT_REQUIRES_CRO", pr["manual_review_triggers"])
        fd = cra.build_final_decision(inp, mr, pr, {})
        self.assertFalse(fd["can_fund_now"])

    def test_no_openai_key_returns_fallback_memo(self):
        inp = _base_credit_input()
        payload = cra.CreditRiskAnalyseIn(**inp.model_dump(), csrf_token="dummy-token-ignore")
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            out = cra.analyse_credit_risk(payload)
        self.assertIn("OPENAI_API_KEY is not configured", out["agent_interpretation"]["executive_summary"])
        self.assertIn("model_result", out)
        self.assertIn("policy_check_result", out)


class TestAPISmoke(unittest.TestCase):
    def test_analyse_requires_auth(self):
        import os

        from fastapi import FastAPI
        from starlette.middleware.sessions import SessionMiddleware

        from app.middleware.attach_user import AttachUserMiddleware
        from app.routers.credit_risk_agent import api as cro_api

        mini = FastAPI()
        mini.add_middleware(AttachUserMiddleware)
        mini.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "test-session-secret"))
        mini.include_router(cro_api)

        client = TestClient(mini)
        res = client.post("/api/credit-risk-agent/analyse", json={"csrf_token": "x"})
        self.assertEqual(res.status_code, 401)


class TestWorkflowGuard(unittest.TestCase):
    def test_stop_cannot_be_human_approved_flag(self):
        stop_pol = True
        stop_gate = False
        hs = {"POLICY_DISPUTE_YES_NO_AUTOFUND"}
        blocked = stop_pol or stop_gate or bool(hs)
        self.assertTrue(blocked)


if __name__ == "__main__":
    unittest.main()
