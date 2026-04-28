import { apiFetch } from "@/lib/apiBase"

export type McpPolicyTag =
  | "read-only"
  | "write"
  | "destructive"
  | "external-send"
  | "robot-motion"
  | "secret-use"

export type McpRiskLevel = "low" | "medium" | "high" | "critical"

export type McpRuntime = "sparkbot" | "lima-robo-os"

export interface McpToolManifest {
  id: string
  name: string
  owner: string
  runtime: McpRuntime
  description: string
  policy: McpPolicyTag[]
  riskLevel: McpRiskLevel
  requiredSecrets: string[]
  healthSource: "sparkbot-api" | "task-guardian" | "guardian-vault" | "external-mcp"
  dryRunSupport: "native" | "explain-plan" | "required-before-motion"
  approvalRequired?: boolean
  explainPlanRequired?: boolean
  status?: {
    state: string
    label: string
    configured: boolean
    details: string
  }
}

export const MCP_TOOL_MANIFESTS: McpToolManifest[] = [
  {
    id: "sparkbot.shell_run",
    name: "shell_run",
    owner: "Sparkbot",
    runtime: "sparkbot",
    description: "Run PowerShell or bash commands on the Sparkbot host with persisted working directory.",
    policy: ["write", "destructive"],
    riskLevel: "high",
    requiredSecrets: [],
    healthSource: "sparkbot-api",
    dryRunSupport: "explain-plan",
  },
  {
    id: "sparkbot.terminal_send",
    name: "terminal_send",
    owner: "Sparkbot",
    runtime: "sparkbot",
    description: "Send commands into an attached live Workstation terminal session.",
    policy: ["write", "destructive"],
    riskLevel: "high",
    requiredSecrets: [],
    healthSource: "sparkbot-api",
    dryRunSupport: "explain-plan",
  },
  {
    id: "sparkbot.browser_control",
    name: "browser_open / click / fill",
    owner: "Sparkbot",
    runtime: "sparkbot",
    description: "Open Chromium, read pages, click controls, and fill forms.",
    policy: ["read-only", "write", "external-send"],
    riskLevel: "medium",
    requiredSecrets: [],
    healthSource: "sparkbot-api",
    dryRunSupport: "explain-plan",
  },
  {
    id: "sparkbot.google_calendar",
    name: "calendar_list_events / calendar_create_event",
    owner: "Sparkbot",
    runtime: "sparkbot",
    description: "Read Google Calendar events and create meetings through the Google API.",
    policy: ["read-only", "write", "external-send", "secret-use"],
    riskLevel: "medium",
    requiredSecrets: ["google_client_id", "google_client_secret", "google_refresh_token"],
    healthSource: "guardian-vault",
    dryRunSupport: "explain-plan",
  },
  {
    id: "sparkbot.task_guardian",
    name: "Task Guardian jobs",
    owner: "Sparkbot",
    runtime: "sparkbot",
    description: "Run scheduled tool workflows with verifier checks, retries, run history, and notifications.",
    policy: ["read-only", "write", "external-send"],
    riskLevel: "high",
    requiredSecrets: [],
    healthSource: "task-guardian",
    dryRunSupport: "native",
  },
  {
    id: "sparkbot.guardian_vault",
    name: "vault_use_secret / vault_add_secret",
    owner: "Sparkbot",
    runtime: "sparkbot",
    description: "Store and use encrypted secrets with break-glass PIN and redacted audit logs.",
    policy: ["secret-use", "write", "destructive"],
    riskLevel: "critical",
    requiredSecrets: ["SPARKBOT_VAULT_KEY"],
    healthSource: "guardian-vault",
    dryRunSupport: "explain-plan",
  },
  {
    id: "sparkbot.memory_recall",
    name: "memory_recall / memory_reindex",
    owner: "Sparkbot",
    runtime: "sparkbot",
    description: "Search and maintain the source-grounded Guardian Memory ledger.",
    policy: ["read-only", "write"],
    riskLevel: "medium",
    requiredSecrets: [],
    healthSource: "sparkbot-api",
    dryRunSupport: "native",
  },
  {
    id: "lima.navigate",
    name: "navigate / follow_route / return_home",
    owner: "LIMA Robotics OS",
    runtime: "lima-robo-os",
    description: "Move a robot through a route or send it home through LIMA MCP skills.",
    policy: ["robot-motion", "write"],
    riskLevel: "critical",
    requiredSecrets: ["LIMA_MCP_URL or local LIMA daemon"],
    healthSource: "external-mcp",
    dryRunSupport: "required-before-motion",
  },
  {
    id: "lima.inspect",
    name: "inspect / detect_object / report_status",
    owner: "LIMA Robotics OS",
    runtime: "lima-robo-os",
    description: "Read robot state, perception streams, object detections, and inspection reports.",
    policy: ["read-only"],
    riskLevel: "medium",
    requiredSecrets: ["LIMA_MCP_URL or local LIMA daemon"],
    healthSource: "external-mcp",
    dryRunSupport: "native",
  },
  {
    id: "lima.stop",
    name: "stop",
    owner: "LIMA Robotics OS",
    runtime: "lima-robo-os",
    description: "Stop active robot motion or an active blueprint immediately.",
    policy: ["robot-motion", "write"],
    riskLevel: "critical",
    requiredSecrets: ["LIMA_MCP_URL or local LIMA daemon"],
    healthSource: "external-mcp",
    dryRunSupport: "required-before-motion",
  },
  {
    id: "lima.replay_simulation",
    name: "replay / simulation blueprints",
    owner: "LIMA Robotics OS",
    runtime: "lima-robo-os",
    description: "Run no-hardware robot demos through replay data or MuJoCo simulation.",
    policy: ["read-only"],
    riskLevel: "low",
    requiredSecrets: [],
    healthSource: "external-mcp",
    dryRunSupport: "native",
  },
]

export const MCP_RUN_TIMELINE = [
  "User request",
  "Parsed intent and context pack",
  "Tool manifests matched",
  "Policy tags and risk evaluated",
  "Dry run or explain plan",
  "Operator approval when required",
  "Execution",
  "Audit evidence and run summary",
]

export interface McpRegistryResponse {
  manifests: McpToolManifest[]
  runTimeline: string[]
  health: {
    sparkbotApiLive: boolean
    vaultConfigured: boolean
    taskGuardianEnabled: boolean
    taskGuardianWriteEnabled: boolean
    limaBridgeConfigured: boolean
  }
}

export interface McpExplainPlanRequest {
  manifestId: string
  toolArgs?: Record<string, unknown>
  userRequest?: string
  roomId?: string
}

export interface McpExplainPlanStep {
  step: string
  status: string
  detail: string
}

export interface McpExplainPlanResponse {
  simulationOnly: boolean
  runId?: string
  runStatus?: string
  createdAt?: string
  manifest: McpToolManifest
  policyToolName: string
  toolArgs: Record<string, unknown>
  policy: {
    decision: {
      action: string
      reason: string
      high_risk: boolean
      resource: string
      scope: string
    }
    classification: {
      action_type: string
      default_action: string
      requires_execution_gate: boolean
    }
  }
  dryRunRequired: boolean
  approvalRequired: boolean
  canExecuteNow: boolean
  nextAction: string
  timeline: McpExplainPlanStep[]
  notes: string[]
}

export interface McpRunRecord {
  id: string
  userId: string
  roomId: string | null
  manifestId: string
  manifestName: string
  runtime: "sparkbot" | "lima-robo-os" | string
  policyToolName: string
  policyAction: string
  status: string
  approvalRequired: boolean
  dryRunRequired: boolean
  canExecuteNow: boolean
  userRequest: string
  nextAction: string
  plan: McpExplainPlanResponse
  createdAt: string
  updatedAt: string
}

export async function fetchMcpRegistry(): Promise<McpRegistryResponse> {
  const response = await apiFetch("/api/v1/chat/mcp/registry", { credentials: "include" })
  if (!response.ok) {
    throw new Error(`MCP registry API ${response.status}`)
  }
  return response.json() as Promise<McpRegistryResponse>
}

export async function fetchMcpExplainPlan({
  manifestId,
  toolArgs = {},
  userRequest = "",
  roomId,
}: McpExplainPlanRequest): Promise<McpExplainPlanResponse> {
  const response = await apiFetch("/api/v1/chat/mcp/explain-plan", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      manifest_id: manifestId,
      tool_args: toolArgs,
      user_request: userRequest,
      room_id: roomId,
    }),
  })
  if (!response.ok) {
    throw new Error(`MCP explain-plan API ${response.status}`)
  }
  return response.json() as Promise<McpExplainPlanResponse>
}

export async function fetchMcpRuns(limit = 10): Promise<{ runs: McpRunRecord[]; count: number }> {
  const response = await apiFetch(`/api/v1/chat/mcp/runs?limit=${encodeURIComponent(String(limit))}`, {
    credentials: "include",
  })
  if (!response.ok) {
    throw new Error(`MCP runs API ${response.status}`)
  }
  return response.json() as Promise<{ runs: McpRunRecord[]; count: number }>
}

export const FALLBACK_MCP_REGISTRY: McpRegistryResponse = {
  manifests: MCP_TOOL_MANIFESTS,
  runTimeline: MCP_RUN_TIMELINE,
  health: {
    sparkbotApiLive: false,
    vaultConfigured: false,
    taskGuardianEnabled: false,
    taskGuardianWriteEnabled: false,
    limaBridgeConfigured: false,
  },
}

