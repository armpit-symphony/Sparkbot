# Sparkbot

Sparkbot is an early public, local-first AI workstation shell from SparkPit Labs. It is for builders, hobbyists, and technical users who want a self-hosted workspace for future chat, model seats, Round Table collaboration, provider setup, and safety-gated controls.

The current repository is a validated shell baseline. It is useful for review, local validation, and continued public development, but it is not a complete product release.

## Who this is for

- Hobbyists and tinkerers who want to inspect and run the local shell baseline.
- Developers evaluating the project structure, validation path, and public roadmap.
- Security-conscious users who want clear boundaries before provider credentials, model calls, or sensitive actions exist.
- Future contributors who want to understand what is implemented, what is preview-only, and what is intentionally excluded.

## Current status at a glance

| Area | Current status | Notes |
| --- | --- | --- |
| Backend health endpoint | Available | FastAPI exposes local `GET /health`. |
| Backend capabilities endpoint | Available | FastAPI exposes static read-only `GET /capabilities`. |
| Frontend shell | Available | React/Vite shell builds and tests successfully. |
| Workstation shell | Preview | Read-only product layout. |
| Chat shell | Preview | Disabled planned composer; no send action. |
| Work Page | Preview | Read-only program/workspace planning; no file reads, writes, connector calls, or worker execution. |
| Round Table | Preview | Inert planned seats for future collaboration. |
| Provider Setup | Preview | No API key fields, save action, or provider calls. |
| Local AI Settings | Preview | Read-only local setup route; no credentials, endpoint checks, provider calls, or model routing. |
| Guardian Controls | Preview | No approvals, enforcement, or sensitive actions. |
| Desktop packaging | Planned | No installer or desktop binary exists yet. |
| Connectors | Guarded future | No connector calls or external sends. |
| Model calls | Guarded future | No model routing or provider runtime is active. |
| Credential storage | Guarded future | No secrets are accepted, stored, or transmitted. |
| Tool execution | Guarded future | No terminal, tool execution, connector calls, or external sends. |

## Release and checkpoint status

The latest public checkpoint tag on `main` is `public-v1-capabilities-contract-alignment-0`.

The GitHub pre-release `public-v1-shell-baseline-0` remains the first published shell baseline release. Development continues on `main` through checkpoint tags, so `main` may include newer docs and planning checkpoints than the first pre-release page.

## Quickstart

### Prerequisites

- Python 3.12 or newer
- Node.js 20.19.0 or newer
- npm

### 1. Validate the full shell baseline

From the repository root:

```bash
bash scripts/validate-public-shell.sh
```

This runs backend compile/tests, frontend install/audit/tests/build, and does not start long-running services.

### 2. Run the public safety scan

```bash
bash scripts/check-public-safety.sh
```

This checks for blocked private references, unexpected publishing identity references, and non-BMP characters.

### 3. Start the backend in terminal 1

```bash
python3 -m venv .venv-local
. .venv-local/bin/activate
python -m pip install --upgrade pip
python -m pip install -e "backend[dev]"
bash scripts/start-backend-dev.sh
```

Expected backend health URL:

```text
http://127.0.0.1:8000/health
```

Expected backend capabilities URL:

```text
http://127.0.0.1:8000/capabilities
```

### 4. Start the frontend in terminal 2

```bash
cd frontend
npm ci
cd ..
bash scripts/start-frontend-dev.sh
```

Expected frontend URL:

```text
http://127.0.0.1:5173
```

Vite may print the exact local URL when the frontend server starts.

### 5. Optional alternate-port smoke test

When the default ports are already in use, run the shell on alternate localhost ports and verify both surfaces:

```bash
SPARKBOT_BACKEND_PORT=18000 bash scripts/start-backend-dev.sh
```

```bash
SPARKBOT_BACKEND_PORT=18000 \
VITE_SPARKBOT_API_BASE_URL=http://127.0.0.1:18000 \
SPARKBOT_FRONTEND_PORT=15173 \
bash scripts/start-frontend-dev.sh
```

```bash
SPARKBOT_BACKEND_URL=http://127.0.0.1:18000 \
SPARKBOT_FRONTEND_URL=http://127.0.0.1:15173 \
bash scripts/smoke-check-local.sh
```

Open `http://127.0.0.1:15173` for the browser check. See `docs/LOCAL_SMOKE_TEST.md` for details.

## What this repository does not do yet

- No desktop installer or desktop binary.
- No real chat runtime.
- No model calls or model routing.
- No provider credential setup.
- No local model endpoint checks.
- No credential storage.
- No file ingestion or file mutation workflows.
- No Round Table meeting engine.
- No Guardian policy enforcement runtime.
- No terminal, tool execution, connector calls, external sends, or file mutation controls.
- No production deployment workflow.

## Documentation map

Start with `docs/README.md` for a grouped documentation index.

Key docs:

- `CONTRIBUTING.md` for contribution scope and validation expectations.
- `SECURITY.md` for reporting security concerns.
- `docs/DEVELOPMENT.md` for local development workflow.
- `docs/VALIDATION.md` for validation commands.
- `docs/LOCAL_DEVELOPMENT.md` for local runner scripts.
- `docs/LOCAL_SMOKE_TEST.md` for alternate-port local smoke testing.
- `docs/PUBLIC_CAPABILITY_CONTRACTS.md` for capability status definitions and promotion gates.
- `docs/CONNECTOR_SAFETY_CONTRACT.md` for future connector safety gates.
- `docs/PROVIDER_CONFIG_CONTRACT.md` for future provider setup and model-call gates.
- `docs/GUARDIAN_POLICY_CONTRACT.md` for future sensitive-action policy gates.
- `docs/ROADMAP.md` for staged product direction.
- `docs/RELEASE_READINESS.md` for current release-readiness boundaries.
- `docs/PUBLIC_ARTIFACT_MANIFEST.md` for included and excluded public artifacts.
- `docs/DESKTOP_PACKAGING_PLAN.md` for desktop packaging planning only.

## Security and privacy posture

Current validation does not require secrets. The repository does not accept provider credentials, store credentials, call models, execute tools, run connectors, or send data to external services. Product surfaces beyond the backend health endpoint and frontend shell are previews until explicit public contracts and runtime gates are added.

Future provider, connector, model-call, credential, and Guardian runtime work must satisfy the public contracts in `docs/` before implementation branches can claim active behavior.

## Repository standards

This repository is maintained as a professional public project. Public documentation should describe only supported or planned public functionality and should avoid private infrastructure details, internal operating notes, or unsupported claims.

## License

This repository is licensed under the MIT License. The license applies to the contents of this public `sparkpit-labs/Sparkbot` repository only.

## Maintainers

Maintained by Spark Pit Labs Team.

## Command Center audit persistence for release

To enable immutable command-center audit persistence and integrity signing in release environments:

```bash
COMMAND_CENTER_AUDIT_FILE=./logs/command-center-audit.jsonl
COMMAND_CENTER_AUDIT_SIGNING_KEY=__REPLACE_ME__
```

If `COMMAND_CENTER_AUDIT_SIGNING_KEY` is set, each persisted JSONL row is signed with `HMAC-SHA256` and includes the immutable `chain_hash` for tamper-evident ordering. Keep the signing key in secret configuration.
