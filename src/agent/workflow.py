"""
Agent Workflow for SmartPay AP (D3 Deliverable).

LangGraph state graph:

  START
    -> planner           (analyse batch, produce plan)
    -> guardrail         (validate IDs, block high-value invoices)
    -> matcher           (D2 model as tool: match + classify)
        -> [no mismatches] -> END (auto-approved)
        -> [mismatches]   -> rag_lookup
    -> rag_lookup        (vendor contracts + dispute history)
    -> dispute           (draft emails via LLM/template)
    -> approval          (HITL gate - pauses for human review)
        -> [all approved] -> END
        -> [some rejected]-> discard -> END

Why LangGraph over CrewAI/AutoGen:
  - Deterministic control flow suits AP workflows (auditable, explainable)
  - Native human-in-the-loop interrupt support
  - Explicit state schema (TypedDict) = full traceability
  - Conditional edges model the approval/rejection branching clearly
"""

import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from langgraph.graph import StateGraph, END
except ImportError:
    raise ImportError("pip install langgraph>=0.2.0")

from src.agent.state import ReconciliationState
from src.agent.nodes import (
    planner_node, guardrail_node, matcher_node,
    rag_lookup_node, dispute_node, approval_node,
)
from src.agent.guardrails import make_audit_entry
from src.data_loader import load_invoices, aggregate_invoices

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def _route_after_matcher(state: ReconciliationState) -> str:
    """Route to RAG lookup if mismatches found, else end."""
    if state.get("mismatches"):
        return "has_mismatches"
    return "no_mismatches"


def _route_after_approval(state: ReconciliationState) -> str:
    """Route to discard if any emails were rejected."""
    approved = state.get("approved", [])
    return "end" if (not approved or all(approved)) else "discard"


# ---------------------------------------------------------------------------
# Discard node (rejections)
# ---------------------------------------------------------------------------

def _discard_node(state: ReconciliationState) -> dict:
    """Remove rejected emails and log each rejection."""
    emails   = state.get("emails", [])
    approved = state.get("approved", [])
    audit    = state.get("audit_trail", [])
    kept     = []

    for email, ok in zip(emails, approved):
        if ok:
            kept.append(email)
        else:
            audit.append(make_audit_entry(
                "discard", "DISCARDED",
                {"invoice_id": email.get("invoice_id"),
                 "reason": "rejected_by_human"}
            ))
            logger.info("Discarded email for invoice %s.", email.get("invoice_id"))

    return {
        "emails":       kept,
        "current_step": "discard",
        "audit_trail":  audit,
        "final_status": (
            f"COMPLETED: {len(kept)} email(s) approved, "
            f"{len(emails)-len(kept)} rejected and discarded."
        ),
    }


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_workflow() -> StateGraph:
    """Compile the reconciliation workflow graph.

    Graph:
        planner -> guardrail -> matcher
                                 |
                   no_mismatches -> END (all clean)
                   has_mismatches -> rag_lookup -> dispute -> approval
                                                               |
                                                  end -> END
                                                  discard -> discard_node -> END
    """
    wf = StateGraph(ReconciliationState)

    wf.add_node("planner",    planner_node)
    wf.add_node("guardrail",  guardrail_node)
    wf.add_node("matcher",    matcher_node)
    wf.add_node("rag_lookup", rag_lookup_node)
    wf.add_node("dispute",    dispute_node)
    wf.add_node("approval",   approval_node)
    wf.add_node("discard",    _discard_node)

    wf.set_entry_point("planner")

    wf.add_edge("planner",    "guardrail")
    wf.add_edge("guardrail",  "matcher")

    wf.add_conditional_edges(
        "matcher",
        _route_after_matcher,
        {"has_mismatches": "rag_lookup", "no_mismatches": END},
    )

    wf.add_edge("rag_lookup", "dispute")
    wf.add_edge("dispute",    "approval")

    wf.add_conditional_edges(
        "approval",
        _route_after_approval,
        {"end": END, "discard": "discard"},
    )
    wf.add_edge("discard", END)

    return wf


# ---------------------------------------------------------------------------
# Run helpers
# ---------------------------------------------------------------------------

def run_workflow(invoices: list[dict] | None = None) -> dict:
    """Run the full reconciliation workflow end-to-end.

    Args:
        invoices: Optional pre-loaded invoice dicts. If None, loads from CSV.

    Returns:
        Final workflow state dict including audit_trail.
    """
    if invoices is None:
        data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data"
        )
        inv_df   = load_invoices(os.path.join(data_dir, "invoices.csv"))
        invoices = aggregate_invoices(inv_df).to_dict(orient="records")

    initial: ReconciliationState = {
        "invoices":          invoices,
        "plan":              "",
        "matches":           [],
        "mismatches":        [],
        "emails":            [],
        "approved":          [],
        "current_step":      "start",
        "audit_trail":       [make_audit_entry("workflow_start", "INITIATED",
                              {"invoice_count": len(invoices)})],
        "rag_context":       {},
        "high_value_blocked": False,
        "final_status":      "",
    }

    app = build_workflow().compile()
    logger.info("Workflow started: %d invoices.", len(invoices))
    result = app.invoke(initial)
    logger.info("Workflow complete. Step: %s", result.get("current_step"))
    return result


def print_summary(result: dict) -> None:
    """Print a concise summary of workflow results."""
    mismatches = result.get("mismatches", [])
    emails     = result.get("emails", [])
    approved   = result.get("approved", [])
    audit      = result.get("audit_trail", [])

    type_counts: dict[str, int] = {}
    for m in mismatches:
        t = m.get("mismatch_type", "UNKNOWN")
        type_counts[t] = type_counts.get(t, 0) + 1

    print("\n" + "=" * 64)
    print("  SMARTPAY AP -- RECONCILIATION SUMMARY")
    print("=" * 64)
    print(f"  Mismatches detected : {len(mismatches)}")
    for t, c in sorted(type_counts.items()):
        print(f"    {t:<24} : {c}")
    print(f"  Emails drafted      : {len(emails)}")
    if approved:
        print(f"  Approved            : {sum(approved)}")
        print(f"  Rejected/escalated  : {len(approved) - sum(approved)}")
    if result.get("high_value_blocked"):
        print("  [!] High-value invoices were blocked -> manual review required")
    print(f"  Audit trail entries : {len(audit)}")
    if result.get("final_status"):
        print(f"  Status              : {result['final_status']}")
    print("=" * 64 + "\n")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    result = run_workflow()
    print_summary(result)
