from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from atlas_evolution.models import FeedbackRecord, ProjectedFeedbackRecord
from atlas_evolution.openclaw_contract import OpenClawAtlasEventEnvelope, parse_openclaw_atlas_event_envelopes


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()


@dataclass(slots=True)
class FeedbackStore:
    state_dir: Path
    events_path: Path = field(init=False)
    runtime_events_path: Path = field(init=False)
    projected_feedback_path: Path = field(init=False)
    reports_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.state_dir / "events.jsonl"
        self.runtime_events_path = self.state_dir / "runtime_event_envelopes.jsonl"
        self.projected_feedback_path = self.state_dir / "projected_feedback.jsonl"
        self.reports_dir = self.state_dir / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def _append_jsonl(self, path: Path, payload: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def append_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self._append_jsonl(
            self.events_path,
            {
                "timestamp": utc_now(),
                "event_type": event_type,
                "payload": payload,
            },
        )

    def log_session_start(
        self,
        session_id: str,
        task: str,
        metadata: dict[str, Any],
        selected_skill_ids: list[str],
    ) -> None:
        self.append_event(
            "session_started",
            {
                "session_id": session_id,
                "task": task,
                "metadata": metadata,
                "selected_skill_ids": selected_skill_ids,
            },
        )

    def log_feedback(self, record: FeedbackRecord) -> None:
        self.append_event("feedback_recorded", record.to_dict())

    def log_runtime_event_envelope(self, envelope: OpenClawAtlasEventEnvelope) -> None:
        self._append_jsonl(self.runtime_events_path, envelope.to_dict())

    def log_projected_feedback(self, record: ProjectedFeedbackRecord) -> None:
        self._append_jsonl(self.projected_feedback_path, record.to_dict())

    def record_runtime_ingest(self, envelope: OpenClawAtlasEventEnvelope) -> ProjectedFeedbackRecord | None:
        self.log_runtime_event_envelope(envelope)
        projected = envelope.to_projected_feedback_record()
        if projected is not None:
            self.log_projected_feedback(projected)
        return projected

    def iter_events(self) -> list[dict[str, Any]]:
        return self._read_jsonl(self.events_path)

    def iter_runtime_event_envelopes(self) -> list[OpenClawAtlasEventEnvelope]:
        payload = self._read_jsonl(self.runtime_events_path)
        if not payload:
            return []
        return parse_openclaw_atlas_event_envelopes(payload)

    def iter_projected_feedback_records(self) -> list[ProjectedFeedbackRecord]:
        return [ProjectedFeedbackRecord.from_dict(item) for item in self._read_jsonl(self.projected_feedback_path)]

    def load_feedback(self) -> list[FeedbackRecord]:
        records: list[FeedbackRecord] = []
        for event in self.iter_events():
            event_type = event.get("event_type")
            payload = event["payload"]
            if event_type == "feedback_recorded":
                records.append(FeedbackRecord.from_dict(payload))
                continue
            if event_type == "runtime_session_event":
                legacy_envelopes = parse_openclaw_atlas_event_envelopes(payload)
                legacy_feedback = legacy_envelopes[0].to_projected_feedback_record()
                if legacy_feedback is not None:
                    records.append(legacy_feedback.to_feedback_record())
        records.extend(record.to_feedback_record() for record in self.iter_projected_feedback_records())
        return records

    def build_runtime_ingest_report(self, session_id: str | None = None, limit: int | None = 20) -> dict[str, Any]:
        raw_envelopes = self.iter_runtime_event_envelopes()
        projected_records = self.iter_projected_feedback_records()
        if session_id:
            raw_envelopes = [item for item in raw_envelopes if item.event.session_id == session_id]
            projected_records = [item for item in projected_records if item.feedback.session_id == session_id]
        projected_by_envelope = {item.source_envelope_id: item for item in projected_records}
        displayed_raw = raw_envelopes[-limit:] if limit is not None else raw_envelopes
        audit_records = [
            {
                "envelope_id": envelope.envelope_id,
                "session_id": envelope.event.session_id,
                "task": envelope.event.task,
                "source": envelope.source,
                "event_kind": envelope.event.event_kind,
                "recorded_at": envelope.recorded_at,
                "projection_status": "projected" if envelope.envelope_id in projected_by_envelope else "raw_only",
                "raw_envelope": envelope.to_dict(),
                "projected_feedback": (
                    projected_by_envelope[envelope.envelope_id].to_dict()
                    if envelope.envelope_id in projected_by_envelope
                    else None
                ),
            }
            for envelope in displayed_raw
        ]
        return {
            "summary": {
                "session_filter": session_id,
                "raw_envelopes": len(raw_envelopes),
                "displayed_raw_envelopes": len(displayed_raw),
                "projected_feedback_records": len(projected_records),
                "raw_only_envelopes": len([item for item in raw_envelopes if item.envelope_id not in projected_by_envelope]),
            },
            "audit_records": audit_records,
        }

    def write_report(self, name: str, payload: dict[str, Any]) -> Path:
        path = self.reports_dir / name
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path
