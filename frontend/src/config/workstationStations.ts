// ─── workstationStations.ts ───────────────────────────────────────────────────
// Shared config for all Workstation station data.
// Imported by WorkstationPage and SparkBudPage.

import type React from "react"
import { Bot, Plus, Terminal, Search, Code2, Globe, Zap, Users } from "lucide-react"

// ─── Types ────────────────────────────────────────────────────────────────────

export type StationType = "main" | "invite" | "terminal" | "sparkbud" | "table"
export type StationStatus = "active" | "idle" | "empty" | "offline"

export interface Station {
  id: string
  label: string
  subtitle: string
  type: StationType
  status: StationStatus
  icon: React.FC<{ size?: number; className?: string; style?: React.CSSProperties }>
  route?: string
  accentHex: string
  description: string
  capabilities: string[]
  invitePrompt?: string
  isInviteSlot?: boolean
  shellType?: "bash" | "zsh" | "ssh" | "powershell"
  host?: string
}

// ─── Station data ─────────────────────────────────────────────────────────────

export const MAIN_DESK: Station = {
  id: "sparkbot",
  label: "Sparkbot",
  subtitle: "Main Assistant",
  type: "main",
  status: "active",
  icon: Bot,
  route: "/dm",
  accentHex: "#00d4ff",
  description:
    "Your primary AI workspace. Full memory, vault access, Guardian-confirmed actions, and Telegram bridge integration.",
  capabilities: ["Chat & memory", "Vault access", "Guardian suite", "Telegram bridge"],
}

export const INVITE_DESKS: Station[] = [
  {
    id: "invite-claude",
    label: "Claude",
    subtitle: "Invite Desk",
    type: "invite",
    status: "empty",
    icon: Plus,
    accentHex: "#a78bfa",
    description:
      "Connect Anthropic Claude as a dedicated agent desk with its own history and persona.",
    capabilities: ["Long context", "Vision", "Multi-turn chat"],
    invitePrompt:
      "Configure an Anthropic API key in Controls to activate this desk.",
    isInviteSlot: true,
  },
  {
    id: "invite-gpt",
    label: "GPT",
    subtitle: "Invite Desk",
    type: "invite",
    status: "empty",
    icon: Plus,
    accentHex: "#34d399",
    description:
      "Connect an OpenAI GPT model as a dedicated agent desk with function calling support.",
    capabilities: ["Function calling", "Vision", "Code interpreter"],
    invitePrompt:
      "Configure an OpenAI API key in Controls to activate this desk.",
    isInviteSlot: true,
  },
  {
    id: "invite-custom",
    label: "Add Agent",
    subtitle: "Invite Desk",
    type: "invite",
    status: "empty",
    icon: Plus,
    accentHex: "#64748b",
    description:
      "Define a custom agent with any provider, API key, system prompt, and capabilities.",
    capabilities: ["Custom provider", "Custom persona", "Dedicated history"],
    invitePrompt:
      "Open Controls → Spawn Agent to create a new agent desk.",
    isInviteSlot: true,
  },
]

export const ROUND_TABLE: Station = {
  id: "round-table",
  label: "Project Room",
  subtitle: "Active Collaboration",
  type: "table",
  status: "idle",
  icon: Users,
  accentHex: "#f59e0b",
  description:
    "Bring multiple agents together for a shared project. Coordinate tasks, share files, and run multi-agent workflows.",
  capabilities: ["Multi-agent chat", "Task board", "File drops", "Agent coordination"],
}

export const TERMINALS: Station[] = [
  {
    id: "terminal-1",
    label: "Terminal 1",
    subtitle: "System Shell",
    type: "terminal",
    status: "idle",
    icon: Terminal,
    accentHex: "#4ade80",
    description:
      "Direct shell access. Runs bash, PowerShell, or SSH depending on your platform.",
    capabilities: ["bash / zsh", "ssh", "docker", "git"],
    shellType: "bash",
    host: "localhost",
  },
  {
    id: "terminal-2",
    label: "Terminal 2",
    subtitle: "System Shell",
    type: "terminal",
    status: "idle",
    icon: Terminal,
    accentHex: "#4ade80",
    description:
      "Second terminal session — server logs, builds, or a separate workspace.",
    capabilities: ["Server logs", "Docker", "Build env", "Log tail"],
    shellType: "bash",
    host: "localhost",
  },
]

export const SPARKBUDS: Station[] = [
  {
    id: "sb-research",
    label: "Research",
    subtitle: "SparkBud",
    type: "sparkbud",
    status: "idle",
    icon: Search,
    route: "/sparkbud-research",
    accentHex: "#60a5fa",
    description:
      "Autonomous research agent. Gathers data, summarizes sources, and compiles reports.",
    capabilities: ["Web research", "Data gathering", "Source citation", "Report gen"],
  },
  {
    id: "sb-builder",
    label: "Builder",
    subtitle: "SparkBud",
    type: "sparkbud",
    status: "idle",
    icon: Code2,
    route: "/sparkbud-builder",
    accentHex: "#f97316",
    description:
      "Code and build specialist. Writes modules, edits repos, reviews PRs, and generates code.",
    capabilities: ["Write code", "Edit repos", "PR generation", "Code review"],
  },
  {
    id: "sb-webmaker",
    label: "Web Maker",
    subtitle: "SparkBud",
    type: "sparkbud",
    status: "idle",
    icon: Globe,
    route: "/sparkbud-webmaker",
    accentHex: "#f472b6",
    description:
      "Frontend specialist. Generates landing pages, edits UI components, and manages frontend builds.",
    capabilities: ["Landing pages", "UI components", "Frontend deploy", "Styles"],
  },
  {
    id: "sb-automation",
    label: "Automation",
    subtitle: "SparkBud",
    type: "sparkbud",
    status: "idle",
    icon: Zap,
    route: "/sparkbud-automation",
    accentHex: "#fbbf24",
    description:
      "Automation and ops agent. Handles cron jobs, server automation, and pipeline creation.",
    capabilities: ["Cron jobs", "Server ops", "Pipelines", "Task scheduling"],
  },
]

export const ALL_STATIONS: Station[] = [
  MAIN_DESK,
  ...INVITE_DESKS,
  ROUND_TABLE,
  ...TERMINALS,
  ...SPARKBUDS,
]

export const STATION_BY_ID = new Map<string, Station>(
  ALL_STATIONS.map((s) => [s.id, s]),
)
