from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from atlas_evolution.config import load_config, write_default_config
from atlas_evolution.models import EvolutionReport
from atlas_evolution.runtime.orchestrator import AtlasOrchestrator
from atlas_evolution.runtime.proxy import run_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="atlas-evolution")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Write a sample config file.")
    init_parser.add_argument("path", nargs="?", default="atlas.toml")
    init_parser.add_argument("--overwrite", action="store_true")

    skills_parser = subparsers.add_parser("skills", help="Inspect the loaded skill bank.")
    skills_parser.add_argument("--config", default="demo/atlas.toml")
    skills_subparsers = skills_parser.add_subparsers(dest="skills_command", required=True)
    skills_subparsers.add_parser("list", help="List available skills.")

    route_parser = subparsers.add_parser("route", help="Route a task through the skill bank.")
    route_parser.add_argument("--config", default="demo/atlas.toml")
    route_parser.add_argument("--task", required=True)
    route_parser.add_argument("--metadata", action="append", default=[], help="key=value pairs")

    feedback_parser = subparsers.add_parser("feedback", help="Record post-session feedback.")
    feedback_parser.add_argument("--config", default="demo/atlas.toml")
    feedback_parser.add_argument("--session-id", required=True)
    feedback_parser.add_argument("--task", required=True)
    feedback_parser.add_argument("--status", required=True)
    feedback_parser.add_argument("--score", required=True, type=float)
    feedback_parser.add_argument("--comment")
    feedback_parser.add_argument("--step", action="append", default=[])
    feedback_parser.add_argument("--skill", action="append", default=[])
    feedback_parser.add_argument("--missing-capability", action="append", default=[])
    feedback_parser.add_argument("--metadata", action="append", default=[], help="key=value pairs")

    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Ingest external runtime session events from JSON.",
    )
    ingest_parser.add_argument("--config", default="demo/atlas.toml")
    ingest_parser.add_argument(
        "--file",
        help="Read JSON from a file. If omitted, JSON is read from stdin.",
    )

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect raw runtime event envelopes and projected feedback records.",
    )
    inspect_parser.add_argument("--config", default="demo/atlas.toml")
    inspect_parser.add_argument("--session-id")
    inspect_parser.add_argument("--limit", type=int, default=20)
    inspect_parser.add_argument("--write-report", action="store_true")

    evolve_parser = subparsers.add_parser("evolve", help="Generate and gate evolution proposals.")
    evolve_parser.add_argument("--config", default="demo/atlas.toml")

    promote_parser = subparsers.add_parser(
        "promote",
        help="Apply only proposals that passed the evaluation gate.",
    )
    promote_parser.add_argument("--config", default="demo/atlas.toml")

    serve_parser = subparsers.add_parser("serve", help="Run the local HTTP proxy surface.")
    serve_parser.add_argument("--config", default="demo/atlas.toml")
    return parser


def parse_key_values(items: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Expected key=value, got: {item}")
        key, value = item.split("=", 1)
        result[key] = value
    return result


def cmd_init(args: argparse.Namespace) -> int:
    path = write_default_config(args.path, overwrite=args.overwrite)
    print(f"Wrote config to {path}")
    return 0


def cmd_skills(args: argparse.Namespace) -> int:
    orchestrator = AtlasOrchestrator.from_config_path(args.config)
    for skill in orchestrator.skill_bank.list_skills():
        print(f"{skill.id}\t{skill.name}\t{', '.join(skill.tags)}")
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    orchestrator = AtlasOrchestrator.from_config_path(args.config)
    payload = orchestrator.route_task(task=args.task, metadata=parse_key_values(args.metadata))
    print(json.dumps(payload, indent=2))
    return 0


def cmd_feedback(args: argparse.Namespace) -> int:
    orchestrator = AtlasOrchestrator.from_config_path(args.config)
    record = orchestrator.record_feedback(
        session_id=args.session_id,
        task=args.task,
        status=args.status,
        score=args.score,
        comment=args.comment,
        steps=list(args.step),
        selected_skill_ids=list(args.skill),
        missing_capabilities=list(args.missing_capability),
        metadata=parse_key_values(args.metadata),
    )
    print(json.dumps(record.to_dict(), indent=2))
    return 0


def _read_ingest_payload(file_path: str | None) -> object:
    if file_path:
        return json.loads(Path(file_path).read_text(encoding="utf-8"))
    return json.loads(sys.stdin.read() or "{}")


def cmd_ingest(args: argparse.Namespace) -> int:
    orchestrator = AtlasOrchestrator.from_config_path(args.config)
    try:
        payload = _read_ingest_payload(args.file)
        envelopes, projected_records = orchestrator.ingest_runtime_events(payload)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"Invalid ingest payload: {error}") from error
    print(
        json.dumps(
            {
                "status": "recorded",
                "ingested": len(envelopes),
                "projected_feedback_records": len(projected_records),
                "events": [event.to_dict() for event in envelopes],
                "projected_feedback": [record.to_dict() for record in projected_records],
            },
            indent=2,
        )
    )
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    if args.limit <= 0:
        raise SystemExit("--limit must be greater than zero")
    orchestrator = AtlasOrchestrator.from_config_path(args.config)
    payload = orchestrator.build_runtime_ingest_report(session_id=args.session_id, limit=args.limit)
    if args.write_report:
        report_path = orchestrator.feedback_store.write_report("latest_runtime_ingest_audit.json", payload)
        payload = {"report_path": str(report_path), **payload}
    print(json.dumps(payload, indent=2))
    return 0


def cmd_evolve(args: argparse.Namespace) -> int:
    orchestrator = AtlasOrchestrator.from_config_path(args.config)
    report, path = orchestrator.pipeline.run()
    print(json.dumps({"report_path": str(path), **report.to_dict()}, indent=2))
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    orchestrator = AtlasOrchestrator.from_config_path(args.config)
    report_path = orchestrator.feedback_store.reports_dir / "latest_evolution_report.json"
    if report_path.exists():
        report = EvolutionReport.from_dict(json.loads(report_path.read_text(encoding="utf-8")))
    else:
        report, _ = orchestrator.pipeline.run()
    changed = orchestrator.pipeline.promote_approved(report)
    print(json.dumps({"promoted_files": [str(path) for path in changed]}, indent=2))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    orchestrator = AtlasOrchestrator(config)
    print(
        f"Serving Atlas Evolution proxy on http://{config.runtime.host}:{config.runtime.port}",
        flush=True,
    )
    run_server(orchestrator)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command_map = {
        "init": cmd_init,
        "skills": cmd_skills,
        "route": cmd_route,
        "feedback": cmd_feedback,
        "ingest": cmd_ingest,
        "inspect": cmd_inspect,
        "evolve": cmd_evolve,
        "promote": cmd_promote,
        "serve": cmd_serve,
    }
    return command_map[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
