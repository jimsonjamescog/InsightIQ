---
associate: Jimson James, Vinay Joshi, Taranjit Singh, Brian Tapia, Issouf Diara
case_study: InsightIQ - Autonomous Business Investigation Agent
---

# Hackathon Theme & Idea

## THEME

DataDriven Everything (Unlocking Optimization and Growth Through Advanced Analytics)

## IDEA

InsightIQ is an autonomous business investigation agent that helps organizations understand why
critical business KPIs unexpectedly change. Instead of simply detecting anomalies, it investigates
enterprise data and operational context to identify evidence-backed root causes, quantify business
impact, and recommend next actions.

## HOW_IT_WORKS

A user asks a question such as, "Why did revenue drop yesterday?" InsightIQ decomposes the KPI,
generates competing hypotheses, and gathers evidence from business data, data-quality metrics,
pipeline activity, deployments, dependencies, and historical incidents. It eliminates unsupported
explanations, constructs an auditable root-cause chain, quantifies the business impact, and produces
an investigation report with supporting evidence and recommendations. If the evidence is missing,
conflicting, or insufficient, it returns **Root cause not established**.

## WHAT_MAKES_IT_DIFFERENT

Unlike traditional dashboards, anomaly-detection systems, or AI chatbots, InsightIQ does not jump
directly to an answer. It conducts an evidence-gated investigation, tests competing explanations,
distinguishes observed facts from inferred conclusions, and establishes a root cause only when
sufficient traceable evidence exists. The language model selects from controlled tools, while SQL
and Python perform calculations, preserve provenance, score confidence, and enforce the final gate.

## MEASURED_RESULTS

- Reproduces the expected hidden root cause across 10 consecutive regression runs.
- Correctly handles five negative or alternative-cause scenarios, including conflicting evidence,
  missing deployment metadata, genuine payment failure, and insufficient evidence.
- Achieves 90% automated test coverage with all tests passing in deterministic mode.
- Calculates the demonstration incident's 40% revenue understatement as USD 48,000 using warehouse
  values rather than model-generated numbers.

## WHY_IT_FITS

InsightIQ aligns directly with the DataDriven Everything theme by using advanced analytics to
transform raw business and operational data into actionable, auditable insights. It combines KPI
decomposition, anomaly analysis, segmentation, data-quality analysis, operational metadata, and
evidence-based reasoning to move organizations from detecting what changed to understanding why it
changed, enabling faster and more informed decisions.
