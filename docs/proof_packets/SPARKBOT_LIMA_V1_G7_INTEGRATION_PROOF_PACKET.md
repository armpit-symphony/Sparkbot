# Sparkbot LIMA V1-G7 Integration Proof Packet

Date: 2026-06-14
Repository: `armpit-symphony/Sparkbot`
Proof branch: `v1-g7-sparkbot-integration-proof-packet`
Source evidence branch: `public-release-final-cleanup-assessment`
Source evidence commit: `0f8d059fc5927e3466d269ca5479df4c56b3c06f`
Proof commit: `reported-by-git-after-commit`

## Scope

This packet answers the LIMA-AI-OS `V1-G7` first-shell integration proof request for Sparkbot.

It is docs/tests/fixtures-only. It does not add Sparkbot runtime behavior, LIMA runtime wiring, LIMA imports, LIMA export requirements, provider/model calls, Guardian policy changes, approval behavior, persistence behavior, haptic device behavior, connector behavior, file mutation, browser/network/device/robotics behavior, or physical-world behavior.

Sparkbot is evaluated here as the R&D behavior reference for:

- shell response states
- Guardian policy and approval posture
- provider/model routing posture
- audit/evidence posture
- destructive edit/delete approval expectations
- connector/tool/browser/network/robotics boundaries

LIMA may accept this packet as static shell evidence only. It must not be treated as live LIMA runtime parity.

## LIMA Request Inputs Reviewed

- `docs/V1_G7_FIRST_SHELL_INTEGRATION_PROOF_REQUEST.md`
- `docs/V1_G7_FIRST_SHELL_INTEGRATION_PROOF_AUDIT_CRITERIA.md`
- `tests/fixtures/runtime_extraction/v1_g7_first_shell_integration_proof_request.json`
- `docs/V1_G7_SPARKBOT_SHELL_INTEGRATION_PROOF_INTAKE_CLOSEOUT.md`

## Sparkbot Files Reviewed

- `AGENTS.md`
- `docs/capabilities.md`
- `docs/PUBLIC_RELEASE_CAPABILITY_MODEL.md`
- `docs/guardian-spine.md`
- `docs/LIMA_RUNTIME_ALIGNMENT_NOTES.md`
- `backend/app/services/guardian/policy.py`
- `backend/app/services/guardian/pending_approvals.py`
- `backend/app/services/guardian/spine.py`
- `backend/app/services/model_seats.py`
- `backend/app/api/routes/chat/rooms.py`
- `backend/app/api/routes/chat/llm.py`
- `backend/app/api/routes/chat/dashboard.py`
- `backend/app/api/routes/chat/tools.py`
- `backend/app/api/routes/chat/mcp.py`
- `backend/app/services/mcp_registry.py`
- `backend/app/services/mcp_runs.py`
- `frontend/src/pages/SparkbotDmPage.tsx`
- `frontend/src/components/chat/MessageBubble.tsx`
- `frontend/src/components/chat/ChatWindow.tsx`
- `frontend/src/lib/sparkbotControls.ts`
- `frontend/src/lib/mcpRegistry.ts`
- `frontend/src/lib/spine.ts`

## Validation

Validation performed for this proof branch:

- `cmd /c "python3 --version || python --version"`: passed, Python 3.12.10, with known trailing Windows environment message.
- `cmd /c "python3 -m pytest -q tests/test_sparkbot_lima_v1_g7_integration_proof_packet.py || python -m pytest -q tests/test_sparkbot_lima_v1_g7_integration_proof_packet.py"`: passed, 9 passed in 0.05s, with known trailing Windows environment message.
- `cmd /c "python3 -m json.tool tests/fixtures/sparkbot_lima_v1_g7_integration_proof_packet.json || python -m json.tool tests/fixtures/sparkbot_lima_v1_g7_integration_proof_packet.json"`: passed, JSON parsed and printed, with known trailing Windows environment message.
- `git diff --check`: passed, clean.

## What Sparkbot Proves

Sparkbot proves source-backed behavior-reference evidence for the LIMA V1 target:

- It has in-band message receipt, token streaming, typing/progress indicators, done events, and error events.
- It has Guardian policy actions for `allow`, `confirm`, `deny`, `privileged`, and `privileged_reveal`.
- It stores pending approvals and emits approval lifecycle events.
- It surfaces pending approvals through dashboard flows and can approve or deny them.
- It rechecks policy before dashboard approval execution and refuses non-allow/non-confirm decisions.
- It supports provider/model route selection across OpenRouter, local, OpenAI, OpenAI Codex subscription, Claude subscription, Anthropic, Google, Groq, MiniMax, xAI, and local AI.
- It records model latency/errors and route context.
- It exposes policy simulation and MCP explain-plan paths that preview plan/policy results without executing actions.
- It records audit/log/timeline/spine evidence for policy and tool events.
- It requires confirmation or privileged paths for high-risk writes, sends, service control, shell writes, credential reveal/write, Vault deletion, and destructive actions.
- It keeps public Robo behavior preview-only by default and requires explicit private gates for private bridge execution.

## What Sparkbot Does Not Prove For LIMA

This packet does not prove:

- live LIMA runtime output consumption
- LIMA runtime wiring
- LIMA `GuardianDecision` authority
- LIMA approval enforcement
- LIMA provider/model routing
- LIMA audit persistence
- LIMA haptic device behavior
- LIMA shell rendering
- LIMA runtime export cleanup readiness
- final LIMA API freeze readiness
- V1 product readiness
- production readiness

Sparkbot has its own runtime behavior. LIMA may use it as reference evidence, but this proof does not migrate or wire that behavior into LIMA.

## Required Shell Response States

| State | Sparkbot evidence classification | Evidence |
| --- | --- | --- |
| `received` | source-backed | `rooms.py` emits `human_message`; chat stream stores user messages. |
| `thinking` | source-backed | `rooms.py` streams `token`; `SparkbotDmPage.tsx`, `MessageBubble.tsx`, and `ChatWindow.tsx` render `isStreaming` / typing indicators. |
| `preview_ready` | source-backed | `guardian_simulate_policy`, `/mcp/explain-plan`, and MCP run records preview policy/plan results without execution. |
| `blocked` | source-backed | Guardian policy can return `deny`; meeting/roundtable statuses include `blocked`; MCP runs include `blocked`. |
| `needs_approval` | source-backed | `confirm_required` / `privileged_required`, persistent pending approvals, dashboard approval actions, and `needs_approval` meeting statuses. |
| `completed` | source-backed | SSE `done` events, `execution_status="success"`, and completed MCP run statuses. |
| `failed_safe` | source-backed | SSE `error` events, denied tool execution status, rejected guardrail status, and humanized provider errors. |
| `deferred` | docs/fixture-only | Sparkbot has deferred/planned work references and planned MCP run status, but no dedicated shell response-state named `deferred`. |

## Packet Status And Kernel Mapping

Accepted V1-G7 packet statuses:

- `preview_only`
- `explain_plan`
- `blocked`
- `completed`
- `deferred`

Kernel status mapping:

- `proposed -> preview_only`
- `needs_review -> explain_plan`
- `blocked -> blocked`
- `completed -> completed`
- `deferred -> deferred`

The additional `completed` and `deferred` mappings are reference mappings only and do not change the required LIMA mappings.

## Haptics Ownership

- Shell owns haptics: yes.
- LIMA owns haptic device behavior: no.
- Sparkbot haptic device behavior added by this branch: no.
- Device vibration command added by this branch: no.
- Source search found no `navigator.vibrate` or device vibration implementation in Sparkbot source roots reviewed.

For LIMA V1, haptics remain shell-owned rendering/device behavior. LIMA may define non-device haptic intent metadata only.

## Destructive Edit/Delete Approval

Sparkbot source and docs support the V1 destructive edit/delete posture:

- `docs/PUBLIC_RELEASE_CAPABILITY_MODEL.md` says file edits/deletes, external sends, browser writes, service control, credential writes/reveals, terminal writes, and Git mutations require confirmation.
- `docs/capabilities.md` says dangerous/destructive actions ask yes/no before execution, including deletes and risky writes.
- `policy.py` returns `confirm`, `privileged`, `privileged_reveal`, or `deny` for high-risk and destructive tools.
- `policy.py` explicitly says write-like shell commands require confirmation before execution.
- Vault deletion requires break-glass and explicit confirmation.

This proves Sparkbot behavior-reference alignment. It does not prove LIMA runtime enforcement.

## Approval And GuardianDecision Classification

Sparkbot has real source-backed approval and policy-decision behavior in its own runtime:

- `PolicyAction = Literal["allow", "confirm", "deny", "privileged", "privileged_reveal"]`
- `decide_tool_use(...)` selects policy outcomes.
- `pending_approvals.py` stores, consumes, discards, and lists pending approvals.
- `rooms.py` emits `confirm_required` and `privileged_required`.
- `dashboard.py` approves or denies dashboard approval requests and refuses non-allow/non-confirm policy rechecks.

This is Sparkbot's own Guardian policy path. It is not LIMA `GuardianDecision` authority and does not approve LIMA runtime `GuardianDecision` implementation.

## Provider/Model Routing Classification

Sparkbot has source-backed provider/model routing behavior:

- `VALID_AGENT_ROUTES` includes default, OpenRouter, local, local AI, OpenAI, OpenAI Codex subscription, Claude subscription, Anthropic, Google, Groq, MiniMax, and xAI route families.
- `get_agent_route_context(...)` builds route context from agent/model seat selection.
- `model_seats.py` normalizes model-seat providers and secret references.
- `sparkbotControls.ts` maps model selections to provider routes and model seats.
- `llm.py` records model latency and errors and uses provider-aware streaming/fallback helpers.

This is Sparkbot runtime evidence. It does not add LIMA provider/model routing or provider/model calls.

## Audit/Evidence Classification

Sparkbot has source-backed audit/evidence behavior:

- `dashboard.py` records policy/tool audit entries and exposes a run timeline with audit hashes.
- `pending_approvals.py` emits approval lifecycle events.
- `spine.py` defines Guardian Spine task/event/approval tables and queues.
- `frontend/src/lib/spine.ts` reads operator queues, events, tasks, projects, approvals, and lineage.
- `docs/capabilities.md` documents persistent approvals, redacted audit, run timelines, and Guardian Spine queues.

This is Sparkbot behavior-reference evidence. It does not add LIMA durable audit persistence.

## Connector, Tool, Browser, Network, Device, Robotics, And Physical-World Classification

Sparkbot has runtime-enabled connector/tool/browser/network behavior where configured, but it is governed by Sparkbot's Guardian policy and operator approval posture.

For V1-G7 LIMA intake:

- Connector and communication sends are guarded by confirmation.
- Browser writes/clicks/fills are high-risk and guarded.
- File edits/deletes and shell writes require confirmation or elevated approval.
- Credential reveal/write and Vault destructive paths require privileged/break-glass flows.
- Public Robo behavior is preview-only by default.
- Real robotics/IoT bridge execution is excluded from public core behavior and requires explicit private configuration.
- This packet adds no new connector, browser, network, file, device, robotics, or physical-world behavior.

## Raw Natural-Language-To-Tool Execution

Sparkbot does not support raw natural language directly executing tools as a bypass. User messages may cause model tool calls, but those tool calls flow through Sparkbot's tool catalogue, Guardian policy decisions, confirmation/privileged gates, and audit paths.

## Boundary Results

- LIMA runtime wiring added: no.
- LIMA runtime behavior added: no.
- LIMA runtime exports changed: no.
- Runtime exports required from LIMA: none.
- Sparkbot code copied to LIMA: no.
- Sparkbot imported by LIMA: no.
- LIMA imported by Sparkbot runtime for this proof: no.
- Production readiness claimed: no.
- V1 product readiness claimed: no.
- Accepted as static shell evidence: yes.
- Accepted as live runtime parity: no.

## Blockers

- LIMA has no live runtime wiring to Sparkbot.
- LIMA has no real runtime `GuardianDecision` authority.
- LIMA has no live approval enforcement.
- LIMA has no provider/model runtime routing.
- LIMA has no durable audit persistence.
- LIMA has no haptic device behavior and should not own it.
- `Arc-Bot-shell` V1-G7 packet is still not accepted by LIMA.
- Consolidated V1-G7 closeout is still not complete.
- Runtime export cleanup remains unapproved.
- Final API freeze remains unapproved.

## Recommended Next Step

After Sparkbot validation passes, LIMA should intake this packet as static behavior-reference evidence only. The next V1-G7 step after Sparkbot intake is to request or normalize the `Arc-Bot-shell` V1-G7 proof packet, then perform a separate LIMA intake audit for it.
