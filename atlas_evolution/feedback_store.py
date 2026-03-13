from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from atlas_evolution.models import FeedbackRecord
from atlas_evolution.runtime_events import RuntimeSessionEvent


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()


@dataclass(slots=True)
class FeedbackStore:
    state_dir: Path
    events_path: Path = field(init=False)
    reports_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.state_dir / "events.jsonl"
        self.reports_dir = self.state_dir / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def append_event(self, event_type: str, payload: dict[str, Any]) -> None:
        record = {
            "timestamp": utc_now(),
            "event_type": event_type,
            "payload": payload,
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

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

    def log_runtime_event(self, event: RuntimeSessionEvent) -> None:
        self.append_event("runtime_session_event", event.to_dict())

    def iter_events(self) -> list[dict[str, Any]]:
        if not self.events_path.exists():
            return []
        return [
            json.loads(line)
            for line in self.events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def load_feedback(self) -> list[FeedbackRecord]:
        records: list[FeedbackRecord] = []
        for event in self.iter_events():
            event_type = event.get("event_type")
            payload = event["payload"]
            if event_type == "feedback_recorded":
                records.append(
                    FeedbackRecord(
                        session_id=payload["session_id"],
                        task=payload["task"],
                        status=payload["status"],
                        score=float(payload["score"]),
                        comment=payload.get("comment"),
                        steps=list(payload.get("steps", [])),
                        selected_skill_ids=list(payload.get("selected_skill_ids", [])),
                        missing_capabilities=list(payload.get("missing_capabilities", [])),
                        metadata=dict(payload.get("metadata", {})),
                    )
                )
                continue
            if event_type == "runtime_session_event":
                runtime_event = RuntimeSessionEvent.from_dict(payload)
                feedback = runtime_event.to_feedback_record()
                if feedback is not None:
                    records.append(feedback)
        return records

    def write_report(self, name: str, payload: dict[str, Any]) -> Path:
        path = self.reports_dir / name
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path
