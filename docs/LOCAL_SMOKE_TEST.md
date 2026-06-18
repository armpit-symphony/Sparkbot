# Local Smoke Test

This guide verifies that the public Sparkbot shell can run locally on alternate localhost ports without touching existing development or server processes.

The smoke test starts only local development servers that you launch for the test. It does not configure provider credentials, call models, enable chat runtime behavior, run connectors, execute tools, or start deployment infrastructure.

## Default ports

By default, the development scripts use:

- Backend: `127.0.0.1:8000`
- Frontend: `127.0.0.1:5173`
- Frontend API base URL: `http://127.0.0.1:8000`

Use alternate ports when either default port is already occupied.

## Start backend on an alternate port

From the repository root:

```bash
SPARKBOT_BACKEND_PORT=18000 bash scripts/start-backend-dev.sh
```

The backend script supports:

- `SPARKBOT_BACKEND_HOST`, default `127.0.0.1`
- `SPARKBOT_BACKEND_PORT`, default `8000`

The script only allows `127.0.0.1` or `localhost` as the bind host.

## Start frontend on an alternate port

In a second terminal, from the repository root:

```bash
SPARKBOT_BACKEND_PORT=18000 \
VITE_SPARKBOT_API_BASE_URL=http://127.0.0.1:18000 \
SPARKBOT_FRONTEND_PORT=15173 \
bash scripts/start-frontend-dev.sh
```

The frontend script supports:

- `SPARKBOT_FRONTEND_HOST`, default `127.0.0.1`
- `SPARKBOT_FRONTEND_PORT`, default `5173`
- `SPARKBOT_BACKEND_PORT`, default `8000`
- `VITE_SPARKBOT_API_BASE_URL`, default `http://127.0.0.1:${SPARKBOT_BACKEND_PORT}`

The script only allows `127.0.0.1` or `localhost` as the bind host.

## Run the smoke check

In a third terminal, from the repository root:

```bash
SPARKBOT_BACKEND_URL=http://127.0.0.1:18000 \
SPARKBOT_FRONTEND_URL=http://127.0.0.1:15173 \
bash scripts/smoke-check-local.sh
```

The smoke check script supports:

- `SPARKBOT_BACKEND_URL`, default `http://127.0.0.1:8000`
- `SPARKBOT_FRONTEND_URL`, default `http://127.0.0.1:5173`

It verifies backend `/health`, backend `/capabilities`, and the frontend HTTP response.

Expected result:

```text
PASS: local Sparkbot shell smoke check completed
```

## Browser check

Open:

```text
http://127.0.0.1:15173
```

The page should show the Sparkbot shell with Workstation navigation, preview-only Chat, Work Page, Round Table, Provider Setup, Local AI Settings, Guardian Controls, backend capability statuses when available, and the read-only backend health panel.

## Cleanup

Stop only the backend and frontend processes that you started for the smoke test. Do not stop unrelated local services.
