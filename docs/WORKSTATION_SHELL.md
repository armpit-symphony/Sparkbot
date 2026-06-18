# Workstation Shell

The current public shell baseline includes a local Workstation shell skeleton for the Sparkbot public frontend.

## What Exists

- Read-only Workstation shell layout in the frontend.
- Structured status cards using the public contract statuses: Available, Preview, Planned, Disabled by default, and Guarded future.
- Read-only section selector for Workstation, Chat, Work Page, Round Table, Provider Setup, Local AI Settings, and Guardian Controls surfaces.
- Planned follow-up roadmap card for next product slices.
- Static Chat Shell preview with a disabled read-only planned composer and no send action.
- Static Work Page preview with inert program queue, workspace file, and remote-index cards.
- Static Round Table preview with inert Operator, Assistant, Research, Builder, and Reviewer seats.
- Static Provider Setup preview with inert local, compatible provider, and custom endpoint cards.
- Static Local AI Settings preview with inert local runtime setup, model-seat, and readiness-check cards.
- Static Guardian Controls preview with inert local action, provider access, workspace, connection, checkpoint, and audit cards.
- Existing backend health panel retained in the same frontend app.

## Current Status Model

- Backend health endpoint: Available
- Frontend shell: Available
- Workstation shell: Preview
- Chat shell: Preview
- Work Page shell: Preview
- Round Table: Preview
- Provider setup: Planned
- Local AI Settings shell: Preview
- Guardian-gated controls: Planned

Status labels in the UI mean:

- Available: implemented in the public repo, validated, documented, and safe by default.
- Preview: shape is visible, but runtime behavior is intentionally inactive.
- Planned: public direction is shown without input handling or integrations.
- Guarded future: not implemented; future runtime work requires contract gates and review.

## What Is Intentionally Excluded

- Workstation agent orchestration
- Chat runtime implementation
- Round Table runtime implementation
- Work Page file handling, connector search, or worker assignment execution
- Model calls
- Tool execution
- Provider setup runtime forms
- Local AI settings endpoint checks or saved provider settings
- Guardian runtime controls and policy enforcement
- Desktop and Tauri surfaces

## Validation Commands

```bash
cd frontend
npm ci
npm test -- --run
npm run build
```

```bash
python3 -m compileall backend
pytest backend/tests -q
```

## Scope Notes

This is a product-direction shell slice only. It does not claim release readiness and does not activate Chat, Work Page, Round Table, Provider Setup, Local AI Settings, or Guardian Controls runtime behavior beyond the existing read-only backend health and capabilities fetches.
