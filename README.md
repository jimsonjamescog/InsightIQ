# InsightIQ

**Autonomous Business Investigation Agent**

> Don't just detect what changed. Investigate why.

InsightIQ is an OpenAI-powered business investigation agent. It analyzes warehouse data through controlled tools, tracks competing hypotheses, validates evidence provenance, enforces a deterministic evidence gate, and produces an auditable root-cause report.

The included scenario investigates a 40% reported-revenue drop caused by a deployment that introduced null customer regions. Traffic and payment failures act as decoys. Hidden ground truth is used only by the evaluation harness and is never exposed to the investigator.

## What is included

- Stateful single-agent investigation loop
- OpenAI Responses API investigator with strict function calling
- Deterministic offline fallback for development and tests
- Typed, allowlisted investigation tools
- Evidence provenance and validation
- Hypothesis lifecycle management
- Deterministic confidence scoring and evidence gate
- NetworkX investigation graph
- FastAPI service and investigation workspace UI
- Structured JSON logging
- Hidden-ground-truth evaluation harness
- Reproducible 90-day DuckDB business warehouse
- Snowflake DDL, loader, and dbt transformation project
- Operational metadata, realistic decoys, and resettable failure injection
- Twelve typed analytics, quality, metadata, lineage, and impact tools
- Typed observed/inferred causal links with link-level evidence references
- Seven resettable warehouse scenarios and investigation regression coverage
- Rejected-hypothesis explanations in the demo UI
- Generic question understanding and dynamic hypothesis contracts
- Capability-based Tool Registry discovery with schemas, domains, evidence types, and cost hints
- Evidence-gap prioritization using deterministic investigation priority and information value
- Recursive follow-up investigations for supported but incomplete explanations
- Live background investigation API and polling UI showing intent, evidence, and belief updates
- Generic-investigator acceptance coverage for revenue, regional orders, data completeness,
  recursion, insufficiency, and new-tool discovery
- Unit and integration tests
- Docker and GitHub Actions configuration

## Quick start

Python 3.11 or newer is required.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Add your OpenAI API key to `.env`:

```text
OPENAI_API_KEY=your_api_key_here
INSIGHTIQ_AGENT_MODE=openai
INSIGHTIQ_OPENAI_MODEL=gpt-4.1-mini
```

Keep `.env` local and never commit a real API key. Start the application:

```bash
uvicorn insightiq.api.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000). The UI shows live hypotheses, evidence attached to each hypothesis, provenance and tool results, the evidence-gate decision, financial impact, and the final recommendation.

Try questions that produce different hypotheses and investigation paths:

```text
Why did revenue drop yesterday?
Which region had the lost revenue yesterday?
Investigate what changed in the business yesterday and identify the root cause.
Why did Northeast order volume fall yesterday?
Why did customer region data become incomplete?
Why did employee happiness change?
```

The last question intentionally demonstrates `INSUFFICIENT_EVIDENCE` because the registered
enterprise environment has no capability that can responsibly answer it.

On first startup, InsightIQ creates `data/insightiq.duckdb`. You can explicitly manage it with:

```bash
insightiq-data build
insightiq-data validate
insightiq-data profile
insightiq-data reset
```

Run a trust/negative scenario with:

```bash
insightiq-data reset --scenario missing_deployment
insightiq-data reset --scenario conflicting_evidence
insightiq-data reset --scenario payment_failure
insightiq-data reset --scenario custom_region_failure
insightiq-data reset --scenario data_quality_no_deployment
insightiq-data reset --scenario insufficient_evidence
```

For a real-world ingestion demonstration, the project selects [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail). After downloading its workbook, install the `real-data` extra and run `insightiq-data import-uci --source <workbook>`.

Run the tests and evaluator:

```bash
pytest
python -m insightiq.evaluation.runner
```

## OpenAI investigator

OpenAI mode is the primary application path. The API key is loaded explicitly from `.env` and passed to the OpenAI client without being returned by the health endpoint or written to application logs.

The investigator uses custom function tools through the Responses API. OpenAI chooses the next allowlisted evidence tool and produces the recommendation. Tool execution, SQL, calculations, evidence IDs, provenance validation, confidence scoring, root-cause chain construction, and the final evidence-gate decision remain deterministic application responsibilities.

For offline development or tests, set `INSIGHTIQ_AGENT_MODE=deterministic`. That mode requires no API key and follows the same tool, evidence, confidence, and report contracts.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/investigations` | Run an investigation |
| `POST` | `/investigations/start` | Start a live background investigation |
| `GET` | `/tools` | Discover registered tool contracts and capabilities |
| `GET` | `/investigations/{id}` | Read investigation state |
| `GET` | `/investigations/{id}/evidence` | Read evidence and provenance |
| `GET` | `/investigations/{id}/graph` | Read graph nodes and edges |
| `GET` | `/investigations/{id}/report` | Read the canonical report |
| `GET` | `/health` | Health/configuration check |

Example:

```bash
curl -X POST http://localhost:8000/investigations \
  -H "Content-Type: application/json" \
  -d '{"question":"Why did revenue decrease yesterday?"}'
```

## Architecture

```text
Question -> OpenAI planner -> Allowlisted tools -> DuckDB/Snowflake
                  |                    |                |
                  v                    v                v
             Hypotheses          Tool results      Warehouse data
                  |                    |
                  +------> Evidence store
                               |
                               v
                    Deterministic evidence gate
                               |
                               v
                     Auditable investigation report
```

The Investigator loop contains no KPI, revenue, payment, region, deployment, or data-quality
branches. Question-specific hypotheses and evidence requirements come from declarative enterprise
context. Tools are selected by matching those requirements to capabilities advertised by the Tool
Registry. Tool-specific interpretation remains with each registered tool, so a new matching tool
does not require an Investigator change.

The project uses an in-memory repository for the MVP. Replace it with durable storage before running multiple application instances.

## Repository layout

```text
src/insightiq/
  agent/          investigator and decision providers
  api/            FastAPI routes
  data/           DuckDB generation and data-management CLI
  evaluation/     hidden-ground-truth evaluator
  tools/          controlled deterministic tools
  trust/          evidence, confidence, and graph
  models.py       canonical contracts
frontend/         zero-build demo interface
scenarios/        hidden evaluator fixtures
tests/            unit and end-to-end tests
```

## Data engineering implementation

The default DuckDB backend mirrors the target Snowflake schemas and makes the entire project runnable without cloud credentials:

```text
RAW          customers, orders, order_items, products, web_traffic, payments
BUSINESS     customer snapshots, order facts, KPI and regional models
QUALITY      historical field-quality metrics
OPERATIONS   deployments, pipeline runs, schema changes, lineage, incidents, docs
```

The injected scenario preserves actual revenue at `$120,000` while a customer-region mapping regression causes the reporting model to emit `$72,000`. Traffic, payments, pipeline status, and unrelated deployments provide plausible decoys.

See [`docs/data-engineering.md`](docs/data-engineering.md) for ownership, contracts, warehouse setup, and Snowflake instructions.
See [`docs/generic-investigator.md`](docs/generic-investigator.md) for planning, recursion,
tool discovery, live progress, and the implementation freeze.
See [`docs/architecture.md`](docs/architecture.md) for the system architecture diagram.
See [`docs/plan.md`](docs/plan.md) for phased milestones and definition-of-done checks.
See [`docs/prompts.md`](docs/prompts.md) for significant prompts, responses, and refinements.

Every backend returns the same `ToolResult` envelope:

```text
tool_name, execution_id, query_id, source, timestamp, result
```

To use Snowflake:

```bash
pip install -e ".[snowflake]"
insightiq-snowflake-load
dbt build --profiles-dir dbt
```

Then set `INSIGHTIQ_DATA_BACKEND=snowflake`. Keep metric names, dimensions, and SQL templates allowlisted. Never grant the model unrestricted SQL access, and never make `scenarios/ground_truth.json` available to an investigation tool.

## Trust rules

- Facts come from tools; the model does not invent measurements.
- Business-impact inputs are fetched by the tool from the warehouse, not supplied by the model.
- Observed evidence must link to a recorded tool execution.
- Every root-cause link is labeled `OBSERVED` or `INFERRED` and cites evidence IDs.
- Inferences are labeled separately from observations.
- Hypotheses require evidence to be supported or rejected.
- Unresolved evidence against the proposed hypothesis blocks the evidence gate.
- Confidence is calculated in code.
- A failed evidence gate returns **Root cause not established**.
- Hidden ground truth is evaluation-only.

## Implementation freeze

The bundled revenue mystery is a test fixture, not the investigation algorithm. The known
enterprise context, registry metadata, schemas, deterministic scoring rules, and scenarios are
configured. Hypotheses, evidence gaps, tool selection, investigation path, recursive questions,
conclusions, and root-cause chains are produced at runtime.

The central stopping rule is: investigate the most valuable unresolved question next, and stop
only when the Evidence Gate finds sufficient evidence or the available evidence runs out.

## Current MVP limitations

- Investigation work runs in an in-process background thread and progress is polled by the UI.
- State is stored in memory and is lost when the server restarts.
- The bundled scenarios are deliberately controlled and compact.
- OpenAI mode requires network access and a valid API key with access to the configured model.
- Snowflake requires your account, warehouse, role, and authentication configuration.
