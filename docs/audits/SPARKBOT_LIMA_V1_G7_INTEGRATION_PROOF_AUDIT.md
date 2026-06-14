# Sparkbot LIMA V1-G7 Integration Proof Audit

Date: 2026-06-14
Repository: `armpit-symphony/Sparkbot`
Branch: `v1-g7-sparkbot-integration-proof-packet`
Source evidence commit: `0f8d059fc5927e3466d269ca5479df4c56b3c06f`

## Audit Verdict

Recommended verdict: `accept_as_static_behavior_reference_evidence_only`.

Sparkbot provides strong source-backed behavior-reference evidence for approvals, Guardian posture, provider/model routing, audit/spine evidence, destructive edit/delete approval posture, and response-state behavior. LIMA must not treat this proof as live LIMA runtime parity.

## Request Gate Answers

| Question | Answer |
| --- | --- |
| Did Sparkbot provide the requested proof packet? | Yes: `docs/proof_packets/SPARKBOT_LIMA_V1_G7_INTEGRATION_PROOF_PACKET.md`. |
| Did Sparkbot provide the requested audit? | Yes: this document. |
| Did Sparkbot provide machine-readable fixture evidence? | Yes: `backend/tests/fixtures/sparkbot_lima_v1_g7_integration_proof_packet.json`. |
| Did Sparkbot run and report validation commands? | To be finalized after branch validation. |
| Did Sparkbot evaluate all required response states? | Yes. |
| Did Sparkbot evaluate packet/kernel status mappings? | Yes. |
| Did Sparkbot preserve haptics as shell-owned? | Yes. |
| Did Sparkbot avoid claiming LIMA owns haptic device behavior? | Yes. |
| Did Sparkbot prove destructive edit/delete requires operator approval or is blocked? | Yes, as Sparkbot behavior-reference evidence. |
| Did Sparkbot classify approval status? | Yes: source-backed Sparkbot runtime enforcement, not LIMA enforcement. |
| Did Sparkbot classify `GuardianDecision` authority? | Yes: Sparkbot has policy decisions; LIMA runtime `GuardianDecision` remains missing. |
| Did Sparkbot classify provider/model routing? | Yes: source-backed Sparkbot runtime routing, not LIMA routing. |
| Did Sparkbot constrain provider/model routing? | Yes, through Sparkbot route context, model seats, secrets/auth posture, Token Guardian route evidence, and audit posture. |
| Did Sparkbot classify audit/evidence lineage? | Yes: source-backed Sparkbot audit/spine evidence, not LIMA audit persistence. |
| Did Sparkbot avoid raw natural-language-to-tool execution shortcuts? | Yes. Tool calls are policy-gated. |
| Did Sparkbot avoid unsafe connector/file/browser/network/device/robotics claims? | Yes. Runtime surfaces are classified as Guardian-gated, preview-only, private-gated, or out of LIMA scope. |
| Did Sparkbot avoid LIMA runtime wiring? | Yes. |
| Did Sparkbot avoid requiring unapproved LIMA runtime exports? | Yes. |
| Did Sparkbot avoid importing/copying Sparkbot code into LIMA? | Yes. |
| Is this acceptable as static shell integration evidence? | Yes. |
| Is this insufficient for live runtime parity? | Yes. |

## State Coverage Audit

Source-backed:

- `received`
- `thinking`
- `preview_ready`
- `blocked`
- `needs_approval`
- `completed`
- `failed_safe`

Docs/fixture-only:

- `deferred`

Missing:

- none

Reasoning:

- `received`, `thinking`, `completed`, and `failed_safe` are backed by chat SSE stream events and frontend streaming state.
- `preview_ready` is backed by policy simulation and MCP explain-plan.
- `blocked` is backed by Guardian deny decisions and blocked meeting/MCP statuses.
- `needs_approval` is backed by persistent approval records, `confirm_required`, `privileged_required`, and dashboard approval flows.
- `deferred` is represented by planned/deferred references and MCP planned status, but not by a dedicated Sparkbot shell response-state label.

## Status Mapping Audit

Required mappings are present:

- `proposed -> preview_only`
- `needs_review -> explain_plan`
- `blocked -> blocked`

Additional mappings are present as reference:

- `completed -> completed`
- `deferred -> deferred`

## Haptics Audit

Sparkbot does not add haptic device behavior in this proof branch. Source search found no `navigator.vibrate` or device vibration implementation in the reviewed source roots.

Audit result:

- shell owns haptics: yes
- LIMA owns haptic device behavior: no
- haptic device behavior added: no
- device haptic command added: no

## Approval And Guardian Audit

Sparkbot has real approval enforcement in its own runtime. Relevant evidence includes:

- Guardian policy action families in `policy.py`
- `decide_tool_use(...)`
- persistent approval storage in `pending_approvals.py`
- `confirm_required` and `privileged_required` events in chat streaming
- dashboard approval approve/deny endpoints
- policy recheck before dashboard-approved execution

LIMA should accept this as Sparkbot behavior-reference evidence only. LIMA should reject any claim that this proves LIMA runtime `GuardianDecision` authority.

## Provider/Model Routing Audit

Sparkbot has real provider/model routing in its own runtime. Relevant evidence includes:

- `VALID_AGENT_ROUTES`
- `get_agent_route_context(...)`
- model-seat provider normalization
- frontend provider/model route resolution
- streaming/fallback helpers
- latency/error recording

LIMA should accept this as provider/model routing reference evidence only. LIMA should reject any claim that this adds LIMA routing or provider/model calls.

## Audit/Evidence Audit

Sparkbot has source-backed audit/evidence paths:

- policy/tool audit entries
- run timeline with audit hashes
- Guardian Spine task/event/approval tables
- approval lifecycle events
- operator queues and lineage UI clients

LIMA should accept this as Sparkbot reference evidence only. LIMA should reject any claim that this adds LIMA audit persistence.

## Safety Boundary Audit

Pass:

- no LIMA runtime behavior added
- no LIMA runtime exports changed
- no LIMA runtime exports required
- no Sparkbot code copied into LIMA
- no Sparkbot import added to LIMA
- no new provider/model calls
- no new approval behavior
- no new connector/file/browser/network/device/robotics behavior
- no production/V1 readiness claim

Risk to preserve:

- Sparkbot has powerful runtime surfaces. LIMA intake must classify them as reference behavior, not inherited LIMA capability.
- Sparkbot has LIMA/Robo-OS bridge references. This packet does not accept those as LIMA-AI-OS runtime wiring.
- `deferred` remains weak as a dedicated shell response-state because Sparkbot has planned/deferred concepts but no dedicated response-state label.

## What LIMA Should Accept

- Sparkbot is the strongest behavior-reference source for approvals, Guardian posture, provider/model routing, audit/spine posture, and shell response feel.
- Sparkbot source supports required V1-G7 response-state coverage except `deferred`, which is docs/fixture-only.
- Sparkbot source supports destructive edit/delete confirmation/elevated approval posture.
- Sparkbot source supports no raw natural-language-to-tool bypass.
- Sparkbot haptic behavior remains shell-owned or absent.

## What LIMA Should Reject

- live LIMA runtime parity
- LIMA approval enforcement
- LIMA `GuardianDecision` authority
- LIMA provider/model routing
- LIMA audit persistence
- LIMA haptic device behavior
- runtime export cleanup approval
- final API freeze
- V1 product readiness
- production readiness

## Follow-Up Requested From Sparkbot

None before static LIMA intake if validation passes.

Future implementation gates should request narrower runtime parity proofs only after LIMA explicitly approves runtime work. The next V1-G7 shell packet should come from `Arc-Bot-shell`.
