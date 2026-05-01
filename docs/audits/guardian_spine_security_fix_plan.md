# Guardian/Spine Security Fix Plan

**Date:** 2026-05-01
**Prerequisite for:** LIMA-Guardian-Suite extraction
**Status:** Active — fixes in progress

---

## Risk Register

### RISK-1: Pending Approvals Emit Unredacted Tool Args to Spine Events
- **Severity:** MEDIUM
- **Affected files:** `backend/app/services/guardian/pending_approvals.py`
- **Description:** `store_pending_approval()`, `consume_pending_approval()`, and `discard_pending_approval()` emit Spine events containing raw `tool_args` in the event payload (lines 100, 143, 194). If tool_args contain vault secrets, API keys, or passwords (e.g., from `vault_add_secret` or tools that accept credentials), the plaintext ends up in `guardian_spine_events` table permanently.
- **Recommended fix:** Redact secret-like keys in tool_args before including in Spine event payloads. Use the same `_GENERIC_SECRET_PAIR_RE` pattern from `llm.py` audit redaction.
- **Tests needed:** Test that `store_pending_approval()` with a `tool_args={"api_key": "sk-live-xxx"}` produces a Spine event with `[REDACTED]` instead of the key value.
- **Rollback plan:** Revert the redaction function. Tool args in Spine events go back to unredacted (pre-existing behavior). No data loss.

### RISK-2: Executive Decision JSONL May Contain Sensitive Metadata
- **Severity:** MEDIUM
- **Affected files:** `backend/app/services/guardian/executive.py`
- **Description:** `exec_with_guard()` writes `metadata` dict to JSONL (line 152) and passes it to `_emit_spine_decision()` (line 96). The metadata dict comes from callers and may contain tool args with secrets. The `result_excerpt` (line 164) is truncated to 500 chars but not redacted.
- **Recommended fix:** Redact secret-like keys in metadata and result_excerpt before writing to JSONL and before emitting to Spine.
- **Tests needed:** Test that `exec_with_guard()` with metadata containing `{"password": "s3cret"}` writes `[REDACTED]` to JSONL, not the plaintext.
- **Rollback plan:** Revert redaction. JSONL goes back to unredacted (pre-existing behavior).

### RISK-3: Tool Args Stored Unredacted in Pending Approvals SQLite DB
- **Severity:** LOW (mitigated by 600s TTL)
- **Affected files:** `backend/app/services/guardian/pending_approvals.py`
- **Description:** `tool_args_json` column stores full JSON of tool arguments including potential secrets. Entries expire after 600s and are pruned on access, but during that window the plaintext is on disk.
- **Recommended fix:** Accept as low risk with current 600s TTL. Document as known limitation. The approval flow needs the original args to execute the tool, so redaction at storage time would break functionality. Instead, ensure file permissions on `pending_approvals.db` are restricted.
- **Tests needed:** Test that `_prune_expired()` actually removes entries after TTL.
- **Rollback plan:** N/A — no code change recommended.

### RISK-4: Global Computer Control Bypass Persisted as Env Var
- **Severity:** LOW (TTL-enforced)
- **Affected files:** `backend/app/services/guardian/policy.py`
- **Description:** `SPARKBOT_GLOBAL_COMPUTER_CONTROL` and `SPARKBOT_GLOBAL_COMPUTER_CONTROL_EXPIRES_AT` are env vars that bypass all policy checks when active. TTL is enforced (24h max). The bypass state is logged by the executive decision system.
- **Recommended fix:** Already has TTL enforcement. Add a test proving that expired bypass returns `False` from `global_bypass_enabled()`.
- **Tests needed:** Test with expired TTL returns disabled.
- **Rollback plan:** N/A — behavior unchanged.

### RISK-5: No Test for Vault Route Unauthorized Access Denial
- **Severity:** MEDIUM
- **Affected files:** `backend/app/api/routes/chat/guardian.py`, `backend/tests/`
- **Description:** Vault write endpoints (`POST /guardian/vault`, `DELETE /guardian/vault/{alias}`) require both operator identity and an active privileged session. The route code enforces this, but no test explicitly verifies that a non-operator or non-privileged user receives 403.
- **Recommended fix:** Add tests proving: (a) non-operator gets 403, (b) operator without break-glass session gets 403 on vault writes.
- **Tests needed:** Test vault POST/DELETE without operator auth → 403. Test vault POST/DELETE as operator without privileged session → 403.
- **Rollback plan:** Tests only — no production code change.

### RISK-6: No Test for Task Guardian Write-Mode Gate
- **Severity:** MEDIUM
- **Affected files:** `backend/app/services/guardian/task_guardian.py`, `backend/tests/`
- **Description:** Write tools (gmail_send, slack_send_message, calendar_create_event) are gated by `SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED`. The code enforces this, but no test explicitly verifies that scheduling a write tool without the gate enabled is rejected.
- **Recommended fix:** Add test proving that scheduling a write tool with `SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED=false` raises or rejects.
- **Tests needed:** Test `schedule_task(tool_name="gmail_send")` with write mode off → rejected.
- **Rollback plan:** Tests only — no production code change.

### RISK-7: No Test for Memory PII Redaction Before Persistence
- **Severity:** MEDIUM
- **Affected files:** `backend/app/services/guardian/memory.py`, `backend/tests/`
- **Description:** Memory writes go through `_redact_sensitive_text()` and `_sanitize_metadata()`. The existing test (`test_guardian_memory.py`) tests redaction outcomes but doesn't explicitly verify that the stored ledger event contains redacted content (not just the returned context).
- **Recommended fix:** Add test that writes a memory with PII, then reads the raw ledger to verify the stored content is redacted.
- **Tests needed:** Test `remember_chat_message()` with email/phone/API-key in content → ledger contains `[REDACTED_*]`.
- **Rollback plan:** Tests only — no production code change.

### RISK-8: Vault Key Rotation Not Implemented
- **Severity:** LOW (operational gap, not active vulnerability)
- **Affected files:** `backend/app/services/guardian/vault.py`
- **Description:** No tooling exists to rotate `SPARKBOT_VAULT_KEY`. If the key is compromised, all vault entries must be re-encrypted manually.
- **Recommended fix:** Document as known gap. Defer implementation to Phase 2 extraction.
- **Tests needed:** None for now.
- **Rollback plan:** N/A.

### RISK-9: Frontend Operator Guard Is Client-Side Only
- **Severity:** LOW (backend enforces server-side)
- **Affected files:** `frontend/src/routes/_layout/spine.tsx`
- **Description:** The `beforeLoad` guard in `spine.tsx` redirects non-operators. However, this is a UX convenience — all backend routes independently check operator identity and return 403.
- **Recommended fix:** No code change needed. Backend auth is the real gate. Document that frontend guard is defense-in-depth only.
- **Tests needed:** Covered by existing backend route auth tests.
- **Rollback plan:** N/A.

---

## Fix Priority

| Risk | Severity | Action | Phase |
|------|----------|--------|-------|
| RISK-1 | MEDIUM | **Implement fix** — redact tool_args in Spine event payloads | Phase 3 (now) |
| RISK-2 | MEDIUM | **Implement fix** — redact metadata and result_excerpt in JSONL | Phase 3 (now) |
| RISK-5 | MEDIUM | **Add tests** — vault route unauthorized denial | Phase 3 (now) |
| RISK-6 | MEDIUM | **Add tests** — write-mode gate enforcement | Phase 3 (now) |
| RISK-7 | MEDIUM | **Add tests** — memory PII redaction at persistence layer | Phase 3 (now) |
| RISK-3 | LOW | **Document** — accepted risk with 600s TTL | Phase 3 (now) |
| RISK-4 | LOW | **Add test** — bypass TTL expiry | Phase 3 (now) |
| RISK-8 | LOW | **Document** — defer to extraction phase | Deferred |
| RISK-9 | LOW | **Document** — backend is the real gate | Done (this doc) |

---

## Extraction Gate Criteria

Extraction to LIMA-Guardian-Suite is **blocked** until:

- [x] Phase 0: Preservation doc exists (`guardian_spine_current_state.md`)
- [x] Phase 1-2: Security fix plan exists (this file)
- [x] Phase 3: RISK-1 fix implemented and tested (commit v1.6.48)
- [x] Phase 3: RISK-2 fix implemented and tested (commit v1.6.48)
- [x] Phase 3: RISK-4 test added (commit v1.6.48)
- [x] Phase 3: RISK-5 tests added (commit v1.6.48)
- [x] Phase 3: RISK-6 tests added (commit v1.6.48)
- [x] Phase 3: RISK-7 tests added (commit v1.6.48)
- [x] Phase 3: All tests pass — 181/181 green (21 new security + 140 existing + 41 breakglass route)

---

*This plan governs the security stabilization before extraction. No architectural refactoring until these gates pass.*
