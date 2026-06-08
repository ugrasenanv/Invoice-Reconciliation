# SmartPay AP — AI-Powered Invoice Reconciliation
## Architecture Presentation Deck (15 Slides)

---

## Slide 1: Title & Context

### SmartPay AP
**AI-Powered Invoice Reconciliation for Acme Manufacturing**

- Automates invoice-to-PO matching and mismatch detection
- Agentic workflow with human-in-the-loop safeguards
- Built with Python, LangGraph, and OpenAI

**Case Study Deliverable** | AI Architect Assessment

---

## Slide 2: Problem Statement

### The Challenge

Acme Manufacturing's AP team manually reconciles **300+ invoices** against purchase orders each cycle.

| Pain Point | Impact |
|-----------|--------|
| Manual matching | 8–12 hours per reconciliation cycle |
| Missed mismatches | Revenue leakage from undetected variances |
| Inconsistent follow-up | Delayed or missing dispute communications |
| No audit trail | Compliance gaps in vendor dispute records |

**Goal:** Reduce reconciliation time by 80%+ while maintaining human oversight on all external actions.

---

## Slide 3: Solution Overview

### SmartPay AP — End-to-End Automation

```
CSV Data → Matching Model → Classification → Agent Workflow → Human Approval
```

**Three Layers:**

1. **Data Pipeline** — Ingest, validate, aggregate invoice/PO data
2. **Matching & Classification** — Rule-based mismatch detection (4 types)
3. **Agentic Orchestration** — LangGraph workflow with HITL gate

**Key Principle:** The AI agent plans and proposes; humans approve and act.

---

## Slide 4: High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     SMARTPAY AP SYSTEM                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  DATA LAYER          CLASSIFICATION LAYER     AGENTIC LAYER      │
│  ┌──────────┐        ┌──────────────┐        ┌──────────────┐   │
│  │  Data    │──────▶ │  Matcher +   │──────▶ │  LangGraph   │   │
│  │  Loader  │        │  Classifier  │        │  Workflow     │   │
│  └──────────┘        └──────────────┘        └──────────────┘   │
│       ▲                     │                       │            │
│  CSV Files            Evaluator              Human Approval      │
│  (AcmeMini)          (P/R/F1)                   Gate            │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  GUARDRAILS: Input Validation │ Tool Whitelist │ HITL     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Slide 5: Data Pipeline

### Data Ingestion & Preprocessing

**Input:** AcmeMini dataset (3 CSV files)
- `invoices.csv` — 1,500 line items across 300 invoices
- `po_grn.csv` — 300 purchase orders with GRN data
- `labelled_mismatches.csv` — 82 ground-truth labels

**Processing Steps:**
1. Load & validate columns (schema enforcement)
2. Parse dates (DD-MM-YYYY → datetime)
3. Handle nulls/invalid numerics (log & exclude)
4. Aggregate line items → one total per invoice_id

**Design Choice:** Early validation with descriptive errors. Fail fast on schema issues, graceful handling on data quality.

---

## Slide 6: Matching Strategy

### Invoice-to-PO Matching

**Approach:** Numeric ID suffix extraction

```
INV0001 → extract "0001" → match to PO0001
INV0042 → extract "0042" → match to PO0042
```

**Why this approach?**
- AcmeMini uses a clear `INV000X ↔ PO000X` naming convention
- Achieves 100% match rate on the current dataset
- Simpler, more reliable than fuzzy matching for structured IDs

**Validation Flags:**
- `vendor_match` — Same vendor_id on both sides?
- `currency_match` — Same currency on both sides?

**Result:** Left-join semantics — all invoices appear; unmatched ones flagged.

---

## Slide 7: Classification Engine

### Rule-Based Mismatch Classification

Applied in **priority order** to prevent multi-classification:

| Priority | Type | Detection Logic | Confidence |
|----------|------|----------------|-----------|
| 1 | **MISSING_PO** | No matching PO found | 1.0 |
| 2 | **TAX_MISCODE** | Difference is 5–25% of min total | 0.8 |
| 3 | **QUANTITY_VARIANCE** | Ratio > 20% (whole-unit delta) | 0.75 |
| 4 | **PRICE_VARIANCE** | Remaining diffs above tolerance | 0.70 |

**Why rules over ML?**
- Only 82 labelled samples — insufficient for reliable ML
- Rules are interpretable and auditable (critical for finance)
- Thresholds are configurable without retraining

---

## Slide 8: Model Evaluation

### Accuracy Metrics

**Evaluation approach:**
- Inner-join predictions against 82 ground-truth labels
- Per-class precision, recall, F1 (sklearn)
- Macro-averaged metrics across all 4 types

| Metric | Purpose |
|--------|---------|
| Precision | How many flagged items are correct? |
| Recall | How many real mismatches did we catch? |
| F1 | Harmonic mean (balanced view) |

**Extensibility:** When >500 labelled records accumulate, switch to ML-based classification with these metrics as the benchmark.

---

## Slide 9: Agentic Workflow (LangGraph)

### Workflow Graph

```
START → Planner → Matcher → Dispute Generator → Human Approval → END
                                                       │
                                                  ┌────┴────┐
                                                  ▼         ▼
                                              Approved   Rejected
                                              (proceed)  (discard + log)
```

**Node Responsibilities:**

| Node | Action |
|------|--------|
| **Planner** | Analyze invoices, produce reconciliation plan |
| **Matcher** | Invoke matching model as a tool, classify mismatches |
| **Dispute Generator** | Draft emails per mismatch (LLM or template) |
| **Human Approval** | Display draft, wait for y/n confirmation |

---

## Slide 10: Email Generation

### Dispute Email Drafting

**Dual-mode generation:**

| Mode | When | Advantage |
|------|------|-----------|
| **LLM** (GPT-3.5-turbo) | API key available | Natural, contextual language |
| **Template** (fallback) | No API key / API failure | Consistent, reliable, free |

**Email contains:**
- Professional greeting to vendor
- Invoice ID + PO number references
- Mismatch type and exact discrepancy amount
- Specific resolution request per type:
  - PRICE/QUANTITY → credit note or corrected invoice
  - TAX_MISCODE → tax calculation correction
  - MISSING_PO → provide PO reference

---

## Slide 11: Guardrails & Safety

### Responsible AI Controls

| Guardrail | What It Prevents |
|-----------|-----------------|
| **Input Validation** | Malformed invoice IDs (must match `INV\d+`) |
| **Tool Whitelist** | Agent calling unregistered/arbitrary tools |
| **Auto-Send Prevention** | Emails sent without human review |
| **Rejection Logging** | Full audit trail for discarded drafts |

**Key Principle:** The agent can *propose* actions but never *execute* external actions autonomously.

```python
class GuardrailViolation(Exception):
    """Raised when agent attempts a forbidden action."""
```

---

## Slide 12: Technology Stack

### Technology Choices & Rationale

| Technology | Purpose | Why Chosen |
|-----------|---------|-----------|
| **Python 3.10+** | Primary language | Rich ML/data ecosystem |
| **pandas** | Data processing | Ideal for <1K row datasets |
| **scikit-learn** | Evaluation metrics | Battle-tested, industry standard |
| **LangGraph** | Agent orchestration | Explicit HITL, state control |
| **LangChain + OpenAI** | LLM integration | Provider-agnostic abstraction |
| **pytest** | Testing (96 tests) | Concise, parametrize support |
| **python-dotenv** | Config management | 12-factor app pattern |

**No over-engineering:** Technology choices match the problem scale.

---

## Slide 13: Production Deployment Architecture

### Multi-Cloud Strategy (Azure Primary + AWS DR)

```
┌─────────────── AZURE (Primary) ───────────────┐
│  Blob Storage → Azure Functions → Azure OpenAI │
│                      ↓                          │
│              Cosmos DB (State)                   │
└─────────────────────────────────────────────────┘

┌─────────────── AWS (Secondary/DR) ────────────┐
│  S3 Bucket → Lambda → Amazon Bedrock            │
│                  ↓                               │
│            DynamoDB (Replica)                     │
└─────────────────────────────────────────────────┘

Shared: Azure AD/IAM, Key Vault/Secrets Manager, CI/CD
```

**Cost:** ~$50–$100/month at production scale (serverless, scales to zero)

---

## Slide 14: Scalability & Future Roadmap

### Current Scale → Production Scale

| Factor | Now (AcmeMini) | Future |
|--------|----------------|--------|
| Data volume | 300 invoices | 10K+/day → Spark/Polars |
| Matching | ID-suffix | Fuzzy + ML matching |
| Processing | Batch (seconds) | Event-driven (real-time) |
| Classification | Rules (82 labels) | ML model (500+ labels) |
| Currencies | Single | Multi-currency + FX |
| Approval | Console y/n | Web UI + approval chains |

### Planned Enhancements
1. ML classification when sufficient training data
2. PDF invoice parsing (OCR/multi-modal)
3. Vendor portal API integration
4. Real-time dashboard (Streamlit / Power BI)
5. Confidence scoring for prioritized review

---

## Slide 15: Summary & Key Takeaways

### What SmartPay AP Delivers

✅ **Automated matching** — 300 invoices matched in <1 second
✅ **Intelligent classification** — 4 mismatch types with configurable rules
✅ **Agentic workflow** — End-to-end orchestration with LangGraph
✅ **Human oversight** — No external action without explicit approval
✅ **Production-ready** — Guardrails, audit logging, template fallback
✅ **Extensible** — Clear path from rules to ML as data grows

### Design Principles Applied
- **Interpretability over black-box** — Rules are auditable
- **Human-in-the-loop** — AI proposes, humans approve
- **Graceful degradation** — Template fallback, error tolerance
- **Right-sized technology** — No over-engineering for the problem scale

---

## Appendix: How to Run

```bash
# Setup
cd SmartPayAP
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt

# Run matching model
jupyter notebook notebooks/matching_model.ipynb

# Run agent workflow
python src/agent/workflow.py

# Run tests (96 unit tests)
pytest -v
```

---
