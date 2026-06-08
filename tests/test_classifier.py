"""Unit tests for the Classifier module."""

import numpy as np
import pandas as pd
import pytest

from src.classifier import classify_mismatches, _classify_rule_based


def _make_df(rows: list[dict]) -> pd.DataFrame:
    defaults = {
        "invoice_id": "INV0001",
        "po_number": "PO0001",
        "matched": True,
        "invoice_total": 1000.0,
        "po_total": 1000.0,
        "vendor_match": True,
        "currency_match": True,
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


class TestClassifyMismatches:

    def test_empty_input(self):
        empty = pd.DataFrame(columns=[
            "invoice_id", "po_number", "matched",
            "invoice_total", "po_total", "vendor_match", "currency_match",
        ])
        result = classify_mismatches(empty)
        assert list(result.columns) == [
            "invoice_id", "po_number", "mismatch_type",
            "invoice_value", "po_value", "difference", "confidence",
        ]
        assert len(result) == 0

    def test_missing_po(self):
        df = _make_df([{
            "invoice_id": "INV0099", "po_number": None, "matched": False,
            "invoice_total": 5000.0, "po_total": np.nan,
            "vendor_match": False, "currency_match": False,
        }])
        result = classify_mismatches(df)
        assert len(result) == 1
        row = result.iloc[0]
        assert row["mismatch_type"] == "MISSING_PO"
        assert row["invoice_value"] == 5000.0
        assert pd.isna(row["po_value"])

    def test_label_driven_overrides_rules(self):
        """When labels provided, mismatch type comes from label, not ratio."""
        df = _make_df([{
            "invoice_id": "INV0001", "po_number": "PO0001",
            "invoice_total": 10000.0, "po_total": 10000.0,  # ratio=0, no mismatch by rules
        }])
        labels = pd.DataFrame([{"invoice_id": "INV0001", "mismatch_type": "TAX_MISCODE"}])
        result = classify_mismatches(df, labels=labels)
        assert len(result) == 1
        assert result.iloc[0]["mismatch_type"] == "TAX_MISCODE"
        assert result.iloc[0]["confidence"] == 1.0

    def test_tax_miscode_percentage_difference(self):
        """Rule-based: 10% difference classified as TAX_MISCODE."""
        df = _make_df([{"invoice_id": "INV0010", "invoice_total": 1000.0, "po_total": 909.09}])
        result = classify_mismatches(df)
        assert len(result) == 1
        assert result.iloc[0]["mismatch_type"] == "TAX_MISCODE"

    def test_quantity_variance_large_difference(self):
        """Rule-based: >20% difference classified as QUANTITY_VARIANCE."""
        df = _make_df([{"invoice_id": "INV0020", "invoice_total": 13000.0, "po_total": 10000.0}])
        result = classify_mismatches(df)
        assert len(result) == 1
        assert result.iloc[0]["mismatch_type"] == "QUANTITY_VARIANCE"

    def test_price_variance_small_difference(self):
        """Rule-based: <5% difference classified as PRICE_VARIANCE."""
        df = _make_df([{"invoice_id": "INV0030", "invoice_total": 10200.0, "po_total": 10000.0}])
        result = classify_mismatches(df)
        assert len(result) == 1
        assert result.iloc[0]["mismatch_type"] == "PRICE_VARIANCE"

    def test_no_mismatch_within_tolerance(self):
        df = _make_df([{
            "invoice_id": "INV0040", "invoice_total": 10000.005, "po_total": 10000.0,
            "vendor_match": True, "currency_match": True,
        }])
        result = classify_mismatches(df)
        assert len(result) == 0

    def test_output_columns(self):
        df = _make_df([{
            "invoice_id": "INV0001", "po_number": None, "matched": False,
            "po_total": np.nan, "vendor_match": False, "currency_match": False,
        }])
        result = classify_mismatches(df)
        assert list(result.columns) == [
            "invoice_id", "po_number", "mismatch_type",
            "invoice_value", "po_value", "difference", "confidence",
        ]

    def test_difference_computed_correctly(self):
        df = _make_df([{"invoice_id": "INV0060", "invoice_total": 8000.0, "po_total": 10000.0}])
        result = classify_mismatches(df)
        assert len(result) == 1
        assert result.iloc[0]["difference"] == pytest.approx(-2000.0)

    def test_custom_tolerance(self):
        df = _make_df([{
            "invoice_id": "INV0070", "invoice_total": 10000.50, "po_total": 10000.0,
            "vendor_match": True, "currency_match": True,
        }])
        assert len(classify_mismatches(df, tolerance=0.01)) == 1
        assert len(classify_mismatches(df, tolerance=1.0)) == 0

    def test_multiple_label_types(self):
        """All four types returned when labels provide full coverage."""
        df = _make_df([
            {"invoice_id": "INV0001", "po_number": None, "matched": False,
             "po_total": np.nan, "vendor_match": False, "currency_match": False},
            {"invoice_id": "INV0002", "invoice_total": 11000.0, "po_total": 10000.0},
            {"invoice_id": "INV0003", "invoice_total": 12500.0, "po_total": 10000.0},
            {"invoice_id": "INV0004", "invoice_total": 10200.0, "po_total": 10000.0},
        ])
        labels = pd.DataFrame([
            {"invoice_id": "INV0001", "mismatch_type": "MISSING_PO"},
            {"invoice_id": "INV0002", "mismatch_type": "TAX_MISCODE"},
            {"invoice_id": "INV0003", "mismatch_type": "QUANTITY_VARIANCE"},
            {"invoice_id": "INV0004", "mismatch_type": "PRICE_VARIANCE"},
        ])
        result = classify_mismatches(df, labels=labels)
        assert len(result) == 4
        types = set(result["mismatch_type"])
        assert types == {"MISSING_PO", "TAX_MISCODE", "QUANTITY_VARIANCE", "PRICE_VARIANCE"}

    def test_negative_difference(self):
        """Negative differences (PO > invoice) are classified correctly."""
        df = _make_df([{"invoice_id": "INV0090", "invoice_total": 8500.0, "po_total": 10000.0}])
        result = classify_mismatches(df)
        assert len(result) == 1
        assert result.iloc[0]["difference"] < 0


class TestClassifyRuleBased:

    def test_returns_none_for_clean_match(self):
        row = pd.Series({
            "invoice_id": "INV0001", "po_number": "PO0001",
            "matched": True, "invoice_total": 5000.0, "po_total": 5000.0,
            "vendor_match": True, "currency_match": True,
        })
        assert _classify_rule_based(row, tolerance=0.01, quantity_threshold=0.20) is None

    def test_missing_po_takes_priority(self):
        row = pd.Series({
            "invoice_id": "INV0001", "po_number": None,
            "matched": False, "invoice_total": 5000.0, "po_total": np.nan,
            "vendor_match": False, "currency_match": False,
        })
        result = _classify_rule_based(row, tolerance=0.01, quantity_threshold=0.20)
        assert result["mismatch_type"] == "MISSING_PO"
