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

