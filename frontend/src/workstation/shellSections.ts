export type ShellSectionStatus = "available" | "preview" | "planned" | "disabled-by-default" | "guarded-future";

export type ShellSection = {
  id: string;
  label: string;
  status: ShellSectionStatus;
  summary: string;
};

export const shellStatusLabels: Record<ShellSectionStatus, string> = {
  available: "Available",
  preview: "Preview",
  planned: "Planned",
  "disabled-by-default": "Disabled by default",
  "guarded-future": "Guarded future"
};

export const shellSections: ShellSection[] = [
  {
    id: "workstation-overview",
    label: "Workstation",
    status: "preview",
    summary: "Read-only shell map, status cards, and local health check surface."
  },
  {
    id: "chat-shell",
    label: "Chat",
    status: "preview",
    summary: "Static chat preview with message actions inactive."
  },
  {
    id: "work-page",
    label: "Work Page",
    status: "preview",
    summary: "Static work-program and workspace planning surface with actions inactive."
  },
  {
    id: "round-table",
    label: "Round Table",
    status: "preview",
    summary: "Static seat layout for future multi-participant work."
  },
  {
    id: "provider-setup",
    label: "Provider Setup",
    status: "preview",
    summary: "Read-only provider planning cards with credentials inactive."
  },
  {
    id: "local-ai-settings",
    label: "Local AI Settings",
    status: "preview",
    summary: "Read-only local model setup route with endpoint checks inactive."
  },
  {
    id: "guardian-controls",
    label: "Guardian Controls",
    status: "preview",
    summary: "Read-only control categories remain inactive in this preview."
  }
];
