"""
Evaluator Module for SmartPay AP.

Measures classification accuracy against labelled ground truth using
sklearn.metrics.classification_report.
"""

import logging

import pandas as pd
from sklearn.metrics import classification_report

logger = logging.getLogger(__name__)

# The four mismatch classes in priority order
MISMATCH_CLASSES = [
    "PRICE_VARIANCE",
    "QUANTITY_VARIANCE",
    "TAX_MISCODE",
    "MISSING_PO",
]


def evaluate(predictions: pd.DataFrame, ground_truth: pd.DataFrame) -> dict:
    """Compare predicted mismatch classifications against ground truth.

    Parameters:
        predictions: DataFrame with columns invoice_id, mismatch_type
        ground_truth: DataFrame from labelled_mismatches.csv with columns
                      invoice_id, mismatch_type

    Returns:
        dict with structure:
        {
            "per_class": {
                "PRICE_VARIANCE": {"precision": float, "recall": float, "f1": float, "support": int},
                "QUANTITY_VARIANCE": {"precision": float, "recall": float, "f1": float, "support": int},
                "TAX_MISCODE": {"precision": float, "recall": float, "f1": float, "support": int},
                "MISSING_PO": {"precision": float, "recall": float, "f1": float, "support": int}
            },
            "macro_avg": {"precision": float, "recall": float, "f1": float}
        }

    Handles misaligned invoice sets by inner-joining on invoice_id.
    Uses sklearn.metrics.classification_report internally.
    """
    # Handle empty inputs
    if predictions.empty or ground_truth.empty:
        empty_class = {"precision": 0.0, "recall": 0.0, "f1": 0.0, "support": 0}
        return {
            "per_class": {cls: empty_class.copy() for cls in MISMATCH_CLASSES},
            "macro_avg": {"precision": 0.0, "recall": 0.0, "f1": 0.0},
        }

    # Inner join on invoice_id to handle misaligned sets
    merged = predictions[["invoice_id", "mismatch_type"]].merge(
        ground_truth[["invoice_id", "mismatch_type"]],
        on="invoice_id",
        how="inner",
        suffixes=("_pred", "_true"),
    )

    if merged.empty:
        empty_class = {"precision": 0.0, "recall": 0.0, "f1": 0.0, "support": 0}
        return {
            "per_class": {cls: empty_class.copy() for cls in MISMATCH_CLASSES},
            "macro_avg": {"precision": 0.0, "recall": 0.0, "f1": 0.0},
        }

    y_true = merged["mismatch_type_true"]
    y_pred = merged["mismatch_type_pred"]

    # Generate classification report as dict
    report = classification_report(
        y_true,
        y_pred,
        labels=MISMATCH_CLASSES,
        output_dict=True,
        zero_division=0,
    )

    # Build per-class metrics
    per_class = {}
    for cls in MISMATCH_CLASSES:
        cls_metrics = report.get(cls, {})
        per_class[cls] = {
            "precision": cls_metrics.get("precision", 0.0),
            "recall": cls_metrics.get("recall", 0.0),
            "f1": cls_metrics.get("f1-score", 0.0),
            "support": int(cls_metrics.get("support", 0)),
        }

    # Macro average
    macro = report.get("macro avg", {})
    macro_avg = {
        "precision": macro.get("precision", 0.0),
        "recall": macro.get("recall", 0.0),
        "f1": macro.get("f1-score", 0.0),
    }

    logger.info(
        "Evaluation complete on %d common invoices. Macro F1: %.3f",
        len(merged),
        macro_avg["f1"],
    )

    return {"per_class": per_class, "macro_avg": macro_avg}
