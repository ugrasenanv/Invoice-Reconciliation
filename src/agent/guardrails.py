"""
Agent Guardrails for SmartPay AP.

Three guardrails required by the case study spec:
  1. validate_invoice_id    - INV format check (malformed input rejection)
  2. prevent_auto_send      - blocks emails without passing Human Approval Gate
  3. tool_whitelist_check   - only registered tools callable by the agent
  4. high_value_guardrail   - invoices above $50k threshold -> manual review
"""

import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

REGISTERED_TOOLS = ["match_invoices", "classify", "generate_email", "rag_lookup"]
HIGH_VALUE_THRESHOLD = 50_000.0


class GuardrailViolation(Exception):
    """Raised when an agent guardrail is violated."""
    pass


def validate_invoice_id(invoice_id: str) -> bool:
    """Validate that invoice_id matches INV followed by digits.

    Args:
        invoice_id: The invoice ID string to validate.

    Returns:
        True if valid, False otherwise.
    """
    if not re.match(r'^INV\d+$', invoice_id):
        logger.warning("Guardrail: invalid invoice_id format '%s'", invoice_id)
        return False
    return True


def prevent_auto_send(state: dict) -> bool:
    """Ensure no email is sent without passing through Human Approval Gate.

    Args:
        state: Current workflow state.

    Returns:
        True if approval step completed.

    Raises:
        GuardrailViolation: If called before approval step.
    """
    if state.get("current_step") != "approval":
        raise GuardrailViolation(
            "Cannot send emails without human approval. Current step: "
            + state.get("current_step", "unknown")
        )
    return True


def tool_whitelist_check(tool_name: str) -> bool:
    """Validate that only registered tools are called.

    Registered tools: match_invoices, classify, generate_email, rag_lookup.

    Args:
        tool_name: Name of the tool being invoked.

    Returns:
        True if registered, False otherwise.
    """
    if tool_name not in REGISTERED_TOOLS:
        logger.warning(
            "Guardrail: unregistered tool '%s'. Allowed: %s",
            tool_name, REGISTERED_TOOLS,
        )
        return False
    return True


def high_value_guardrail(invoice_total: float, invoice_id: str) -> bool:
    """Block invoices exceeding the high-value threshold from auto-processing.

    Invoices above $50,000 must be routed to manual AP Manager review.
    This is a hard guardrail — cannot be bypassed by the agent.

    Args:
        invoice_total: Total value of the invoice.
        invoice_id   : Invoice identifier for logging.

    Returns:
        True if invoice can proceed automatically, False if blocked.
    """
    if invoice_total > HIGH_VALUE_THRESHOLD:
        logger.warning(
            "Guardrail: HIGH-VALUE invoice %s ($%.2f) exceeds threshold ($%.2f). "
            "Routing to manual review.",
            invoice_id, invoice_total, HIGH_VALUE_THRESHOLD,
        )
        return False
    return True


def make_audit_entry(action: str, status: str, details: dict | None = None) -> dict:
    """Create a structured audit trail entry.

    Args:
        action : Node or action name.
        status : Outcome (SUCCESS, FAILED, BLOCKED, etc.)
        details: Optional additional context.

    Returns:
        Audit entry dict with timestamp.
    """
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "action":    action,
        "status":    status,
        "details":   details or {},
    }
