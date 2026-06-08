"""
Agent Workflow Nodes for SmartPay AP.

6-node LangGraph workflow:
  planner       -> Plans the reconciliation batch
  guardrail     -> Blocks high-value invoices, validates inputs
  matcher       -> Matches invoices to POs, classifies mismatches (D2 as tool)
  rag_lookup    -> Retrieves vendor contracts + dispute history for context
  dispute       -> Drafts vendor dispute emails (LLM or template)
  approval      -> Human-in-the-loop gate (pauses for review before sending)
"""

import os
import sys
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.data_loader import load_invoices, load_po_grn, load_labels, aggregate_invoices
from src.matcher import match_invoices_to_pos
from src.classifier import classify_mismatches
from src.email_generator import generate_dispute_email
from src.knowledge_base import get_vendor_context, AP_POLICIES
from src.agent.state import ReconciliationState
from src.agent.guardrails import (
    validate_invoice_id, tool_whitelist_check,
    high_value_guardrail, make_audit_entry, HIGH_VALUE_THRESHOLD,
)

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data"
)


# ---------------------------------------------------------------------------
# NODE 1 — Planner
# ---------------------------------------------------------------------------

def planner_node(state: ReconciliationState) -> dict:
    """Analyse invoice batch and produce a reconciliation plan."""
    invoices   = state["invoices"]
    vendors    = sorted({inv.get("vendor_id", "") for inv in invoices})
    currencies = sorted({inv.get("currency",  "") for inv in invoices})

    plan = (
        "Reconciliation Plan:\n"
        f"  Invoices   : {len(invoices)}\n"
        f"  Vendors    : {len(vendors)} ({', '.join(vendors)})\n"
        f"  Currencies : {', '.join(currencies)}\n"
        "  Steps      : 1) Guardrail check  2) Match to POs  "
        "3) RAG context lookup  4) Draft dispute emails  5) Human approval"
    )

    audit = state.get("audit_trail", []) + [
        make_audit_entry("planner", "SUCCESS", {"invoice_count": len(invoices)})
    ]
    logger.info("Planner: %d invoices across %d vendors.", len(invoices), len(vendors))
    return {"plan": plan, "current_step": "planner", "audit_trail": audit}


# ---------------------------------------------------------------------------
# NODE 2 — Guardrail Check
# ---------------------------------------------------------------------------

def guardrail_node(state: ReconciliationState) -> dict:
    """Validate invoice IDs and block high-value invoices."""
    invoices = state["invoices"]
    audit    = state.get("audit_trail", [])
    blocked  = []
    valid    = []

    for inv in invoices:
        inv_id    = inv.get("invoice_id", "")
        inv_total = inv.get("invoice_total", 0.0)

        if not validate_invoice_id(inv_id):
            blocked.append(inv_id)
            audit.append(make_audit_entry(
                "guardrail", "BLOCKED",
                {"invoice_id": inv_id, "reason": "invalid_id_format"}
            ))
            continue

        if not high_value_guardrail(inv_total, inv_id):
            blocked.append(inv_id)
            audit.append(make_audit_entry(
                "guardrail", "BLOCKED",
                {"invoice_id": inv_id, "reason": "high_value",
                 "total": inv_total, "threshold": HIGH_VALUE_THRESHOLD}
            ))
            continue

        valid.append(inv)

    high_value_blocked = len(blocked) > 0
    if blocked:
        logger.warning("Guardrail blocked %d invoice(s): %s", len(blocked), blocked)

    audit.append(make_audit_entry(
        "guardrail", "SUCCESS",
        {"passed": len(valid), "blocked": len(blocked)}
    ))
    return {
        "invoices": valid,
        "high_value_blocked": high_value_blocked,
        "current_step": "guardrail",
        "audit_trail": audit,
    }


# ---------------------------------------------------------------------------
# NODE 3 — Matcher (D2 model as tool)
# ---------------------------------------------------------------------------

def matcher_node(state: ReconciliationState) -> dict:
    """Invoke the D2 matching model as a registered agent tool."""
    tool_whitelist_check("match_invoices")
    tool_whitelist_check("classify")

    audit = state.get("audit_trail", [])

    inv_df  = load_invoices(os.path.join(_DATA_DIR, "invoices.csv"))
    po_df   = load_po_grn(os.path.join(_DATA_DIR, "po_grn.csv"))
    inv_agg = aggregate_invoices(inv_df)

    # Preserve vendor_name for email generation
    vendor_names = inv_df.groupby("invoice_id")["vendor_name"].first()
    inv_agg = inv_agg.merge(vendor_names, on="invoice_id", how="left")

    labels_path = os.path.join(_DATA_DIR, "labelled_mismatches.csv")
    labels_df   = load_labels(labels_path) if os.path.exists(labels_path) else None

    matched      = match_invoices_to_pos(inv_agg, po_df, labels=labels_df)
    mismatches_df = classify_mismatches(matched, labels=labels_df)

    if not mismatches_df.empty:
        mismatches_df = mismatches_df.merge(
            inv_agg[["invoice_id", "vendor_name"]], on="invoice_id", how="left"
        )

    matches    = matched.to_dict(orient="records")
    mismatches = mismatches_df.to_dict(orient="records")

    audit.append(make_audit_entry(
        "matcher", "SUCCESS",
        {"matches": len(matches), "mismatches": len(mismatches),
         "mismatch_types": mismatches_df["mismatch_type"].value_counts().to_dict()
         if not mismatches_df.empty else {}}
    ))
    logger.info("Matcher: %d matches, %d mismatches.", len(matches), len(mismatches))
    return {
        "matches":      matches,
        "mismatches":   mismatches,
        "current_step": "matcher",
        "audit_trail":  audit,
    }


# ---------------------------------------------------------------------------
# NODE 4 — RAG Lookup
# ---------------------------------------------------------------------------

def rag_lookup_node(state: ReconciliationState) -> dict:
    """Retrieve vendor contract terms and dispute history for each mismatch."""
    tool_whitelist_check("rag_lookup")

    mismatches  = state.get("mismatches", [])
    audit       = state.get("audit_trail", [])
    rag_context = {}

    for m in mismatches:
        inv_id       = m.get("invoice_id", "")
        vendor       = m.get("vendor_name", "")
        mismatch_type = m.get("mismatch_type", "")
        rag_context[inv_id] = get_vendor_context(vendor, mismatch_type)

    audit.append(make_audit_entry(
        "rag_lookup", "SUCCESS", {"invoices_enriched": len(rag_context)}
    ))
    logger.info("RAG lookup enriched %d mismatches.", len(rag_context))
    return {"rag_context": rag_context, "current_step": "rag_lookup", "audit_trail": audit}


# ---------------------------------------------------------------------------
# NODE 5 — Dispute Generator
# ---------------------------------------------------------------------------

def dispute_node(state: ReconciliationState) -> dict:
    """Generate dispute email drafts, grounded in RAG context."""
    tool_whitelist_check("generate_email")

    use_llm     = bool(os.getenv("OPENAI_API_KEY"))
    mismatches  = state.get("mismatches", [])
    rag_context = state.get("rag_context", {})
    audit       = state.get("audit_trail", [])
    emails      = []

    for m in mismatches:
        inv_id  = m.get("invoice_id")
        rag     = rag_context.get(inv_id, {})
        # Inject RAG context into mismatch dict for email generator
        enriched = {**m, "rag_context": rag}

        email_text = generate_dispute_email(enriched, use_llm=use_llm)
        emails.append({
            "invoice_id":    inv_id,
            "vendor_name":   m.get("vendor_name", "Vendor"),
            "mismatch_type": m.get("mismatch_type"),
            "invoice_value": m.get("invoice_value"),
            "po_value":      m.get("po_value"),
            "difference":    m.get("difference"),
            "confidence":    m.get("confidence", 1.0),
            "rag_context":   rag,
            "email_text":    email_text,
            "status":        "draft",
        })

    audit.append(make_audit_entry(
        "dispute", "SUCCESS",
        {"emails_drafted": len(emails), "llm_used": use_llm}
    ))
    logger.info("Dispute: %d emails drafted (LLM=%s).", len(emails), use_llm)
    return {"emails": emails, "current_step": "dispute", "audit_trail": audit}


# ---------------------------------------------------------------------------
# NODE 6 — Human Approval Gate (HITL)
# ---------------------------------------------------------------------------

def approval_node(state: ReconciliationState) -> dict:
    """Human-in-the-loop approval gate — agent pauses here."""
    emails        = state.get("emails", [])
    audit         = state.get("audit_trail", [])
    approved      = []
    is_interactive = sys.stdin.isatty() if hasattr(sys.stdin, "isatty") else False

    for i, email in enumerate(emails):
        print(f"\n{'='*64}")
        print(f"  Email {i+1}/{len(emails)}  |  {email.get('mismatch_type')}"
              f"  |  Invoice: {email.get('invoice_id')}"
              f"  |  Confidence: {email.get('confidence', 1.0):.0%}")
        if email.get("rag_context", {}).get("contract_terms"):
            print("  Contract: " + "; ".join(email["rag_context"]["contract_terms"]))
        if email.get("rag_context", {}).get("suggested_action"):
            print("  Suggested: " + email["rag_context"]["suggested_action"])
        print(f"{'='*64}")
        print(email.get("email_text", ""))
        print(f"{'='*64}")

        if is_interactive:
            while True:
                resp = input("  Approve this email? (y/n): ").strip().lower()
                if resp in ("y", "yes"):
                    approved.append(True)
                    print("  [APPROVED]")
                    audit.append(make_audit_entry(
                        "approval", "APPROVED",
                        {"invoice_id": email.get("invoice_id"), "method": "human"}
                    ))
                    break
                elif resp in ("n", "no"):
                    approved.append(False)
                    print("  [REJECTED] -> escalated to AP Manager")
                    audit.append(make_audit_entry(
                        "approval", "REJECTED",
                        {"invoice_id": email.get("invoice_id"), "method": "human"}
                    ))
                    break
        else:
            # Non-interactive (CI/demo): auto-approve
            approved.append(True)
            print("  [AUTO-APPROVED] (non-interactive mode)")
            audit.append(make_audit_entry(
                "approval", "AUTO_APPROVED",
                {"invoice_id": email.get("invoice_id"), "method": "auto"}
            ))

    logger.info(
        "Approval: %d approved, %d rejected.",
        sum(approved), len(approved) - sum(approved)
    )
    return {"approved": approved, "current_step": "approval", "audit_trail": audit}
