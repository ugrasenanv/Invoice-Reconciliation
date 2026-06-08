"""Tests for the Email Generator module."""

import pytest

from src.email_generator import generate_dispute_email


class TestGenerateDisputeEmail:
    """Tests for template-based email generation."""

    @pytest.fixture
    def price_variance_mismatch(self):
        return {
            "invoice_id": "INV0001",
            "po_number": "PO0001",
            "mismatch_type": "PRICE_VARIANCE",
            "vendor_name": "Acme Supplies",
            "invoice_value": 1050.00,
            "po_value": 1000.00,
            "difference": 50.00,
        }

    @pytest.fixture
    def quantity_variance_mismatch(self):
        return {
            "invoice_id": "INV0002",
            "po_number": "PO0002",
            "mismatch_type": "QUANTITY_VARIANCE",
            "vendor_name": "Widget Co",
            "invoice_value": 3000.00,
            "po_value": 2000.00,
            "difference": 1000.00,
        }

    @pytest.fixture
    def tax_miscode_mismatch(self):
        return {
            "invoice_id": "INV0003",
            "po_number": "PO0003",
            "mismatch_type": "TAX_MISCODE",
            "vendor_name": "Tax Corp",
            "invoice_value": 1100.00,
            "po_value": 1000.00,
            "difference": 100.00,
        }

    @pytest.fixture
    def missing_po_mismatch(self):
        return {
            "invoice_id": "INV0004",
            "po_number": None,
            "mismatch_type": "MISSING_PO",
            "vendor_name": "Unknown Vendor",
            "invoice_value": 500.00,
            "po_value": None,
            "difference": None,
        }

    def test_price_variance_has_subject(self, price_variance_mismatch):
        email = generate_dispute_email(price_variance_mismatch)
        assert "Subject:" in email
        assert "INV0001" in email

    def test_price_variance_has_vendor_name(self, price_variance_mismatch):
        email = generate_dispute_email(price_variance_mismatch)
        assert "Acme Supplies" in email

    def test_price_variance_mentions_credit_note(self, price_variance_mismatch):
        email = generate_dispute_email(price_variance_mismatch)
        assert "credit note" in email.lower() or "corrected invoice" in email.lower()

    def test_quantity_variance_email(self, quantity_variance_mismatch):
        email = generate_dispute_email(quantity_variance_mismatch)
        assert "INV0002" in email
        assert "Widget Co" in email
        assert "quantities" in email.lower() or "quantity" in email.lower()

    def test_tax_miscode_email(self, tax_miscode_mismatch):
        email = generate_dispute_email(tax_miscode_mismatch)
        assert "INV0003" in email
        assert "tax" in email.lower()
        assert "Tax Corp" in email

    def test_missing_po_email(self, missing_po_mismatch):
        email = generate_dispute_email(missing_po_mismatch)
        assert "INV0004" in email
        assert "purchase order" in email.lower()

    def test_use_llm_false_uses_template(self, price_variance_mismatch):
        # With use_llm=False, should produce a deterministic template result
        email1 = generate_dispute_email(price_variance_mismatch, use_llm=False)
        email2 = generate_dispute_email(price_variance_mismatch, use_llm=False)
        assert email1 == email2

    def test_email_includes_amounts(self, price_variance_mismatch):
        email = generate_dispute_email(price_variance_mismatch)
        # Numbers are formatted as 1,050.00 in the new template
        assert "1,050.00" in email or "1050" in email
        assert "1,000.00" in email or "1000" in email
