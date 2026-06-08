"""Agent State Schema for SmartPay AP."""

from typing import TypedDict, Optional


class ReconciliationState(TypedDict):
    """Shared state passed between all LangGraph nodes.

    Attributes:
        invoices         : Aggregated invoice records loaded from CSV.
        plan             : Reconciliation plan text from Planner node.
        matches          : Match results from Matcher node.
        mismatches       : Classified mismatch records (with confidence).
        emails           : Generated dispute email drafts.
        approved         : Human approval decisions per email.
        current_step     : Name of the current workflow node.
        audit_trail      : Immutable log of every node action + timestamp.
        rag_context      : Per-invoice RAG context from knowledge base.
        high_value_blocked: True if any invoice exceeded the high-value threshold.
        final_status     : Human-readable completion status.
    """
    invoices:          list[dict]
    plan:              str
    matches:           list[dict]
    mismatches:        list[dict]
    emails:            list[dict]
    approved:          list[bool]
    current_step:      str
    audit_trail:       list[dict]
    rag_context:       dict
    high_value_blocked: bool
    final_status:      str
