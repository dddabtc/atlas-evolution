# Changelog

All notable changes to Atlas Evolution will be documented in this file.

The format is inspired by Keep a Changelog and this project follows a practical, operator-focused version history.

## [Unreleased]

### Planned
- tighter operator cockpit / status surface
- stronger handoff packaging
- harder promotion gates
- more complete OpenClaw operator import coverage

## [v1.1.0] - 2026-03-13

### Added
- typed runtime event schema and local runtime ingest flow
- CLI ingest from file or stdin
- local HTTP ingest endpoint
- raw inbound envelope ledger plus projected feedback ledger
- raw → projected audit inspection surface
- formal OpenClaw/Atlas contract
- explicit `openclaw-import` command for realistic OpenClaw operator session artifacts
- JSON / markdown operator evidence reports
- governance metadata for readiness, risk, and rollback context
- operator review queue with ready / risky / rollback-sensitive / blocked buckets
- reviewable promotion artifacts and dry-run support
- restart-safe workflow state with `resume` command
- replayable operator handoff bundles
- v1.1 milestone document
- v1.2 productization roadmap document

### Changed
- README rewritten to better explain what Atlas Evolution is, who it is for, and how to use it
- Chinese README updated to match the current v1.1 product surface
- project framing clarified as a governed local evolution system, not an autonomous self-improving agent

### Notes
- v1.1 is intentionally local-only and conservative
- v1.1 excludes RL, OPD, cloud training, and blind self-modification
- the main value of v1.1 is operator-grade governance, auditability, recovery, and handoff

## [v1.0.0] - 2026-03-13

### Added
- local scaffold for Atlas Evolution
- TOML config loading
- deterministic skill retrieval
- append-only feedback logging
- proposal generation pipeline
- offline evaluation gate
- minimal local proxy/orchestration surface
