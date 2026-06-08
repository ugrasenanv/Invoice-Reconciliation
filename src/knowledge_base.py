"""
Knowledge Base for SmartPay AP.

Simulates the vendor contract store, dispute history ledger,
and internal AP policy rules that a production system would
retrieve from Azure AI Search (vector embeddings).

In production: embedded documents in Azure AI Search, queried
via semantic similarity. Here: in-memory dicts for MVP.
"""

VENDOR_CONTRACTS: dict[str, dict] = {
    "Vendor_4":  {"contract_date": "2024-01-15", "currency": "USD",
                  "payment_terms": 30, "dispute_sla_days": 5},
    "Vendor_5":  {"contract_date": "2024-01-20", "currency": "INR",
                  "payment_terms": 45, "dispute_sla_days": 7},
    "Vendor_12": {"contract_date": "2024-03-10", "currency": "GBP",
                  "payment_terms": 30, "dispute_sla_days": 5},
    "Vendor_19": {"contract_date": "2024-02-01", "currency": "EUR",
                  "payment_terms": 30, "dispute_sla_days": 5},
}

DISPUTE_HISTORY: dict[str, list[dict]] = {
    "Vendor_4":  [
        {"date": "2024-03-01", "type": "PRICE_VARIANCE",    "resolution": "Credit note issued"},
        {"date": "2024-05-15", "type": "QUANTITY_VARIANCE", "resolution": "Revised invoice accepted"},
    ],
    "Vendor_19": [
        {"date": "2024-02-10", "type": "PRICE_VARIANCE",    "resolution": "Credit note issued"},
        {"date": "2024-04-20", "type": "PRICE_VARIANCE",    "resolution": "Credit note issued"},
    ],
    "Vendor_12": [
        {"date": "2024-01-05", "type": "TAX_MISCODE",       "resolution": "Tax code corrected, resubmitted"},
    ],
    "Vendor_5":  [
        {"date": "2024-03-18", "type": "QUANTITY_VARIANCE", "resolution": "Revised invoice accepted"},
        {"date": "2024-06-02", "type": "PRICE_VARIANCE",    "resolution": "Credit note issued"},
    ],
}

AP_POLICIES: dict[str, object] = {
    "high_value_threshold":    50_000.0,   # invoices above this go to manual review
    "dual_approval_threshold": 25_000.0,   # invoices above this need two approvers
    "price_tolerance_pct":     0.01,       # 1% price deviation allowed without dispute
    "dispute_response_days":   5,          # SLA for vendor to respond
    "payment_terms_days":      30,
    "duplicate_check_days":    90,
}


def get_vendor_context(vendor_name: str, mismatch_type: str) -> dict:
    """Return contract terms and dispute history for a vendor + mismatch type.

    Args:
        vendor_name  : e.g. 'Vendor_19'
        mismatch_type: e.g. 'PRICE_VARIANCE'

    Returns:
        dict with contract_terms, dispute_history, suggested_action, policy_notes
    """
    context: dict = {
        "contract_terms":  [],
        "dispute_history": [],
        "suggested_action": "",
        "policy_notes":    [],
    }

    contract = VENDOR_CONTRACTS.get(vendor_name)
    if contract:
        context["contract_terms"].append(
            f"Contract dated {contract['contract_date']} | "
            f"Payment terms: {contract['payment_terms']} days | "
            f"Dispute SLA: {contract['dispute_sla_days']} business days"
        )

    history = DISPUTE_HISTORY.get(vendor_name, [])
    if history:
        for h in history[-2:]:
            context["dispute_history"].append(
                f"{h['date']}: {h['type']} resolved via {h['resolution']}"
            )
        resolutions = [h["resolution"] for h in history]
        credit_count = sum(1 for r in resolutions if "Credit note" in r)
        if credit_count >= 2:
            context["suggested_action"] = (
                f"Request credit note — vendor has resolved {credit_count} "
                "disputes this way previously"
            )
        elif any("Revised invoice" in r for r in resolutions):
            context["suggested_action"] = (
                "Request revised invoice — vendor has accepted this approach previously"
            )

    context["policy_notes"].append(
        f"Dispute response required within "
        f"{AP_POLICIES['dispute_response_days']} business days"
    )
    context["policy_notes"].append(
        f"Price tolerance: {AP_POLICIES['price_tolerance_pct']*100:.0f}% — "
        "deviations above this must be formally disputed"
    )

    return context
