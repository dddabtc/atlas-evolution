from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from typing import Any

from atlas_evolution.runtime.orchestrator import AtlasOrchestrator


def _json_response(handler: BaseHTTPRequestHandler, status: HTTPStatus, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload).encode("utf-8")
    handler.send_response(status.value)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def _parse_body(handler: BaseHTTPRequestHandler) -> Any:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON body: {error.msg}") from error


def make_handler(orchestrator: AtlasOrchestrator) -> type[BaseHTTPRequestHandler]:
    class AtlasProxyHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                _json_response(self, HTTPStatus.OK, {"status": "ok"})
                return
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/v1/route":
                try:
                    body = _parse_body(self)
                except ValueError as error:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(error)})
                    return
                if not isinstance(body, dict):
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "request body must be a JSON object"})
                    return
                task = str(body.get("task", "")).strip()
                if not task:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "task is required"})
                    return
                payload = orchestrator.route_task(task=task, metadata=dict(body.get("metadata", {})))
                _json_response(self, HTTPStatus.OK, payload)
                return
            if self.path == "/v1/feedback":
                try:
                    body = _parse_body(self)
                except ValueError as error:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(error)})
                    return
                if not isinstance(body, dict):
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "request body must be a JSON object"})
                    return
                try:
                    record = orchestrator.record_feedback(
                        session_id=str(body["session_id"]),
                        task=str(body["task"]),
                        status=str(body.get("status", "unknown")),
                        score=float(body.get("score", 0.0)),
                        comment=body.get("comment"),
                        steps=list(body.get("steps", [])),
                        selected_skill_ids=list(body.get("selected_skill_ids", [])),
                        missing_capabilities=list(body.get("missing_capabilities", [])),
                        metadata=dict(body.get("metadata", {})),
                    )
                except KeyError as error:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"missing field: {error.args[0]}"})
                    return
                _json_response(self, HTTPStatus.OK, {"status": "recorded", "feedback": record.to_dict()})
                return
            if self.path == "/v1/ingest":
                try:
                    body = _parse_body(self)
                    events = orchestrator.ingest_runtime_events(body)
                except ValueError as error:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(error)})
                    return
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "status": "recorded",
                        "ingested": len(events),
                        "events": [event.to_dict() for event in events],
                    },
                )
                return
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})

    return AtlasProxyHandler


def run_server(orchestrator: AtlasOrchestrator) -> None:
    host = orchestrator.config.runtime.host
    port = orchestrator.config.runtime.port
    server = ThreadingHTTPServer((host, port), make_handler(orchestrator))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
