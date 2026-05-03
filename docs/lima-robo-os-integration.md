# LIMA Robo OS Integration

Status: Phase 0 and Phase 1 baseline are done; Phase 2 API bridge is now scaffolded in Sparkbot.

## Goal

Sparkbot is the governed command center. LIMA Robo OS is the robotics runtime. Together they should let an operator use natural language for robot status, replay/simulation control, and eventually real hardware motion, with Guardian safety and audit evidence around every physical-world action.

## Current Status

Phase 0, repository and control-plane audit:

- Sparkbot documents LIMA Robo OS as the robotics runtime, not a separate assistant.
- Workstation -> Robo OS exposes the unified MCP registry with Sparkbot and LIMA manifests.
- Robot-motion manifests are tagged as high-risk/critical and require explain-plan/approval posture.

Phase 1, simulation/MCP proof baseline:

- LIMA Robo OS provides an MCP server at `http://localhost:9990/mcp` when a blueprint includes `McpServer`.
- The first target remains `LIMA --simulation run unitree-go2-agentic-mcp`.
- Sparkbot stores durable MCP explain-plan runs and approval state, but the original MCP run lifecycle intentionally did not execute tools.

Phase 2, Sparkbot API bridge:

- `GET /api/v1/chat/robotics/status` reports whether `LIMA_MCP_URL` is configured.
- `GET /api/v1/chat/robotics/tools` lists tools from the configured LIMA MCP server.
- `POST /api/v1/chat/robotics/command` accepts a natural-language `requested_action`, creates the LIMA command contract, classifies risk, and calls the chosen MCP tool only when safe.
- `POST /api/v1/chat/robotics/emergency-stop` calls the best available stop tool and audits the stop event.
- Chat now has a `lima_robot_command` tool so users can ask Sparkbot for robot status, camera inspection, and replay/simulation commands in natural language.

## Safety Posture

- Dry runs work without a running LIMA bridge.
- Replay/simulation is the default environment.
- Small replay/simulation movement is allowed when `LIMA_MCP_URL` points to a running LIMA MCP server.
- Real-hardware motion is blocked by default until the Guardian approval handoff is wired to actual execution.
- Emergency stop bypasses approval and is audited.
- The bridge does not expose raw shell or terminal access.

## Runbook

Start LIMA Robo OS simulation with MCP:

```bash
LIMA --simulation run unitree-go2-agentic-mcp --daemon
```

Point Sparkbot at the local MCP server:

```bash
LIMA_MCP_URL=http://127.0.0.1:9990/mcp
```

Verify from Sparkbot:

```bash
curl -H "Authorization: Bearer <chat-token>" http://127.0.0.1:8000/api/v1/chat/robotics/status
curl -H "Authorization: Bearer <chat-token>" http://127.0.0.1:8000/api/v1/chat/robotics/tools
```

Example dry-run command body:

```json
{
  "requested_action": "move forward 0.5 meters",
  "environment": "simulation",
  "dry_run": true
}
```

## Remaining Work

- Wire approved MCP run records to the robotics command executor without bypassing Guardian.
- Add a Workstation Robo OS telemetry panel for tool list, current robot state, command history, and emergency stop.
- Add real hardware adapters only after simulation acceptance passes.
- Add per-robot safety limits for maximum distance, rotation, speed, restricted zones, battery minimums, and telemetry freshness.
- Load-test MCP calls and long-running robot jobs outside the web/API worker process.
