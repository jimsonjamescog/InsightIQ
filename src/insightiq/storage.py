from __future__ import annotations

from dataclasses import dataclass

from insightiq.models import GraphExport, InvestigationReport, InvestigationState


@dataclass
class InvestigationRecord:
    state: InvestigationState
    report: InvestigationReport
    graph: GraphExport


class InMemoryRepository:
    def __init__(self) -> None:
        self._records: dict[str, InvestigationRecord] = {}

    def save(self, record: InvestigationRecord) -> None:
        self._records[record.state.investigation_id] = record

    def get(self, investigation_id: str) -> InvestigationRecord | None:
        return self._records.get(investigation_id)
