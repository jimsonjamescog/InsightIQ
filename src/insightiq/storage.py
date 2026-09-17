from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from insightiq.models import GraphExport, InvestigationReport, InvestigationState


@dataclass
class InvestigationRecord:
    state: InvestigationState
    report: InvestigationReport | None = None
    graph: GraphExport | None = None


class InMemoryRepository:
    def __init__(self) -> None:
        self._records: dict[str, InvestigationRecord] = {}
        self._lock = Lock()

    def save(self, record: InvestigationRecord) -> None:
        with self._lock:
            self._records[record.state.investigation_id] = record

    def save_state(self, state: InvestigationState) -> None:
        with self._lock:
            current = self._records.get(state.investigation_id)
            self._records[state.investigation_id] = InvestigationRecord(
                state=state,
                report=current.report if current else None,
                graph=current.graph if current else None,
            )

    def get(self, investigation_id: str) -> InvestigationRecord | None:
        with self._lock:
            return self._records.get(investigation_id)
