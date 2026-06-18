import type { PublicCapability } from "../api";
import type { ShellSectionStatus } from "./shellSections";

export type WorkstreamStatus = ShellSectionStatus;

export type WorkstationStatusItem = {
  id: string;
  name: string;
  status: WorkstreamStatus;
  summary: string;
};

export const workstationStatusItems: WorkstationStatusItem[] = [
  {
    id: "backend-health",
    name: "Backend health endpoint",
    status: "available",
    summary: "Read-only local health check."
  },
  {
    id: "frontend-shell",
    name: "Frontend shell",
    status: "available",
    summary: "Public shell interface."
  },
  {
    id: "workstation",
    name: "Workstation shell",
    status: "preview",
    summary: "Navigation and product shell preview."
  },
  {
    id: "chat",
    name: "Chat shell",
    status: "preview",
    summary: "No model calls or message persistence."
  },
  {
    id: "work-page",
    name: "Work Page shell",
    status: "preview",
    summary: "No file reads, file writes, connector calls, or worker execution."
  },
  {
    id: "round-table",
    name: "Round Table",
    status: "preview",
    summary: "No meeting engine or agent orchestration."
  },
  {
    id: "provider-setup",
    name: "Provider Setup shell",
    status: "preview",
    summary: "No credential storage or provider calls."
  },
  {
    id: "local-ai-settings",
    name: "Local AI Settings shell",
    status: "preview",
    summary: "No credentials, endpoint checks, provider calls, or model routing."
  },
  {
    id: "guardian-controls",
    name: "Guardian Controls shell",
    status: "preview",
    summary: "No policy enforcement runtime."
  },
  {
    id: "desktop-packaging",
    name: "Desktop packaging",
    status: "planned",
    summary: "No installer or desktop binary yet."
  },
  {
    id: "connectors",
    name: "Connectors",
    status: "guarded-future",
    summary: "No connector calls or external sends."
  },
  {
    id: "model-calls",
    name: "Model calls",
    status: "guarded-future",
    summary: "No provider runtime or model routing."
  },
  {
    id: "credential-storage",
    name: "Credential storage",
    status: "guarded-future",
    summary: "No credential entry or storage path."
  },
  {
    id: "tool-execution",
    name: "Tool execution",
    status: "guarded-future",
    summary: "No terminal, tool, or automation execution."
  }
];

export function capabilityToStatusItem(capability: PublicCapability): WorkstationStatusItem {
  return {
    id: capability.id,
    name: capability.label,
    status: capability.status,
    summary: capability.notes
  };
}

export const workstationRoadmapItems: string[] = [
  "Define workstation view structure with stable public contracts.",
  "Document chat interaction contracts before enabling message handling or model behavior.",
  "Keep Work Page and Local AI Settings previews inert until public-safe local action contracts exist.",
  "Expand Round Table preview surfaces only after public interaction contracts are documented.",
  "Document provider setup contracts before enabling credential or network behavior.",
  "Document Guardian control contracts before enabling approval or enforcement behavior.",
  "Prepare provider and guardrail integration points without runtime activation."
];
