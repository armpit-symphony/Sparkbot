# Sparkbot Public Release Next Decision Matrix

Date: 2026-05-20
Branch: `public-release-qa-assessment`

| Option | Why do it now | Why wait | Risk | Estimated scope | Recommended priority |
|---|---|---|---|---|---|
| 1. Browser/live QA fixes | Validates the core product promise before extraction and catches visible breakage. | Some packaging/source boundary blockers should be fixed first so QA targets the public artifact. | Medium; can expand into feature work if not disciplined. | 1-2 focused passes. | P0 after packaging sanitation. |
| 2. Sparkbot_shell extraction map refresh | Needed before safe Layer 1 import; current map should reflect final cleanup and QA findings. | Map will be stale if package tests/workflows/docs boundary changes first. | Medium; wrong map can import private code. | 1 focused audit pass. | P0 after package/source boundary cleanup. |
| 3. Layer 1 shell import | Moves toward public repo. | Too early while package/source docs and browser/live QA are unresolved. | High; private bridge/tests/workflows could leak. | Multi-pass extraction. | Wait. |
| 4. More guardrail/security behavior polish | Security profiles are central to public trust and backend separation exists. | Browser QA should identify the highest-impact UI gaps first. | Medium; policy changes can regress capability. | 1-2 focused passes. | P1 after profile QA. |
| 5. More Round Table UI polish | Round Table is the hook and likely benefits from polish after real QA. | Avoid polishing before confirming launch/streaming/assignment behavior. | Low to medium. | 1 focused UI pass. | P1 after browser QA. |
| 6. Scheduler leadership/locking | Needed before multi-worker public server recommendations. | Public defaults already use `BACKEND_WORKERS=1`; extraction can proceed without solving distributed scheduling if documented. | Medium/high backend complexity. | Larger backend platform pass. | P2 unless server beta requires multi-worker. |
| 7. First-run onboarding polish | Improves conversion and reduces confusion around AI Setup/local models. | Needs live QA findings to avoid designing around assumptions. | Low to medium. | 1 focused frontend/docs pass. | P1 after live QA. |
| 8. Public docs/download polish | Auditor found public clone/source path issues and stale copy. | Should not wait; docs can leak wrong installation path immediately. | Low implementation risk, high public impact. | Small focused docs/package pass. | P0 first. |

## Recommended Sequence

1. Public package/source-boundary sanitation: exclude or sanitize tests and private/stale workflows, add root `.dockerignore`, fix public clone/download copy.
2. Browser/live QA pass using `PUBLIC_RELEASE_BROWSER_QA_CHECKLIST.md` and `PUBLIC_RELEASE_LIVE_QA_PLAN.md`.
3. Refresh `Sparkbot_shell` extraction map from the validated public artifact.
4. Start Layer 1 shell import only if the QA pass finds no P0 public blockers.
