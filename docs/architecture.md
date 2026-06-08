# SmartPay AP – Architecture Document

## 1. System Overview

SmartPay AP implements an AI-powered Accounts Payable reconciliation system for Acme Manufacturing. The architecture is designed around three layers: a data processing pipeline, a rule-based classification engine, and an agentic orchestration layer with human-in-the-loop safeguards.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SMARTPAY AP SYSTEM                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    DATA LAYER                                        │    │
│  │                                                                      │    │
│  │  invoices.csv ──┐                                                    │    │
│  │                  ├──▶ Data Loader ──▶ Aggregation ──▶ Clean DataFrames│   │
│  │  po_grn.csv ────┘         │                                          │    │
│  │                           ▼                                          │    │
│  │                    Validation & Preprocessing                        │    │
│  │                    (date parsing, null handling)                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                 MATCHING & CLASSIFICATION LAYER                       │    │
│  │                                                                      │    │
│  │  ┌──────────┐     ┌──────────────┐     ┌──────────────┐            │    │
│  │  │ Matcher  │────▶│  Classifier  │────▶│  Evaluator   │            │    │
│  │  │          │     │              │     │              │            │    │
│  │  │ ID-suffix│     │ Rule-based   │     │ P/R/F1 vs   │            │    │
│  │  │ pairing  │     │ heuristics   │     │ ground truth │            │    │
│  │  └──────────┘     └──────────────┘     └──────────────┘            │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    AGENTIC LAYER (LangGraph)                         │    │
│  │                                                                      │    │
│  │  ┌─────────┐  ┌─────────┐  ┌───────────┐  ┌──────────────────┐    │    │
│  │  │ Planner │─▶│ Matcher │─▶│ Dispute   │─▶│ Human Approval   │    │    │
│  │  │         │  │  Tool   │  │ Generator │  │     Gate         │    │    │
│  │  └─────────┘  └─────────┘  └───────────┘  └────────┬─────────┘    │    │
│  │                                                      │              │    │
│  │                                           ┌──────────┴──────────┐   │    │
│  │                                           ▼                     ▼   │    │
│  │                                       Approved              Rejected │    │
│  │                                      (send email)          (discard) │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    SECURITY & GUARDRAILS LAYER                        │    │
│  │                                                                      │    │
│  │  • Input Validation (invoice_id format: INV\d+)                      │    │
│  │  • Tool Whitelist (only registered tools callable)                   │    │
│  │  • Auto-Send Prevention (emails require human approval)              │    │
│  │  • Rejection Logging (audit trail for discarded drafts)              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Interactions

### 2.1 Data Flow

```
                        INPUT                           PROCESSING                        OUTPUT
                    ┌──────────┐                    ┌──────────────┐                 ┌────────────┐
                    │          │                    │              │                 │            │
invoices.csv ──────▶│  Data    │── validate ──────▶│  Aggregation │────────────────▶│ Aggregated │
(line items)        │  Loader  │   & clean         │  (group by   │                 │ Invoices   │
                    │          │                    │  invoice_id) │                 │            │
                    └──────────┘                    └──────────────┘                 └─────┬──────┘
                         │                                                                 │
                         │                                                                 ▼
po_grn.csv ─────────────▶│                                                         ┌────────────┐
(PO records)             │                                                         │  Matcher   │
                         ▼                                                         │  (join by  │
                    ┌──────────┐                                                   │  ID suffix)│
                    │  PO Data │──────────────────────────────────────────────────▶│            │
                    └──────────┘                                                   └─────┬──────┘
                                                                                         │
                                                                                         ▼
                                                                                  ┌────────────┐
                                                                                  │ Classifier │
                                                                                  │ (rules)    │
                                                                                  └─────┬──────┘
                                                                                        │
                                                                         ┌──────────────┼──────────┐
                                                                         ▼              ▼          ▼
                                                                   ┌──────────┐  ┌──────────┐  ┌──────┐
                                                                   │Evaluator │  │  Email   │  │Agent │
                                                                   │(metrics) │  │Generator │  │Layer │
                                                                   └──────────┘  └──────────┘  └──────┘
```

### 2.2 Module Dependencies

```
data_loader.py ◄─── matcher.py ◄─── classifier.py ◄─── evaluator.py
      │                  │                │
      │                  │                ▼
      │                  │         email_generator.py
      │                  │                │
      ▼                  ▼                ▼
agent/nodes.py (imports all three as tools)
      │
      ▼
agent/workflow.py (orchestrates nodes via LangGraph)
      │
      ▼
agent/guardrails.py (validates at each step)
```

---

## 3. Layer Descriptions

### 3.1 Data Layer

**Purpose:** Ingest, validate, and preprocess raw CSV data from the AcmeMini dataset.

| Component | Responsibility |
|-----------|---------------|
| `load_invoices()` | Parse invoices.csv, validate columns, convert dates, handle nulls |
| `load_po_grn()` | Parse po_grn.csv, validate columns, convert dates |
| `load_labels()` | Load ground truth labels for evaluation |
| `aggregate_invoices()` | Sum line items per invoice_id for comparison with PO totals |

**Key Design Choices:**
- Date format: DD-MM-YYYY (as per AcmeMini dataset convention)
- Invalid numeric rows are logged and excluded rather than failing the pipeline
- Column validation raises descriptive errors early in the pipeline

### 3.2 Matching & Classification Layer

**Purpose:** Pair invoices to POs and classify discrepancies by type.

**Matching Strategy:**
- Extract numeric suffix from invoice_id (INV0001 → 0001)
- Pair with PO having the same suffix (PO0001)
- Left-join: all invoices appear in output, unmatched ones flagged

**Classification Rules (priority order):**

| Priority | Type | Detection Logic |
|----------|------|-----------------|
| 1 | MISSING_PO | No matching PO found |
| 2 | TAX_MISCODE | Difference is 5–20% of min(invoice, PO) total |
| 3 | QUANTITY_VARIANCE | Total ratio suggests whole-unit quantity delta |
| 4 | PRICE_VARIANCE | Catch-all for remaining differences above tolerance |

**Evaluation:**
- Per-class precision, recall, F1 using sklearn
- Macro-averaged metrics across all 4 mismatch types
- Inner-join alignment between predictions and ground truth

### 3.3 Agentic Layer (LangGraph)

**Purpose:** Orchestrate end-to-end reconciliation with AI planning and human oversight.

**Workflow Nodes:**

| Node | Function | Input | Output |
|------|----------|-------|--------|
| Planner | Analyze invoices, produce reconciliation plan | Invoice data | Plan text |
| Matcher | Invoke matching model as a tool | Invoices + POs | Classified mismatches |
| Dispute Generator | Draft emails for each mismatch | Mismatches list | Email drafts |
| Human Approval Gate | HITL pause for review | Email drafts | Approve/reject decisions |

**State Management:**
```python
class ReconciliationState(TypedDict):
    invoices: list[dict]
    plan: str
    matches: list[dict]
    mismatches: list[dict]
    emails: list[dict]
    approved: list[bool]
    current_step: str
```

### 3.4 Security & Guardrails Layer

**Purpose:** Prevent the agentic workflow from performing unsafe actions.

| Guardrail | Protection |
|-----------|-----------|
| Input Validation | Rejects malformed invoice_id (must match `INV\d+`) |
| Tool Whitelist | Only registered tools (`match_invoices`, `classify`, `generate_email`) can be invoked |
| Auto-Send Prevention | Emails cannot be sent without passing through the Human Approval Gate |
| Rejection Logging | Discarded emails and rejection reasons are logged for audit |

---

## 4. Multi-Cloud Deployment Architecture

### Production Deployment (Azure + AWS)

For a production deployment at Acme Manufacturing scale, the system would be deployed across Azure and AWS:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        AZURE (Primary)                                   │
├────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │ Azure Blob      │    │ Azure Functions  │    │ Azure OpenAI     │  │
│  │ Storage         │    │ (Matching Model) │    │ Service          │  │
│  │ (CSV ingestion) │───▶│                  │───▶│ (Email drafting) │  │
│  └─────────────────┘    └──────────────────┘    └──────────────────┘  │
│                                  │                                      │
│                                  ▼                                      │
│                         ┌──────────────────┐                           │
│                         │ Azure Cosmos DB  │                           │
│                         │ (State store)    │                           │
│                         └──────────────────┘                           │
│                                                                         │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│                        AWS (Secondary / DR)                              │
├────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │ S3 Bucket       │    │ Lambda           │    │ Amazon Bedrock   │  │
│  │ (Replicated     │    │ (Backup compute) │    │ (LLM fallback)   │  │
│  │  data)          │    │                  │    │                  │  │
│  └─────────────────┘    └──────────────────┘    └──────────────────┘  │
│                                  │                                      │
│                                  ▼                                      │
│                         ┌──────────────────┐                           │
│                         │ DynamoDB         │                           │
│                         │ (State replica)  │                           │
│                         └──────────────────┘                           │
│                                                                         │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│                    SHARED SERVICES                                       │
├────────────────────────────────────────────────────────────────────────┤
│  • Azure AD / AWS IAM: Identity & access management                    │
│  • Azure Monitor / CloudWatch: Observability & alerting                │
│  • Azure Key Vault / AWS Secrets Manager: API key management           │
│  • Azure DevOps / GitHub Actions: CI/CD pipelines                      │
└────────────────────────────────────────────────────────────────────────┘
```

### Deployment Rationale

| Choice | Reasoning |
|--------|-----------|
| Azure as primary | Acme's existing enterprise agreement; Azure OpenAI for data residency |
| AWS as secondary | Disaster recovery; Amazon Bedrock as LLM fallback |
| Serverless compute | Cost-efficient for batch processing; scales to zero |
| Managed databases | Reduced operational overhead; built-in replication |

---

## 5. Security Considerations

### 5.1 Data Protection (GDPR Compliance)

| Concern | Mitigation |
|---------|-----------|
| PII in invoice data | Vendor names treated as business data; no personal customer data in AcmeMini dataset |
| Data at rest | Encrypted storage (Azure: SSE, AWS: S3 encryption) |
| Data in transit | TLS 1.3 for all API calls and data transfers |
| Data retention | Configurable retention policies; automated deletion after reconciliation period |
| Right to erasure | Vendor data can be purged from state store on request |

### 5.2 Application Security

| Layer | Control |
|-------|---------|
| Input validation | Invoice ID format enforcement prevents injection attacks |
| Tool whitelist | Agent cannot invoke arbitrary tools or external services |
| Human gate | No automated external actions (emails) without approval |
| API key management | Keys stored in environment variables / secret managers, never in code |
| Audit logging | All guardrail violations, approvals, and rejections logged |

### 5.3 AI Safety

| Risk | Mitigation |
|------|-----------|
| LLM hallucination | Template fallback ensures consistent output; structured prompts with constraints |
| Prompt injection | Agent operates on structured data, not free-text user input |
| Uncontrolled actions | Tool whitelist + human approval gate prevent unauthorized operations |
| Data leakage to LLM | Only mismatch details sent to OpenAI; no raw invoice data in prompts |

---

## 6. Cost Estimation

### Development/Demo Environment

| Resource | Monthly Cost (Est.) |
|----------|-------------------|
| Local Python runtime | $0 |
| OpenAI API (gpt-3.5-turbo, ~100 emails/month) | $0.10–$0.50 |
| **Total (dev)** | **< $1/month** |

### Production Environment (Azure Primary)

| Resource | Monthly Cost (Est.) |
|----------|-------------------|
| Azure Functions (matching model, ~10K invocations) | $5–$15 |
| Azure Cosmos DB (state store, 10GB) | $25–$50 |
| Azure Blob Storage (CSV data, <1GB) | $1–$2 |
| Azure OpenAI (gpt-35-turbo, ~1K emails) | $5–$10 |
| Azure Monitor (logging & alerts) | $10–$20 |
| **Total (production)** | **$50–$100/month** |

### Cost Optimization Strategies

- Template fallback eliminates LLM costs for standard mismatch types
- Serverless compute scales to zero during off-hours
- Batch processing (daily/weekly) instead of real-time reduces invocations
- Reserved capacity for predictable workloads

---

## 7. Technology Choices

| Technology | Purpose | Alternative | Why Chosen |
|-----------|---------|-------------|-----------|
| **Python 3.10+** | Primary language | Java, TypeScript | Rich ML/data ecosystem; team expertise |
| **pandas** | Data processing | PySpark, Polars | Ideal for small datasets (<1K rows); widely understood |
| **scikit-learn** | Evaluation metrics | Custom implementation | Battle-tested metrics; consistent with industry standards |
| **LangGraph** | Agent orchestration | CrewAI, AutoGen, custom FSM | Explicit state management, native HITL interrupts, graph visualization |
| **LangChain** | LLM abstraction | Direct API calls | Provider-agnostic; easy model swapping |
| **OpenAI GPT-3.5-turbo** | Email generation | GPT-4, Claude, Bedrock | Cost-effective for structured text; sufficient quality for dispute emails |
| **pytest** | Testing | unittest, nose2 | Concise syntax, fixtures, parametrize, rich plugins |
| **python-dotenv** | Config management | os.environ, configparser | Simple .env file loading; 12-factor app pattern |

---

## 8. Scalability Considerations

### Current Scale (AcmeMini)

- ~100 invoices, ~100 POs, 82 labelled mismatches
- Single-threaded processing completes in <1 second
- In-memory pandas DataFrames sufficient

### Future Scale (Production)

| Scale Factor | Adaptation |
|-------------|-----------|
| 10K+ invoices/day | Move to batch processing with Spark/Polars |
| Multi-vendor matching | Replace ID-suffix with fuzzy matching + ML |
| Real-time processing | Event-driven architecture (Azure Event Grid) |
| Multiple currencies | Add FX rate lookup service |
| Regulatory compliance | Add approval chain with multiple reviewers |

---

## 9. Monitoring & Observability

### Metrics to Track

| Metric | Purpose |
|--------|---------|
| Matching accuracy (F1) | Model drift detection |
| Mismatch volume by type | Trend analysis |
| Email approval rate | Human trust indicator |
| Guardrail violation count | Security monitoring |
| Processing latency | Performance SLA |
| API error rate | Integration health |

### Alerting Thresholds

| Alert | Condition |
|-------|-----------|
| Accuracy degradation | F1 drops below 0.85 |
| High rejection rate | >50% emails rejected in a batch |
| Guardrail breach | Any tool whitelist violation |
| Processing failure | Pipeline error rate >5% |

---

## 10. Future Enhancements

1. **ML-based classification** — Train on accumulated labelled data once sufficient volume exists (>500 records)
2. **Multi-modal matching** — Incorporate PDF invoice parsing with OCR
3. **Vendor portal integration** — Auto-send approved dispute emails via vendor APIs
4. **Learning from rejections** — Use rejected drafts as negative examples to improve email quality
5. **Dashboard** — Real-time reconciliation status via Streamlit or Power BI
6. **Confidence scoring** — Add confidence levels to classifications for prioritized human review
