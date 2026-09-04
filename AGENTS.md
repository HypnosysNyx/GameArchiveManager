# GameArchiveManager agent policy

These instructions apply to the entire repository.

## Canonical workspace

- Use `C:\Users\<redacted>\Documents\GameArchiveManager` as the only project entry. It is a junction to this Git working tree.
- Read `START_HERE.md` before doing any project work. It is the agent-neutral continuation entry and records the current handoff state and next action.
- Do not create or resume another GameArchiveManager clone, worktree, agent workspace, or version-suffixed copy unless the user explicitly requests one.
- Historical Grok, Codex, Antigravity, evidence, and legacy-copy material is centralized under `.project_archive/`. Treat it as read-only reference material, not as an active checkout.
- Keep new product code, tests, and authoritative documentation in this main working tree. Put local VM evidence in `.vm_gate/` and handoff snapshots in `handoff_output/` rather than creating another project directory.
- Read `docs/WORKSPACE_MAP.md` when locating historical material.

## Coordination

- Inspect `git status --short` before editing and preserve unrelated user or agent changes.
- Never allow two agents to edit the same files concurrently. Assign non-overlapping ownership if the user explicitly asks for parallel agent work.
- Handoffs must name the canonical path, changed files, verification commands, and unresolved risks. Do not refer another agent to an archived checkout as its working directory.
- Do not move material back out of `.project_archive/` to recreate an old workspace. Copy only the specific information that is intentionally being promoted into the main project.

## Project safety gates

- Do not push, merge, rebase, reset, clean, tag, publish a release, upload artifacts, or modify repository settings without the user's clear authorization for that action.
- Do not overwrite or delete source archives, weaken CRC/SHA-256/path-boundary checks, persist plaintext passwords, or treat skipped tests as clean-VM evidence.
- Keep the application identified as the published `0.1.0 Release`; historical RC documents remain historical records and must not be presented as the current download.
- Before release-related changes, read `project_state.json`, `docs/CURRENT_STATUS.md`, `docs/KNOWN_ISSUES.md`, and `docs/RC_SMOKE_TEST.md`.
- For code changes, run relevant focused tests and then the full suite: `py -B -m unittest discover -s tests -p "test_*.py" -v`.
