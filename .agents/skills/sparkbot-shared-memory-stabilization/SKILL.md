# Sparkbot Shared Memory & Guardian OS Stabilization Skill

Use this skill when working on Sparkbot memory, roundtable meetings, Guardian integration, model switching, local/server packaging drift, or public release stabilization.

## Mission

Stabilize Sparkbot for public launch without making the codebase more brittle.

The key product requirement:

A user can talk to Sparkbot in main chat, start or join a roundtable meeting, have that roundtable use relevant prior Sparkbot memory, then return to main chat and have Sparkbot know what happened in the meeting.

## Mental model

Sparkbot is the app/product shell.

LIMA-Guardian-Suite is the long-term Guardian OS layer.

For now, do not perform a large extraction. First create or strengthen a stable Sparkbot-side contract that can later be backed by LIMA.

Target shape:

- Main chat
- Roundtable meetings
- Workstation
- Agent sessions
- Guardian approvals

should all use one shared durable memory/event contract.

## Before editing

First inspect and document:

1. Main chat persistence path.
2. Main chat context retrieval path.
3. Roundtable message persistence path.
4. Roundtable context retrieval path.
5. Meeting summary/finalization path.
6. Workstation/chat bridge path.
7. Guardian/Memory/Spine modules currently used.
8. Storage backends involved.
9. Model/provider config paths.
10. Server-mode versus Windows/local-mode differences.

Do not assume the bug is local to the file mentioned by the user.

## Preferred implementation pattern

Prefer a small backend service or adapter such as:

- SharedMemoryAdapter
- MemoryService
- ConversationMemoryService
- GuardianMemoryBridge

The contract should expose a small set of operations:

- save_message
- save_event
- retrieve_context
- summarize_thread
- attach_memory_to_project
- list_recent_context

Every chat-like surface should call the same contract.

## Acceptance requirements

For any memory change, add or update tests proving:

1. Main chat writes memory.
2. Main chat can retrieve prior memory.
3. Roundtable can retrieve relevant main chat memory.
4. Roundtable summary writes back to shared memory.
5. Main chat can retrieve roundtable summary later.
6. Existing storage behavior is preserved unless intentionally migrated.

For model/provider changes, prove:

1. Primary model selection works.
2. Model switching works.
3. Missing provider keys fail gracefully.
4. Server and Windows/local mode do not diverge unnecessarily.

## Guardrails

Do not:

- Add a second independent memory system.
- Hardcode memory into frontend state only.
- Hide persistence failures.
- Rewrite roundtable or chat wholesale.
- Move everything into LIMA in one PR.
- Change unrelated UI while fixing memory.
- Change packaging and runtime behavior in the same PR unless required.
- Remove existing Guardian code without a compatibility plan.
- Commit secrets, keys, tokens, or local machine paths.

## Recommended PR sequence

### PR 1 — Read-only inventory

Create or update:

docs/architecture/memory_surface_inventory.md

Include:

- Current memory flow diagram.
- File-by-file map.
- Which surfaces share memory.
- Which surfaces are isolated.
- Where roundtable loses main chat context.
- Where meeting outcomes should be written back.
- Risks.
- Proposed minimal adapter interface.

No runtime behavior changes.

### PR 2 — Shared memory contract

Add the shared adapter/service with tests.

Keep existing storage if possible.

Use a feature flag if needed:

SPARKBOT_SHARED_MEMORY_ENABLED=true

### PR 3 — Roundtable bridge

Wire roundtable retrieval and summary writeback through the shared contract.

Keep changes small.

### PR 4 — Main chat verification

Make main chat retrieval and persistence use the same contract.

Add regression tests.

### PR 5 — Windows/local parity

Verify packaged/local mode uses the same backend memory and model-switching behavior as server mode.

## Definition of done

A change is not done until:

- Relevant tests pass.
- Memory path is documented.
- No duplicate memory path was introduced.
- Server/local mode impact is stated.
- Handoff/logbook is updated if this repo uses one.
- The commit message describes the actual scope.
