# Generic Investigator Architecture

InsightIQ separates the known enterprise environment from the investigation decisions made at
runtime.

## Configured knowledge

- Enterprise vocabulary and question profiles live in `agent/context.py`.
- Every tool advertises its description, schemas, capabilities, evidence types, applicable
  domains, and cost/latency hint through the Tool Registry.
- Tool result interpretation lives beside the tools in `tools/findings.py`.
- Evidence scoring and gate thresholds are deterministic application rules.
- Revenue and negative scenarios remain test fixtures.

## Runtime decisions

For each question, the provider generates question-appropriate hypotheses and evidence
requirements. The planner ranks unresolved requirements using investigation priority, expected
information value, and registered tool cost. It discovers a matching tool rather than naming one
in the Investigator loop.

Each cycle records the current intent before execution, executes one typed tool, creates traceable
observed evidence, recalculates Evidence Support Scores, and updates hypothesis states. Explicit
contradicting evidence is required for rejection. A supported broad hypothesis may add a follow-up
question and child hypotheses; this is how the revenue investigation moves from a data-quality
finding to its underlying operational cause.

The root-cause chain is synthesized from supporting evidence at runtime. The Evidence Gate—not the
highest score—decides whether it may be published. Missing capabilities, unresolved alternatives,
contradictions, incomplete provenance, or an incomplete chain result in
`INSUFFICIENT_EVIDENCE`.

## Live API

`POST /investigations/start` creates a background investigation. Poll
`GET /investigations/{id}` to observe `current_intent`, the event stream, evidence, scores,
priorities, and state transitions. The UI uses this flow. The synchronous
`POST /investigations` endpoint remains available for integrations and tests.

`GET /tools` exposes the discoverable registry contract.

## Acceptance suite

`tests/test_generic_investigator.py` proves:

1. Revenue questions generate and evaluate suitable competing hypotheses.
2. Regional order questions generate a different hypothesis set and tool path.
3. Data-completeness questions use operational and quality evidence without replaying revenue.
4. Supported broad explanations create recursive follow-up investigations.
5. Unknown questions finish with insufficient evidence instead of a guess.
6. A replacement tool can satisfy a requested capability without changing Investigator logic.

The invariant is: the Investigator does not search for a winner. It investigates the most valuable
unresolved question until sufficient evidence exists or evidence runs out.
