"""
Email Generator Module for SmartPay AP.

Drafts professional vendor dispute emails for each mismatch type.
When RAG context is available (vendor contracts, dispute history),
it is woven into the email for a grounded, personalised message.

Supports:
  - Template-based generation (no API key required)
  - LLM generation via OpenAI gpt-3.5-turbo (optional, falls back to template)
"""

import logging
import os

logger = logging.getLogger(__name__)

_DISPUTE_SLA = 5   # business days default


def generate_dispute_email(mismatch: dict, use_llm: bool = False) -> str:
    """Generate a dispute email for a single mismatch.

    Args:
        mismatch : dict with keys: invoice_id, po_number, mismatch_type,
                   vendor_name, invoice_value, po_value, difference,
                   rag_context (optional)
        use_llm  : If True, calls OpenAI. Falls back to template on failure.

    Returns:
        Formatted email string (subject + body).
    """
    if use_llm:
        email = _llm_email(mismatch)
        if email:
            return email
    return _template_email(mismatch)


# ---------------------------------------------------------------------------
# Template generator
# ---------------------------------------------------------------------------

_TEMPLATES = {
    "PRICE_VARIANCE": (
        "Subject: Invoice Price Variance – {invoice_id} / {po_number}\n\n"
        "Dear {vendor_name} Finance Team,\n\n"
        "During reconciliation of invoice {invoice_id} against purchase order "
        "{po_number}, we identified a price variance of {difference} "
        "(Invoice: {invoice_value} | PO: {po_value}).\n\n"
        "{rag_section}"
        "Please issue a credit note or corrected invoice within "
        "{sla} business days.\n\n"
        "Best regards,\nAccounts Payable Team\nAcme Manufacturing\n"
        "ap-disputes@acme-manufacturing.com"
    ),
    "QUANTITY_VARIANCE": (
        "Subject: Invoice Quantity Variance – {invoice_id} / {po_number}\n\n"
        "Dear {vendor_name} Finance Team,\n\n"
        "We have identified a quantity variance of {difference} on invoice "
        "{invoice_id} against purchase order {po_number} "
        "(Invoice: {invoice_value} | PO: {po_value}).\n\n"
        "{rag_section}"
        "Please issue a credit note or corrected invoice reflecting the "
        "correct quantities within {sla} business days.\n\n"
        "Best regards,\nAccounts Payable Team\nAcme Manufacturing\n"
        "ap-disputes@acme-manufacturing.com"
    ),
    "TAX_MISCODE": (
        "Subject: Tax Calculation Discrepancy – {invoice_id} / {po_number}\n\n"
        "Dear {vendor_name} Finance Team,\n\n"
        "We have identified a tax calculation discrepancy on invoice "
        "{invoice_id} against purchase order {po_number}. "
        "The applied tax code does not match our registered tax rate.\n\n"
        "{rag_section}"
        "Please review the tax code applied and resubmit a corrected invoice "
        "within {sla} business days.\n\n"
        "Best regards,\nAccounts Payable Team\nAcme Manufacturing\n"
        "ap-disputes@acme-manufacturing.com"
    ),
    "MISSING_PO": (
        "Subject: Missing Purchase Order Reference – {invoice_id}\n\n"
        "Dear {vendor_name} Finance Team,\n\n"
        "We received invoice {invoice_id} (total: {invoice_value}), but we "
        "are unable to locate a corresponding purchase order in our system.\n\n"
        "{rag_section}"
        "Please provide the purchase order reference within {sla} business "
        "days so we can complete reconciliation.\n\n"
        "Best regards,\nAccounts Payable Team\nAcme Manufacturing\n"
        "ap-disputes@acme-manufacturing.com"
    ),
}


def _build_rag_section(rag: dict) -> str:
    """Build the RAG-grounded context paragraph for the email."""
    parts = []
    if rag.get("contract_terms"):
        parts.append("Contract reference: " + "; ".join(rag["contract_terms"]))
    if rag.get("dispute_history"):
        parts.append("Prior disputes: " + "; ".join(rag["dispute_history"]))
    if rag.get("suggested_action"):
        parts.append("Suggested resolution: " + rag["suggested_action"] + ".")
    return ("\n".join(parts) + "\n\n") if parts else ""


def _fmt(value) -> str:
    """Format numeric value to 2dp string, or return as-is if not numeric."""
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value) if value is not None else "N/A"


def _template_email(mismatch: dict) -> str:
    mismatch_type = mismatch.get("mismatch_type", "PRICE_VARIANCE")
    template      = _TEMPLATES.get(mismatch_type, _TEMPLATES["PRICE_VARIANCE"])
    rag           = mismatch.get("rag_context", {})
    sla           = AP_POLICIES_SLA(rag, mismatch.get("vendor_name", ""))

    return template.format(
        invoice_id    = mismatch.get("invoice_id", "N/A"),
        po_number     = mismatch.get("po_number", "N/A"),
        vendor_name   = mismatch.get("vendor_name", "Vendor"),
        invoice_value = _fmt(mismatch.get("invoice_value")),
        po_value      = _fmt(mismatch.get("po_value")),
        difference    = _fmt(mismatch.get("difference")),
        rag_section   = _build_rag_section(rag),
        sla           = sla,
    )


def AP_POLICIES_SLA(rag: dict, vendor_name: str) -> int:
    """Return SLA days from contract if available, else default."""
    if rag.get("contract_terms"):
        for term in rag["contract_terms"]:
            if "Dispute SLA:" in term:
                try:
                    return int(term.split("Dispute SLA:")[1].split("business")[0].strip())
                except (ValueError, IndexError):
                    pass
    return _DISPUTE_SLA


# ---------------------------------------------------------------------------
# LLM generator (OpenAI gpt-3.5-turbo)
# ---------------------------------------------------------------------------

def _llm_email(mismatch: dict) -> str:
    """Generate email via OpenAI API. Returns empty string on failure."""
    try:
        from openai import OpenAI
        client = OpenAI()

        rag = mismatch.get("rag_context", {})
        rag_text = _build_rag_section(rag).strip()

        system_prompt = (
            "You are a professional accounts payable specialist at Acme Manufacturing. "
            "Write a polite but firm vendor dispute email. "
            "Be concise (under 200 words). Include subject line."
        )
        user_prompt = (
            f"Write a dispute email for:\n"
            f"- Invoice: {mismatch.get('invoice_id')}\n"
            f"- PO: {mismatch.get('po_number', 'N/A')}\n"
            f"- Vendor: {mismatch.get('vendor_name', 'Vendor')}\n"
            f"- Issue: {mismatch.get('mismatch_type')}\n"
            f"- Invoice value: {_fmt(mismatch.get('invoice_value'))}\n"
            f"- PO value: {_fmt(mismatch.get('po_value'))}\n"
            f"- Difference: {_fmt(mismatch.get('difference'))}\n"
            + (f"\nContext from knowledge base:\n{rag_text}" if rag_text else "")
            + f"\n\nRequest response within {_DISPUTE_SLA} business days."
        )

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=400,
        )
        return response.choices[0].message.content

    except Exception as e:
        logger.warning("LLM email generation failed (%s). Using template.", e)
        return ""
