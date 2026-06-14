# V1-G12 Sparkbot LIMA Consumer Proof Intake

Date: 2026-06-14
LIMA repository: `github.com/armpit-symphony/LIMA-AI-OS`
LIMA intake branch: `v1-g12-sparkbot-lima-consumer-proof-intake`
LIMA intake commit: `0ec8d230d5bd9ff56432e206adc7a5c147397cf8`

## Scope

This document records what the LIMA team accepted from the Sparkbot-side packet
`842a6757a2fbdc87451042eec465eb76be5bea80` and the remaining gaps for live
LIMA runtime parity.

## Files reviewed on LIMA side

- `docs/V1_G12_SPARKBOT_LIMA_CONSUMER_PROOF_INTAKE.md`
- `docs/V1_G12_SPARKBOT_LIMA_CONSUMER_PROOF_AUDIT.md`
- `docs/V1_G12_SPARKBOT_LIMA_CONSUMER_PROOF_CLOSEOUT.md`
- `docs/CURRENT_PROJECT_STATE.md`
- `tests/fixtures/runtime_extraction/v1_g12_sparkbot_lima_consumer_proof_intake.json`
- `tests/test_v1_g12_sparkbot_lima_consumer_proof_intake.py`

## Accepted evidence from Sparkbot

- proof packet, audit, and machine-readable summary were accepted as static evidence
  for review:
  - `docs/proof_packets/SPARKBOT_SHELL_LIMA_CONSUMER_PROOF_PACKET.md`
  - `docs/audits/SPARKBOT_SHELL_LIMA_CONSUMER_PACKET_AUDIT.md`
  - `docs/proof_packets/sparkbot_shell_lima_consumer_packet.json`
- route and surface coverage for chat, workstation, meeting/round table, command
  center, controls, Guardian/approval, audit/spine, model-seat, provider/model,
  tool/action paths
- `CandidatePreview` status use and examples included:
  - `preview_only`
  - `explain_plan`
  - `blocked`
  - `deferred`
- `embodiment_profile` included on each mapped `CandidatePreview` example
- explicit static boundary framing:
  - no live Sparkbot-on-LIMA runtime parity
  - no live ConsumerRequest intake
  - no shared task-intent adapter
  - no canonical live `RuntimeStateSnapshot`
  - no LIMA-native `GuardianDecision` authority
  - no production/runtime export claims

## Rejected as-is

LIMA did not accept any live runtime claims in this packet:

- no live provider/model execution in Sparkbot
- no runtime action handoff
- no LIMA-native approval enforcement
- no durable runtime audit ownership transfer
- no connector/tool/file/browser/network/robotics/device behavior

## Boundary outcome for this phase

- Runtime behavior added: `no`
- LIMA-runtime files changed: `no`
- Runtime exports changed: `no`
- Sparkbot runtime touched: `no`
- Sparkbot/Lima package coupling added: `no`
- API status for this scope: `CANDIDATE_ONLY`
- Final API freeze readiness: `no`

## Recommended immediate next step

LIMA-side proof is complete and accepted for static consumption only. Sparkbot-side
work should now remain evidence-only until a dedicated non-execution LIMA intake
adapter is added in Sparkbot and retested under a new contract-review packet.
