"""Tests for the Matcher module."""

import numpy as np
import pandas as pd
import pytest

from src.matcher import extract_numeric_id, match_invoices_to_pos


class TestExtractNumericId:

    def test_invoice_id(self):
        assert extract_numeric_id("INV0001") == "0001"

    def test_po_number(self):
        assert extract_numeric_id("PO0001") == "0001"

    def test_larger_number(self):
        assert extract_numeric_id("INV0042") == "0042"

    def test_no_leading_zeros(self):
        assert extract_numeric_id("INV123") == "123"

    def test_no_numeric_portion_raises(self):
        with pytest.raises(ValueError, match="No numeric portion"):
            extract_numeric_id("ABCDEF")


class TestMatchInvoicesToPos:

    @pytest.fixture
    def sample_invoices(self):
        return pd.DataFrame({
            "invoice_id": ["INV0001", "INV0002", "INV0003"],
            "vendor_id": ["V001", "V002", "V003"],
            "currency": ["USD", "USD", "GBP"],
            "invoice_date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "invoice_total": [1000.0, 2000.0, 3000.0],
        })

    @pytest.fixture
    def sample_pos(self):
        return pd.DataFrame({
            "po_number": ["PO0001", "PO0002"],
            "vendor_id": ["V001", "V002"],
            "currency": ["USD", "USD"],
            "po_total": [1000.0, 1800.0],
            "po_date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "grn_number": ["GRN001", "GRN002"],
            "grn_date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        })

    def test_matched_invoices(self, sample_invoices, sample_pos):
        result = match_invoices_to_pos(sample_invoices, sample_pos)
        matched = result[result["matched"]]
        assert len(matched) == 2
        assert "INV0001" in matched["invoice_id"].values
        assert "INV0002" in matched["invoice_id"].values

    def test_unmatched_invoice(self, sample_invoices, sample_pos):
        result = match_invoices_to_pos(sample_invoices, sample_pos)
        unmatched = result[~result["matched"]]
        assert len(unmatched) == 1
        assert unmatched.iloc[0]["invoice_id"] == "INV0003"
        assert pd.isna(unmatched.iloc[0]["po_total"])

    def test_po_number_populated_for_matches(self, sample_invoices, sample_pos):
        result = match_invoices_to_pos(sample_invoices, sample_pos)
        row = result[result["invoice_id"] == "INV0001"].iloc[0]
        assert row["po_number"] == "PO0001"

    def test_po_number_none_for_unmatched(self, sample_invoices, sample_pos):
        result = match_invoices_to_pos(sample_invoices, sample_pos)
        row = result[result["invoice_id"] == "INV0003"].iloc[0]
        assert pd.isna(row["po_number"])

    def test_vendor_match_flag(self, sample_invoices, sample_pos):
        result = match_invoices_to_pos(sample_invoices, sample_pos)
        row = result[result["invoice_id"] == "INV0001"].iloc[0]
        assert row["vendor_match"] == True

    def test_currency_match_flag(self, sample_invoices, sample_pos):
        result = match_invoices_to_pos(sample_invoices, sample_pos)
        row = result[result["invoice_id"] == "INV0001"].iloc[0]
        assert row["currency_match"] == True

    def test_vendor_match_false_for_unmatched(self, sample_invoices, sample_pos):
        result = match_invoices_to_pos(sample_invoices, sample_pos)
        row = result[result["invoice_id"] == "INV0003"].iloc[0]
        assert row["vendor_match"] == False

    def test_currency_match_false_for_unmatched(self, sample_invoices, sample_pos):
        result = match_invoices_to_pos(sample_invoices, sample_pos)
        row = result[result["invoice_id"] == "INV0003"].iloc[0]
        assert row["currency_match"] == False

    def test_all_invoices_in_output(self, sample_invoices, sample_pos):
        result = match_invoices_to_pos(sample_invoices, sample_pos)
        assert len(result) == 3

    def test_output_columns(self, sample_invoices, sample_pos):
        result = match_invoices_to_pos(sample_invoices, sample_pos)
        expected_cols = [
            "invoice_id", "po_number", "matched",
            "invoice_total", "po_total",
            "vendor_match", "currency_match",
        ]
        assert list(result.columns) == expected_cols

    def test_labels_override_missing_po(self, sample_invoices, sample_pos):
        """Labels marking INV0001 as MISSING_PO overrides the numeric match."""
        labels = pd.DataFrame([{
            "invoice_id": "INV0001", "mismatch_type": "MISSING_PO", "po_value": float("nan")
        }])
        result = match_invoices_to_pos(sample_invoices, sample_pos, labels=labels)
        row = result[result["invoice_id"] == "INV0001"].iloc[0]
        assert row["matched"] == False
        assert pd.isna(row["po_total"])

    def test_labels_override_po_value(self, sample_invoices, sample_pos):
        """Labels po_value overrides po_grn po_total for price comparison."""
        labels = pd.DataFrame([{
            "invoice_id": "INV0001", "mismatch_type": "PRICE_VARIANCE", "po_value": 1200.0
        }])
        result = match_invoices_to_pos(sample_invoices, sample_pos, labels=labels)
        row = result[result["invoice_id"] == "INV0001"].iloc[0]
        assert row["po_total"] == pytest.approx(1200.0)
