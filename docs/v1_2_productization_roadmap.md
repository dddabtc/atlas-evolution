# Atlas Evolution v1.2 Productization Roadmap

## Objective
Turn the current governed evolution control plane into a more complete product surface that operators can actually run, review, hand off, and maintain.

## Priority 1 — Product closeout
These are the most important next steps.

### 1. Stronger handoff chain
- single command to export a complete operator handoff package
- include latest workflow state, relevant reports, proposal snapshots, resume commands, and source artifact references
- make cross-machine / cross-directory replay easier

### 2. Better operator cockpit
- status/dashboard-style command that summarizes:
  - latest ingest state
  - pending review items
  - risky proposals
  - resume pointers
  - last promotion action
- reduce the need to manually inspect multiple report files

### 3. Realer OpenClaw import path
- support additional realistic operator-session shapes
- support more partial session states
- make import/report/review feel like one coherent workflow rather than separate commands

## Priority 2 — Evaluation quality
### 4. Harder promotion gate
- move from purely heuristic evaluator toward benchmark-backed checks
- require stronger evidence before promotion
- make failed/blocked reasons more explicit and easier to diff across runs

### 5. Proposal hygiene and conflict handling
- detect overlapping or conflicting proposal targets
- make supersession / obsolescence first-class
- keep review queues from getting noisy over time

## Priority 3 — Product operations
### 6. Better artifacts for recovery and forensics
- stronger log/index layout
- stable artifact naming
- easier archive/restore flow
- cleaner separation between raw evidence, projected signals, review output, and promotion artifacts

### 7. Packaging and release story
- cleaner install path
- more polished docs
- example operator walkthroughs
- release notes template

## What should still stay out of scope
Until the governance and evaluation story is stronger, keep these out:
- RL / OPD
- cloud training loops
- autonomous self-modification
- automatic deployment into production runtimes

## Desired end state for v1.2
At the end of v1.2, Atlas Evolution should feel like:
- a real operator tool
- easy to inspect
- easy to resume after interruption
- easy to hand off to another human or machine
- conservative by default
- clearly safer and more operationally credible than MetaClaw
