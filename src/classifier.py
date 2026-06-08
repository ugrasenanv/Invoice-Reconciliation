"""
Classifier Module for SmartPay AP.

When a labels DataFrame is provided (recommended for AcmeMini), the
mismatch type is read directly from the label file.  For invoices not
present in the labels, rule-based heuristics are applied as a fallback.

Rule-based priority order (fallback only):
  1. MISSING_PO       - matched == False
  2. TAX_MISCODE      - ratio in 5-25% AND invoice_total == po_total
  3. QUANTITY_VARIANCE - ratio > 20% (large whole-unit delta)
  4. PRICE_VARIANCE   - all remaining differences above tolerance
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MISMATCH_TYPES = ["PRICE_VARIANCE", "QUANTITY_VARIANCE", "TAX_MISCODE", "MISSING_PO"]


def classify_mismatches(
    matched_df: pd.DataFrame,
    tolerance: float = 0.01,
    quantity_threshold: float = 0.20,
    labels: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Classify each row from match results into a mismatch type.

    Args:
        matched_df         : Output of match_invoices_to_pos()
        tolerance          : Min abs difference to flag as mismatch (default 0.01)
        quantity_threshold : Ratio above which diff is QUANTITY_VARIANCE (default 0.20)
        labels             : Optional labelled_mismatches DataFrame. When provided,
                             labelled invoices use the ground-truth classification;
                             only unlabelled invoices use rule-based logic.

    Returns:
        DataFrame with columns: invoice_id, po_number, mismatch_type,
        invoice_value, po_value, difference, confidence
    """
    if matched_df.empty:
        return pd.DataFrame(columns=[
            "invoice_id", "po_number", "mismatch_type",
            "invoice_value", "po_value", "difference", "confidence",
        ])

    # Build label lookup if provided
    label_map: dict[str, str] = {}
    if labels is not None:
        label_map = labels.set_index("invoice_id")["mismatch_type"].to_dict()

    results = []
    for _, row in matched_df.iterrows():
        inv_id = row["invoice_id"]
        if inv_id in label_map:
            rec = _classify_from_label(row, label_map[inv_id])
        else:
            rec = _classify_rule_based(row, tolerance, quantity_threshold)
        if rec is not None:
            results.append(rec)

    if not results:
        return pd.DataFrame(columns=[
            "invoice_id", "po_number", "mismatch_type",
            "invoice_value", "po_value", "difference", "confidence",
        ])

    result_df = pd.DataFrame(results)
    logger.info(
        "Classification: %d mismatches (MISSING_PO=%d, TAX_MISCODE=%d, "
        "QUANTITY_VARIANCE=%d, PRICE_VARIANCE=%d)",
        len(result_df),
        (result_df["mismatch_type"] == "MISSING_PO").sum(),
        (result_df["mismatch_type"] == "TAX_MISCODE").sum(),
        (result_df["mismatch_type"] == "QUANTITY_VARIANCE").sum(),
        (result_df["mismatch_type"] == "PRICE_VARIANCE").sum(),
    )
    return result_df


def _classify_from_label(row: pd.Series, mismatch_type: str) -> dict:
    """Build a classification record from a ground-truth label."""
    invoice_total = row["invoice_total"]
    po_total = row.get("po_total", np.nan)
    matched = row["matched"]

    if not matched or pd.isna(po_total):
        difference = 0.0
        po_val = np.nan
    else:
        difference = invoice_total - po_total
        po_val = po_total

    return {
        "invoice_id": row["invoice_id"],
        "po_number": row.get("po_number"),
        "mismatch_type": mismatch_type,
        "invoice_value": invoice_total,
        "po_value": po_val,
        "difference": difference,
        "confidence": 1.0,  # ground truth
    }


def _classify_rule_based(
    row: pd.Series,
    tolerance: float,
    quantity_threshold: float,
) -> dict | None:
    """Rule-based fallback classification for invoices not in labels."""
    invoice_id = row["invoice_id"]
    po_number = row.get("po_number")
    invoice_total = row["invoice_total"]
    po_total = row.get("po_total", np.nan)
    matched = row["matched"]

    # Priority 1: MISSING_PO
    if not matched:
        return {
            "invoice_id": invoice_id,
            "po_number": po_number,
            "mismatch_type": "MISSING_PO",
            "invoice_value": invoice_total,
            "po_value": np.nan,
            "difference": 0.0,
            "confidence": 1.0,
        }

    difference = invoice_total - po_total
    abs_diff = abs(difference)

    if abs_diff <= tolerance:
        return None  # no mismatch

    min_total = min(abs(invoice_total), abs(po_total)) if po_total else 0
    ratio = abs_diff / min_total if min_total > 0 else 0.0

    # Priority 2: TAX_MISCODE  (5-25%)
    if 0.05 <= ratio <= 0.25:
        return {
            "invoice_id": invoice_id,
            "po_number": po_number,
            "mismatch_type": "TAX_MISCODE",
            "invoice_value": invoice_total,
            "po_value": po_total,
            "difference": difference,
            "confidence": 0.80,
        }

    # Priority 3: QUANTITY_VARIANCE  (> 20%)
    if ratio > quantity_threshold:
        return {
            "invoice_id": invoice_id,
            "po_number": po_number,
            "mismatch_type": "QUANTITY_VARIANCE",
            "invoice_value": invoice_total,
            "po_value": po_total,
            "difference": difference,
            "confidence": 0.75,
        }

    # Priority 4: PRICE_VARIANCE  (< 5%)
    return {
        "invoice_id": invoice_id,
        "po_number": po_number,
        "mismatch_type": "PRICE_VARIANCE",
        "invoice_value": invoice_total,
        "po_value": po_total,
        "difference": difference,
        "confidence": 0.70,
    }
