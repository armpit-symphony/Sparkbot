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
  inviteApiKey?: string
  inviteAuthMode?: "api_key" | "oauth" | "codex_sub"
  shellType?: "bash" | "zsh" | "ssh" | "powershell"
  host?: string
}

// ─── Station data ─────────────────────────────────────────────────────────────

export const MAIN_DESK: Station = {
  id: "sparkbot",
  label: "Sparkbot",
  subtitle: "Corner Office",
  type: "main",
  status: "active",
  icon: Bot,
  route: "/dm",
  accentHex: "#8b93ff",
  description:
    "Your main workspace for everyday chat, memory, guided actions, and optional channels. Workstation is the desktop overview around that core surface.",
  capabilities: ["Everyday chat", "Memory", "Guided actions", "Optional channels"],
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
    label: "Codex",
    subtitle: "Invite Desk",
    type: "invite",
    status: "empty",
    icon: Plus,
    accentHex: "#7dd3fc",
    description:
      "Use the ChatGPT workstation button as the Codex gateway desk for an OpenAI coding seat with its own sub-account key and history.",
    capabilities: ["Codex workflows", "Function calling", "Vision"],
    invitePrompt:
      "Configure an OpenAI API key or Codex sub-account key to activate this desk.",
    isInviteSlot: true,
  },
  {
    id: "invite-custom",
    label: "OpenClaw",
    subtitle: "Invite Desk",
    type: "invite",
    status: "empty",
    icon: Plus,
    accentHex: "#f472b6",
    description:
      "Stage an external assistant or operator desk, including OpenClaw or another custom collaborator.",
    capabilities: ["External operator", "Custom provider", "Dedicated history"],
    invitePrompt:
      "Configure this slot later for OpenClaw or another invited collaborator.",
    isInviteSlot: true,
  },
]

export const ROUND_TABLE: Station = {
  id: "round-table",
  label: "Roundtable",
  subtitle: "Shared Project Room",
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
    label: "Local Terminal",
    subtitle: "Downloaded Machine",
    type: "terminal",
    status: "idle",
    icon: Terminal,
    accentHex: "#7dd3fc",
    description:
      "Connect directly to the machine running this Sparkbot download. Use it for local model installs, logs, git, and environment checks.",
    capabilities: ["Local shell", "Model installs", "Logs", "Git"],
    shellType: "bash",
    host: "localhost",
  },
  {
    id: "terminal-2",
    label: "Secondary Terminal",
    subtitle: "Parallel Shell",
    type: "terminal",
    status: "idle",
    icon: Terminal,
    accentHex: "#8b93ff",
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
