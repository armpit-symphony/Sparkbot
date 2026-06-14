# Sparkbot LIMA Consumer Proof Packet

Date: 2026-06-14
Source repo: `sparkpit-labs/Sparkbot`
Branch: `proof-sparkbot-shell-lima-consumer-packet`
Packet intent: Evidence summary for LIMA-AI-OS API freeze review of the public Sparkbot shell

## 1) Current Sparkbot status

Sparkbot in this repo is a production-oriented fullstack shell with real runtime behavior:

- Runtime architecture: FastAPI backend + React/TanStack frontend.
- Primary surfaces are active and API-backed (`/dm`, `/meeting/$roomId`, `/workstation`, `/command-center`, `/controls`, `/spine`, `/` dashboard).
- LIMA-AI-OS runtime is not wired in this branch.
- LIMA-specific bridging to robotics / broader office systems is intentionally not in this scope.

What is already in place is behavior-reference quality for a first shell candidate, not a completed LIMA contract runtime.

## 2) What works today

- **Chat / room conversation**:
  - `frontend/src/routes/dm.tsx` and `frontend/src/pages/SparkbotDmPage.tsx`.
  - API-backed message endpoints and streaming in `backend/app/api/routes/chat/rooms.py`.
- **Workstation / model configuration**:
  - `frontend/src/routes/workstation.tsx`.
  - model seat and route surfaces in `backend/app/services/model_seats.py`.
- **Round Table meeting manager**:
  - `frontend/src/routes/meeting.$roomId.tsx` + `frontend/src/pages/MeetingRoomPage.tsx`.
  - meeting lifecycle and artifacts via backend chat/room routes.
- **Command center**:
  - `frontend/src/routes/command-center.tsx`.
  - routing/profile controls and operational settings from `frontend/src/lib/sparkbotControls.ts`.
- **Guardian and pending approvals**:
  - approval lifecycle in `frontend/src/routes/_layout/index.tsx` and `backend/app/services/guardian/policy.py`.
  - pending approval persistence in `backend/app/services/guardian/pending_approvals.py`.
- **Audit/spine queue/state**:
  - `frontend/src/routes/_layout/spine.tsx`, `frontend/src/lib/spine.ts`.
  - backend spine and dashboard route layers (`backend/app/services/guardian/spine.py`, `backend/app/api/routes/chat/dashboard.py`).
- **Tool/connector call channels**:
  - tool calls via `backend/app/api/routes/chat/tools.py`, MCP bridge patterns in `backend/app/api/routes/chat/mcp.py`.
- **History and note flow**:
  - meeting notes, artifacts, reminders, and summary flows in `frontend/src/pages/MeetingRoomPage.tsx` + `backend` room endpoints.

## 3) What is mocked / placeholder / incomplete / missing

- **Mocked or staged for now**
  - Robo preview and non-shipping robotics command language still appears as a bounded product teaser in several UX places.
  - External connector flows remain high-variance across deployments and are not normalized as LIMA contracts in this branch.
  - Some runtime endpoints are not exposed as explicit LIMA envelope objects yet.
- **Missing for LIMA API freeze intake**
  - `ConsumerRequest` intake endpoint in the shell.
  - Shared `HumanInput` schema and LIMA intake transform layer.
  - `CandidatePreview` publish API.
  - `RuntimeStateSnapshot` contract serializer from shell surfaces.
  - Explicit `GuardianDecision` object handoff to LIMA runtime.
  - Runtime contract adapter for `TaskIntent` / `TypedIntentEnvelope` admission.
  - Stable machine-only payload contract for cross-surface event export.
- **Missing by policy in this phase**
  - live LIMA runtime export import path.
  - LIMA-validated execution authority on this branch.

## 4) Human input surfaces that can feed LIMA

The following UI surfaces currently produce bounded operator intent that can be normalized to `HumanInput`:

- **DM/Room compose input**: message text, model selection hints, attachment metadata.
  - `frontend/src/components/chat/ChatInput.tsx`
  - `frontend/src/pages/SparkbotDmPage.tsx`
- **Workstation station controls**: desk seat mappings, mode selectors, route labels.
  - workstation page and panels under `frontend/src/pages/WorkstationPage.tsx`.
  - `frontend/src/config/workstationStations.ts`
- **Command center controls**: profile choice, enablement toggles, security posture.
  - `frontend/src/routes/command-center.tsx`
  - `frontend/src/components/CommandCenter/*`
- **Meeting manager flow**: phase progression, assignee, artifact and action intents.
  - `frontend/src/routes/meeting.$roomId.tsx`
  - `frontend/src/pages/MeetingRoomPage.tsx`
- **Guardian/task controls**: approve/deny, confirm/deny queue operations.
  - `frontend/src/routes/_layout/index.tsx`
  - `backend/app/services/guardian/pending_approvals.py`
- **Connector / channel setup fields**:
  - settings and config surfaces where source channels are declared.

## 5) Chat / Workstation / Round Table / model-seat surfaces

### Chat

- Route: `/dm`
- Current behavior: streaming chat with model output and room/thread context.
- LIMA consumption readiness: can be reduced to `TaskIntent` objects, but current route returns Sparkbot-native payload shapes.

### Workstation

- Route: `/workstation`
- Current behavior: station status, model seat overview, quick command controls.
- LIMA consumption readiness: good structural surface for occupancy, seat state, and posture readout.

### Round Table

- Route: `/meeting/$roomId`
- Current behavior: hosted meeting state, assignments, artifacts, and phase state transitions.
- LIMA consumption readiness: good surface for intent extraction and history serialization once envelope mapping exists.

### Model-seat / command surfaces

- Route: `/command-center`
- Current behavior: operational controls and profile routing inputs.
- LIMA consumption readiness: candidate source for `modelSeat`, `providerRoute`, and safety postures.

## 6) Memory, note, audit, event, and history

- **Memory/notes**: meeting notes and memory-like summaries exist with persistence tied to backend room/deployment model.
- **History**:
  - `backend/app/api/routes/chat/dashboard.py` and `backend/app/services/guardian/spine.py` expose queue/event state.
  - frontend surfaces events in `_layout/index.tsx` and `_layout/spine.tsx`.
- **Audit**:
  - durable events are present for task status, guardrail outcomes, and approvals.
  - no single canonical LIMA audit spine envelope yet in this branch.
- **History surfaces**
  - Dashboard state and recent spine events are currently UI-rendered from endpoint data.

## 7) Guardian / approval UX

- Sparkbot has real approval surfaces already:
  - policy decisions (`allow`, `confirm`, `deny`, `privileged`, `privileged_reveal`).
  - approval queue and action routes in chat dashboard.
- LIMA requirement gap:
  - must not treat Sparkbot policy objects as LIMA `GuardianDecision` in this phase.
  - LIMA must own runtime-boundary decision semantics through its own envelope and persistence.
- Presently, all high-risk actions are policy-checked by Sparkbot paths, but this is not equal to LIMA contract enforcement.

## 8) Provider / model routing surfaces

- `backend/app/api/routes/chat/llm.py` and provider route service paths already emit routing metadata.
- Frontend provider controls are present in command center and runtime settings.
- This is source-backed Sparkbot model routing behavior; LIMA runtime routing is not yet wired.
- For LIMA intake, provider calls and route outcomes are useful as fixture/reference until mapped through intake contracts.

## 9) Tool-call or action surfaces

- Shell-call style actions are active in Sparkbot backend:
  - model actions, room tooling, reminders, approvals, terminal/connector-capable paths.
- For LIMA freeze decision, all of these must be considered `blocked` unless they pass a LIMA contract adapter and explicit intent envelope checks.
- No live connection to LIMA executor is present in this branch.

## 10) Protected categories that must remain Guardian-gated

For any LIMA-first migration, these remain non-authoritative until runtime gates are explicit:

- Connector sends, network egress, channel writes.
- Provider calls and model routing dispatch.
- Shell command/terminal actions.
- Browser/automation tool writes/clicks/fills.
- Secret capture and credential disclosure flows.
- File mutation / upload in mutable contexts.
- Robot/IoT physical execution.
- Memory writeback and memory import/export beyond explicit LIMA policy.
- Audit integrity persistence and rollback log ownership.

## 11) Current routes / components / services that can map into LIMA contracts

- `frontend/src/routes/dm.tsx` -> chat surface
- `frontend/src/routes/workstation.tsx` -> workstation state surface
- `frontend/src/routes/meeting.$roomId.tsx` -> meeting intent surface
- `frontend/src/routes/command-center.tsx` -> seat/profile/runtime config surface
- `frontend/src/routes/controls.tsx` -> control/action surface
- `frontend/src/routes/_layout/spine.tsx` and `frontend/src/lib/spine.ts` -> audit/queue event surface
- `backend/app/api/routes/chat/rooms.py` -> room lifecycle and message state
- `backend/app/services/model_seats.py` -> seat/model/provider mapping
- `backend/app/services/guardian/policy.py` -> current policy decision logic (reference only)
- `backend/app/services/guardian/spine.py` -> durable queue/event source (reference only)
- `backend/app/api/routes/chat/mcp.py` and `tools.py` -> action interface reference

## 12) Proposed LIMA vocabulary mapping

Allowed mock-safe active states for this packet:

- `preview_only`
- `explain_plan`
- `blocked`
- `deferred`

Each proposal includes an `embodiment_profile`.

### A. Workstation state

```json
{
  "consumer_request": { "type": "ConsumerRequest", "request_type": "workstation_state_read" },
  "intent": { "type": "TypedIntentEnvelope", "intent_type": "workstation_read" },
  "candidate": {
    "type": "CandidatePreview",
    "active_state": "preview_only",
    "embodiment_profile": {
      "embodiment_id": "sparkbot-public-workstation",
      "embodiment_type": "text_only",
      "physical_world_target": false,
      "emergency_stop_vocabulary_only": true
    },
    "payload": "workstation cards, station metadata, desk-level posture"
  },
  "runtime_state_snapshot": "workstation overview and active surface flags"
}
```

### B. Chat command

```json
{
  "consumer_request": { "type": "ConsumerRequest", "request_type": "chat_intent_preview" },
  "intent": { "type": "TaskIntent", "task_type": "operator_message_preview" },
  "candidate": {
    "type": "CandidatePreview",
    "active_state": "explain_plan",
    "embodiment_profile": {
      "embodiment_id": "sparkbot-text-chat",
      "embodiment_type": "text_only",
      "physical_world_target": false,
      "emergency_stop_vocabulary_only": true
    },
    "payload": "draft text, context hints, room_id, selected model seat"
  }
}
```

### C. Meeting / Round Table

```json
{
  "consumer_request": { "type": "ConsumerRequest", "request_type": "meeting_plan" },
  "intent": { "type": "TaskIntent", "task_type": "meeting_phase_plan" },
  "candidate": {
    "type": "CandidatePreview",
    "active_state": "explain_plan",
    "embodiment_profile": {
      "embodiment_id": "sparkbot-text-roundtable",
      "embodiment_type": "text_only",
      "physical_world_target": false,
      "emergency_stop_vocabulary_only": true
    },
    "payload": "phase, assignments, artifact draft, chair instructions"
  }
}
```

### D. Model-seat setup

```json
{
  "consumer_request": { "type": "ConsumerRequest", "request_type": "model_seat_config" },
  "intent": { "type": "TypedIntentEnvelope", "intent_type": "seat_configuration" },
  "candidate": {
    "type": "CandidatePreview",
    "active_state": "blocked",
    "embodiment_profile": {
      "embodiment_id": "sparkbot-text-seat-config",
      "embodiment_type": "text_only",
      "physical_world_target": false,
      "emergency_stop_vocabulary_only": true
    },
    "payload": "provider selection, seat mappings, guardrail flags"
  }
}
```

### E. Memory/context payload

```json
{
  "consumer_request": { "type": "ConsumerRequest", "request_type": "memory_context_read" },
  "intent": { "type": "TaskIntent", "task_type": "memory_context_preview" },
  "candidate": {
    "type": "CandidatePreview",
    "active_state": "deferred",
    "embodiment_profile": {
      "embodiment_id": "sparkbot-text-memory-context",
      "embodiment_type": "text_only",
      "physical_world_target": false,
      "emergency_stop_vocabulary_only": true
    },
    "payload": "note summary, artifact excerpts, meeting history snapshots"
  }
}
```

### F. Guardian and approval status

```json
{
  "consumer_request": { "type": "ConsumerRequest", "request_type": "guardian_posture_read" },
  "intent": { "type": "TaskIntent", "task_type": "guardian_posture_preview" },
  "candidate": {
    "type": "CandidatePreview",
    "active_state": "preview_only",
    "embodiment_profile": {
      "embodiment_id": "sparkbot-text-guardian",
      "embodiment_type": "text_only",
      "physical_world_target": false,
      "emergency_stop_vocabulary_only": true
    },
    "payload": "policy mode, approval mode, confirm queue counts"
  }
}
```

### G. Action and connector preview

```json
{
  "consumer_request": { "type": "ConsumerRequest", "request_type": "action_bridge_read" },
  "intent": { "type": "TypedIntentEnvelope", "intent_type": "connector_or_tool_preview" },
  "candidate": {
    "type": "CandidatePreview",
    "active_state": "deferred",
    "embodiment_profile": {
      "embodiment_id": "sparkbot-text-connectors-tools",
      "embodiment_type": "text_only",
      "physical_world_target": false,
      "emergency_stop_vocabulary_only": true
    },
    "payload": "connector capability labels, tool names, tool args summary"
  }
}
```

## 13) Verdict on allowed statuses

- `preview_only`: status surfaces where no execution is triggered in LIMA-safe mode.
- `explain_plan`: routes that can produce recommendation or planning outputs.
- `blocked`: execution-bearing configuration and high-risk pathways.
- `deferred`: capabilities that remain post-freeze scope (not yet admitted to contracts).

## 14) Packet conclusion

Sparkbot is strong behavior-reference evidence for LIMA consumption, but it is **not yet a direct LIMA runtime contract consumer**.
LIMA-AI-OS can treat this as non-binding evidence packet while planning first-party runtime intake adapters and approval schema.
