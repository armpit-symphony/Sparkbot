# Public Release Alignment Protocol (phase 1–5, phase 6 paused)

Current stance: keep the public shell baseline as-is (no additional runtime feature
promotion) while hardening source-of-truth sync and release hygiene.

## 1) Canonical source-of-truth

- Primary source for public-surface behavior: source repo branch
  `public-release-final-cleanup-assessment` and approved downstream public-alignment
  commits.
- Keep `sparkpit-labs/Sparkbot` as the public distribution repository.
- Do not merge unrelated local commits into public without passing the gates below.

## 2) Baseline packaging workflow

- Use the existing cleanup/export path from the source repo branch:
  `scripts/package-public-download.sh`
- This script:
  - exports the canonical source,
  - removes private/runtime artifacts,
  - rewrites non-public Robo internals with a preview stub,
  - produces tar/zip + checksums + release notes bundle.
- Any public release must be produced through this package path.

## 3) Continuous safety and validation gates (already present)

- `scripts/check-public-safety.sh`
  - blocked/private references scan,
  - identity scan,
  - non-BMP character scan.
- `scripts/validate-public-shell.sh`
  - backend compile/test,
  - frontend install/audit/tests/build.
- GitHub workflows
  - `.github/workflows/validate-public-shell.yml`
  - `.github/workflows/test-backend.yml`
  - `.github/workflows/test-frontend.yml`

## 4) Boundary documentation contract

Public boundary remains:

- no production claims,
- no model calls/credential storage/connector writes/tool execution in baseline,
- no desktop installers/binaries in this public baseline,
- explicit contracts in:
  - `docs/PUBLIC_CAPABILITY_CONTRACTS.md`
  - `docs/CONNECTOR_SAFETY_CONTRACT.md`
  - `docs/PROVIDER_CONFIG_CONTRACT.md`
  - `docs/GUARDIAN_POLICY_CONTRACT.md`
  - `docs/RELEASE_READINESS.md`

## 5) Sync checklist before any public merge

1. Confirm expected source branch/commit is explicit in PR description.
2. Verify the candidate tree still satisfies `validate-public-shell.yml`.
3. Verify source code diff is limited to boundary-respecting public-surface changes.
4. Confirm package artifacts generated via `scripts/package-public-download.sh`.
5. Record any drift notes in PR and update the release notes accordingly.

Phase 6 (feature re-introduction beyond the current baseline) is intentionally paused.