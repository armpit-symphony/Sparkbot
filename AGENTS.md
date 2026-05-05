# AGENTS.md — Sparkbot

## Product context

Sparkbot is the public/R&D assistant app for SparkPit Labs. It includes main chat, workstation, roundtable meetings, model/provider switching, Guardian approvals, and local/server packaging.

This repository is live-product sensitive. Do not make broad rewrites unless explicitly requested.

## Current priority

Public release stabilization.

The main blocker is shared durable memory:

- Main chat memory must persist.
- Roundtable meetings must retrieve relevant main chat memory.
- Roundtable summaries must write back to shared memory.
- Main chat must later retrieve roundtable outcomes.
- Server mode and Windows/local packaged mode should behave consistently.

## Architecture direction

Sparkbot is the product shell.

LIMA-Guardian-Suite is the long-term Guardian OS layer.

Do not prematurely move all logic into LIMA. First stabilize Sparkbot behind a small shared memory contract, then make that contract extractable.

Preferred direction:

Sparkbot UI / routes
→ Sparkbot adapter/service layer
→ Shared memory contract
→ existing storage now
→ LIMA Guardian OS later

## Rules

- Read existing docs and handoff files before editing.
- Prefer small, reversible changes.
- Do not patch isolated bugs without first checking whether the change affects shared memory, Guardian, model routing, packaging, or approvals.
- Do not create duplicate memory paths.
- Do not break server mode to fix Windows mode.
- Do not break Windows/local mode to fix server mode.
- Add tests for any behavior change.
- Update docs when architecture changes.
- Keep commits scoped and explain verification.

## Required checks

When applicable, run the smallest relevant tests first. If changing backend behavior, run backend tests. If changing frontend behavior, run frontend build/tests. If packaging or Windows/local mode changes, verify the local-mode path explicitly.

If tests cannot be run, document why.
