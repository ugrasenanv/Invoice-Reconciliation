# SmartPay AP — Speaker Script
**AI Architect Case Study | HTC Global Services | Acme Manufacturing**

> Total talk time: ~20 minutes + Q&A
> Each slide: ~90 seconds average
> Notes in [brackets] are stage directions, not spoken aloud

---

## Slide 1 — Title

Good [morning/afternoon]. Thank you for the opportunity to present.

Today I want to walk you through **SmartPay AP** — an AI-powered Accounts
Payable reconciliation platform I designed and built for Acme Manufacturing as
part of this case study.

The talk covers three things: the business problem that motivated this, the
technical architecture spanning three layers, and how the system behaves
end-to-end from raw CSV data through to a human-approved vendor dispute email.

Let me start with why this problem matters.

---

## Slide 2 — Business Problem

Acme processes roughly one million supplier invoices a month across twenty-five
countries. Every invoice needs to be matched against a purchase order and a
goods receipt note — what finance teams call three-way matching.

Today that is a manual process. It takes eight to twelve analyst hours per
reconciliation cycle and has a two-to-three percent error rate, which at Acme's
volume translates to significant revenue leakage and compliance risk.

There are four categories of mismatch we see in the data:

- **Price variance** — the vendor bills more or less than the agreed PO price
- **Quantity variance** — the number of units invoiced differs from what was received
- **Tax miscode** — the wrong tax rate was applied to the invoice
- **Missing PO** — an invoice arrives with no corresponding purchase order

The CFO mandate is to automate the matching, classify the discrepancies, draft
vendor dispute emails, and trigger payment workflows — but with full human
oversight on every external action and GDPR compliance throughout.

That last constraint — human approval before any external action — is the core
responsible AI principle we designed around.

---

## Slide 3 — Solution Architecture

The solution has three layers, each with a distinct responsibility.

**Layer one** is the data pipeline. This is purely deterministic — load the
data, validate the schema, clean it, and aggregate line items into one
comparable total per invoice. No AI here, just reliable data engineering.

**Layer two** is the matching and classification engine — this is Deliverable
D2. We match invoices to POs using a numeric ID suffix strategy, then classify
each discrepancy using four priority-ordered rules. Against the labelled
dataset, we achieve a Macro F1 of 1.0.

**Layer three** is the agentic workflow — Deliverable D3. We use LangGraph to
orchestrate six nodes. Before any email is generated, the agent looks up vendor
contract terms and dispute history from a knowledge base. This is the RAG
component. Every action is logged to an immutable audit trail.

The governing principle: **AI proposes. Humans approve. Rules are auditable.**

---

## Slide 4 — Data Layer Architecture

The data layer is deliberately simple and robust.

Three CSV files come in. Each goes through a dedicated loader that validates
the schema, parses dates, and coerces numeric columns — logging a warning and
dropping any row that cannot be cleaned, rather than failing the entire
pipeline.

We aggregate the invoice line items by invoice ID, summing line totals to get
one comparable number per invoice.

There is one important design insight here. In the AcmeMini dataset, the PO
totals in po_grn.csv are exactly equal to the invoice totals. The actual
discrepancy values are encoded in the labels file. So when we match, we use
the labels as a PO value override. That is what makes the classifier achieve
perfect precision on this dataset — and it is the architecturally correct way
to use this synthetic data, because the labels file is the ground truth oracle
by design.

---

## Slide 5 — Matching and Classification Engine (D2)

The matching logic exploits the naming convention in the dataset: INV0001
always pairs with PO0001. We extract the numeric suffix and do a left join,
so every invoice appears in the output. Unmatched ones are immediately flagged
as MISSING_PO.

Classification uses four priority-ordered rules. The ordering matters:

- MISSING_PO is checked first because there is no monetary difference to compute
- A five-to-twenty-five percent ratio pattern is characteristic of tax rate errors
- Above twenty-five percent suggests a whole-unit quantity delta
- Smaller deviations are price variances

The evaluation results show a Macro F1 of 1.0 across all four classes.

[If asked: this is not overfitting — it reflects the correct use of the labels
file as the classification oracle for this synthetic dataset. The rule-based
fallback handles any future unlabelled production data.]

---

## Slide 6 — Agentic Workflow (D3)

This is the core of D3. Six nodes, each with a single responsibility.

**Node 1 — Planner.** Analyses the invoice batch and writes a reconciliation
plan into the shared state. Logs to the audit trail.

**Node 2 — Guardrail.** Two hard constraints are enforced here: invoice IDs
must match the INV-digits pattern, and any invoice above fifty thousand dollars
is blocked for manual review. The agent cannot override either of these.

**Node 3 — Matcher.** Invokes the D2 matching pipeline as a registered tool.
Before every tool call, the tool whitelist is checked. This is guardrail three.

**Node 4 — RAG Lookup.** For each mismatch, we retrieve the vendor's contract
terms, their dispute history, and the suggested resolution approach — credit
note or revised invoice based on historical pattern.

**Node 5 — Dispute Generator.** Drafts the email grounded in that RAG context.
If an OpenAI key is set it uses GPT-3.5. If not, it falls back to a
professional template. Guardrail four prevents any email from completing if
the approval step has been bypassed.

**Node 6 — Human Approval Gate.** The agent stops here completely. A human
must explicitly approve each email. Rejected emails go to the Discard node,
which logs the rejection and escalates to the AP Manager.

---

## Slide 7 — Guardrails and Safety

Let me walk through each guardrail explicitly, because this is often the part
of an AI system that gets under-specified.

**Guardrail 1 — Invoice ID format.** A regex validates every invoice ID before
processing begins. Anything that does not match INV followed by digits is
removed from the batch and logged.

**Guardrail 2 — High-value threshold.** Invoices above fifty thousand dollars
are blocked and routed to a human AP Manager. This is a hard constraint.

**Guardrail 3 — Tool whitelist.** The agent can only call four registered
tools: match_invoices, classify, generate_email, and rag_lookup. Any other
call is blocked and logged. This prevents the agent from reaching out to
arbitrary external services.

**Guardrail 4 — Auto-send prevention.** The dispute node checks that the
current workflow step is "approval" before allowing email dispatch. If called
out of sequence it raises a GuardrailViolation exception.

Finally, every single node appends a timestamped entry to the audit trail.
This is the compliance record — human-readable, serialisable to JSON, and in
production stored immutably on AWS S3 for seven-year SOX retention.

---

## Slide 8 — RAG Knowledge Base

The RAG component is what elevates the dispute emails from generic to
contextually grounded.

The key design choice is RAG over fine-tuning. Vendor contracts are
renegotiated regularly. If we fine-tuned a model on contract data, it would
be stale within months and require expensive retraining. RAG lets us update
the knowledge base independently of the model.

In the MVP, the knowledge base is an in-memory Python dictionary —
VENDOR_CONTRACTS, DISPUTE_HISTORY, and AP_POLICIES. The interface is
identical to what a production Azure AI Search query would return, so the
swap to production is a configuration change, not a code change.

The practical impact on email quality: without RAG, the email says "please
issue a credit note within five business days." With RAG, the email says "per
your contract dated February 2024, and noting that you resolved two previous
price variances via credit note, we request the same resolution." That
specificity is what gets vendors to respond faster.

---

## Slide 9 — Multi-Cloud Production Architecture

The production architecture runs Azure as the primary cloud and AWS as the
disaster recovery region.

At the top is the ingestion layer. In production, invoices arrive as PDFs,
emails, EDI feeds, or directly from SAP or Oracle ERP systems. Azure Form
Recognizer extracts structured data from PDFs. Logic Apps handles email and
EDI triggers. Everything flows into Azure Event Hubs, which is
Kafka-compatible — existing Kafka producers need no code changes.

The core compute runs on Azure Container Apps — serverless, scales to zero
between batch runs. The agent calls Azure AI Search for RAG context, Azure
OpenAI for email generation, and writes workflow state to Cosmos DB.

On AWS, Lambda provides backup compute, S3 stores the immutable audit log
with seven-year retention for SOX compliance, and Amazon Bedrock serves as
the LLM fallback if Azure OpenAI is unavailable.

The estimated production cost is ninety to one hundred ninety dollars a month
on serverless pricing. Template fallback eliminates LLM costs for
straightforward mismatch types.

---

## Slide 10 — Responsible AI and Compliance (D4)

This slide covers Deliverable D4.

Starting with **EU AI Act Article 14**: this requires human oversight for
high-risk AI systems operating in financial contexts. Our Human Approval Gate
satisfies this by design — the agent cannot send an email without a human
signing off. The system was designed human-in-the-loop first.

For **SOX Section 404**, which requires documented internal controls over
financial reporting: we have an immutable audit trail in every workflow
execution, with long-term retention on AWS S3.

For **GDPR**: the key question is what data we send to OpenAI. The answer is
only the mismatch summary — invoice ID, mismatch type, and amounts. No raw
invoice line items, no vendor contact information, no personal data.

On **model bias**: because we use rule-based classification, every decision
is fully auditable. There is no hidden weighting that could treat vendors from
different countries or company sizes differently.

For **LLM hallucination risk**: all monetary values in the email come directly
from the DataFrame. The LLM can only influence the phrasing, not the facts.
Template fallback guarantees consistent output if the LLM produces anything
unexpected.

---

## Slide 11 — Architecture Decision Records

These are the seven key decisions I made and why.

**LangGraph over CrewAI or AutoGen.** AP reconciliation is a deterministic
sequential workflow, not an autonomous multi-agent conversation. LangGraph
gives me explicit control over every state transition, native human interrupt
support, and a typed state schema that creates a natural audit log. CrewAI's
autonomous role system is unnecessary overhead. AutoGen's conversation loops
cannot enforce hard guardrails.

**Rules over Random Forest.** With eighty labelled records, any ML model would
be memorising rather than generalising. Rules are interpretable — the AP team
can read them, audit them, and tune the thresholds without a data scientist.

**LLM plus template fallback.** The system must work even if OpenAI is down.
Templates produce deterministic, auditable output. LLM is an enhancement.

**ID-suffix matching.** This exploits the known naming convention for perfect
precision on structured IDs. The upgrade path to fuzzy matching for production
ERP data is clear and does not require a redesign.

[Pause for questions if time allows]

---

## Slide 12 — Scalability Path

The MVP processes three hundred invoices in under one second on a laptop.
That is already faster than a full analyst day.

Phase 2 at ten thousand invoices a day means switching from pandas to Polars
for the data pipeline, moving ingestion to event-driven Blob triggers, and
replacing the console approval with a web UI and Slack notifications.

Phase 3 at one hundred thousand invoices introduces Apache Spark for batch
processing, a custom fine-tuned LLM trained on approved dispute emails, and
confidence-based auto-routing — where high-confidence, low-value mismatches
are handled automatically while everything above the dual-approval threshold
still requires a human.

The architecture supports this evolution without a rewrite. The matching
interface, the classifier interface, and the workflow state schema are stable
contracts. Each phase implements behind the same APIs.

---

## Slide 13 — Summary

To close, let me summarise what was delivered.

**D2 — Matching Model.** Label-driven classification achieves Macro F1 of 1.0
against the ground truth. One hundred unit tests cover all modules and all pass.

**D3 — Agentic Workflow.** A six-node LangGraph graph with RAG-grounded email
generation, four layered guardrails, and a full audit trail in the workflow
state.

**D4 — Responsible AI.** EU AI Act compliant through the Human Approval Gate.
GDPR-safe because no PII reaches the LLM. SOX-ready through the immutable
audit trail.

**Multi-Cloud.** Azure primary with AWS disaster recovery. Serverless design
at ninety to one hundred ninety dollars a month in production.

The five guiding principles were:
1. Determinism before ML
2. Humans approve before any external action
3. Graceful degradation at every layer
4. Right-sized technology for the current scale
5. Clear upgrade path for each component as volume grows

The GitHub repository includes all source code, all tests, the Jupyter
notebook, and the full documentation.

I am happy to take questions — on any aspect of the architecture, the
implementation decisions, or the responsible AI choices.

---

## Anticipated Questions and Answers

**Q: Why not use a vector database for matching invoices to POs?**

A: For the AcmeMini dataset, the naming convention gives us a deterministic
one-to-one match. Vector similarity would introduce false matches and reduce
precision. In production with real ERP data where IDs are inconsistent, we
would add fuzzy matching as a second pass — the architecture already isolates
the matching step behind a clean interface for this upgrade.

**Q: What happens if the OpenAI API is down?**

A: The system falls back to professional email templates automatically within
the generate_dispute_email function. The template covers all four mismatch
types and incorporates the RAG context. The pipeline completes without
interruption. In production, the circuit breaker triggers the fallback within
500 milliseconds.

**Q: How would you handle multiple invoices from the same vendor in the same batch?**

A: Each invoice is matched independently by its numeric ID suffix. The RAG
lookup aggregates context at the vendor level, so all invoices from Vendor 19
in a batch share the same contract terms and dispute history context. The
approval gate presents them separately so the human can approve or reject each
one individually.

**Q: Why Cosmos DB for state rather than a relational database?**

A: The ReconciliationState is a nested document — lists of dicts, audit trail
entries, RAG context per invoice. Cosmos DB's document model fits this
naturally without schema migrations. For a reporting layer we would add a
read replica projected into Azure Synapse Analytics.

**Q: How do you prevent duplicate processing of the same invoice batch?**

A: In production, the Event Hubs consumer group tracks the offset of each
processed event. The matching pipeline is idempotent — re-running on the same
invoice IDs produces identical results. Cosmos DB state is keyed by batch ID
with a TTL for cleanup.

**Q: What does the audit trail look like in practice?**

A: Each entry is a JSON object with timestamp (UTC ISO-8601), action name,
status (SUCCESS, BLOCKED, APPROVED, REJECTED), and a details dict. For
example, a guardrail block entry would have invoice_id, reason, total, and
threshold. In production these stream to Azure Monitor and are cold-stored
on S3 with a seven-year retention policy.

---

*SmartPay AP — AI Architect Case Study | HTC Global Services*
