# InsightIQ Build Plan

This plan organizes InsightIQ into independently verifiable phases. A phase is complete only when
its **Done means** checks pass; code presence alone does not count as completion.

## Phase 1: Project Foundation

**Milestone:** A developer can install, configure, run, and test the application locally.

- [x] Define the Python package and dependencies in `pyproject.toml`.
- [x] Add environment-based configuration with safe defaults.
- [x] Add FastAPI application and health endpoint.
- [x] Add structured logging.
- [x] Add Docker and CI configuration.
- [x] Document OpenAI-first local setup and deterministic fallback.

**Done means**

- [x] `pip install -e ".[dev]"` installs the project.
- [x] `GET /health` reports the configured agent mode, model, backend, and tools.
- [x] A real API key remains outside version control.
- [x] The test suite can run without an OpenAI API call by using deterministic mode.

## Phase 2: Reproducible Data Foundation

**Milestone:** The same business world and incident scenarios can be rebuilt on demand.

- [x] Generate 90 days of customers, products, orders, traffic, and payment history.
- [x] Build business facts, KPI models, regional models, and quality history.
- [x] Add deployment, pipeline, schema-change, lineage, and incident metadata.
- [x] Add DuckDB build, reset, validate, and profile commands.
- [x] Add controlled base, failure, conflict, and insufficient-evidence scenarios.
- [x] Add Snowflake DDL, loader, and dbt models.

**Done means**

- [x] `insightiq-data reset --scenario <name>` produces a deterministic scenario.
- [x] `insightiq-data validate --scenario <name>` returns no errors.
- [x] Warehouse tests verify row counts, incident metrics, null rates, and impact values.
- [x] Hidden ground truth is not available to investigation tools.

## Phase 3: Controlled Tool Layer

**Milestone:** The investigator can inspect business data without unrestricted SQL access.

- [x] Implement a typed Tool Registry.
- [x] Add analytics, segmentation, anomaly, quality, operations, lineage, and impact tools.
- [x] Validate tool inputs with strict Pydantic models.
- [x] Record execution ID, query ID, source, arguments, result, and timestamp.
- [x] Interpret tool results as typed evidence findings.
- [x] Support DuckDB and Snowflake through a shared `QueryRunner` contract.

**Done means**

- [x] Every registered tool exposes an input schema and capability metadata.
- [x] Unknown tools and invalid arguments are rejected before execution.
- [x] Every tool result contains traceable query provenance.
- [x] The model cannot submit arbitrary SQL or invented business-impact values.

## Phase 4: Investigation Engine

**Milestone:** A question produces competing hypotheses and an evidence-driven investigation path.

- [x] Add question profiles and evidence requirements.
- [x] Add hypothesis support, rejection, and insufficiency states.
- [x] Add OpenAI Responses API strict function calling.
- [x] Restrict each model turn to tools for unresolved evidence requirements.
- [x] Add deterministic offline provider.
- [x] Add recursive follow-up investigations for supported broad hypotheses.
- [x] Add step, tool-call, and repeated-request limits.

**Done means**

- [x] Revenue, orders, regional, payment, and data-quality questions take relevant tool paths.
- [x] Open-ended business questions generate measurable competing hypotheses.
- [x] Evidence is linked back to the hypothesis requirement it satisfies.
- [x] Unsupported questions stop with insufficient evidence instead of a guess.
- [x] A live OpenAI investigation can establish a supported root cause from warehouse data.

## Phase 5: Trust and Auditability

**Milestone:** A conclusion cannot be published without sufficient, traceable evidence.

- [x] Convert findings into observed evidence with execution provenance.
- [x] Calculate evidence strength, coverage, consistency, and overall confidence.
- [x] Build deterministic causal links from recorded evidence IDs.
- [x] Enforce the Evidence Gate.
- [x] Export a NetworkX evidence graph.
- [x] Return explicit missing-evidence reasons when the gate stops.

**Done means**

- [x] Multiple observed evidence items support the target hypothesis.
- [x] Contradicting evidence blocks publication.
- [x] Every observed causal link cites valid observed evidence.
- [x] Major competing hypotheses are resolved.
- [x] Required business impact is calculated from warehouse values.
- [x] A failed gate returns `Root cause not established`.

## Phase 6: API and Investigation UI

**Milestone:** A user can run and inspect an investigation from the browser.

- [x] Add synchronous and background investigation endpoints.
- [x] Add live state polling and canonical report retrieval.
- [x] Add overview, hypotheses, evidence, and timeline views.
- [x] Show supporting and contradicting evidence beneath each hypothesis.
- [x] Show evidence provenance, query IDs, tool arguments, and returned data.
- [x] Show conclusion confidence as unavailable when the evidence gate stops.
- [x] Add responsive desktop and mobile layouts.

**Done means**

- [x] A user can submit a question and observe progress without refreshing.
- [x] The final view distinguishes a passed gate from insufficient evidence.
- [x] Evidence can be traced from a hypothesis to a tool execution and returned data.
- [x] Repeated investigations reset loading and result states correctly.
- [x] The UI remains usable at desktop and mobile widths.

## Phase 7: Evaluation and Release Readiness

**Milestone:** Behavior is repeatable and regressions are detected before release.

- [x] Add unit tests for tools, trust rules, providers, and question profiles.
- [x] Add API and warehouse integration tests.
- [x] Add negative and conflicting-evidence scenarios.
- [x] Add hidden-ground-truth evaluation metrics.
- [x] Add Ruff linting and CI execution.
- [ ] Run visual regression tests against desktop and mobile screenshots in CI.
- [ ] Add release versioning and a changelog process.

**Done means**

- [x] Deterministic tests pass without external network access.
- [x] Lint and whitespace checks pass.
- [x] Scenario validation catches incorrect generated data.
- [ ] CI verifies the rendered UI at supported viewport sizes.
- [ ] A tagged release can be reproduced from documented commands.

## Phase 8: Production Hardening

**Milestone:** InsightIQ can operate reliably for authenticated users across multiple instances.

- [ ] Replace in-memory state with durable storage.
- [ ] Move investigations from threads to a persistent task queue.
- [ ] Add authentication, authorization, and tenant isolation.
- [ ] Store API and warehouse credentials in a managed secret store.
- [ ] Add request limits, model budgets, retries, and timeout policies.
- [ ] Add warehouse read-only roles and query timeouts.
- [ ] Add metrics, tracing, alerting, and audit retention.
- [ ] Add data retention and deletion policies.
- [ ] Perform threat modeling and dependency/security scanning.

**Done means**

- [ ] Restarting an API instance does not lose investigation state.
- [ ] A failed worker can retry without duplicating tool executions or reports.
- [ ] Users can access only their authorized investigations and data.
- [ ] Secrets never appear in logs, API responses, or persisted evidence.
- [ ] Cost, latency, error rate, and gate outcomes are observable.
- [ ] Recovery, rollback, and incident-response procedures are documented and tested.

## Release Gate

Before declaring a release ready:

- [ ] All checks in the target phase are complete.
- [ ] `ruff check .` passes.
- [ ] `pytest` passes in deterministic mode.
- [ ] Warehouse validation passes for every bundled scenario.
- [ ] One approved OpenAI smoke investigation passes against a non-sensitive test warehouse.
- [ ] Documentation matches the shipped configuration and UI.
- [ ] No real credentials, generated databases, or sensitive tool results are committed.
