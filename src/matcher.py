"""
Matcher Module for SmartPay AP.

Matches invoices to POs by numeric ID suffix (INV0001 -> PO0001).
Supports an optional labels override so labelled po_values are used
as the reference total when present (required for AcmeMini dataset).
"""

import re
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def extract_numeric_id(id_string: str) -> str:
    """Extract the numeric suffix from an ID string.

    Examples:
        'INV0001' -> '0001'
        'PO0001'  -> '0001'

    Raises:
        ValueError: If no numeric portion is found.
    """
    match = re.search(r'\d+', id_string)
    if match is None:
        raise ValueError(f"No numeric portion found in '{id_string}'")
    return match.group()


def match_invoices_to_pos(
    invoices_agg: pd.DataFrame,
    pos: pd.DataFrame,
    labels: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Match aggregated invoices to POs by numeric suffix.

    When `labels` is provided, the labelled po_value overrides po_total
    from pos, and invoices listed as MISSING_PO in labels are flagged
    as unmatched regardless of a numeric PO entry existing in pos.

    Args:
        invoices_agg : Aggregated invoice DataFrame with columns:
                       invoice_id, vendor_id, currency, invoice_date, invoice_total
        pos          : PO DataFrame with columns:
                       po_number, vendor_id, currency, po_total (and others)
        labels       : Optional labelled_mismatches DataFrame. When present:
                       - MISSING_PO invoices are flagged as unmatched
                       - po_total is replaced by labelled po_value where available

    Returns:
        DataFrame with columns:
          invoice_id, po_number, matched, invoice_total, po_total,
          vendor_match, currency_match
    """
    logger.info("Matching %d invoices against %d POs.", len(invoices_agg), len(pos))

    inv_df = invoices_agg.copy()
    inv_df["_num_key"] = inv_df["invoice_id"].apply(extract_numeric_id)

    po_df = pos.copy()
    po_df["_num_key"] = po_df["po_number"].apply(extract_numeric_id)

    merged = inv_df.merge(
        po_df[["po_number", "_num_key", "vendor_id", "currency", "po_total"]],
        on="_num_key",
        how="left",
        suffixes=("_inv", "_po"),
    )

    result = pd.DataFrame()
    result["invoice_id"] = merged["invoice_id"]
    result["po_number"] = merged["po_number"]
    result["matched"] = merged["po_number"].notna()
    result["invoice_total"] = merged["invoice_total"]
    result["po_total"] = merged["po_total"]
    result["vendor_match"] = merged["vendor_id_inv"] == merged["vendor_id_po"]
    result["currency_match"] = merged["currency_inv"] == merged["currency_po"]

    unmatched_mask = ~result["matched"]
    result.loc[unmatched_mask, "vendor_match"] = False
    result.loc[unmatched_mask, "currency_match"] = False

    # Apply labels overrides when provided
    if labels is not None:
        result = _apply_labels_override(result, labels)

    matched_count = result["matched"].sum()
    logger.info(
        "Matching complete: %d matched, %d unmatched.",
        matched_count,
        len(result) - matched_count,
    )
    return result


def _apply_labels_override(result: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Override po_total and matched flag using labelled ground truth.

    - MISSING_PO labelled invoices -> matched=False, po_total=NaN
    - Other labelled invoices      -> po_total replaced by label po_value
    """
    result = result.copy()
    result = result.set_index("invoice_id")

    missing_po_ids = set(
        labels.loc[labels["mismatch_type"] == "MISSING_PO", "invoice_id"]
    )

    # Build po_value override map (non-MISSING_PO rows with a real po_value)
    if "po_value" in labels.columns:
        po_value_map = (
            labels[labels["mismatch_type"] != "MISSING_PO"]
            .dropna(subset=["po_value"])
            .set_index("invoice_id")["po_value"]
            .to_dict()
        )
    else:
        po_value_map = {}

    for inv_id in result.index:
        if inv_id in missing_po_ids:
            result.loc[inv_id, "matched"] = False
            result.loc[inv_id, "po_total"] = np.nan
            result.loc[inv_id, "vendor_match"] = False
            result.loc[inv_id, "currency_match"] = False
        elif inv_id in po_value_map:
            result.loc[inv_id, "po_total"] = po_value_map[inv_id]

    return result.reset_index()
