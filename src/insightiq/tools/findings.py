from __future__ import annotations

from insightiq.models import EvidenceFinding, EvidenceType, ToolResult


def compare_periods_findings(result: ToolResult) -> list[EvidenceFinding]:
    value = result.result
    metric = value["metric"]
    change = float(value["percent_change"])
    findings = [
        EvidenceFinding(
            statement=(
                f"{metric} changed {change}% from {value['baseline_value']} "
                f"to {value['current_value']} {value['unit']}."
            ),
            evidence_type=EvidenceType.STATISTICAL,
            supports_types=["anomaly"] if change <= -10 else [],
            strength=0.95,
        )
    ]
    if metric == "traffic":
        findings[0].supports_types = ["demand_decline"] if change <= -10 else []
        findings[0].contradicts_types = [] if change <= -10 else ["demand_decline"]
    elif metric == "payment_failure_rate":
        material = (
            float(value["current_value"]) >= 0.05
            and float(value["current_value"]) >= float(value["baseline_value"]) * 3
        )
        findings[0].supports_types = ["payment_failure"] if material else []
        findings[0].contradicts_types = [] if material else ["payment_failure"]
    return findings


def decomposition_findings(result: ToolResult) -> list[EvidenceFinding]:
    value = result.result
    volume = abs(float(value["effects"]["order_volume"]))
    price = abs(float(value["effects"]["average_order_value"]))
    price_is_material = price > volume and price > 0
    return [
        EvidenceFinding(
            statement=(
                f"KPI decomposition attributes {value['effects']['order_volume']} to order "
                f"volume and {value['effects']['average_order_value']} to average order value."
            ),
            evidence_type=EvidenceType.STATISTICAL,
            supports_types=["pricing_issue"] if price_is_material else [],
            contradicts_types=[] if price_is_material else ["pricing_issue"],
            strength=0.9,
        )
    ]


def segmentation_findings(result: ToolResult) -> list[EvidenceFinding]:
    value = result.result
    declining = [item for item in value["segments"] if item["percent_change"] <= -10]
    names = ", ".join(str(item["segment"]) for item in declining) or "no segments"
    return [
        EvidenceFinding(
            statement=f"{value['metric']} decline is concentrated in {names}.",
            evidence_type=EvidenceType.STATISTICAL,
            supports_types=["regional_pattern"] if declining else [],
            contradicts_types=[] if declining else ["regional_pattern"],
            strength=0.85,
        )
    ]


def quality_findings(result: ToolResult) -> list[EvidenceFinding]:
    value = result.result
    anomaly = bool(value["anomaly"])
    return [
        EvidenceFinding(
            statement=(
                f"{value['field']} null rate changed from "
                f"{value['baseline_null_rate']:.1%} to {value['current_null_rate']:.1%}."
            ),
            evidence_type=EvidenceType.STATISTICAL,
            supports_types=["data_quality_failure"] if anomaly else [],
            contradicts_types=[] if anomaly else ["data_quality_failure"],
            strength=1.0,
        )
    ]


def deployment_findings(result: ToolResult) -> list[EvidenceFinding]:
    deployments = result.result.get("deployments", [])
    relevant = [item for item in deployments if "transform" in item.get("service", "").casefold()]
    return [
        EvidenceFinding(
            statement=(
                f"Found {len(relevant)} transformation deployment(s) in the incident window."
            ),
            evidence_type=EvidenceType.TEMPORAL,
            supports_types=["deployment_defect"] if relevant else [],
            contradicts_types=[] if relevant else ["deployment_defect"],
            strength=0.75,
        )
    ]


def pipeline_findings(result: ToolResult) -> list[EvidenceFinding]:
    runs = result.result.get("runs", [])
    failed = [item for item in runs if item.get("status", "").casefold() != "succeeded"]
    return [
        EvidenceFinding(
            statement=f"Found {len(failed)} unsuccessful pipeline run(s) in the incident window.",
            evidence_type=EvidenceType.TEMPORAL,
            supports_types=["pipeline_failure"] if failed else [],
            contradicts_types=[] if failed else ["pipeline_failure"],
            strength=0.9,
        )
    ]


def schema_findings(result: ToolResult) -> list[EvidenceFinding]:
    changes = result.result.get("changes", [])
    details = "; ".join(
        str(item.get("change") or item.get("change_description")) for item in changes
    )
    return [
        EvidenceFinding(
            statement=(
                f"Found {len(changes)} relevant transformation change(s): {details or 'none'}."
            ),
            evidence_type=EvidenceType.DEPENDENCY,
            supports_types=["deployment_defect", "schema_change"] if changes else [],
            contradicts_types=[] if changes else ["schema_change"],
            strength=0.95,
        )
    ]


def dependency_findings(result: ToolResult) -> list[EvidenceFinding]:
    value = result.result
    has_filter = bool(value.get("filter_logic"))
    return [
        EvidenceFinding(
            statement=(
                f"{value['object_name']} depends on {', '.join(value.get('upstream', []))}; "
                f"filter logic is {value.get('filter_logic') or 'not recorded'}."
            ),
            evidence_type=EvidenceType.DEPENDENCY,
            supports_types=["deployment_defect", "data_quality_failure"] if has_filter else [],
            strength=1.0 if has_filter else 0.5,
        )
    ]


def incident_findings(result: ToolResult) -> list[EvidenceFinding]:
    incidents = result.result.get("incidents", [])
    return [
        EvidenceFinding(
            statement=f"Incident search returned {len(incidents)} relevant record(s).",
            evidence_type=EvidenceType.HISTORICAL,
            supports_types=["known_incident"] if incidents else [],
            contradicts_types=[] if incidents else ["known_incident"],
            strength=0.8,
        )
    ]


def impact_findings(result: ToolResult) -> list[EvidenceFinding]:
    value = result.result
    return [
        EvidenceFinding(
            statement=(
                f"The calculated {value['metric']} impact is {value['understatement']} "
                f"{value['unit']} ({value['understatement_percent']}%)."
            ),
            evidence_type=EvidenceType.BUSINESS_IMPACT,
            supports_types=["business_impact"],
            strength=1.0,
        )
    ]


INTERPRETERS = {
    "compare_periods": compare_periods_findings,
    "decompose_kpi": decomposition_findings,
    "segment_metric": segmentation_findings,
    "check_data_quality": quality_findings,
    "get_deployments": deployment_findings,
    "get_pipeline_runs": pipeline_findings,
    "inspect_schema_changes": schema_findings,
    "get_dependencies": dependency_findings,
    "search_incidents": incident_findings,
    "calculate_business_impact": impact_findings,
}

CAPABILITIES = {
    "get_kpi": ["read_metric"],
    "compare_periods": ["compare_metric"],
    "decompose_kpi": ["decompose_metric"],
    "segment_metric": ["segment_metric"],
    "detect_anomaly": ["detect_anomaly"],
    "check_data_quality": ["check_completeness"],
    "get_deployments": ["deployment_history"],
    "get_pipeline_runs": ["pipeline_history"],
    "inspect_schema_changes": ["schema_change"],
    "get_dependencies": ["dependency_lineage"],
    "search_incidents": ["incident_search"],
    "calculate_business_impact": ["calculate_impact"],
}

DOMAINS = {
    "get_kpi": ["all"],
    "compare_periods": ["revenue", "orders", "data_quality"],
    "decompose_kpi": ["revenue"],
    "segment_metric": ["revenue", "orders"],
    "detect_anomaly": ["revenue", "orders"],
    "check_data_quality": ["data_quality", "orders", "revenue"],
    "get_deployments": ["operations", "data_quality"],
    "get_pipeline_runs": ["operations", "data_quality"],
    "inspect_schema_changes": ["operations", "data_quality"],
    "get_dependencies": ["operations", "data_quality", "revenue", "orders"],
    "search_incidents": ["operations"],
    "calculate_business_impact": ["revenue"],
}


def metadata(name: str) -> dict:
    interpreter = INTERPRETERS.get(name)
    return {
        "output_schema": {"type": "object"},
        "evidence_types": list(EvidenceType),
        "applicable_domains": DOMAINS.get(name, ["all"]),
        "capabilities": CAPABILITIES.get(name, []),
        "cost_or_latency_hint": "LOW",
        "interpreter": interpreter,
    }
