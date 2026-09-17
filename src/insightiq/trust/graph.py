from __future__ import annotations

import networkx as nx

from insightiq.models import GraphEdge, GraphExport, GraphNode, InvestigationState


def build_graph(state: InvestigationState) -> GraphExport:
    graph = nx.DiGraph()
    question_id = f"question:{state.investigation_id}"
    graph.add_node(question_id, type="QUESTION", label=state.question)

    for hypothesis in state.hypotheses:
        graph.add_node(
            hypothesis.hypothesis_id,
            type="HYPOTHESIS",
            label=hypothesis.description,
            status=hypothesis.status.value,
            support_score=hypothesis.support_score,
            investigation_priority=hypothesis.investigation_priority.value,
        )
        graph.add_edge(question_id, hypothesis.hypothesis_id, type="GENERATED")
        if hypothesis.parent_hypothesis_id:
            graph.add_edge(
                hypothesis.parent_hypothesis_id,
                hypothesis.hypothesis_id,
                type="DEPENDS_ON",
            )

    for evidence in state.evidence:
        graph.add_node(
            evidence.evidence_id,
            type="EVIDENCE",
            label=evidence.statement,
            classification=evidence.classification.value,
            evidence_type=evidence.evidence_type.value,
            source=evidence.source,
        )
        if evidence.execution_id:
            graph.add_node(
                evidence.execution_id,
                type="TOOL_CALL",
                label=f"{evidence.tool_name}: {evidence.query_id}",
            )
            graph.add_edge(evidence.execution_id, evidence.evidence_id, type="PRODUCED")
        for hypothesis_id in evidence.supports:
            graph.add_edge(evidence.evidence_id, hypothesis_id, type="SUPPORTS")
        for hypothesis_id in evidence.contradicts:
            graph.add_edge(evidence.evidence_id, hypothesis_id, type="CONTRADICTS")

    if state.conclusion:
        conclusion_id = f"conclusion:{state.investigation_id}"
        graph.add_node(conclusion_id, type="CONCLUSION", label=state.conclusion)
        for evidence in state.evidence:
            if evidence.supports:
                graph.add_edge(evidence.evidence_id, conclusion_id, type="JUSTIFIES")

        prior_id = conclusion_id
        for link in state.root_cause_chain:
            link_id = f"cause:{state.investigation_id}:{link.link_id}"
            graph.add_node(
                link_id,
                type="ROOT_CAUSE_LINK",
                label=link.statement,
                classification=link.classification.value,
                sequence=link.sequence,
                evidence_ids=link.evidence_ids,
            )
            for evidence_id in link.evidence_ids:
                graph.add_edge(evidence_id, link_id, type="SUPPORTS_LINK")
            graph.add_edge(link_id, prior_id, type="CAUSES")
            prior_id = link_id

    nodes = [
        GraphNode(
            id=node_id,
            type=attrs.pop("type"),
            label=attrs.pop("label"),
            data=attrs,
        )
        for node_id, original_attrs in graph.nodes(data=True)
        for attrs in [dict(original_attrs)]
    ]
    edges = [
        GraphEdge(source=source, target=target, type=attrs["type"])
        for source, target, attrs in graph.edges(data=True)
    ]
    return GraphExport(nodes=nodes, edges=edges)
