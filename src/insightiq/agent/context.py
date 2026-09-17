from __future__ import annotations

from dataclasses import dataclass

from insightiq.models import (
    EvidenceRequirement,
    Hypothesis,
    InvestigationPriority,
    new_id,
)


@dataclass(frozen=True)
class QuestionContext:
    domains: list[str]
    metric: str | None = None
    dimension: str | None = None
    field: str | None = None
    object_name: str | None = None
    profile: str = "unknown"


def understand_question(question: str) -> QuestionContext:
    text = question.casefold()
    field = "customer_region" if "region" in text else None
    if any(
        word in text
        for word in ("incomplete", "completeness", "null", "data quality", "data-quality")
    ):
        return QuestionContext(
            domains=["data_quality", "operations"],
            field=field or "customer_region",
            object_name="customer_dimension",
            profile="data_completeness",
        )
    if "order" in text:
        return QuestionContext(
            domains=["orders", "operations", "data_quality"],
            metric="orders",
            dimension="region" if any(word in text for word in ("region", "northeast")) else None,
            field=field or "customer_region",
            object_name="daily_revenue",
            profile="regional_orders" if field else "orders",
        )
    if "revenue" in text:
        return QuestionContext(
            domains=["revenue", "operations", "data_quality"],
            metric="revenue",
            dimension="region",
            field="customer_region",
            object_name="daily_revenue",
            profile="regional_revenue" if field else "revenue",
        )
    broad_business_question = (
        any(term in text for term in ("business", "company"))
        and any(
            term in text
            for term in ("change", "happened", "performance", "results", "root cause", "impact")
        )
    )
    if broad_business_question:
        return QuestionContext(
            domains=["revenue", "orders", "operations", "data_quality"],
            metric="revenue",
            dimension="region",
            field="customer_region",
            object_name="daily_revenue",
            profile="revenue",
        )
    return QuestionContext(domains=["operations"], profile="unknown")


def requirement(
    capability: str,
    description: str,
    arguments: dict | None = None,
    information_value: float = 0.7,
) -> EvidenceRequirement:
    return EvidenceRequirement(
        requirement_id=new_id("need"),
        capability=capability,
        description=description,
        arguments=arguments or {},
        information_value=information_value,
    )


def _hypothesis(
    number: int,
    question: str,
    hypothesis_type: str,
    description: str,
    needs: list[EvidenceRequirement],
    *,
    priority: InvestigationPriority = InvestigationPriority.MEDIUM,
    parent_id: str | None = None,
    follow_up: str | None = None,
) -> tuple[Hypothesis, list[EvidenceRequirement]]:
    hypothesis = Hypothesis(
        hypothesis_id=f"H{number}",
        hypothesis_type=hypothesis_type,
        description=description,
        question=question,
        parent_hypothesis_id=parent_id,
        investigation_priority=priority,
        next_evidence_needed=[item.description for item in needs],
        follow_up_question=follow_up,
    )
    return hypothesis, needs


def generate_hypotheses(
    question: str,
    *,
    start_number: int = 1,
    parent_id: str | None = None,
) -> tuple[list[Hypothesis], dict[str, list[EvidenceRequirement]], QuestionContext]:
    context = understand_question(question)
    specifications: list[
        tuple[str, str, list[EvidenceRequirement], InvestigationPriority, str | None]
    ]

    if context.profile in {"revenue", "regional_revenue"}:
        specifications = [
            (
                "demand_decline",
                "Customer demand or traffic declined.",
                [
                    requirement(
                        "compare_metric",
                        "Compare traffic with its baseline.",
                        {"metric": "traffic"},
                        0.9,
                    )
                ],
                InvestigationPriority.HIGH,
                None,
            ),
            (
                "pricing_issue",
                "Pricing or average order value changed materially.",
                [
                    requirement(
                        "decompose_metric",
                        "Decompose revenue into volume and price effects.",
                        {"metric": "revenue"},
                        0.8,
                    )
                ],
                InvestigationPriority.MEDIUM,
                None,
            ),
            (
                "payment_failure",
                "Payment failures prevented otherwise valid orders.",
                [
                    requirement(
                        "compare_metric",
                        "Compare payment failures with their baseline.",
                        {"metric": "payment_failure_rate"},
                        0.9,
                    )
                ],
                InvestigationPriority.HIGH,
                None,
            ),
            (
                "data_quality_failure",
                "A data-quality failure excluded valid records from reporting.",
                [
                    requirement(
                        "check_completeness",
                        "Measure customer-region completeness.",
                        {"field": context.field},
                        1.0,
                    )
                ],
                InvestigationPriority.HIGH,
                "What caused the customer-region data-quality failure?",
            ),
        ]
        if context.profile == "regional_revenue":
            specifications.insert(
                0,
                (
                    "regional_pattern",
                    "The lost revenue is concentrated in one or more geographic regions.",
                    [
                        requirement(
                            "segment_metric",
                            "Compare revenue across regions.",
                            {"metric": "revenue", "dimension": "region"},
                            1.0,
                        )
                    ],
                    InvestigationPriority.HIGH,
                    None,
                )
            )
    elif context.profile in {"regional_orders", "orders"}:
        specifications = [
            (
                "demand_decline",
                "Customer demand or traffic declined.",
                [
                    requirement(
                        "compare_metric",
                        "Compare traffic with its baseline.",
                        {"metric": "traffic"},
                        0.9,
                    )
                ],
                InvestigationPriority.HIGH,
                None,
            ),
            (
                "regional_pattern",
                "The order decline is concentrated in a geographic segment.",
                [
                    requirement(
                        "segment_metric",
                        "Compare order volume across regions.",
                        {"metric": "orders", "dimension": "region"},
                        0.9,
                    )
                ],
                InvestigationPriority.HIGH,
                None,
            ),
            (
                "payment_failure",
                "Payment failures reduced completed order volume.",
                [
                    requirement(
                        "compare_metric",
                        "Compare payment failures with their baseline.",
                        {"metric": "payment_failure_rate"},
                        0.8,
                    )
                ],
                InvestigationPriority.MEDIUM,
                None,
            ),
            (
                "data_quality_failure",
                "Incomplete regional data excluded orders from reporting.",
                [
                    requirement(
                        "check_completeness",
                        "Measure customer-region completeness.",
                        {"field": context.field},
                        1.0,
                    )
                ],
                InvestigationPriority.HIGH,
                "What caused the customer-region data-quality failure?",
            ),
        ]
    elif context.profile == "data_completeness":
        specifications = [
            (
                "deployment_defect",
                "A deployment defect changed the customer-region transformation.",
                [
                    requirement(
                        "deployment_history",
                        "Find deployments near the failure onset.",
                        information_value=0.8,
                    ),
                    requirement(
                        "schema_change",
                        "Inspect changes to the customer dimension.",
                        {"object_name": "customer_dimension"},
                        1.0,
                    ),
                    requirement(
                        "dependency_lineage",
                        "Trace downstream dependencies and filters.",
                        {"object_name": "daily_revenue"},
                        1.0,
                    ),
                ],
                InvestigationPriority.HIGH,
                None,
            ),
            (
                "pipeline_failure",
                "A failed data pipeline caused incomplete customer-region values.",
                [
                    requirement(
                        "pipeline_history",
                        "Inspect pipeline runs near the failure onset.",
                        information_value=0.9,
                    )
                ],
                InvestigationPriority.HIGH,
                None,
            ),
            (
                "upstream_source_issue",
                "The upstream source supplied incomplete customer-region values.",
                [
                    requirement(
                        "check_completeness",
                        "Measure customer-region completeness.",
                        {"field": context.field},
                        0.8,
                    )
                ],
                InvestigationPriority.MEDIUM,
                None,
            ),
        ]
    else:
        specifications = [
            (
                "known_incident",
                "A recorded operational incident explains the reported change.",
                [
                    requirement(
                        "incident_search",
                        "Search known incidents relevant to the question.",
                        {"query": question},
                        0.7,
                    )
                ],
                InvestigationPriority.MEDIUM,
                None,
            )
        ]

    hypotheses: list[Hypothesis] = []
    requirements: dict[str, list[EvidenceRequirement]] = {}
    for offset, (kind, description, needs, priority, follow_up) in enumerate(specifications):
        hypothesis, hypothesis_needs = _hypothesis(
            start_number + offset,
            question,
            kind,
            description,
            needs,
            priority=priority,
            parent_id=parent_id,
            follow_up=follow_up,
        )
        hypotheses.append(hypothesis)
        requirements[hypothesis.hypothesis_id] = hypothesis_needs

    question_needs: list[EvidenceRequirement] = []
    if context.metric:
        question_needs.append(
            requirement(
                "compare_metric",
                f"Verify the reported {context.metric} change.",
                {"metric": context.metric},
                1.0,
            )
        )
    if context.metric == "revenue":
        question_needs.append(
            requirement(
                "calculate_impact",
                "Calculate the business impact from warehouse values.",
                {"metric": "revenue"},
                0.7,
            )
        )
    if question_needs:
        requirements.setdefault("__question__", []).extend(question_needs)
    return hypotheses, requirements, context
