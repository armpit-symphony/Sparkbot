# Development

This repository is an early public shell baseline for local development and review.

## Prerequisites

- Python 3.12 or newer
- Node.js 20.19.0 or newer
- npm

## Full validation

Run the complete backend and frontend validation path from the repository root:

```bash
bash scripts/validate-public-shell.sh
```

Run the public safety scan from the repository root:

```bash
bash scripts/check-public-safety.sh
```

## Backend local workflow

Install backend development dependencies into a local virtual environment:

```bash
python3 -m venv .venv-local
. .venv-local/bin/activate
python -m pip install --upgrade pip
python -m pip install -e "backend[dev]"
```

Validate the backend:

```bash
python3 -m compileall backend
pytest backend/tests -q
```

Start the backend development server:

```bash
bash scripts/start-backend-dev.sh
```

The backend development server binds to `127.0.0.1:8000` and currently exposes a local read-only health endpoint at `GET /health`.

## Frontend local workflow

Install frontend development dependencies:

```bash
cd frontend
npm ci
cd ..
```

Validate the frontend:

```bash
cd frontend
npm audit --audit-level=moderate
npm test -- --run
npm run build
cd ..
```

Start the frontend development server:

```bash
bash scripts/start-frontend-dev.sh
```

The frontend development server binds to `127.0.0.1` through Vite. The frontend currently presents static shell previews for Workstation, Chat Shell, Work Page, Round Table, Provider Setup, Local AI Settings, and Guardian Controls.

## Current limitations

- No provider credentials are accepted, stored, or transmitted.
- No model calls or model routing are active.
- No chat runtime or message persistence is active.
- No approval or policy enforcement runtime is active.
- No sensitive action execution path is active.
- Desktop packaging and release artifacts are future work.
