# InsightIQ Prompt Log

This document records significant prompts used while building and validating InsightIQ, the
observed response or behavior, and the refinement that followed. It is a development and evaluation
log, not a transcript. API keys, credentials, and sensitive tool payloads are intentionally omitted.

## Prompting Strategy

InsightIQ uses two kinds of prompts:

1. **User investigation questions** define the business problem to investigate.
2. **Application instructions** constrain OpenAI to select one allowlisted tool for the highest-value
   unresolved evidence gap or finish only when a traceable causal chain exists.

The model receives structured investigation state: hypotheses, evidence requirements, observed
evidence, business impact, and registered tool contracts. It does not receive unrestricted SQL or
permission to invent facts, calculations, IDs, or sources.

The current application instruction is maintained in
`src/insightiq/agent/providers.py`. Its essential rules are:

- Act as a cautious, general business investigator.
- Investigate the highest-priority unresolved evidence gap.
- Select exactly one discovered tool per turn.
- Never invent facts, calculations, identifiers, or sources.
- Finish only when the evidence forms a traceable causal chain.

## Significant Prompt Log

### 1. Revenue root-cause investigation

**Prompt**

> Why did reported revenue decrease yesterday?

**Initial behavior**

The deterministic path generated demand, pricing, payment, and data-quality hypotheses. OpenAI mode
could call tools, but the API key from `.env` was not passed explicitly to the OpenAI client.

**Refinement**

- Added `OPENAI_API_KEY` as a secret setting.
- Passed the key explicitly to `OpenAIDecisionProvider`.
- Added a clear startup error when OpenAI mode has no key.

**Result**

The Responses API connected successfully and began selecting evidence tools.

### 2. Evidence requirements were not resolving

**Prompt**

> Why did reported revenue decrease yesterday?

**Observed response**

OpenAI collected relevant evidence, but the report returned `INSUFFICIENT_EVIDENCE` because selected
tools were not associated with their owning hypothesis requirements.

**Refinement**

- Matched every selected tool to an unresolved capability requirement.
- Added the hypothesis ID and evidence sought to the investigation intent.
- Marked the matched requirement as satisfied after execution.

**Result**

The data-quality hypothesis reached `SUPPORTED` with evidence attached to the correct hypothesis.

### 3. Recursive cause investigation

**Prompt**

> Why did reported revenue decrease yesterday?

**Observed response**

The broad data-quality hypothesis was supported, but OpenAI mode stopped before asking what caused
the data-quality failure.

**Refinement**

- Made recursive follow-up generation provider-independent.
- Added child hypotheses for deployments, pipelines, schema changes, source quality, and lineage.
- Reused previously collected evidence when it satisfied a child requirement.

**Result**

The investigation continued from the reporting symptom to the underlying transformation defect.

### 4. Redundant tool selection

**Prompt**

> Why did reported revenue decrease yesterday?

**Observed response**

The model exhausted the tool-call budget on repeated or low-value tools before calculating business
impact.

**Refinement**

- Offered OpenAI only tools mapped to unresolved evidence requirements.
- Disabled finalization until those requirements were resolved.
- Preserved one-tool-per-turn execution.

**Result**

The investigation completed within the configured tool-call limit and included deterministic impact.

### 5. Generated evidence IDs failed validation

**Prompt**

> Why did reported revenue decrease yesterday?

**Observed response**

The model found the correct cause and recommendation, but its generated causal chain referenced
evidence incorrectly, so the deterministic gate rejected the conclusion.

**Refinement**

- Reconstructed final causal links deterministically from recorded evidence IDs.
- Retained the model-generated recommendation.
- Kept provenance validation as the final publication boundary.

**Result**

The evidence gate passed with `ROOT_CAUSE_ESTABLISHED` and a fully traceable chain.

### 6. Open-ended business question

**Prompt**

> Why did our business performance change yesterday?

**Initial response**

> A recorded operational incident explains the reported change.

The system searched incidents, found zero records, and stopped. The question had fallen into the
unknown-question profile.

**Refinement**

- Recognized broad business-performance and company-results language.
- Routed broad business questions to revenue, demand, pricing, payment, and data-quality hypotheses.
- Preserved cautious insufficiency for unrelated domains such as employee happiness.

**Result**

Against the payment-failure scenario, the system rejected demand, pricing, and data-quality causes,
supported payment failures, and calculated a `$48,000` impact.

### 7. Longer open-ended root-cause prompt

**Prompt**

> Investigate what changed in the business yesterday, determine the most likely root cause, and
> estimate its financial impact.

**Initial response**

The prompt again entered the incident-only path because the matcher recognized "business
performance" but not "changed in the business."

**Refinement**

- Replaced exact phrase matching with business/company plus change, performance, results,
  root-cause, or impact intent matching.
- Added the exact prompt as a regression test.

**Result**

The prompt now generates measurable competing hypotheses and follows the complete investigation
path.

### 8. Regional revenue question

**Prompt**

> Which region had the lost revenue yesterday?

**Initial behavior**

The warehouse contained the answer, but the revenue profile did not create a regional hypothesis,
so the application never called `segment_metric`.

**Refinement**

- Added a regional-revenue question profile.
- Added a geographic-concentration hypothesis and revenue-by-region requirement.
- Prioritized the explicitly requested segmentation before recursive causal analysis.

**Result**

For the payment-failure scenario, the data showed `$26,400` lost in Europe and `$21,600` lost in
Asia Pacific, with no lost revenue in North America.

### 9. Insufficient evidence displayed as 100 percent

**User feedback**

> It shows 100% even though it is insufficient evidence.

**Observed behavior**

The UI displayed the evidence consistency score as conclusion confidence even when another gate
condition blocked publication.

**Refinement**

- Renamed the summary metric to **Conclusion confidence**.
- Displayed `N/A` when the evidence gate stopped.
- Added the gate's exact missing-evidence reasons to the overview.

**Result**

Evidence dimensions remain available for diagnosis without implying that an unsupported conclusion
is 100 percent certain.

### 10. Evidence placement and audit details

**User prompts**

> Can we have evidence under hypothesis?

> Under Evidence, show derived from, tool result, query, and the data.

**Refinement**

- Displayed supporting and contradicting statements beneath each hypothesis.
- Added source, execution ID, query ID, supported and contradicted hypotheses, tool arguments, and
  returned data to each evidence entry.
- Kept raw tool data in a collapsible section for readability.

**Result**

Users can trace a hypothesis to its evidence and from each evidence item back to the tool execution
and returned warehouse data.

## Current Evaluation Prompts

Use these prompts after changing question routing, tools, evidence scoring, or model instructions:

| Prompt | Expected behavior |
|---|---|
| `Why did reported revenue decrease yesterday?` | Evaluate demand, pricing, payments, and data quality; establish a cause only if the gate passes |
| `Why did our business performance change yesterday?` | Treat as an open-ended measurable business investigation |
| `Which region had the lost revenue yesterday?` | Run revenue segmentation by region before deeper causal analysis |
| `Why did Northeast order volume fall yesterday?` | Evaluate orders and geographic concentration |
| `Why did customer region data become incomplete?` | Use quality, deployment, schema, pipeline, and lineage evidence |
| `Why did employee happiness change?` | Return insufficient evidence because no registered capability supports the domain |

## Refinement Rules

When a prompt produces a poor result:

1. Determine whether the failure came from question routing, model tool selection, tool data,
   finding interpretation, hypothesis scoring, the evidence gate, or UI presentation.
2. Prefer fixing structured context, tool contracts, and deterministic validation over adding
   persuasive wording to the model instruction.
3. Add the failing prompt as a regression test.
4. Preserve insufficient evidence as a valid result.
5. Never weaken provenance or gate checks merely to make a scenario pass.
6. Record the prompt, observed behavior, refinement, and expected outcome in this log.
