import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

const capabilitiesPayload = {
  service: "sparkbot-server",
  mode: "local",
  capabilities: [
    {
      id: "backend-health",
      label: "Backend health endpoint",
      status: "available",
      notes: "Read-only local health check."
    },
    {
      id: "frontend-shell",
      label: "Frontend shell",
      status: "available",
      notes: "Public shell interface."
    },
    {
      id: "workstation",
      label: "Workstation shell",
      status: "preview",
      notes: "Navigation and product shell preview."
    },
    {
      id: "chat",
      label: "Chat shell",
      status: "preview",
      notes: "No model calls or message persistence."
    },
    {
      id: "work-page",
      label: "Work Page shell",
      status: "preview",
      notes: "No file reads, file writes, connector calls, or worker execution."
    },
    {
      id: "round-table",
      label: "Round Table",
      status: "preview",
      notes: "No meeting engine or agent orchestration."
    },
    {
      id: "provider-setup",
      label: "Provider Setup shell",
      status: "preview",
      notes: "No credential storage or provider calls."
    },
    {
      id: "local-ai-settings",
      label: "Local AI Settings shell",
      status: "preview",
      notes: "No credentials, endpoint checks, provider calls, or model routing."
    },
    {
      id: "guardian-controls",
      label: "Guardian Controls shell",
      status: "preview",
      notes: "No policy enforcement runtime."
    },
    {
      id: "desktop-packaging",
      label: "Desktop packaging",
      status: "planned",
      notes: "No installer or desktop binary yet."
    },
    {
      id: "connectors",
      label: "Connectors",
      status: "guarded-future",
      notes: "No connector calls or external sends."
    },
    {
      id: "model-calls",
      label: "Model calls",
      status: "guarded-future",
      notes: "No provider runtime or model routing."
    },
    {
      id: "credential-storage",
      label: "Credential storage",
      status: "guarded-future",
      notes: "No credential entry or storage path."
    },
    {
      id: "tool-execution",
      label: "Tool execution",
      status: "guarded-future",
      notes: "No terminal, tool, or automation execution."
    },
    {
      id: "future-local-action",
      label: "Future local action",
      status: "disabled-by-default",
      notes: "Requires explicit enablement before any action exists."
    }
  ]
};

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("capabilities unavailable")));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders workstation navigation, preview-only shell sections, fallback statuses, and read-only health panel", async () => {
    render(<App />);

    expect(screen.getByRole("heading", { level: 1, name: "Sparkbot" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Workstation Shell" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Shell Sections" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Workstation Overview" })).toBeDefined();
    expect(screen.getByText("Using local fallback status list.")).toBeDefined();
    expect(screen.getByRole("button", { name: /Workstation.*Preview/i })).toBeDefined();
    expect(screen.getByRole("button", { name: /Chat.*Preview/i })).toBeDefined();
    expect(screen.getByRole("button", { name: /Work Page.*Preview/i })).toBeDefined();
    expect(screen.getByRole("button", { name: /Round Table.*Preview/i })).toBeDefined();
    expect(screen.getByRole("button", { name: /Provider Setup.*Preview/i })).toBeDefined();
    expect(screen.getByRole("button", { name: /Local AI Settings.*Preview/i })).toBeDefined();
    expect(screen.getByRole("button", { name: /Guardian Controls.*Preview/i })).toBeDefined();
    expect(screen.getAllByText("Available").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("heading", { name: "Backend health endpoint" })).toBeDefined();
    expect(screen.getByText("Read-only local health check.")).toBeDefined();
    expect(screen.getByRole("heading", { name: "Connectors" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Model calls" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Credential storage" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Tool execution" })).toBeDefined();
    expect(screen.getAllByText("Guarded future").length).toBeGreaterThanOrEqual(4);
    expect(screen.getByText("No connector calls or external sends.")).toBeDefined();
    expect(screen.getByText("No provider runtime or model routing.")).toBeDefined();
    expect(screen.getByText("No credential entry or storage path.")).toBeDefined();
    expect(screen.getByText("No terminal, tool, or automation execution.")).toBeDefined();
    expect(screen.getByRole("heading", { name: "Chat shell" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Chat Shell Preview" })).toBeDefined();
    expect(screen.getByText(/chat runtime is planned for later slices/i)).toBeDefined();
    expect(screen.getByText(/Empty state: chat history will appear here/i)).toBeDefined();
    expect(screen.getByText(/no enabled send action, no chat endpoint/i)).toBeDefined();
    const plannedComposer = screen.getByLabelText("Chat message composer planned") as HTMLTextAreaElement;
    expect(plannedComposer.disabled).toBe(true);
    expect(plannedComposer.readOnly).toBe(true);
    expect(screen.getByRole("heading", { name: "Work Page shell" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Work Page Preview" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Program queue" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Workspace files" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Remote index" })).toBeDefined();
    expect(screen.getByText(/no upload controls, no document editor/i)).toBeDefined();
    expect(screen.getByRole("heading", { name: "Round Table" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Round Table Preview" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Operator" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Assistant seat" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Research seat" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Builder seat" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Reviewer seat" })).toBeDefined();
    expect(screen.getByText(/multi-agent collaboration is planned/i)).toBeDefined();
    expect(screen.getByText(/does not start meetings, call models, run a turn engine/i)).toBeDefined();
    expect(screen.getAllByText("Preview").length).toBeGreaterThanOrEqual(7);
    expect(screen.getByRole("heading", { name: "Provider Setup Preview" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Local model provider" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "OpenAI-compatible provider" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Anthropic-compatible provider" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Google-compatible provider" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Custom endpoint" })).toBeDefined();
    expect(screen.getByText(/provider configuration is planned for later slices/i)).toBeDefined();
    expect(screen.getByText(/no API key fields, no save actions, and no test-connection actions/i)).toBeDefined();
    expect(screen.getByRole("heading", { name: "Provider Setup shell" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Local AI Settings shell" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Local AI Settings Preview" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Local runtime setup" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Model seats" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Readiness checks" })).toBeDefined();
    expect(screen.getByText(/no credential fields, no save actions/i)).toBeDefined();
    expect(screen.getByRole("heading", { name: "Guardian Controls shell" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Guardian Controls Preview" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Local actions" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Provider access" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Files and workspace" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "External connections" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Approval checkpoints" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Audit trail" })).toBeDefined();
    expect(screen.getByText(/Guardian-gated controls are planned for later slices/i)).toBeDefined();
    expect(screen.getByText(/no approval buttons, no execution controls, no save actions/i)).toBeDefined();
    expect(screen.getByRole("heading", { name: "Backend Health" })).toBeDefined();
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/capabilities"), expect.any(Object)));
  });

  it("renders backend capability statuses when the capabilities API responds", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(capabilitiesPayload), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        })
      )
    );

    render(<App />);

    expect(await screen.findByText("Using backend capabilities status.")).toBeDefined();
    expect(screen.getByRole("heading", { name: "Backend health endpoint" })).toBeDefined();
    expect(screen.getByText("Read-only local health check.")).toBeDefined();
    expect(screen.getByText("No file reads, file writes, connector calls, or worker execution.")).toBeDefined();
    expect(screen.getByText("No connector calls or external sends.")).toBeDefined();
    expect(screen.getByText("No credentials, endpoint checks, provider calls, or model routing.")).toBeDefined();
    expect(screen.getByText("No provider runtime or model routing.")).toBeDefined();
    expect(screen.getByText("No credential entry or storage path.")).toBeDefined();
    expect(screen.getByText("No terminal, tool, or automation execution.")).toBeDefined();
    expect(screen.getByText("Future local action")).toBeDefined();
    expect(screen.getAllByText("Disabled by default").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Guarded future").length).toBeGreaterThanOrEqual(4);
  });

  it("keeps fallback statuses on the public capability contract vocabulary", () => {
    render(<App />);

    expect(screen.getAllByText("Available").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("Preview").length).toBeGreaterThanOrEqual(7);
    expect(screen.getAllByText("Planned").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Disabled by default").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Guarded future").length).toBeGreaterThanOrEqual(4);
  });

  it("keeps provider, chat, and guardian surfaces inert", () => {
    render(<App />);

    expect(screen.queryByPlaceholderText(/api key|password|token/i)).toBeNull();
    expect(screen.queryByLabelText(/api key|password|token/i)).toBeNull();
    expect(document.querySelectorAll('input[type="password"]').length).toBe(0);
    expect(screen.queryByRole("button", { name: /save|test connection|connect/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /approve|execute|enforce|allow|deny/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /start|join|send|run/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /send|execute|save|test/i })).toBeNull();
  });
});
