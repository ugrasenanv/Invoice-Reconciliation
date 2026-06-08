"""
Unit tests for src/data_loader.py.

Tests cover:
- Successful loading of invoices, PO/GRN, and labels files
- Aggregation correctness (sum of line items = invoice total)
- Date parsing (DD-MM-YYYY → datetime)
- Error handling for missing files
- Error handling for missing columns
"""

import os
import tempfile

import pandas as pd
import pytest

from src.data_loader import (
    aggregate_invoices,
    load_invoices,
    load_labels,
    load_po_grn,
)

# Path to the actual data directory
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


# --- Fixtures ---


@pytest.fixture
def sample_invoices_csv(tmp_path):
    """Create a small valid invoices CSV for testing."""
    csv_content = (
        "invoice_id,invoice_date,vendor_id,vendor_name,currency,"
        "line_item_number,item_code,description,quantity,unit_price,line_total\n"
        "INV0001,23-11-2024,V004,Vendor_4,USD,1,ITM0048,Widget,19,213.85,4063.15\n"
        "INV0001,23-11-2024,V004,Vendor_4,USD,2,ITM0002,Gadget,7,359.43,2516.01\n"
        "INV0002,04-07-2024,V019,Vendor_19,EUR,1,ITM0046,Component,3,428.38,1285.14\n"
        "INV0002,04-07-2024,V019,Vendor_19,EUR,2,ITM0007,Module,3,306.52,919.56\n"
    )
    path = tmp_path / "invoices.csv"
    path.write_text(csv_content)
    return str(path)


@pytest.fixture
def sample_po_grn_csv(tmp_path):
    """Create a small valid po_grn CSV for testing."""
    csv_content = (
        "po_number,po_date,vendor_id,vendor_name,po_total,currency,grn_number,grn_date\n"
        "PO0001,13-11-2024,V004,Vendor_4,16915.24,USD,GRN0001,19-11-2024\n"
        "PO0002,09-06-2024,V019,Vendor_19,8598.84,EUR,GRN0002,29-06-2024\n"
    )
    path = tmp_path / "po_grn.csv"
    path.write_text(csv_content)
    return str(path)


@pytest.fixture
def sample_labels_csv(tmp_path):
    """Create a small valid labelled_mismatches CSV for testing."""
    csv_content = (
        "invoice_id,po_number,mismatch_type,invoice_value,po_value,difference\n"
        "INV0188,PO0188,TAX_MISCODE,15147.66,,\n"
        "INV0087,,MISSING_PO,7625.74,,\n"
        "INV0272,PO0272,PRICE_VARIANCE,20158.4,20183.82,25.42\n"
    )
    path = tmp_path / "labelled_mismatches.csv"
    path.write_text(csv_content)
    return str(path)


# --- Tests: Successful Loading ---


class TestLoadInvoices:
    """Tests for load_invoices function."""

    def test_loads_valid_csv(self, sample_invoices_csv):
        """Successfully loads a valid invoices CSV."""
        df = load_invoices(sample_invoices_csv)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 4

    def test_contains_expected_columns(self, sample_invoices_csv):
        """Result has all expected columns."""
        df = load_invoices(sample_invoices_csv)
        expected_cols = [
            "invoice_id", "invoice_date", "vendor_id", "vendor_name",
            "currency", "line_item_number", "item_code", "description",
            "quantity", "unit_price", "line_total",
        ]
        for col in expected_cols:
            assert col in df.columns

    def test_date_parsing(self, sample_invoices_csv):
        """invoice_date is parsed as datetime from DD-MM-YYYY."""
        df = load_invoices(sample_invoices_csv)
        assert pd.api.types.is_datetime64_any_dtype(df["invoice_date"])
        # 23-11-2024 should be November 23, 2024
        first_date = df["invoice_date"].iloc[0]
        assert first_date.day == 23
        assert first_date.month == 11
        assert first_date.year == 2024

    def test_numeric_columns_are_numeric(self, sample_invoices_csv):
        """quantity, unit_price, line_total are numeric types."""
        df = load_invoices(sample_invoices_csv)
        assert pd.api.types.is_numeric_dtype(df["quantity"])
        assert pd.api.types.is_numeric_dtype(df["unit_price"])
        assert pd.api.types.is_numeric_dtype(df["line_total"])

    def test_drops_rows_with_invalid_numerics(self, tmp_path):
        """Rows with non-numeric values in quantity/unit_price/line_total are dropped."""
        csv_content = (
            "invoice_id,invoice_date,vendor_id,vendor_name,currency,"
            "line_item_number,item_code,description,quantity,unit_price,line_total\n"
            "INV0001,23-11-2024,V004,Vendor_4,USD,1,ITM0048,Widget,19,213.85,4063.15\n"
            "INV0001,23-11-2024,V004,Vendor_4,USD,2,ITM0002,Gadget,abc,359.43,2516.01\n"
            "INV0002,04-07-2024,V019,Vendor_19,EUR,1,ITM0046,Component,3,N/A,1285.14\n"
        )
        path = tmp_path / "invoices_bad.csv"
        path.write_text(csv_content)
        df = load_invoices(str(path))
        # Only the first row should remain (second has 'abc', third has 'N/A')
        assert len(df) == 1
        assert df["invoice_id"].iloc[0] == "INV0001"

    def test_missing_file_raises_error(self):
        """FileNotFoundError raised for non-existent file."""
        with pytest.raises(FileNotFoundError, match="Invoice file not found"):
            load_invoices("/nonexistent/path/invoices.csv")

    def test_missing_columns_raises_error(self, tmp_path):
        """ValueError raised when required columns are missing."""
        csv_content = "invoice_id,invoice_date,vendor_id\nINV0001,23-11-2024,V004\n"
        path = tmp_path / "invoices_incomplete.csv"
        path.write_text(csv_content)
        with pytest.raises(ValueError, match="missing required columns"):
            load_invoices(str(path))

    def test_loads_real_data_file(self):
        """Integration test: loads the actual data file successfully."""
        real_path = os.path.join(DATA_DIR, "invoices.csv")
        if not os.path.isfile(real_path):
            pytest.skip("Real data file not available")
        df = load_invoices(real_path)
        assert len(df) > 0
        assert "invoice_id" in df.columns


class TestLoadPoGrn:
    """Tests for load_po_grn function."""

    def test_loads_valid_csv(self, sample_po_grn_csv):
        """Successfully loads a valid po_grn CSV."""
        df = load_po_grn(sample_po_grn_csv)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    def test_contains_expected_columns(self, sample_po_grn_csv):
        """Result has all expected columns."""
        df = load_po_grn(sample_po_grn_csv)
        expected_cols = [
            "po_number", "po_date", "vendor_id", "vendor_name",
            "po_total", "currency", "grn_number", "grn_date",
        ]
        for col in expected_cols:
            assert col in df.columns

    def test_date_parsing_po_date(self, sample_po_grn_csv):
        """po_date is parsed as datetime from DD-MM-YYYY."""
        df = load_po_grn(sample_po_grn_csv)
        assert pd.api.types.is_datetime64_any_dtype(df["po_date"])
        # 13-11-2024 should be November 13
        first_date = df["po_date"].iloc[0]
        assert first_date.day == 13
        assert first_date.month == 11
        assert first_date.year == 2024

    def test_date_parsing_grn_date(self, sample_po_grn_csv):
        """grn_date is parsed as datetime from DD-MM-YYYY."""
        df = load_po_grn(sample_po_grn_csv)
        assert pd.api.types.is_datetime64_any_dtype(df["grn_date"])
        # 19-11-2024 should be November 19
        first_date = df["grn_date"].iloc[0]
        assert first_date.day == 19
        assert first_date.month == 11
        assert first_date.year == 2024

    def test_missing_file_raises_error(self):
        """FileNotFoundError raised for non-existent file."""
        with pytest.raises(FileNotFoundError, match="PO/GRN file not found"):
            load_po_grn("/nonexistent/path/po_grn.csv")

    def test_missing_columns_raises_error(self, tmp_path):
        """ValueError raised when required columns are missing."""
        csv_content = "po_number,po_date\nPO0001,13-11-2024\n"
        path = tmp_path / "po_grn_incomplete.csv"
        path.write_text(csv_content)
        with pytest.raises(ValueError, match="missing required columns"):
            load_po_grn(str(path))

    def test_loads_real_data_file(self):
        """Integration test: loads the actual data file successfully."""
        real_path = os.path.join(DATA_DIR, "po_grn.csv")
        if not os.path.isfile(real_path):
            pytest.skip("Real data file not available")
        df = load_po_grn(real_path)
        assert len(df) > 0
        assert "po_number" in df.columns


class TestLoadLabels:
    """Tests for load_labels function."""

    def test_loads_valid_csv(self, sample_labels_csv):
        """Successfully loads a valid labels CSV."""
        df = load_labels(sample_labels_csv)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3

    def test_missing_file_raises_error(self):
        """FileNotFoundError raised for non-existent file."""
        with pytest.raises(FileNotFoundError, match="Labels file not found"):
            load_labels("/nonexistent/path/labels.csv")

    def test_loads_real_data_file(self):
        """Integration test: loads the actual data file successfully."""
        real_path = os.path.join(DATA_DIR, "labelled_mismatches.csv")
        if not os.path.isfile(real_path):
            pytest.skip("Real data file not available")
        df = load_labels(real_path)
        assert len(df) > 0
        assert "invoice_id" in df.columns
        assert "mismatch_type" in df.columns


class TestAggregateInvoices:
    """Tests for aggregate_invoices function."""

    def test_aggregation_sum_correctness(self, sample_invoices_csv):
        """Sum of line_total for each invoice_id matches invoice_total."""
        df = load_invoices(sample_invoices_csv)
        agg = aggregate_invoices(df)

        # INV0001 has line_totals: 4063.15 + 2516.01 = 6579.16
        inv1 = agg[agg["invoice_id"] == "INV0001"]
        assert len(inv1) == 1
        assert abs(inv1["invoice_total"].iloc[0] - 6579.16) < 0.01

        # INV0002 has line_totals: 1285.14 + 919.56 = 2204.70
        inv2 = agg[agg["invoice_id"] == "INV0002"]
        assert len(inv2) == 1
        assert abs(inv2["invoice_total"].iloc[0] - 2204.70) < 0.01

    def test_output_columns(self, sample_invoices_csv):
        """Aggregated output has the correct columns."""
        df = load_invoices(sample_invoices_csv)
        agg = aggregate_invoices(df)
        expected_cols = ["invoice_id", "vendor_id", "currency", "invoice_date", "invoice_total"]
        for col in expected_cols:
            assert col in agg.columns

    def test_preserves_first_vendor_id(self, sample_invoices_csv):
        """Aggregation preserves the first vendor_id per group."""
        df = load_invoices(sample_invoices_csv)
        agg = aggregate_invoices(df)
        inv1 = agg[agg["invoice_id"] == "INV0001"]
        assert inv1["vendor_id"].iloc[0] == "V004"

    def test_preserves_first_currency(self, sample_invoices_csv):
        """Aggregation preserves the first currency per group."""
        df = load_invoices(sample_invoices_csv)
        agg = aggregate_invoices(df)
        inv2 = agg[agg["invoice_id"] == "INV0002"]
        assert inv2["currency"].iloc[0] == "EUR"

    def test_preserves_invoice_date(self, sample_invoices_csv):
        """Aggregation preserves the first invoice_date per group."""
        df = load_invoices(sample_invoices_csv)
        agg = aggregate_invoices(df)
        inv1 = agg[agg["invoice_id"] == "INV0001"]
        assert inv1["invoice_date"].iloc[0].day == 23
        assert inv1["invoice_date"].iloc[0].month == 11

    def test_one_row_per_invoice(self, sample_invoices_csv):
        """Each invoice_id appears exactly once in aggregated output."""
        df = load_invoices(sample_invoices_csv)
        agg = aggregate_invoices(df)
        assert len(agg) == 2  # INV0001 and INV0002
        assert agg["invoice_id"].nunique() == 2

    def test_aggregation_with_real_data(self):
        """Integration test: aggregation on real data produces correct totals."""
        real_path = os.path.join(DATA_DIR, "invoices.csv")
        if not os.path.isfile(real_path):
            pytest.skip("Real data file not available")
        df = load_invoices(real_path)
        agg = aggregate_invoices(df)

        # Verify that sum of line_total per group matches invoice_total
        manual_sums = df.groupby("invoice_id")["line_total"].sum()
        for _, row in agg.iterrows():
            expected_total = manual_sums[row["invoice_id"]]
            assert abs(row["invoice_total"] - expected_total) < 0.01
