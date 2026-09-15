# InsightIQ

**Autonomous Business Investigation Agent**

> Don't just detect what changed. Investigate why.

InsightIQ is a runnable hackathon MVP that investigates a business anomaly, gathers deterministic evidence through controlled tools, tracks competing hypotheses, enforces an evidence gate, and produces an auditable root-cause report.

The included scenario investigates a 40% reported-revenue drop caused by a deployment that introduced null customer regions. Traffic and payment failures act as decoys. Hidden ground truth is used only by the evaluation harness and is never exposed to the investigator.

## What is included

- Stateful single-agent investigation loop
- Deterministic fallback investigator requiring no API key
- Optional OpenAI Responses API function-calling investigator
- Typed, allowlisted investigation tools
- Evidence provenance and validation
- Hypothesis lifecycle management
- Deterministic confidence scoring and evidence gate
- NetworkX investigation graph
- FastAPI service and lightweight demo UI
- Structured JSON logging
- Hidden-ground-truth evaluation harness
- Unit and integration tests
- Docker and GitHub Actions configuration

## Quick start

Python 3.11 or newer is required.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
uvicorn insightiq.api.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000). The default `deterministic` mode runs locally with the built-in scenario.

Run the tests and evaluator:

```bash
pytest
python -m insightiq.evaluation.runner
```

## Optional OpenAI mode

Copy `.env.example` to `.env`, set `OPENAI_API_KEY`, and change:

```text
INSIGHTIQ_AGENT_MODE=openai
INSIGHTIQ_OPENAI_MODEL=gpt-5.6-sol
```

The OpenAI path uses custom function tools through the Responses API. Tool execution, calculations, provenance validation, confidence, and the final evidence-gate decision remain deterministic application responsibilities.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/investigations` | Run an investigation |
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
Question -> Investigator -> Allowlisted tools -> Evidence store
                     |                         |
                     v                         v
                Hypotheses              Provenance graph
                     |                         |
                     +------> Evidence gate <-+
                                   |
                                   v
                         Investigation report
```

The project uses an in-memory repository for the MVP. Replace it with durable storage before running multiple application instances.

## Repository layout

```text
src/insightiq/
  agent/          investigator and decision providers
  api/            FastAPI routes
  evaluation/     hidden-ground-truth evaluator
  tools/          controlled deterministic tools
  trust/          evidence, confidence, and graph
  models.py       canonical contracts
frontend/         zero-build demo interface
scenarios/        hidden evaluator fixtures
tests/            unit and end-to-end tests
```

## Snowflake integration

The MVP ships with a deterministic repository so the complete AI workflow is runnable by every contributor. Production tools should implement the `ToolRegistry` contract and return the same `ToolResult` envelope:

```text
tool_name, execution_id, query_id, source, timestamp, result
```

Keep metric names, dimensions, and SQL templates allowlisted. Never grant the model unrestricted SQL access, and never make `scenarios/ground_truth.json` available to an investigation tool.

## Trust rules

- Facts come from tools; the model does not invent measurements.
- Observed evidence must link to a recorded tool execution.
- Inferences are labeled separately from observations.
- Hypotheses require evidence to be supported or rejected.
- Confidence is calculated in code.
- A failed evidence gate returns **Root cause not established**.
- Hidden ground truth is evaluation-only.

## Current MVP limitations

- Investigations execute synchronously.
- State is stored in memory.
- The bundled scenario is deliberately small.
- The live data warehouse adapter is an extension point rather than a configured deployment.
