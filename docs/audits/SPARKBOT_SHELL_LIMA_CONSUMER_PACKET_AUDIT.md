# Sparkbot LIMA Consumer Packet Audit

Date: 2026-06-14
Scope: `proof-sparkbot-shell-lima-consumer-packet`
Repository: `sparkpit-labs/Sparkbot`

## 1) Is Sparkbot ready to consume LIMA Runtime today?

**No.** Sparkbot is a live consumer shell and strong behavior reference, but it is not a LIMA-runtime intake target yet.
LIMA API freeze requires explicit contract intake, approval object ownership, and contract-safe action routing that is not yet present in this branch.

## 2) What is missing

- `ConsumerRequest` intake endpoint for LIMA.
- `HumanInput` and `TaskIntent`/`TypedIntentEnvelope` ingestion/validation service.
- `CandidatePreview` publication API in a stable schema.
- `RuntimeStateSnapshot` object for shell state serialization.
- Runtime contract boundary that emits and consumes explicit `GuardianDecision`.
- Canonical no-surprise status contract (`preview_only`, `explain_plan`, `blocked`, `deferred`) across all surfaces.
- LIMA-authenticated execution, queue dispatch, and connector/runtime action handoff.

## 3) What data shape can Sparkbot provide safely now

Sparkbot can provide structured evidence in these domains without enabling execution:

- Route-level and component-level surface states (routes + payload shapes).
- Conversation/message metadata and room lifecycle states.
- Dashboard, guardrail, and approval queue state from spine summaries.
- Meeting / roundtable state and artifact metadata.
- Model-seat and provider route configuration views.
- History and event lists exposed through dashboard and spine endpoints.

This is suitable as **consumer preview input only** until contract adapters exist.

## 4) What runtime boundary should LIMA expose first for Sparkbot

LIMA should expose a minimal read-write boundary in this order:

1. **Consumer intake boundary**
   - authenticate shell request context
   - validate `ConsumerRequest`
2. **Intent transform**
   - map shell intent into `TaskIntent`/`TypedIntentEnvelope`
   - emit `CandidatePreview` in allowed safe states
3. **Guarded state projection**
   - return `RuntimeStateSnapshot` plus immutable boundary flags
   - emit `GuardianDecision` only for state transitions beyond preview
4. **Action handoff (gated)**
   - allow runtime actions only after explicit approval and contract match

## 5) What should remain shell-owned vs LIMA-owned

### Shell-owned (keep in Sparkbot now)

- Route UI and form controls.
- Source-facing render logic and status copy.
- Localized data adapters converting backend responses to surface cards.
- Human input capture flows before intent transform.

### LIMA-owned (must own for API freeze)

- `ConsumerRequest` validation and authentication binding.
- Intent normalization and policy/decision objects.
- `CandidatePreview`, `RuntimeStateSnapshot`, and boundary state model.
- `GuardianDecision` authority and audit persistence semantics.
- Actual dispatch and tool/provider invocation contracts.

## 6) Top blockers before Sparkbot-first integration

1. No shared contract adapter layer for intent intake and preview emission.
2. No canonical surface-to-contract mapping table in code for all primary routes.
3. Approval semantics are Sparkbot-native and not yet represented as first-class LIMA `GuardianDecision`.
4. Existing high-risk actions still use Sparkbot runtime paths directly.
5. No stable contract fixture set for LIMA-facing action outcomes in this branch.

## 7) Minimum parity tests LIMA should require

Before accepting Sparkbot as a LIMA-first shell, minimum parity tests should include:

1. **Route ingest test**
   - `/dm`, `/workstation`, `/meeting/$roomId`, `/command-center`, `/controls` can each generate a validated `ConsumerRequest`.
2. **Intent normalization test**
   - all generated intents map to `TaskIntent`/`TypedIntentEnvelope` shape.
3. **Candidate status test**
   - candidate statuses are restricted to `preview_only`, `explain_plan`, `blocked`, `deferred`.
4. **Guardian boundary test**
   - no high-risk path executes without explicit LIMA `GuardianDecision`.
5. **Preview integrity test**
   - `Deferred` and `blocked` states remain non-dispatching by default.
6. **Audit lineage test**
   - state snapshots and decisions carry source labels and timestamps suitable for runtime traceability.
7. **Runtime ownership test**
   - no runtime action payload bypasses LIMA contract boundary.

## 8) Evidence used for this packet

- `frontend/src/routes/dm.tsx`
- `frontend/src/routes/workstation.tsx`
- `frontend/src/routes/command-center.tsx`
- `frontend/src/routes/controls.tsx`
- `frontend/src/routes/meeting.$roomId.tsx`
- `frontend/src/routes/_layout/index.tsx`
- `frontend/src/routes/_layout/spine.tsx`
- `frontend/src/lib/sparkbotControls.ts`
- `frontend/src/lib/spine.ts`
- `backend/app/services/model_seats.py`
- `backend/app/services/guardian/policy.py`
- `backend/app/services/guardian/spine.py`
- `backend/app/services/guardian/pending_approvals.py`
- `backend/app/api/routes/chat/rooms.py`
- `backend/app/api/routes/chat/dashboard.py`
- `backend/app/api/routes/chat/llm.py`
- `backend/app/api/routes/chat/tools.py`
- `backend/app/api/routes/chat/mcp.py`

## 9) Audit conclusion

Sparkbot has substantial evidence for approvals, memory/state history, routing surfaces, and action surfaces.
It is appropriate for LIMA-AI-OS to use as a consumer reference packet only.
It is **not yet** a live LIMA runtime consumer.

Recommended next step:

Create and gate the LIMA intake adapter on top of these surfaces, then rerun parity tests above before declaring API freeze readiness.

## 10) Post-intake status (V1-G12 LIMA AI OS)

- LIMA AI OS side accepted this packet as static reference for intake planning.
- LIMA acceptance branch and commit: `v1-g12-sparkbot-lima-consumer-proof-intake` /
  `0ec8d230d5bd9ff56432e206adc7a5c147397cf8`.
- Runtime API freeze remains not approved.
- API status remains `CANDIDATE_ONLY` for this boundary.
