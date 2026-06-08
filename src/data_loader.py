"""
Data Loader Module for SmartPay AP.

Responsible for reading, validating, and preprocessing the AcmeMini CSV files
(invoices, purchase orders/GRNs, and labelled mismatches).
"""

import logging
import os

import pandas as pd

logger = logging.getLogger(__name__)

# Expected columns for each CSV file
INVOICE_COLUMNS = [
    "invoice_id",
    "invoice_date",
    "vendor_id",
    "vendor_name",
    "currency",
    "line_item_number",
    "item_code",
    "description",
    "quantity",
    "unit_price",
    "line_total",
]

PO_GRN_COLUMNS = [
    "po_number",
    "po_date",
    "vendor_id",
    "vendor_name",
    "po_total",
    "currency",
    "grn_number",
    "grn_date",
]


def _validate_columns(df: pd.DataFrame, required_columns: list[str], file_path: str) -> None:
    """Validate that the DataFrame contains all required columns.

    Raises:
        ValueError: If any required columns are missing, listing them in the message.
    """
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(
            f"File '{file_path}' is missing required columns: {missing}"
        )


def load_invoices(path: str) -> pd.DataFrame:
    """Load invoices.csv into a DataFrame.

    - Validates expected columns: invoice_id, invoice_date, vendor_id,
      vendor_name, currency, line_item_number, item_code, description,
      quantity, unit_price, line_total
    - Converts invoice_date from DD-MM-YYYY string to datetime
    - Logs warning and excludes rows with null/non-numeric quantity,
      unit_price, or line_total
    - Raises FileNotFoundError with descriptive message if file missing

    Args:
        path: Path to the invoices.csv file.

    Returns:
        Cleaned pandas DataFrame with validated and parsed data.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Invoice file not found: '{path}'")

    logger.info("Loading invoices from '%s'", path)
    df = pd.read_csv(path)

    _validate_columns(df, INVOICE_COLUMNS, path)

    # Convert date column
    df["invoice_date"] = pd.to_datetime(df["invoice_date"], format="%d-%m-%Y")

    # Validate numeric columns
    numeric_cols = ["quantity", "unit_price", "line_total"]
    initial_count = len(df)

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows where any numeric column is NaN (after coercion)
    mask = df[numeric_cols].isna().any(axis=1)
    dropped_count = mask.sum()

    if dropped_count > 0:
        logger.warning(
            "Dropped %d rows from invoices due to invalid numeric values in "
            "quantity, unit_price, or line_total.",
            dropped_count,
        )
        df = df[~mask].reset_index(drop=True)

    logger.info(
        "Loaded %d invoice line items (%d rows dropped).",
        len(df),
        dropped_count,
    )
    return df


def load_po_grn(path: str) -> pd.DataFrame:
    """Load po_grn.csv into a DataFrame.

    - Validates expected columns: po_number, po_date, vendor_id,
      vendor_name, po_total, currency, grn_number, grn_date
    - Converts po_date and grn_date from DD-MM-YYYY to datetime
    - Raises FileNotFoundError with descriptive message if file missing

    Args:
        path: Path to the po_grn.csv file.

    Returns:
        Cleaned pandas DataFrame with validated and parsed data.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"PO/GRN file not found: '{path}'")

    logger.info("Loading PO/GRN data from '%s'", path)
    df = pd.read_csv(path)

    _validate_columns(df, PO_GRN_COLUMNS, path)

    # Convert date columns
    df["po_date"] = pd.to_datetime(df["po_date"], format="%d-%m-%Y")
    df["grn_date"] = pd.to_datetime(df["grn_date"], format="%d-%m-%Y")

    logger.info("Loaded %d PO/GRN records.", len(df))
    return df


def load_labels(path: str) -> pd.DataFrame:
    """Load labelled_mismatches.csv as ground truth.

    Args:
        path: Path to the labelled_mismatches.csv file.

    Returns:
        pandas DataFrame containing labelled mismatch records.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Labels file not found: '{path}'")

    logger.info("Loading labelled mismatches from '%s'", path)
    df = pd.read_csv(path)

    logger.info("Loaded %d labelled mismatch records.", len(df))
    return df


def aggregate_invoices(df: pd.DataFrame) -> pd.DataFrame:
    """Group invoice line items by invoice_id and sum line_total.

    Preserves the first vendor_id, currency, and invoice_date per group.

    Args:
        df: DataFrame of invoice line items (output of load_invoices).

    Returns:
        Aggregated DataFrame with columns:
          invoice_id, vendor_id, currency, invoice_date, invoice_total
    """
    logger.info("Aggregating %d line items by invoice_id.", len(df))

    agg_df = (
        df.groupby("invoice_id", as_index=False)
        .agg(
            vendor_id=("vendor_id", "first"),
            currency=("currency", "first"),
            invoice_date=("invoice_date", "first"),
            invoice_total=("line_total", "sum"),
        )
    )

    logger.info("Aggregated into %d invoices.", len(agg_df))
    return agg_df
