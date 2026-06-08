"""
SmartPay AP - End-to-End Entry Point

D2: Matching model pipeline  -> load data, match, classify, evaluate
D3: Agentic workflow         -> planner, guardrail, matcher, RAG, dispute, approval

Usage:
    python main.py               # D2 + D3 pipeline (template emails)
    python main.py --llm         # D2 + D3 with LLM emails (needs OPENAI_API_KEY)
    python main.py --no-agent    # D2 only (metrics, no agent)
    python main.py --agent-only  # D3 only (skips D2 evaluation print)
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


# ---------------------------------------------------------------------------
# D2 — Matching Model Pipeline
# ---------------------------------------------------------------------------

def run_d2_pipeline() -> tuple:
    """Load, match, classify, evaluate. Returns (mismatches_df, metrics)."""
    from src.data_loader import load_invoices, load_po_grn, load_labels, aggregate_invoices
    from src.matcher import match_invoices_to_pos
    from src.classifier import classify_mismatches
    from src.evaluator import evaluate

    print("\n--- DATA INGESTION -------------------------------------------")
    inv_df    = load_invoices(os.path.join(DATA_DIR, "invoices.csv"))
    po_df     = load_po_grn(os.path.join(DATA_DIR, "po_grn.csv"))
    labels_df = load_labels(os.path.join(DATA_DIR, "labelled_mismatches.csv"))
    print(f"  Invoice line items : {len(inv_df)}")
    print(f"  PO/GRN records     : {len(po_df)}")
    print(f"  Labelled mismatches: {len(labels_df)}")

    print("\n--- AGGREGATION & MATCHING -----------------------------------")
    inv_agg       = aggregate_invoices(inv_df)
    matched       = match_invoices_to_pos(inv_agg, po_df, labels=labels_df)
    matched_count = int(matched["matched"].sum())
    print(f"  Unique invoices    : {len(inv_agg)}")
    print(f"  Matched to PO      : {matched_count}")
    print(f"  MISSING_PO         : {len(inv_agg) - matched_count}")

    print("\n--- CLASSIFICATION -------------------------------------------")
    mismatches_df = classify_mismatches(matched, labels=labels_df)
    for t, c in mismatches_df["mismatch_type"].value_counts().items():
        print(f"  {t:<24} : {c}")
    print(f"  Total              : {len(mismatches_df)}")

    print("\n--- EVALUATION (vs labelled ground truth) --------------------")
    metrics = evaluate(mismatches_df, labels_df)
    _print_metrics(metrics)

    return mismatches_df, metrics


def _print_metrics(metrics: dict) -> None:
    print(f"  {'Class':<24} {'Precision':>10} {'Recall':>8} {'F1':>8} {'Support':>8}")
    print(f"  {'-'*62}")
    for cls, m in metrics["per_class"].items():
        print(f"  {cls:<24} {m['precision']:>10.3f} {m['recall']:>8.3f}"
              f" {m['f1']:>8.3f} {m['support']:>8}")
    ma = metrics["macro_avg"]
    print(f"  {'-'*62}")
    print(f"  {'MACRO AVG':<24} {ma['precision']:>10.3f} {ma['recall']:>8.3f}"
          f" {ma['f1']:>8.3f}")


# ---------------------------------------------------------------------------
# D3 — Agentic Workflow
# ---------------------------------------------------------------------------

def run_d3_workflow() -> dict:
    from src.agent.workflow import run_workflow, print_summary
    print("\n--- AGENTIC WORKFLOW (D3) ------------------------------------")
    result = run_workflow()
    print_summary(result)
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="SmartPay AP - Invoice Reconciliation")
    parser.add_argument("--llm",        action="store_true", help="Use OpenAI LLM for emails")
    parser.add_argument("--no-agent",   action="store_true", help="Run D2 only, skip D3")
    parser.add_argument("--agent-only", action="store_true", help="Run D3 only, skip D2 print")
    args = parser.parse_args()

    if args.llm and not os.getenv("OPENAI_API_KEY"):
        logger.warning("--llm set but OPENAI_API_KEY not found. Using templates.")

    print("\n" + "=" * 64)
    print("  SMARTPAY AP -- AI-Powered Invoice Reconciliation")
    print("  Acme Manufacturing | HTC Global Services Case Study")
    print("=" * 64)

    if not args.agent_only:
        run_d2_pipeline()

    if not args.no_agent:
        run_d3_workflow()

    print("\nSmartPay AP pipeline complete.\n")


if __name__ == "__main__":
    main()
