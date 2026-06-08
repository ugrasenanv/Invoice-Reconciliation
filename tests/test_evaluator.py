"""
Tests for the Evaluator Module.

Tests cover:
- Perfect predictions (precision=recall=1.0)
- All wrong predictions
- Partial matches
- Misaligned invoice sets
- Empty inputs
"""

import pandas as pd
import pytest

from src.evaluator import evaluate, MISMATCH_CLASSES


class TestEvaluatePerfectPredictions:
    """Test evaluation when predictions perfectly match ground truth."""

    def test_perfect_predictions_all_classes(self):
        """All predictions match ground truth exactly."""
        data = {
            "invoice_id": ["INV0001", "INV0002", "INV0003", "INV0004"],
            "mismatch_type": [
                "PRICE_VARIANCE",
                "QUANTITY_VARIANCE",
                "TAX_MISCODE",
                "MISSING_PO",
            ],
        }
        predictions = pd.DataFrame(data)
        ground_truth = pd.DataFrame(data)

        result = evaluate(predictions, ground_truth)

        # All per-class metrics should be 1.0
        for cls in MISMATCH_CLASSES:
            assert result["per_class"][cls]["precision"] == 1.0
            assert result["per_class"][cls]["recall"] == 1.0
            assert result["per_class"][cls]["f1"] == 1.0

        # Macro average should be 1.0
        assert result["macro_avg"]["precision"] == 1.0
        assert result["macro_avg"]["recall"] == 1.0
        assert result["macro_avg"]["f1"] == 1.0

    def test_perfect_predictions_single_class(self):
        """Perfect predictions with only one mismatch type."""
        data = {
            "invoice_id": ["INV0001", "INV0002", "INV0003"],
            "mismatch_type": ["PRICE_VARIANCE", "PRICE_VARIANCE", "PRICE_VARIANCE"],
        }
        predictions = pd.DataFrame(data)
        ground_truth = pd.DataFrame(data)

        result = evaluate(predictions, ground_truth)

        assert result["per_class"]["PRICE_VARIANCE"]["precision"] == 1.0
        assert result["per_class"]["PRICE_VARIANCE"]["recall"] == 1.0
        assert result["per_class"]["PRICE_VARIANCE"]["f1"] == 1.0
        assert result["per_class"]["PRICE_VARIANCE"]["support"] == 3


class TestEvaluateAllWrong:
    """Test evaluation when all predictions are wrong."""

    def test_all_wrong_predictions(self):
        """Every prediction is a different class from ground truth."""
        predictions = pd.DataFrame({
            "invoice_id": ["INV0001", "INV0002", "INV0003", "INV0004"],
            "mismatch_type": [
                "MISSING_PO",
                "TAX_MISCODE",
                "PRICE_VARIANCE",
                "QUANTITY_VARIANCE",
            ],
        })
        ground_truth = pd.DataFrame({
            "invoice_id": ["INV0001", "INV0002", "INV0003", "INV0004"],
            "mismatch_type": [
                "PRICE_VARIANCE",
                "QUANTITY_VARIANCE",
                "TAX_MISCODE",
                "MISSING_PO",
            ],
        })

        result = evaluate(predictions, ground_truth)

        # With all wrong, precision and recall should be 0
        for cls in MISMATCH_CLASSES:
            assert result["per_class"][cls]["precision"] == 0.0
            assert result["per_class"][cls]["recall"] == 0.0
            assert result["per_class"][cls]["f1"] == 0.0

        assert result["macro_avg"]["precision"] == 0.0
        assert result["macro_avg"]["recall"] == 0.0
        assert result["macro_avg"]["f1"] == 0.0


class TestEvaluatePartialMatches:
    """Test evaluation with a mix of correct and incorrect predictions."""

    def test_partial_matches(self):
        """Some predictions correct, some wrong."""
        predictions = pd.DataFrame({
            "invoice_id": ["INV0001", "INV0002", "INV0003", "INV0004"],
            "mismatch_type": [
                "PRICE_VARIANCE",       # Correct
                "QUANTITY_VARIANCE",     # Correct
                "PRICE_VARIANCE",        # Wrong (should be TAX_MISCODE)
                "MISSING_PO",            # Correct
            ],
        })
        ground_truth = pd.DataFrame({
            "invoice_id": ["INV0001", "INV0002", "INV0003", "INV0004"],
            "mismatch_type": [
                "PRICE_VARIANCE",
                "QUANTITY_VARIANCE",
                "TAX_MISCODE",
                "MISSING_PO",
            ],
        })

        result = evaluate(predictions, ground_truth)

        # PRICE_VARIANCE: predicted 2 (INV0001 correct, INV0003 wrong)
        # precision = 1/2 = 0.5, recall = 1/1 = 1.0
        assert result["per_class"]["PRICE_VARIANCE"]["precision"] == 0.5
        assert result["per_class"]["PRICE_VARIANCE"]["recall"] == 1.0

        # QUANTITY_VARIANCE: predicted 1 correct out of 1 total
        assert result["per_class"]["QUANTITY_VARIANCE"]["precision"] == 1.0
        assert result["per_class"]["QUANTITY_VARIANCE"]["recall"] == 1.0

        # TAX_MISCODE: not predicted at all, but 1 in ground truth
        assert result["per_class"]["TAX_MISCODE"]["precision"] == 0.0
        assert result["per_class"]["TAX_MISCODE"]["recall"] == 0.0

        # MISSING_PO: predicted 1 correct out of 1 total
        assert result["per_class"]["MISSING_PO"]["precision"] == 1.0
        assert result["per_class"]["MISSING_PO"]["recall"] == 1.0

        # Macro avg should reflect the mix
        assert 0.0 < result["macro_avg"]["f1"] < 1.0


class TestEvaluateMisalignedSets:
    """Test evaluation when predictions and ground truth have different invoice sets."""

    def test_misaligned_invoice_ids(self):
        """Predictions and ground truth overlap only partially."""
        predictions = pd.DataFrame({
            "invoice_id": ["INV0001", "INV0002", "INV0005"],
            "mismatch_type": ["PRICE_VARIANCE", "TAX_MISCODE", "MISSING_PO"],
        })
        ground_truth = pd.DataFrame({
            "invoice_id": ["INV0001", "INV0003", "INV0005"],
            "mismatch_type": ["PRICE_VARIANCE", "QUANTITY_VARIANCE", "MISSING_PO"],
        })

        result = evaluate(predictions, ground_truth)

        # Only INV0001 and INV0005 are in both (inner join)
        # Both are correct
        assert result["per_class"]["PRICE_VARIANCE"]["recall"] == 1.0
        assert result["per_class"]["MISSING_PO"]["recall"] == 1.0

    def test_no_overlap(self):
        """Predictions and ground truth have completely different invoice sets."""
        predictions = pd.DataFrame({
            "invoice_id": ["INV0001", "INV0002"],
            "mismatch_type": ["PRICE_VARIANCE", "TAX_MISCODE"],
        })
        ground_truth = pd.DataFrame({
            "invoice_id": ["INV0003", "INV0004"],
            "mismatch_type": ["PRICE_VARIANCE", "TAX_MISCODE"],
        })

        result = evaluate(predictions, ground_truth)

        # No overlap → all zeros
        for cls in MISMATCH_CLASSES:
            assert result["per_class"][cls]["precision"] == 0.0
            assert result["per_class"][cls]["recall"] == 0.0
        assert result["macro_avg"]["f1"] == 0.0


class TestEvaluateEmptyInputs:
    """Test evaluation with empty DataFrames."""

    def test_empty_predictions(self):
        """Empty predictions DataFrame."""
        predictions = pd.DataFrame(columns=["invoice_id", "mismatch_type"])
        ground_truth = pd.DataFrame({
            "invoice_id": ["INV0001"],
            "mismatch_type": ["PRICE_VARIANCE"],
        })

        result = evaluate(predictions, ground_truth)

        for cls in MISMATCH_CLASSES:
            assert result["per_class"][cls]["precision"] == 0.0
            assert result["per_class"][cls]["recall"] == 0.0
        assert result["macro_avg"]["f1"] == 0.0

    def test_empty_ground_truth(self):
        """Empty ground truth DataFrame."""
        predictions = pd.DataFrame({
            "invoice_id": ["INV0001"],
            "mismatch_type": ["PRICE_VARIANCE"],
        })
        ground_truth = pd.DataFrame(columns=["invoice_id", "mismatch_type"])

        result = evaluate(predictions, ground_truth)

        for cls in MISMATCH_CLASSES:
            assert result["per_class"][cls]["precision"] == 0.0
            assert result["per_class"][cls]["recall"] == 0.0
        assert result["macro_avg"]["f1"] == 0.0

    def test_both_empty(self):
        """Both DataFrames are empty."""
        predictions = pd.DataFrame(columns=["invoice_id", "mismatch_type"])
        ground_truth = pd.DataFrame(columns=["invoice_id", "mismatch_type"])

        result = evaluate(predictions, ground_truth)

        for cls in MISMATCH_CLASSES:
            assert result["per_class"][cls]["precision"] == 0.0
            assert result["per_class"][cls]["recall"] == 0.0
        assert result["macro_avg"]["f1"] == 0.0


class TestEvaluateStructure:
    """Test that return structure is correct."""

    def test_return_keys(self):
        """Result has expected top-level and nested keys."""
        data = {
            "invoice_id": ["INV0001"],
            "mismatch_type": ["PRICE_VARIANCE"],
        }
        result = evaluate(pd.DataFrame(data), pd.DataFrame(data))

        assert "per_class" in result
        assert "macro_avg" in result

        for cls in MISMATCH_CLASSES:
            assert cls in result["per_class"]
            assert "precision" in result["per_class"][cls]
            assert "recall" in result["per_class"][cls]
            assert "f1" in result["per_class"][cls]
            assert "support" in result["per_class"][cls]

        assert "precision" in result["macro_avg"]
        assert "recall" in result["macro_avg"]
        assert "f1" in result["macro_avg"]

    def test_metric_bounds(self):
        """All metrics are between 0 and 1."""
        data = {
            "invoice_id": ["INV0001", "INV0002"],
            "mismatch_type": ["PRICE_VARIANCE", "TAX_MISCODE"],
        }
        result = evaluate(pd.DataFrame(data), pd.DataFrame(data))

        for cls in MISMATCH_CLASSES:
            assert 0.0 <= result["per_class"][cls]["precision"] <= 1.0
            assert 0.0 <= result["per_class"][cls]["recall"] <= 1.0
            assert 0.0 <= result["per_class"][cls]["f1"] <= 1.0
            assert result["per_class"][cls]["support"] >= 0

        assert 0.0 <= result["macro_avg"]["precision"] <= 1.0
        assert 0.0 <= result["macro_avg"]["recall"] <= 1.0
        assert 0.0 <= result["macro_avg"]["f1"] <= 1.0
