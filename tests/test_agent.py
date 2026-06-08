"""Tests for Agent State, Guardrails, and Knowledge Base."""

import pytest
from src.agent.state import ReconciliationState
from src.agent.guardrails import (
    GuardrailViolation,
    validate_invoice_id,
    prevent_auto_send,
    tool_whitelist_check,
    high_value_guardrail,
    make_audit_entry,
    REGISTERED_TOOLS,
    HIGH_VALUE_THRESHOLD,
)
from src.knowledge_base import get_vendor_context, AP_POLICIES


class TestReconciliationState:

    def test_state_creation(self):
        state: ReconciliationState = {
            "invoices": [], "plan": "", "matches": [], "mismatches": [],
            "emails": [], "approved": [], "current_step": "start",
            "audit_trail": [], "rag_context": {},
            "high_value_blocked": False, "final_status": "",
        }
        assert state["current_step"] == "start"
        assert state["high_value_blocked"] is False

    def test_state_with_data(self):
        state: ReconciliationState = {
            "invoices": [{"invoice_id": "INV0001"}],
            "plan": "Match all invoices",
            "matches": [], "mismatches": [], "emails": [],
            "approved": [True], "current_step": "approval",
            "audit_trail": [{"action": "test"}], "rag_context": {},
            "high_value_blocked": False, "final_status": "COMPLETED",
        }
        assert state["final_status"] == "COMPLETED"
        assert len(state["audit_trail"]) == 1


class TestValidateInvoiceId:

    def test_valid(self):
        assert validate_invoice_id("INV0001") is True
        assert validate_invoice_id("INV99999") is True

    def test_invalid_no_prefix(self):
        assert validate_invoice_id("0001") is False

    def test_invalid_wrong_prefix(self):
        assert validate_invoice_id("PO0001") is False

    def test_invalid_empty(self):
        assert validate_invoice_id("") is False

    def test_invalid_mixed(self):
        assert validate_invoice_id("INV00A1") is False


class TestPreventAutoSend:

    def test_approval_step_passes(self):
        assert prevent_auto_send({"current_step": "approval"}) is True

    def test_matcher_step_raises(self):
        with pytest.raises(GuardrailViolation, match="Cannot send emails"):
            prevent_auto_send({"current_step": "matcher"})

    def test_missing_step_raises(self):
        with pytest.raises(GuardrailViolation, match="unknown"):
            prevent_auto_send({})


class TestToolWhitelistCheck:

    def test_registered_tools(self):
        for tool in ["match_invoices", "classify", "generate_email", "rag_lookup"]:
            assert tool_whitelist_check(tool) is True

    def test_unregistered_tool(self):
        assert tool_whitelist_check("delete_all") is False

    def test_empty_tool_name(self):
        assert tool_whitelist_check("") is False

    def test_registered_tools_constant(self):
        assert set(REGISTERED_TOOLS) == {"match_invoices", "classify", "generate_email", "rag_lookup"}


class TestHighValueGuardrail:

    def test_below_threshold_passes(self):
        assert high_value_guardrail(10_000.0, "INV0001") is True

    def test_at_threshold_passes(self):
        assert high_value_guardrail(HIGH_VALUE_THRESHOLD, "INV0001") is True

    def test_above_threshold_blocked(self):
        assert high_value_guardrail(HIGH_VALUE_THRESHOLD + 0.01, "INV0001") is False

    def test_large_invoice_blocked(self):
        assert high_value_guardrail(100_000.0, "INV0099") is False


class TestMakeAuditEntry:

    def test_structure(self):
        entry = make_audit_entry("planner", "SUCCESS", {"count": 5})
        assert entry["action"] == "planner"
        assert entry["status"] == "SUCCESS"
        assert entry["details"]["count"] == 5
        assert "timestamp" in entry
        assert entry["timestamp"].endswith("Z")

    def test_no_details(self):
        entry = make_audit_entry("test", "OK")
        assert entry["details"] == {}


class TestKnowledgeBase:

    def test_known_vendor_returns_contract(self):
        ctx = get_vendor_context("Vendor_19", "PRICE_VARIANCE")
        assert len(ctx["contract_terms"]) > 0
        assert len(ctx["dispute_history"]) > 0

    def test_known_vendor_with_history_suggests_action(self):
        ctx = get_vendor_context("Vendor_19", "PRICE_VARIANCE")
        assert ctx["suggested_action"] != ""

    def test_unknown_vendor_returns_empty_context(self):
        ctx = get_vendor_context("Vendor_Unknown", "PRICE_VARIANCE")
        assert ctx["contract_terms"] == []
        assert ctx["dispute_history"] == []

    def test_policy_notes_always_present(self):
        ctx = get_vendor_context("Vendor_Unknown", "MISSING_PO")
        assert len(ctx["policy_notes"]) >= 1

    def test_ap_policies_have_required_keys(self):
        for key in ["high_value_threshold", "price_tolerance_pct", "dispute_response_days"]:
            assert key in AP_POLICIES
