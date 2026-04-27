// ─── WorkstationPage.tsx ──────────────────────────────────────────────────────
// Retro pixel-art / hacker-lab visual workstation — pure React/CSS, no canvas.
// Route: /workstation
// Phase 3: Live terminal via xterm.js + WebSocket-backed PTY sessions.

import { useState, useCallback, useEffect, lazy, Suspense } from "react"
import { Link, useNavigate } from "@tanstack/react-router"
import {
  Plus,
  Users,
  X,
  ExternalLink,
  Layers,
  Check,
  UserPlus,
  UserMinus,
  ChevronRight,
  SquareTerminal,
  Power,
  PowerOff,
  Loader2,
  SlidersHorizontal,
  Search,
  Code2,
  LineChart,
  Rocket,
  Briefcase,
  Clock,
  Play,
  RefreshCw,
  MonitorCog,
  Terminal,
  Globe,
  Zap,
} from "lucide-react"
import SparkbotSurfaceTabs from "@/components/Common/SparkbotSurfaceTabs"
import SparkbotSurfaceInfoDialog from "@/components/Common/SparkbotSurfaceInfoDialog"
import { Button } from "@/components/ui/button"
import {
  type Station,
  type StationStatus,
  MAIN_DESK,
  INVITE_DESKS,
  ROUND_TABLE,
  TERMINALS,
} from "@/config/workstationStations"
import { useTerminalSession } from "@/hooks/useTerminalSession"

// Lazy-load xterm.js so the ~93kB gzip chunk only loads when a terminal panel is opened
const XtermTerminal = lazy(() =>
  import("@/components/Terminal/XtermTerminal").then((m) => ({ default: m.XtermTerminal }))
)
import { apiFetch } from "@/lib/apiBase"
import { fetchControlsConfig, type SparkbotControlsConfig } from "@/lib/sparkbotControls"
import {
  buildSparkBudChatLaunchText,
  getSparkBudLaunchConfig,
  saveSparkBudChatLaunchDraft,
} from "@/lib/sparkbudLaunch"
import {
  MCP_RUN_TIMELINE,
  MCP_TOOL_MANIFESTS,
  type McpRiskLevel,
  type McpToolManifest,
} from "@/lib/mcpRegistry"
import {
  launchMeetingRoom,
  launchTaskMeeting,
  ROUND_TABLE_SEAT_COUNT,
  loadMeetingDraft,
  loadTaskMeetingLink,
  normalizeMeetingSeats,
  saveMeetingDraft,
  saveTaskMeetingLink,
  type GuardianTaskInfo,
  type WorkstationMeetingSeatMeta,
} from "@/lib/workstationMeeting"

// ─── Types ────────────────────────────────────────────────────────────────────

type PanelMode =
  | { kind: "station"; station: Station }
  | { kind: "table" }
  | { kind: "terminal"; station: Station }
  | { kind: "computercontrol" }
  | { kind: "mcp" }
  | null

interface ProjectRoom {
  roomName: string
  roomId: string | null
  seats: Array<string | null>
}

type InviteAuthMode = "api_key" | "oauth" | "codex_sub"

interface InviteConfig {
  label: string
  provider: string
  description: string
  modelId?: string
  apiKey?: string
  authMode?: InviteAuthMode
}

interface SeatPickerState {
  seatIndex: number
}

interface CompanionSlotMeta {
  key: "backup_1" | "backup_2" | "heavy_hitter"
  fallbackLabel: string
  fallbackSubtitle: string
  accentHex: string
}

interface WorkstationTaskRecord extends GuardianTaskInfo {
  enabled: boolean
  room_id: string
  last_run_at: string | null
  next_run_at: string | null
  consecutive_failures: number
}

interface WorkstationOverview {
  stack: { primary: string; backup_1: string; backup_2: string; heavy_hitter: string }
  stack_labels: { primary: string; backup_1: string; backup_2: string; heavy_hitter: string }
  tasks: WorkstationTaskRecord[]
  meetings: Array<{ id: string; name: string; description?: string; updated_at: string | null; created_at: string | null }>
}

interface ComputerControlRoomStatus {
  enabled: boolean | null
  pinConfigured: boolean | null
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function resolveInviteStation(
  station: Station,
  configuredInvites: Map<string, InviteConfig>,
): Station {
  if (!station.isInviteSlot) return station
  const config = configuredInvites.get(station.id)
  if (!config) return station
  return {
    ...station,
    label: config.label,
    subtitle: config.provider,
    description: config.description || station.description,
    status: "idle" as StationStatus,
    invitePrompt: undefined,
    ...(config.apiKey ? { inviteApiKey: config.apiKey } : {}),
    ...(config.authMode ? { inviteAuthMode: config.authMode } : {}),
  }
}

function slugifyMeetingHandleLabel(value: string, fallback: string): string {
  const normalized = (value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
  return normalized || fallback
}

function deriveMeetingAgentHandle(station: Station): string | null {
  switch (station.id) {
    case MAIN_DESK.id:
      return "sparkbot"
    case "sb-researcher":
      return "researcher"
    case "sb-coder":
      return "coder"
    case "sb-analyst":
      return "analyst"
    default:
      break
  }

  if (station.isInviteSlot || station.id.startsWith("stack-")) {
    return slugifyMeetingHandleLabel(station.label, station.id)
  }

  return null
}

function buildMeetingSeatMeta(
  station: Station,
  seatIndex: number,
  modelId?: string,
): WorkstationMeetingSeatMeta {
  const agentHandle = deriveMeetingAgentHandle(station)
  return {
    seatIndex,
    stationId: station.id,
    label: station.label,
    accentHex: station.accentHex,
    ...(modelId ? { modelId, route: "default" as const } : {}),
    ...(agentHandle ? { agentHandle } : {}),
    ...((station.isInviteSlot || Boolean(modelId)) && agentHandle
      ? {
          agentProvisioning: "custom" as const,
          agentProvider: station.subtitle,
          agentDescription: station.description,
        }
      : agentHandle
      ? { agentProvisioning: "builtin" as const }
      : {}),
    ...(station.inviteApiKey ? { inviteApiKey: station.inviteApiKey } : {}),
    ...(station.inviteAuthMode ? { inviteAuthMode: station.inviteAuthMode } : {}),
  }
}

const COMPANION_SLOT_META: CompanionSlotMeta[] = [
  {
    key: "backup_1",
    fallbackLabel: "Companion 01",
    fallbackSubtitle: "Model office",
    accentHex: "#8b93ff",
  },
  {
    key: "backup_2",
    fallbackLabel: "Companion 02",
    fallbackSubtitle: "Model office",
    accentHex: "#7dd3fc",
  },
  {
    key: "heavy_hitter",
    fallbackLabel: "Heavy Hitter",
    fallbackSubtitle: "Deep-work office",
    accentHex: "#c084fc",
  },
]

function titleCaseWords(value: string): string {
  return value
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}

function simplifyModelOfficeLabel(
  modelId: string,
  controlsConfig: SparkbotControlsConfig | null,
): string {
  const normalized = modelId.toLowerCase()

  if (normalized.includes("gpt")) return "GPT"
  if (normalized.includes("claude")) return "Claude"
  if (normalized.includes("grok")) return "Grok"
  if (normalized.includes("gemini")) return "Gemini"
  if (normalized.includes("llama")) return "Llama"
  if (normalized.includes("mistral")) return "Mistral"
  if (normalized.includes("deepseek")) return "DeepSeek"
  if (normalized.includes("qwen")) return "Qwen"
  if (normalized.includes("phi")) return "Phi"

  const providerLabel = controlsConfig?.providers.find((provider) =>
    provider.models.includes(modelId),
  )?.label
  if (providerLabel) return providerLabel.replace(/\s*\(.+\)\s*$/, "")

  const tail = modelId.split("/").pop() ?? modelId
  return titleCaseWords(tail.split(":")[0] ?? tail)
}

function buildCompanionModelStations(
  controlsConfig: SparkbotControlsConfig | null,
): Station[] {
  return COMPANION_SLOT_META.map((slot) => {
    const modelId = controlsConfig?.stack[slot.key] ?? ""
    const hasModel = Boolean(modelId)
    const modelLabel = hasModel
      ? simplifyModelOfficeLabel(modelId, controlsConfig)
      : slot.fallbackLabel

    return {
      id: `stack-${slot.key}`,
      label: modelLabel,
      subtitle: hasModel ? slot.fallbackSubtitle : "Awaiting setup",
      type: "main",
      status: hasModel ? "idle" : "empty",
      icon: Layers,
      route: "/dm?controls=open",
      accentHex: slot.accentHex,
      description: hasModel
        ? `${modelLabel} is staged as part of your current Sparkbot model stack. Adjust its role, fallback order, or replacement model from Sparkbot Controls.`
        : "Reserve this office for another model in your stack. Configure it in Sparkbot Controls when you want Sparkbot to have another companion desk available.",
      capabilities: hasModel
        ? [slot.fallbackSubtitle, modelId, "Review in Controls"]
        : ["Stack slot", "Configure in Controls", "Future companion desk"],
    }
  })
}

const SPECIALTY_PLACEHOLDERS: Station[] = [
  {
    id: "sb-researcher",
    label: "Researcher",
    subtitle: "Launch-ready specialty desk",
    type: "sparkbud",
    status: "idle",
    icon: Search,
    accentHex: "#60a5fa",
    description:
      "Pulls sources, compares references, and assembles research packets when Sparkbot needs a deeper evidence pass.",
    capabilities: ["Source sweeps", "Reference compare", "Draft brief"],
  },
  {
    id: "sb-coder",
    label: "Coder",
    subtitle: "Launch-ready specialty desk",
    type: "sparkbud",
    status: "idle",
    icon: Code2,
    accentHex: "#fb7185",
    description:
      "Handles repo edits, implementation passes, and code-focused breakdowns when Sparkbot needs a dedicated builder.",
    capabilities: ["Code changes", "Repo review", "Patch drafting"],
  },
  {
    id: "sb-analyst",
    label: "Analyst",
    subtitle: "Launch-ready specialty desk",
    type: "sparkbud",
    status: "idle",
    icon: LineChart,
    accentHex: "#c084fc",
    description:
      "Sorts signals, compares tradeoffs, and turns rough findings into clearer recommendations and decision support.",
    capabilities: ["Compare options", "Decision support", "Trend summaries"],
  },
  {
    id: "sb-custom",
    label: "Custom",
    subtitle: "Launch-ready custom desk",
    type: "sparkbud",
    status: "idle",
    icon: Plus,
    accentHex: "#7dd3fc",
    description:
      "Use this desk to define a specialist in plain language, set its launch prompt, and create a named custom SparkBud for the current workspace.",
    capabilities: ["Custom role", "Editable prompt", "Named specialist"],
  },
]

function getAssignedStationIds(projectRoom: ProjectRoom): string[] {
  return Array.from(new Set(projectRoom.seats.filter((seatId): seatId is string => Boolean(seatId))))
}

function isStationAssigned(projectRoom: ProjectRoom, stationId: string): boolean {
  return projectRoom.seats.includes(stationId)
}

function assignStationToSeat(
  projectRoom: ProjectRoom,
  stationId: string,
  seatIndex: number,
): ProjectRoom {
  const nextSeats = normalizeMeetingSeats(projectRoom.seats).map((seatId) =>
    seatId === stationId ? null : seatId,
  )
  nextSeats[seatIndex] = stationId
  return {
    ...projectRoom,
    seats: nextSeats,
  }
}

function removeStationFromSeats(projectRoom: ProjectRoom, stationId: string): ProjectRoom {
  return {
    ...projectRoom,
    seats: normalizeMeetingSeats(projectRoom.seats).map((seatId) =>
      seatId === stationId ? null : seatId,
    ),
  }
}

function addStationToFirstOpenSeat(projectRoom: ProjectRoom, stationId: string): ProjectRoom {
  if (isStationAssigned(projectRoom, stationId)) return projectRoom
  const nextSeats = normalizeMeetingSeats(projectRoom.seats)
  const firstOpenSeat = nextSeats.findIndex((seatId) => !seatId)
  if (firstOpenSeat === -1) return projectRoom
  nextSeats[firstOpenSeat] = stationId
  return {
    ...projectRoom,
    seats: nextSeats,
  }
}

// ─── Shared CSS strings ───────────────────────────────────────────────────────

const SCANLINE_BG =
  "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.08) 2px, rgba(0,0,0,0.08) 4px)"

const PLASMA_PRIMARY = "#8b93ff"
const PLASMA_SECONDARY = "#7dd3fc"
const PLASMA_BORDER = "rgba(99, 102, 241, 0.22)"

// ─── StatusLight sub-component ────────────────────────────────────────────────

interface StatusLightProps {
  status: StationStatus
  hex: string
}

function StatusLight({ status, hex }: StatusLightProps) {
  const isPulsing = status === "active"
  const color = status === "empty" || status === "offline" ? "#374151" : hex
  return (
    <span
      style={{
        display: "inline-block",
        width: 8,
        height: 8,
        borderRadius: "50%",
        backgroundColor: color,
        boxShadow: isPulsing ? `0 0 6px 2px ${color}` : undefined,
        flexShrink: 0,
        animation: isPulsing ? "statusPulse 2s ease-in-out infinite" : undefined,
      }}
      aria-label={`Status: ${status}`}
    />
  )
}

// ─── MonitorScreen sub-component ──────────────────────────────────────────────

interface MonitorScreenProps {
  icon: React.FC<{ size?: number; className?: string; style?: React.CSSProperties }>
  status: StationStatus
  hex: string
  size?: "sm" | "md" | "lg"
}

function MonitorScreen({ icon: Icon, status, hex, size = "md" }: MonitorScreenProps) {
  const iconSize = size === "sm" ? 18 : size === "lg" ? 40 : 28
  const screenHeight = size === "sm" ? 64 : size === "lg" ? 160 : 96
  const iconColor = status === "empty" || status === "offline" ? "#374151" : hex
  const glowStrength = status === "active" ? "0 0 18px 4px" : "0 0 10px 2px"
  return (
    <div
      style={{
        backgroundColor: "#030508",
        height: screenHeight,
        borderRadius: 4,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backgroundImage: SCANLINE_BG,
        boxShadow: "inset 0 2px 8px rgba(0,0,0,0.8)",
        position: "relative",
        overflow: "hidden",
        flexShrink: 0,
      }}
    >
      <Icon
        size={iconSize}
        style={{
          color: iconColor,
          filter:
            status !== "empty" && status !== "offline"
              ? `drop-shadow(${glowStrength} ${iconColor}88)`
              : undefined,
        }}
      />
    </div>
  )
}

// ─── DeskCard sub-component ───────────────────────────────────────────────────

interface DeskCardProps {
  station: Station
  onClick: (station: Station) => void
  isSelected: boolean
  compact?: boolean
}

function DeskCard({ station, onClick, isSelected, compact = false }: DeskCardProps) {
  const [hovered, setHovered] = useState(false)
  const handleClick = useCallback(() => onClick(station), [onClick, station])
  const handleMouseEnter = useCallback(() => setHovered(true), [])
  const handleMouseLeave = useCallback(() => setHovered(false), [])
  const { accentHex, status, icon: Icon, label, subtitle, capabilities } = station
  const isActive = status !== "empty" && status !== "offline"
  const glowColor = isActive ? accentHex : "#374151"
  const borderColor = isSelected
    ? accentHex
    : hovered && isActive
      ? `${accentHex}88`
      : "#1a2235"
  const shadowStr = isSelected
    ? `0 0 0 1px ${accentHex}, 0 0 24px 4px ${accentHex}44`
    : hovered && isActive
      ? `0 0 0 1px ${accentHex}66, 0 0 16px 2px ${accentHex}22`
      : "0 2px 8px rgba(0,0,0,0.6)"
  return (
    <div
      onClick={handleClick}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      style={{
        backgroundColor: "#0a1120",
        border: `1px solid ${borderColor}`,
        borderRadius: 8,
        overflow: "hidden",
        cursor: "pointer",
        transition: "transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease",
        transform: hovered ? "translateY(-2px) scale(1.01)" : "none",
        boxShadow: shadowStr,
        display: "flex",
        flexDirection: "column",
        fontFamily: "monospace",
      }}
      role="button"
      tabIndex={0}
      aria-pressed={isSelected}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") handleClick()
      }}
    >
      <div
        style={{
          backgroundColor: `${accentHex}14`,
          borderBottom: `1px solid ${accentHex}22`,
          padding: compact ? "8px 10px" : "10px 12px",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <StatusLight status={status} hex={accentHex} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: compact ? 11 : 12,
              fontWeight: 700,
              color: isActive ? accentHex : "#4b5563",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {label}
          </div>
          <div style={{ fontSize: 10, color: "#4b5563", letterSpacing: "0.04em", marginTop: 1 }}>
            {subtitle}
          </div>
        </div>
        <span
          style={{
            fontSize: 9,
            color: isActive ? glowColor : "#374151",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            border: `1px solid ${isActive ? `${glowColor}44` : "#1f2937"}`,
            borderRadius: 3,
            padding: "1px 5px",
            flexShrink: 0,
          }}
        >
          {status}
        </span>
      </div>
      <div style={{ padding: compact ? "8px 10px" : "10px 12px" }}>
        <MonitorScreen icon={Icon} status={status} hex={accentHex} size={compact ? "sm" : "md"} />
      </div>
      {!compact && (
        <div style={{ padding: "0 12px 10px", display: "flex", gap: 6, flexWrap: "wrap" }}>
          {capabilities.slice(0, 2).map((cap) => (
            <span
              key={cap}
              style={{
                fontSize: 9,
                color: isActive ? accentHex : "#374151",
                border: `1px solid ${isActive ? `${accentHex}33` : "#1f2937"}`,
                borderRadius: 3,
                padding: "2px 6px",
                letterSpacing: "0.05em",
                backgroundColor: isActive ? `${accentHex}08` : "transparent",
              }}
            >
              {cap}
            </span>
          ))}
        </div>
      )}
      <div
        style={{
          height: 6,
          background: isActive
            ? `linear-gradient(90deg, ${accentHex}22, ${accentHex}08, ${accentHex}22)`
            : "linear-gradient(90deg, #0f172a, #1a2235, #0f172a)",
          marginTop: "auto",
        }}
      />
    </div>
  )
}

// ─── InviteConfigModal ────────────────────────────────────────────────────────

interface InviteConfigModalProps {
  station: Station
  onSave: (id: string, config: InviteConfig) => void
  onCancel: () => void
}

const PROVIDER_OPTIONS = [
  { value: "OpenAI", label: "OpenAI (ChatGPT)" },
  { value: "Anthropic", label: "Anthropic (Claude)" },
  { value: "xAI", label: "xAI (Grok)" },
  { value: "Google", label: "Google (Gemini)" },
  { value: "Ollama", label: "Ollama (Local)" },
  { value: "Custom", label: "Custom Provider" },
]

const MODEL_ID_PLACEHOLDER: Record<string, string> = {
  Anthropic: "e.g. claude-sonnet-4-6",
  OpenAI: "e.g. codex-mini-latest or gpt-5",
  xAI: "e.g. xai/grok-4.20-multi-agent-0309",
  Ollama: "e.g. ollama/phi4-mini",
  Google: "e.g. gemini/gemini-1.5-pro",
  Custom: "e.g. openrouter/openai/gpt-4o",
}

function InviteConfigModal({ station, onSave, onCancel }: InviteConfigModalProps) {
  const [label, setLabel] = useState(
    station.label === "Add Agent" ? "" : station.label,
  )
  const defaultProvider =
    station.id === "invite-claude" ? "Anthropic" :
    station.id === "invite-gpt" ? "OpenAI" :
    station.id === "invite-custom" ? "xAI" :
    "Custom"
  const [provider, setProvider] = useState(defaultProvider)
  const [description, setDescription] = useState("")
  const [modelId, setModelId] = useState(
    station.id === "invite-gpt"
      ? "codex-mini-latest"
      : station.id === "invite-custom"
        ? "xai/grok-4.20-multi-agent-0309"
        : "",
  )
  const [apiKey, setApiKey] = useState("")
  const [authMode, setAuthMode] = useState<InviteAuthMode>(
    station.id === "invite-gpt" ? "codex_sub" : "api_key",
  )

  const { accentHex } = station
  const canSave = label.trim().length > 0
  const supportsClaudeOAuth = provider === "Anthropic"
  const supportsCodexSub = provider === "OpenAI"
  const showsAuthModeToggle = supportsClaudeOAuth || supportsCodexSub
  const authModeOptions: InviteAuthMode[] = supportsClaudeOAuth
    ? ["api_key", "oauth"]
    : supportsCodexSub
      ? ["api_key", "codex_sub"]
      : ["api_key"]
  const effectiveAuthMode: InviteAuthMode =
    supportsClaudeOAuth || supportsCodexSub ? authMode : "api_key"

  const handleSave = useCallback(() => {
    if (!canSave) return
    onSave(station.id, {
      label: label.trim(),
      provider,
      description: description.trim(),
      modelId: modelId.trim() || undefined,
      apiKey: apiKey.trim() || undefined,
      authMode: effectiveAuthMode,
    })
  }, [canSave, label, provider, description, modelId, apiKey, effectiveAuthMode, station.id, onSave])

  const inputStyle: React.CSSProperties = {
    width: "100%",
    backgroundColor: "#030508",
    border: "1px solid #1a2235",
    borderRadius: 4,
    padding: "8px 10px",
    fontSize: 12,
    color: "#d1d5db",
    fontFamily: "monospace",
    letterSpacing: "0.03em",
    outline: "none",
    boxSizing: "border-box",
  }

  const labelStyle: React.CSSProperties = {
    fontSize: 10,
    fontWeight: 700,
    color: "#4b5563",
    letterSpacing: "0.1em",
    textTransform: "uppercase",
    marginBottom: 6,
    display: "block",
  }

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onCancel}
        style={{
          position: "fixed",
          inset: 0,
          backgroundColor: "rgba(6,10,19,0.82)",
          zIndex: 60,
          backdropFilter: "blur(2px)",
        }}
      />
      {/* Modal */}
      <div
        style={{
          position: "fixed",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          zIndex: 61,
          width: 380,
          backgroundColor: "#07101e",
          border: `1px solid ${accentHex}`,
          borderRadius: 10,
          boxShadow: `0 0 40px 8px ${accentHex}22`,
          fontFamily: "monospace",
          animation: "slideInPanel 0.18s ease-out",
        }}
      >
        {/* Modal header */}
        <div
          style={{
            backgroundColor: `${accentHex}18`,
            borderBottom: `1px solid ${accentHex}33`,
            padding: "14px 18px",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <Plus size={15} style={{ color: accentHex }} />
          <div style={{ flex: 1 }}>
            <div
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: accentHex,
                letterSpacing: "0.07em",
                textTransform: "uppercase",
              }}
            >
              Invite Agent Desk
            </div>
            <div style={{ fontSize: 10, color: "#6b7280", marginTop: 2 }}>
              {station.label} · {station.id}
            </div>
          </div>
          <button
            onClick={onCancel}
            style={{
              background: "none",
              border: "1px solid #1f2937",
              borderRadius: 4,
              cursor: "pointer",
              color: "#6b7280",
              width: 28,
              height: 28,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
            aria-label="Cancel"
          >
            <X size={13} />
          </button>
        </div>

        {/* Form */}
        <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 14 }}>
          <div>
            <label style={labelStyle}>Display Name *</label>
            <input
              style={inputStyle}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. Claude Sonnet"
              maxLength={32}
              autoFocus
            />
          </div>
          <div>
            <label style={labelStyle}>Provider</label>
            <select
              style={{ ...inputStyle, cursor: "pointer" }}
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
            >
              {PROVIDER_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label style={labelStyle}>Model ID</label>
            <input
              style={inputStyle}
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
              placeholder={MODEL_ID_PLACEHOLDER[provider] ?? "e.g. gpt-4o"}
              maxLength={80}
              spellCheck={false}
            />
            <div style={{ fontSize: 10, color: "#4b5563", marginTop: 4 }}>
              {provider === "Ollama"
                ? "No API key needed — Ollama runs locally."
                : "Leave blank to use the model configured in Controls."}
            </div>
          </div>
          {provider !== "Ollama" && (
            <div>
              {showsAuthModeToggle && (
                <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
                  {authModeOptions.map((mode) => {
                    const active = authMode === mode
                    return (
                      <button
                        key={mode}
                        type="button"
                        onClick={() => setAuthMode(mode)}
                        style={{
                          flex: 1,
                          padding: "6px 8px",
                          fontSize: 10,
                          fontWeight: 700,
                          fontFamily: "monospace",
                          letterSpacing: "0.06em",
                          textTransform: "uppercase",
                          color: active ? "#060a13" : "#9ca3af",
                          backgroundColor: active ? accentHex : "#0b1424",
                          border: `1px solid ${active ? accentHex : "#1f2937"}`,
                          borderRadius: 4,
                          cursor: "pointer",
                        }}
                      >
                        {mode === "api_key" ? "API Key" : "Subscription"}
                      </button>
                    )
                  })}
                </div>
              )}
              <label style={labelStyle}>
                {effectiveAuthMode === "oauth"
                  ? "Claude Subscription Token"
                  : effectiveAuthMode === "codex_sub"
                    ? "OpenAI Subscription Key"
                    : "API Key"}
              </label>
              <input
                style={inputStyle}
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={
                  effectiveAuthMode === "oauth"
                    ? "sk-ant-oat01-…"
                    : effectiveAuthMode === "codex_sub"
                      ? "sk-proj-… or other OpenAI key"
                    : "sk-… or your provider key"
                }
                maxLength={400}
                spellCheck={false}
                autoComplete="off"
              />
              <div style={{ fontSize: 10, color: "#4b5563", marginTop: 4, lineHeight: 1.5 }}>
                {effectiveAuthMode === "oauth" ? (
                  <>
                    Paste your Claude Pro/Max OAuth token — same credential openclaw and Hermes use.
                    Generate with <code style={{ color: "#9ca3af" }}>claude setup-token</code> or copy the{" "}
                    <code style={{ color: "#9ca3af" }}>access_token</code> from{" "}
                    <code style={{ color: "#9ca3af" }}>~/.claude/credentials.json</code>.
                    Stored locally — used only when this seat joins a meeting.
                  </>
                ) : effectiveAuthMode === "codex_sub" ? (
                  <>
                    Use your ChatGPT/Codex-linked OpenAI key here. OpenAI’s current Codex setup uses{" "}
                    <code style={{ color: "#9ca3af" }}>codex --login</code> or{" "}
                    <code style={{ color: "#9ca3af" }}>codex --free</code> to connect a ChatGPT plan and create
                    an API key automatically. Paste that generated OpenAI key here and keep{" "}
                    <code style={{ color: "#9ca3af" }}>codex-mini-latest</code> as the model for a Codex desk.
                    Stored locally — used only when this seat joins a meeting.
                  </>
                ) : provider === "xAI" ? (
                  <>
                    Use an xAI API key for Grok seats. xAI’s official docs currently require an xAI account plus{" "}
                    API key for developer access; Grok app or X subscription status does not replace{" "}
                    <code style={{ color: "#9ca3af" }}>XAI_API_KEY</code> here.
                  </>
                ) : (
                  <>Stored locally — used only when this seat joins a meeting.</>
                )}
              </div>
            </div>
          )}
          <div>
            <label style={labelStyle}>Description (optional)</label>
            <textarea
              style={{
                ...inputStyle,
                height: 56,
                resize: "vertical",
                verticalAlign: "top",
              }}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What will this agent handle?"
              maxLength={120}
            />
          </div>
        </div>

        {/* Actions */}
        <div
          style={{
            padding: "0 18px 18px",
            display: "flex",
            gap: 10,
          }}
        >
          <button
            onClick={onCancel}
            style={{
              flex: 1,
              padding: "9px 0",
              fontSize: 11,
              fontWeight: 700,
              color: "#6b7280",
              backgroundColor: "transparent",
              border: "1px solid #1f2937",
              borderRadius: 6,
              cursor: "pointer",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              fontFamily: "monospace",
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={!canSave}
            style={{
              flex: 1,
              padding: "9px 0",
              fontSize: 11,
              fontWeight: 700,
              color: canSave ? "#060a13" : "#374151",
              backgroundColor: canSave ? accentHex : "#1a2235",
              border: "none",
              borderRadius: 6,
              cursor: canSave ? "pointer" : "not-allowed",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              fontFamily: "monospace",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
              boxShadow: canSave ? `0 0 12px 2px ${accentHex}44` : "none",
              transition: "opacity 0.15s",
            }}
            onMouseEnter={(e) => { if (canSave) e.currentTarget.style.opacity = "0.85" }}
            onMouseLeave={(e) => { e.currentTarget.style.opacity = "1" }}
          >
            <Check size={12} />
            Invite
          </button>
        </div>
      </div>
    </>
  )
}

// ─── StationDetailPanel ───────────────────────────────────────────────────────

interface StationDetailPanelProps {
  station: Station
  onClose: () => void
  onNavigate: (route: string) => void
  projectRoom: ProjectRoom
  onAddToRoom: (id: string) => void
  onRemoveFromRoom: (id: string) => void
  availableSeatCount: number
  onLaunchSparkBud: (station: Station, config: { prompt: string; agentName?: string }) => Promise<string | null>
  launchingSparkBudId: string | null
}

function StationDetailPanel({
  station,
  onClose,
  onNavigate,
  projectRoom,
  onAddToRoom,
  onRemoveFromRoom,
  availableSeatCount,
  onLaunchSparkBud,
  launchingSparkBudId,
}: StationDetailPanelProps) {
  const {
    accentHex,
    status,
    icon: Icon,
    label,
    subtitle,
    description,
    capabilities,
    type,
    route,
    invitePrompt,
    id,
  } = station

  const isActive = status !== "empty" && status !== "offline"
  const isSparkbot = id === "sparkbot"
  const isSparkBud = type === "sparkbud"
  const isModelOffice = id.startsWith("stack-")
  const isInRoom = isStationAssigned(projectRoom, id)
  const canToggleRoom = type !== "table" && type !== "terminal"
  const sparkBudLaunchConfig = isSparkBud ? getSparkBudLaunchConfig(id) : null
  const [launchPrompt, setLaunchPrompt] = useState(sparkBudLaunchConfig?.defaultPrompt ?? "")
  const [launchAgentName, setLaunchAgentName] = useState(sparkBudLaunchConfig?.defaultHandle ?? "")
  const [launchError, setLaunchError] = useState("")

  useEffect(() => {
    setLaunchPrompt(sparkBudLaunchConfig?.defaultPrompt ?? "")
    setLaunchAgentName(sparkBudLaunchConfig?.defaultHandle ?? "")
    setLaunchError("")
  }, [sparkBudLaunchConfig, station.id])

  const resetLaunchPrompt = useCallback(() => {
    if (!sparkBudLaunchConfig) return
    setLaunchPrompt(sparkBudLaunchConfig.defaultPrompt)
    if (sparkBudLaunchConfig.defaultHandle) {
      setLaunchAgentName(sparkBudLaunchConfig.defaultHandle)
    }
    setLaunchError("")
  }, [sparkBudLaunchConfig])

  const handleNavigate = useCallback(() => {
    if (route) onNavigate(route)
  }, [route, onNavigate])

  const handleLaunchSparkBud = useCallback(async () => {
    if (!sparkBudLaunchConfig || !launchPrompt.trim()) return
    setLaunchError("")
    const result = await onLaunchSparkBud(station, {
      prompt: launchPrompt,
      agentName: sparkBudLaunchConfig.launchMode === "custom" ? launchAgentName : undefined,
    })
    if (result) setLaunchError(result)
  }, [launchAgentName, launchPrompt, onLaunchSparkBud, sparkBudLaunchConfig, station])

  // Primary action
  let actionLabel = "Coming Soon"
  let actionDisabled = true
  let actionHandler: (() => void) | undefined

  if (isSparkBud) {
    actionLabel = "Launch"
    actionDisabled = false
    actionHandler = handleLaunchSparkBud
  } else if (route && isActive) {
    actionLabel = isSparkbot
      ? "Open Main Chat"
      : isModelOffice
        ? "Review in Controls"
        : "Open Station"
    actionDisabled = false
    actionHandler = handleNavigate
  } else if (type === "invite" && status === "idle") {
    actionLabel = "Open Chat (Phase 3)"
    actionDisabled = true
  } else if (type === "invite" && status === "empty") {
    actionLabel = "Configure Agent"
    actionDisabled = false
    actionHandler = () => {} // handled upstream
  }

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        bottom: 0,
        width: 320,
        backgroundColor: "#07101e",
        borderLeft: `1px solid ${accentHex}`,
        boxShadow: `-4px 0 32px ${accentHex}22`,
        zIndex: 50,
        display: "flex",
        flexDirection: "column",
        fontFamily: "monospace",
        overflowY: "auto",
        animation: "slideInPanel 0.2s ease-out",
      }}
    >
      {/* Panel header */}
      <div
        style={{
          backgroundColor: `${accentHex}18`,
          borderBottom: `1px solid ${accentHex}33`,
          padding: "14px 16px",
          display: "flex",
          alignItems: "center",
          gap: 10,
          flexShrink: 0,
        }}
      >
        <StatusLight status={status} hex={accentHex} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 700,
              color: isActive ? accentHex : "#4b5563",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
            }}
          >
            {label}
          </div>
          <div style={{ fontSize: 10, color: "#6b7280", letterSpacing: "0.04em" }}>{subtitle}</div>
        </div>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border: "1px solid #1f2937",
            borderRadius: 4,
            cursor: "pointer",
            color: "#6b7280",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 28,
            height: 28,
            flexShrink: 0,
          }}
          aria-label="Close panel"
        >
          <X size={14} />
        </button>
      </div>

      {/* Monitor screen */}
      <div style={{ padding: "16px 16px 8px" }}>
        <MonitorScreen icon={Icon} status={status} hex={accentHex} size="lg" />
      </div>

      {/* Description */}
      <div style={{ padding: "8px 16px 12px" }}>
        <p style={{ fontSize: 11, color: "#9ca3af", lineHeight: 1.65, margin: 0 }}>
          {description}
        </p>
      </div>

      {/* Invite prompt (unconfigured desks) */}
      {invitePrompt && (
        <div
          style={{
            margin: "0 16px 12px",
            backgroundColor: `${accentHex}0c`,
            border: `1px solid ${accentHex}33`,
            borderRadius: 6,
            padding: "10px 12px",
          }}
        >
          <div
            style={{
              fontSize: 10,
              color: accentHex,
              letterSpacing: "0.05em",
              textTransform: "uppercase",
              marginBottom: 4,
              fontWeight: 700,
            }}
          >
            Setup Required
          </div>
          <p style={{ fontSize: 10, color: "#9ca3af", lineHeight: 1.6, margin: 0 }}>
            {invitePrompt}
          </p>
        </div>
      )}

      {/* Capability chips */}
      <div style={{ padding: "0 16px 16px" }}>
        <div
          style={{
            fontSize: 10,
            color: "#4b5563",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            marginBottom: 8,
            fontWeight: 700,
          }}
        >
          Capabilities
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {capabilities.map((cap) => (
            <span
              key={cap}
              style={{
                fontSize: 10,
                color: isActive ? accentHex : "#4b5563",
                border: `1px solid ${isActive ? `${accentHex}44` : "#1f2937"}`,
                borderRadius: 4,
                padding: "3px 8px",
                letterSpacing: "0.04em",
                backgroundColor: isActive ? `${accentHex}0a` : "transparent",
              }}
            >
              {cap}
            </span>
          ))}
        </div>
      </div>

      {isSparkbot && (
        <>
          <div style={{ height: 1, backgroundColor: "#1a2235", margin: "0 16px" }} />

          <div style={{ padding: "12px 16px 16px" }}>
            <div
              style={{
                fontSize: 10,
                color: "#4b5563",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                marginBottom: 8,
                fontWeight: 700,
              }}
            >
              Sparkbot Controls
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <button
                onClick={() => onNavigate("/dm")}
                style={{
                  width: "100%",
                  padding: "9px 10px",
                  fontSize: 11,
                  fontWeight: 700,
                  color: "#060a13",
                  backgroundColor: accentHex,
                  border: "none",
                  borderRadius: 6,
                  cursor: "pointer",
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  fontFamily: "monospace",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 6,
                  boxShadow: `0 0 12px 2px ${accentHex}44`,
                }}
              >
                <ExternalLink size={12} />
                Open Main Sparkbot Chat
              </button>

              <button
                onClick={() => onNavigate("/dm?controls=open")}
                style={{
                  width: "100%",
                  padding: "9px 10px",
                  fontSize: 11,
                  fontWeight: 700,
                  color: accentHex,
                  backgroundColor: "#0a1120",
                  border: `1px solid ${accentHex}55`,
                  borderRadius: 6,
                  cursor: "pointer",
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  fontFamily: "monospace",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 6,
                }}
              >
                <SlidersHorizontal size={12} />
                Open Sparkbot Controls
              </button>

              <div
                style={{
                  backgroundColor: "#0a1120",
                  border: `1px solid ${accentHex}22`,
                  borderRadius: 6,
                  padding: "10px 12px",
                }}
              >
                <div
                  style={{
                    fontSize: 10,
                    color: accentHex,
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    marginBottom: 4,
                    fontWeight: 700,
                  }}
                >
                  Everyday use
                </div>
                <p style={{ fontSize: 10, color: "#9ca3af", lineHeight: 1.6, margin: 0 }}>
                  Daily prompting, reminders, file analysis, and slash commands all live in chat.
                  Open Sparkbot DM and type <span style={{ color: accentHex }}>/help</span> for the
                  current command surface.
                </p>
              </div>

              <div
                style={{
                  backgroundColor: "#0a1120",
                  border: `1px solid ${accentHex}22`,
                  borderRadius: 6,
                  padding: "10px 12px",
                }}
              >
                <div
                  style={{
                    fontSize: 10,
                    color: accentHex,
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    marginBottom: 4,
                    fontWeight: 700,
                  }}
                >
                  Setup and safety
                </div>
                <p style={{ fontSize: 10, color: "#9ca3af", lineHeight: 1.6, margin: 0 }}>
                  Provider keys, model stack, channels, Token Guardian, Task Guardian, and room
                  safety settings all remain in Sparkbot Controls today.
                </p>
              </div>

              <div
                style={{
                  backgroundColor: "#0a1120",
                  border: `1px solid ${accentHex}22`,
                  borderRadius: 6,
                  padding: "10px 12px",
                }}
              >
                <div
                  style={{
                    fontSize: 10,
                    color: accentHex,
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    marginBottom: 4,
                    fontWeight: 700,
                  }}
                >
                  Workstation role
                </div>
                <p style={{ fontSize: 10, color: "#9ca3af", lineHeight: 1.6, margin: 0 }}>
                  Workstation is the desktop overview around Chat and Controls. It is meant to feel
                  clear and calm, not like a hidden admin console.
                </p>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Divider */}
      <div style={{ height: 1, backgroundColor: "#1a2235", margin: "0 16px" }} />

      {/* Round Table membership */}
      {canToggleRoom && (
        <div style={{ padding: "12px 16px" }}>
          <div
            style={{
              fontSize: 10,
              color: "#4b5563",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              marginBottom: 8,
              fontWeight: 700,
            }}
          >
            Project Room
          </div>
          {isInRoom ? (
            <button
              onClick={() => onRemoveFromRoom(id)}
              style={{
                width: "100%",
                padding: "8px 0",
                fontSize: 11,
                fontWeight: 700,
                color: "#f87171",
                backgroundColor: "transparent",
                border: "1px solid #7f1d1d",
                borderRadius: 6,
                cursor: "pointer",
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                fontFamily: "monospace",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 6,
              }}
            >
              <UserMinus size={12} />
              Leave Table
            </button>
          ) : availableSeatCount === 0 ? (
            <div
              style={{
                width: "100%",
                padding: "8px 10px",
                fontSize: 11,
                color: "#6b7280",
                border: "1px solid #1f2937",
                borderRadius: 6,
                backgroundColor: "#0a1120",
                lineHeight: 1.6,
              }}
            >
              All eight chairs are filled. Clear a seat or reassign a chair from the table.
            </div>
          ) : (
            <button
              onClick={() => onAddToRoom(id)}
              style={{
                width: "100%",
                padding: "8px 0",
                fontSize: 11,
                fontWeight: 700,
                color: "#4b5563",
                backgroundColor: "transparent",
                border: "1px solid #1f2937",
                borderRadius: 6,
                cursor: "pointer",
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                fontFamily: "monospace",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 6,
                transition: "border-color 0.15s, color 0.15s",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = "#f59e0b44"
                e.currentTarget.style.color = "#f59e0b"
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = "#1f2937"
                e.currentTarget.style.color = "#4b5563"
              }}
            >
              <UserPlus size={12} />
              Add to Table
            </button>
          )}
        </div>
      )}

      {canToggleRoom && <div style={{ height: 1, backgroundColor: "#1a2235", margin: "0 16px" }} />}

      {sparkBudLaunchConfig && (
        <>
          <div style={{ padding: "12px 16px 16px" }}>
            <div
              style={{
                fontSize: 10,
                color: "#4b5563",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                marginBottom: 8,
                fontWeight: 700,
              }}
            >
              Launch Prep
            </div>

            <div
              style={{
                backgroundColor: "#0a1120",
                border: `1px solid ${accentHex}22`,
                borderRadius: 6,
                padding: "10px 12px",
                marginBottom: 10,
              }}
            >
              <div
                style={{
                  fontSize: 10,
                  color: accentHex,
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  marginBottom: 4,
                  fontWeight: 700,
                }}
              >
                Role
              </div>
              <p style={{ fontSize: 10, color: "#9ca3af", lineHeight: 1.6, margin: 0 }}>
                {sparkBudLaunchConfig.summary}
              </p>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 10 }}>
                <span
                  style={{
                    fontSize: 9,
                    color: accentHex,
                    border: `1px solid ${accentHex}33`,
                    borderRadius: 999,
                    padding: "3px 8px",
                    letterSpacing: "0.05em",
                    textTransform: "uppercase",
                    backgroundColor: `${accentHex}10`,
                  }}
                >
                  {sparkBudLaunchConfig.launchModeLabel}
                </span>
                <span
                  style={{
                    fontSize: 9,
                    color: "#cbd5f5",
                    border: "1px solid rgba(125,211,252,0.18)",
                    borderRadius: 999,
                    padding: "3px 8px",
                    letterSpacing: "0.05em",
                    textTransform: "uppercase",
                    backgroundColor: "rgba(10,17,32,0.72)",
                  }}
                >
                  {sparkBudLaunchConfig.launchOutcomeLabel}
                </span>
              </div>
            </div>

            {sparkBudLaunchConfig.launchMode === "custom" && (
              <div style={{ marginBottom: 10 }}>
                <label
                  style={{
                    display: "block",
                    fontSize: 10,
                    color: "#4b5563",
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    marginBottom: 6,
                    fontWeight: 700,
                  }}
                >
                  Agent handle
                </label>
                <input
                  value={launchAgentName}
                  onChange={(event) =>
                    setLaunchAgentName(
                      event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""),
                    )
                  }
                  placeholder="specialist"
                  maxLength={32}
                  style={{
                    width: "100%",
                    backgroundColor: "#030508",
                    border: "1px solid #1a2235",
                    borderRadius: 4,
                    padding: "8px 10px",
                    fontSize: 12,
                    color: "#d1d5db",
                    fontFamily: "monospace",
                    letterSpacing: "0.03em",
                    outline: "none",
                    boxSizing: "border-box",
                  }}
                />
              </div>
            )}

            <div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 8,
                  marginBottom: 6,
                }}
              >
                <label
                  style={{
                    display: "block",
                    fontSize: 10,
                    color: "#4b5563",
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    fontWeight: 700,
                  }}
                >
                  Preloaded launch prompt
                </label>
                <button
                  type="button"
                  onClick={resetLaunchPrompt}
                  style={{
                    background: "none",
                    border: "1px solid #1f2937",
                    borderRadius: 999,
                    padding: "3px 8px",
                    cursor: "pointer",
                    fontSize: 9,
                    color: "#94a3b8",
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    fontFamily: "monospace",
                  }}
                >
                  Reset default
                </button>
              </div>
              <textarea
                value={launchPrompt}
                onChange={(event) => setLaunchPrompt(event.target.value)}
                rows={7}
                style={{
                  width: "100%",
                  backgroundColor: "#030508",
                  border: "1px solid #1a2235",
                  borderRadius: 4,
                  padding: "8px 10px",
                  fontSize: 11,
                  color: "#d1d5db",
                  fontFamily: "monospace",
                  lineHeight: 1.6,
                  letterSpacing: "0.03em",
                  outline: "none",
                  boxSizing: "border-box",
                  resize: "vertical",
                  minHeight: 136,
                }}
              />
            </div>

            <p style={{ fontSize: 10, color: "#94a3b8", lineHeight: 1.6, margin: "8px 0 0" }}>
              {sparkBudLaunchConfig.helperText}
            </p>
            {sparkBudLaunchConfig.launchMode === "custom" && (
              <p style={{ fontSize: 10, color: "#64748b", lineHeight: 1.6, margin: "6px 0 0" }}>
                Handles must be lowercase and unique within this workspace.
              </p>
            )}

            {launchError && (
              <div
                style={{
                  marginTop: 10,
                  border: "1px solid rgba(248,113,113,0.3)",
                  borderRadius: 6,
                  padding: "9px 10px",
                  backgroundColor: "rgba(127,29,29,0.16)",
                  color: "#fca5a5",
                  fontSize: 10,
                  lineHeight: 1.6,
                }}
              >
                {launchError}
              </div>
            )}
          </div>

          <div style={{ height: 1, backgroundColor: "#1a2235", margin: "0 16px" }} />
        </>
      )}

      {/* Primary action button */}
      <div style={{ padding: 16, marginTop: "auto" }}>
        {sparkBudLaunchConfig ? (
          <div style={{ display: "flex", gap: 10 }}>
            <button
              onClick={onClose}
              style={{
                flex: 1,
                padding: "10px 0",
                fontSize: 12,
                fontWeight: 700,
                color: "#94a3b8",
                backgroundColor: "transparent",
                border: "1px solid #1f2937",
                borderRadius: 6,
                cursor: "pointer",
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                fontFamily: "monospace",
              }}
            >
              Cancel
            </button>
            <button
              onClick={handleLaunchSparkBud}
              disabled={
                launchingSparkBudId === station.id ||
                !launchPrompt.trim() ||
                (sparkBudLaunchConfig.launchMode === "custom" && !launchAgentName.trim())
              }
              style={{
                flex: 1,
                padding: "10px 0",
                fontSize: 12,
                fontWeight: 700,
                color:
                  launchingSparkBudId === station.id ||
                  !launchPrompt.trim() ||
                  (sparkBudLaunchConfig.launchMode === "custom" && !launchAgentName.trim())
                    ? "#64748b"
                    : "#060a13",
                backgroundColor:
                  launchingSparkBudId === station.id ||
                  !launchPrompt.trim() ||
                  (sparkBudLaunchConfig.launchMode === "custom" && !launchAgentName.trim())
                    ? "#1a2235"
                    : accentHex,
                border: "none",
                borderRadius: 6,
                cursor:
                  launchingSparkBudId === station.id ||
                  !launchPrompt.trim() ||
                  (sparkBudLaunchConfig.launchMode === "custom" && !launchAgentName.trim())
                    ? "not-allowed"
                    : "pointer",
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                fontFamily: "monospace",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 6,
                boxShadow:
                  launchingSparkBudId === station.id ||
                  !launchPrompt.trim() ||
                  (sparkBudLaunchConfig.launchMode === "custom" && !launchAgentName.trim())
                    ? "none"
                    : `0 0 14px 2px ${accentHex}55`,
              }}
            >
              <Rocket size={13} />
              {launchingSparkBudId === station.id ? "Launching..." : "Launch"}
            </button>
          </div>
        ) : actionDisabled ? (
          <div
            style={{
              width: "100%",
              padding: "10px 0",
              textAlign: "center",
              fontSize: 12,
              color: "#374151",
              border: "1px solid #1f2937",
              borderRadius: 6,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              fontFamily: "monospace",
            }}
          >
            {actionLabel}
          </div>
        ) : (
          <button
            onClick={actionHandler}
            style={{
              width: "100%",
              padding: "10px 0",
              fontSize: 12,
              fontWeight: 700,
              color: "#060a13",
              backgroundColor: accentHex,
              border: "none",
              borderRadius: 6,
              cursor: "pointer",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              fontFamily: "monospace",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
              boxShadow: `0 0 14px 2px ${accentHex}55`,
              transition: "opacity 0.15s",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.opacity = "0.85" }}
            onMouseLeave={(e) => { e.currentTarget.style.opacity = "1" }}
          >
            <ExternalLink size={13} />
            {actionLabel}
          </button>
        )}
      </div>
    </div>
  )
}

// ─── RoundTablePanel ──────────────────────────────────────────────────────────

interface RoundTablePanelProps {
  projectRoom: ProjectRoom
  onClose: () => void
  onAddToRoom: (id: string) => void
  onRemoveFromRoom: (id: string) => void
  eligibleStations: Station[]
  onPickSeat: (seatIndex: number) => void
  onLaunchMeeting: () => void
  onAutoFillStack: () => void
  launchingMeeting: boolean
  meetingLaunchError?: string | null
}

function RoundTablePanel({
  projectRoom,
  onClose,
  onAddToRoom,
  onRemoveFromRoom,
  eligibleStations,
  onPickSeat,
  onLaunchMeeting,
  onAutoFillStack,
  launchingMeeting,
  meetingLaunchError,
}: RoundTablePanelProps) {
  const accentHex = ROUND_TABLE.accentHex
  const assignedIds = getAssignedStationIds(projectRoom)
  const participants = assignedIds
    .map((id) => eligibleStations.find((station) => station.id === id) ?? null)
    .filter((station): station is Station => Boolean(station))
  const available = eligibleStations.filter((s) => !assignedIds.includes(s.id))
  const canLaunchMeeting = participants.length >= 2

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        bottom: 0,
        width: 320,
        backgroundColor: "#07101e",
        borderLeft: `1px solid ${accentHex}`,
        boxShadow: `-4px 0 32px ${accentHex}22`,
        zIndex: 50,
        display: "flex",
        flexDirection: "column",
        fontFamily: "monospace",
        overflowY: "auto",
        animation: "slideInPanel 0.2s ease-out",
      }}
    >
      {/* Header */}
      <div
        style={{
          backgroundColor: `${accentHex}18`,
          borderBottom: `1px solid ${accentHex}33`,
          padding: "14px 16px",
          display: "flex",
          alignItems: "center",
          gap: 10,
          flexShrink: 0,
        }}
      >
        <Users size={15} style={{ color: accentHex }} />
        <div style={{ flex: 1 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 700,
              color: accentHex,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
            }}
          >
            Project Room
          </div>
          <div style={{ fontSize: 10, color: "#6b7280", marginTop: 2 }}>
            {projectRoom.roomName}
          </div>
        </div>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border: "1px solid #1f2937",
            borderRadius: 4,
            cursor: "pointer",
            color: "#6b7280",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 28,
            height: 28,
            flexShrink: 0,
          }}
          aria-label="Close panel"
        >
          <X size={14} />
        </button>
      </div>

      <div style={{ padding: "14px 16px 0" }}>
        <div
          style={{
            fontSize: 10,
            fontWeight: 700,
            color: "#4b5563",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            marginBottom: 10,
          }}
        >
          Table Protocol
        </div>
        <div
          style={{
            border: "1px solid rgba(125,211,252,0.14)",
            borderRadius: 8,
            backgroundColor: "rgba(10,17,32,0.72)",
            padding: "10px 12px",
          }}
        >
          <div style={{ fontSize: 11, color: "#e2e8f0", fontWeight: 700 }}>
            One at a time
          </div>
          <p style={{ fontSize: 10, color: "#94a3b8", lineHeight: 1.6, margin: "6px 0 0" }}>
            This MVP room launches in turn-taking mode. Keep one speaker active at a time, then
            hand the floor to the next participant.
          </p>
        </div>
      </div>

      <div style={{ padding: "12px 16px 0" }}>
        <button
          onClick={onAutoFillStack}
          style={{
            width: "100%",
            padding: "8px 0",
            fontSize: 11,
            fontWeight: 700,
            color: "#8b93ff",
            backgroundColor: "transparent",
            border: "1px solid rgba(139,147,255,0.3)",
            borderRadius: 6,
            cursor: "pointer",
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            fontFamily: "monospace",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 6,
          }}
          onMouseEnter={(e) => { e.currentTarget.style.borderColor = "rgba(139,147,255,0.6)" }}
          onMouseLeave={(e) => { e.currentTarget.style.borderColor = "rgba(139,147,255,0.3)" }}
        >
          <Layers size={11} />
          Auto-fill Stack
        </button>
      </div>

      <div style={{ padding: "14px 16px 0" }}>
        <div
          style={{
            fontSize: 10,
            fontWeight: 700,
            color: "#4b5563",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            marginBottom: 10,
          }}
        >
          Eight Chairs
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          {projectRoom.seats.map((seatId, index) => {
            const station = eligibleStations.find((candidate) => candidate.id === seatId) ?? null
            const seatAccent = station?.accentHex ?? "rgba(125,211,252,0.28)"
            return (
              <button
                key={`seat-${index}`}
                type="button"
                onClick={() => onPickSeat(index)}
                style={{
                  border: `1px solid ${station ? `${seatAccent}33` : "rgba(125,211,252,0.16)"}`,
                  borderRadius: 10,
                  padding: "10px 12px",
                  backgroundColor: station ? `${seatAccent}10` : "rgba(10,17,32,0.72)",
                  textAlign: "left",
                  cursor: "pointer",
                }}
              >
                <div
                  style={{
                    fontSize: 9,
                    color: "#94a3b8",
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                  }}
                >
                  Chair {index + 1}
                </div>
                <div
                  style={{
                    fontSize: 12,
                    color: station ? "#e2e8f0" : "#64748b",
                    fontWeight: 700,
                    marginTop: 6,
                  }}
                >
                  {station?.label ?? "Assign participant"}
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* Participants section */}
      <div style={{ padding: "14px 16px 0" }}>
        <div
          style={{
            fontSize: 10,
            fontWeight: 700,
            color: "#4b5563",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            marginBottom: 10,
          }}
        >
          At the Table ({participants.length})
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {participants.map((s) => {
            const isSparkbot = s.id === "sparkbot"
            return (
              <div
                key={s.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "8px 10px",
                  backgroundColor: "#0a1120",
                  border: `1px solid ${s.accentHex}22`,
                  borderRadius: 6,
                }}
              >
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    backgroundColor: s.accentHex,
                    boxShadow: `0 0 6px 2px ${s.accentHex}66`,
                    flexShrink: 0,
                  }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: 11,
                      fontWeight: 700,
                      color: s.accentHex,
                      letterSpacing: "0.05em",
                      textTransform: "uppercase",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {s.label}
                  </div>
                  <div style={{ fontSize: 9, color: "#4b5563", marginTop: 1 }}>{s.subtitle}</div>
                </div>
                {isSparkbot ? (
                  <span style={{ fontSize: 9, color: "#4b5563", letterSpacing: "0.06em" }}>
                    HOST
                  </span>
                ) : (
                  <button
                    onClick={() => onRemoveFromRoom(s.id)}
                    style={{
                      background: "none",
                      border: "1px solid #7f1d1d",
                      borderRadius: 3,
                      cursor: "pointer",
                      color: "#f87171",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      width: 22,
                      height: 22,
                      flexShrink: 0,
                    }}
                    aria-label={`Remove ${s.label}`}
                  >
                    <X size={10} />
                  </button>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {available.length > 0 && (
        <div style={{ padding: "14px 16px" }}>
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              color: "#4b5563",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              marginBottom: 10,
            }}
          >
            Add from desks
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {available.map((station) => (
              <button
                key={station.id}
                onClick={() => onAddToRoom(station.id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "8px 10px",
                  backgroundColor: "transparent",
                  border: "1px solid #1a2235",
                  borderRadius: 6,
                  cursor: "pointer",
                  textAlign: "left",
                  transition: "border-color 0.15s",
                  width: "100%",
                }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = `${station.accentHex}44` }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = "#1a2235" }}
              >
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    backgroundColor: `${station.accentHex}44`,
                    border: `1px solid ${station.accentHex}66`,
                    flexShrink: 0,
                  }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: 11,
                      fontWeight: 700,
                      color: "#cbd5e1",
                      letterSpacing: "0.05em",
                      textTransform: "uppercase",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      fontFamily: "monospace",
                    }}
                  >
                    {station.label}
                  </div>
                  <div style={{ fontSize: 9, color: "#64748b", marginTop: 1, fontFamily: "monospace" }}>
                    {station.subtitle}
                  </div>
                </div>
                <ChevronRight size={12} style={{ color: "#374151", flexShrink: 0 }} />
              </button>
            ))}
          </div>
        </div>
      )}

      <div
        style={{
          padding: 16,
          marginTop: "auto",
          display: "flex",
          flexDirection: "column",
          gap: 10,
        }}
      >
        <div
          style={{
            fontSize: 10,
            color: "#64748b",
            lineHeight: 1.6,
          }}
        >
          Launch meeting becomes available once at least two chairs are filled.
        </div>
        <button
          onClick={onLaunchMeeting}
          disabled={!canLaunchMeeting || launchingMeeting}
          style={{
            width: "100%",
            padding: "10px 0",
            fontSize: 12,
            fontWeight: 700,
            color: canLaunchMeeting && !launchingMeeting ? "#04101d" : "#475569",
            background: canLaunchMeeting && !launchingMeeting
              ? "linear-gradient(135deg, rgba(245,158,11,0.94), rgba(249,115,22,0.88), rgba(125,211,252,0.42))"
              : "#111827",
            border: "none",
            borderRadius: 8,
            cursor: canLaunchMeeting && !launchingMeeting ? "pointer" : "not-allowed",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            fontFamily: "monospace",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
            boxShadow: canLaunchMeeting && !launchingMeeting
              ? "0 18px 32px rgba(249,115,22,0.18)"
              : "none",
          }}
        >
          {launchingMeeting ? <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} /> : <Rocket size={13} />}
          {launchingMeeting ? "Launching…" : "Launch Meeting"}
        </button>
        {meetingLaunchError && (
          <p style={{ marginTop: 6, fontSize: 11, color: "#f87171", lineHeight: 1.5 }}>
            {meetingLaunchError}
          </p>
        )}
      </div>
    </div>
  )
}

interface SeatPickerModalProps {
  seatIndex: number
  assignedStation: Station | null
  availableStations: Station[]
  onAssign: (stationId: string) => void
  onClear: () => void
  onClose: () => void
}

function SeatPickerModal({
  seatIndex,
  assignedStation,
  availableStations,
  onAssign,
  onClear,
  onClose,
}: SeatPickerModalProps) {
  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          backgroundColor: "rgba(6,10,19,0.82)",
          zIndex: 62,
          backdropFilter: "blur(2px)",
        }}
      />
      <div
        style={{
          position: "fixed",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          zIndex: 63,
          width: "min(92vw, 420px)",
          backgroundColor: "#07101e",
          border: `1px solid ${PLASMA_BORDER}`,
          borderRadius: 12,
          boxShadow: "0 0 40px rgba(0,0,0,0.42)",
          overflow: "hidden",
          fontFamily: "monospace",
        }}
      >
        <div
          style={{
            padding: "14px 16px",
            borderBottom: "1px solid rgba(99,102,241,0.16)",
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: 12,
          }}
        >
          <div>
            <div
              style={{
                fontSize: 10,
                color: "#8b93ff",
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                fontWeight: 700,
              }}
            >
              Chair {seatIndex + 1}
            </div>
            <div style={{ fontSize: 18, color: "#e2e8f0", fontWeight: 700, marginTop: 6 }}>
              {assignedStation ? assignedStation.label : "Assign participant"}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              width: 30,
              height: 30,
              borderRadius: 999,
              border: "1px solid rgba(99,102,241,0.16)",
              backgroundColor: "rgba(7, 13, 28, 0.72)",
              color: "#94a3b8",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
            aria-label="Close chair picker"
          >
            <X size={14} />
          </button>
        </div>

        <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 8 }}>
          {assignedStation && (
            <button
              type="button"
              onClick={onClear}
              style={{
                border: "1px solid rgba(248,113,113,0.28)",
                borderRadius: 8,
                backgroundColor: "rgba(69,10,10,0.28)",
                color: "#fca5a5",
                padding: "10px 12px",
                textAlign: "left",
                cursor: "pointer",
                fontSize: 11,
                letterSpacing: "0.05em",
                textTransform: "uppercase",
              }}
            >
              Clear this chair
            </button>
          )}

          {availableStations.map((station) => (
            <button
              key={station.id}
              type="button"
              onClick={() => onAssign(station.id)}
              style={{
                border: `1px solid ${station.accentHex}22`,
                borderRadius: 10,
                backgroundColor: `${station.accentHex}0e`,
                padding: "10px 12px",
                display: "flex",
                alignItems: "center",
                gap: 10,
                textAlign: "left",
                cursor: "pointer",
              }}
            >
              <span
                style={{
                  width: 9,
                  height: 9,
                  borderRadius: "50%",
                  backgroundColor: station.accentHex,
                  boxShadow: `0 0 10px ${station.accentHex}55`,
                  flexShrink: 0,
                }}
              />
              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    fontSize: 11,
                    color: "#e2e8f0",
                    fontWeight: 700,
                    letterSpacing: "0.05em",
                    textTransform: "uppercase",
                  }}
                >
                  {station.label}
                </div>
                <div style={{ fontSize: 10, color: "#64748b", marginTop: 2 }}>
                  {station.subtitle}
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>
    </>
  )
}

// ─── ComputerControlPanel ─────────────────────────────────────────────────────
// Hub showing Shell, Terminal, and Browser capabilities with quick-start prompts.

interface ComputerControlPanelProps {
  onClose: () => void
  onOpenTerminal: () => void
  status: ComputerControlRoomStatus
}

function ComputerControlPanel({ onClose, onOpenTerminal, status }: ComputerControlPanelProps) {
  const ACCENT = "#38bdf8"
  const enabled = status.enabled === true
  const badgeText = enabled ? "Always on" : "PIN gated"
  const badgeColor = enabled ? "#4ade80" : "#fbbf24"

  const cap = (
    icon: React.ReactNode,
    title: string,
    badge: string,
    badgeColor: string,
    desc: string,
    actionLabel: string,
    onAction: () => void,
    examples: string[],
  ) => (
    <div
      style={{
        border: `1px solid ${ACCENT}1a`,
        borderRadius: 10,
        padding: "14px 16px",
        backgroundColor: "#040d1a",
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ color: ACCENT }}>{icon}</span>
        <span style={{ fontSize: 13, fontWeight: 700, color: "#e2e8f0", letterSpacing: "0.04em" }}>
          {title}
        </span>
        <span
          style={{
            marginLeft: "auto",
            fontSize: 9,
            color: badgeColor,
            border: `1px solid ${badgeColor}44`,
            borderRadius: 3,
            padding: "1px 7px",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
          }}
        >
          {badge}
        </span>
      </div>
      <p style={{ fontSize: 11, color: "#94a3b8", lineHeight: 1.65, margin: 0 }}>{desc}</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {examples.map((ex) => (
          <span
            key={ex}
            style={{
              fontSize: 10,
              color: "#7dd3fc",
              backgroundColor: "#0c1f35",
              borderRadius: 4,
              padding: "2px 8px",
              fontFamily: "monospace",
            }}
          >
            {ex}
          </span>
        ))}
      </div>
      <button
        onClick={onAction}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          background: `${ACCENT}18`,
          border: `1px solid ${ACCENT}44`,
          borderRadius: 6,
          cursor: "pointer",
          color: ACCENT,
          fontSize: 11,
          padding: "6px 12px",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          fontWeight: 600,
          alignSelf: "flex-start",
        }}
      >
        <Zap size={11} />
        {actionLabel}
      </button>
    </div>
  )

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        bottom: 0,
        width: 380,
        backgroundColor: "#07101e",
        borderLeft: `1px solid ${ACCENT}`,
        boxShadow: `-4px 0 32px ${ACCENT}22`,
        zIndex: 50,
        display: "flex",
        flexDirection: "column",
        fontFamily: "system-ui, sans-serif",
        overflow: "hidden",
        animation: "slideInPanel 0.2s ease-out",
      }}
    >
      {/* Header */}
      <div
        style={{
          backgroundColor: `${ACCENT}18`,
          borderBottom: `1px solid ${ACCENT}33`,
          padding: "12px 16px",
          display: "flex",
          alignItems: "center",
          gap: 10,
          flexShrink: 0,
        }}
      >
        <MonitorCog size={15} style={{ color: ACCENT }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: ACCENT, letterSpacing: "0.06em", textTransform: "uppercase" }}>
            Computer Control
          </div>
          <div style={{ fontSize: 10, color: "#6b7280", marginTop: 1 }}>
            Shell · Terminal · Browser
          </div>
        </div>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border: "1px solid #1f2937",
            borderRadius: 4,
            cursor: "pointer",
            color: "#6b7280",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 28,
            height: 28,
          }}
        >
          <X size={14} />
        </button>
      </div>

      {/* Capabilities */}
      <div style={{ flex: 1, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
        <p style={{ fontSize: 11, color: "#64748b", margin: 0, lineHeight: 1.65 }}>
          Sparkbot can control your local machine. Just ask it in chat — or use the terminal panel
          to interact live. This follows the Computer Control checkbox in Sparkbot Controls.
        </p>

        <div
          style={{
            border: `1px solid ${badgeColor}44`,
            borderRadius: 8,
            padding: "10px 12px",
            backgroundColor: enabled ? "rgba(74,222,128,0.08)" : "rgba(251,191,36,0.08)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
            <span style={{ fontSize: 10, color: "#94a3b8", letterSpacing: "0.1em", textTransform: "uppercase", fontWeight: 700 }}>
              Controls status
            </span>
            <span style={{ fontSize: 9, color: badgeColor, border: `1px solid ${badgeColor}44`, borderRadius: 3, padding: "1px 7px", letterSpacing: "0.08em", textTransform: "uppercase" }}>
              {badgeText}
            </span>
          </div>
          <p style={{ fontSize: 11, color: "#94a3b8", lineHeight: 1.6, margin: "8px 0 0" }}>
            {enabled
              ? "Computer Control is on. Sparkbot can run shell, terminal, browser, and comms actions without PIN prompts in its DM room."
              : status.pinConfigured === false
                ? "Computer Control is off and no PIN is configured yet. Open Controls to set the 6-digit PIN before privileged actions."
                : "Computer Control is off. Sparkbot will ask for the break-glass PIN before commands, edits, browser writes, vault access, or comms sends."}
          </p>
        </div>

        {cap(
          <Code2 size={14} />,
          "Shell Commands",
          badgeText,
          badgeColor,
          "Sparkbot runs PowerShell (Windows) or bash commands directly on this machine. Results stream back into chat. Working directory persists per conversation.",
          "Ask Sparkbot",
          () => {
            onClose()
            // Focus the chat input — user can type their command request
          },
          ['"run dir in shell"', '"list running processes"', '"check disk space"'],
        )}

        {cap(
          <Terminal size={14} />,
          "Live Terminal",
          badgeText,
          badgeColor,
          "An interactive xterm.js terminal connected to a live PTY on this machine. Sparkbot can also type into open terminal sessions via terminal_send.",
          "Open Terminal",
          () => {
            onClose()
            onOpenTerminal()
          },
          ['"open terminal and run npm install"', '"check my terminal sessions"'],
        )}

        {cap(
          <Globe size={14} />,
          "Browser Control",
          badgeText,
          badgeColor,
          "Sparkbot can open a Chromium browser, navigate pages, read content, fill forms, and click buttons. On first use, Chromium downloads automatically (~150 MB).",
          "Ask Sparkbot",
          () => { onClose() },
          ['"open chrome and go to google.com"', '"fill the login form on example.com"'],
        )}

        <div
          style={{
            border: "1px dashed #1e3a5f",
            borderRadius: 8,
            padding: "12px 14px",
            backgroundColor: "#040d1a",
          }}
        >
          <div style={{ fontSize: 10, color: "#7dd3fc", letterSpacing: "0.1em", textTransform: "uppercase", fontWeight: 700, marginBottom: 6 }}>
            How to activate
          </div>
          <ol style={{ fontSize: 11, color: "#94a3b8", lineHeight: 1.8, margin: 0, paddingLeft: 16 }}>
            <li>Open Sparkbot chat (click Sparkbot's desk)</li>
            <li>Tell Sparkbot what you want it to do</li>
            <li>For terminal control, connect the terminal panel first</li>
          </ol>
        </div>
      </div>
    </div>
  )
}

// ─── TerminalDetailPanel ──────────────────────────────────────────────────────
// Phase 3: Live xterm.js terminal backed by a WebSocket PTY session.

// MCPControlPlanePanel
// One registry for Sparkbot tools and the LIMA Robotics OS MCP runtime.

interface McpHealth {
  loading: boolean
  sparkbotApiLive: boolean
  skillsCount: number | null
  vaultConfigured: boolean | null
  taskGuardianEnabled: boolean | null
}

function riskColor(risk: McpRiskLevel): string {
  if (risk === "low") return "#4ade80"
  if (risk === "medium") return "#38bdf8"
  if (risk === "high") return "#fbbf24"
  return "#fb7185"
}

function manifestHealthLabel(manifest: McpToolManifest, health: McpHealth): { label: string; color: string } {
  if (manifest.healthSource === "external-mcp") {
    return manifest.id === "lima.replay_simulation"
      ? { label: "Demo-ready", color: "#4ade80" }
      : { label: "Bridge needed", color: "#fbbf24" }
  }
  if (!health.sparkbotApiLive) return { label: "Checking", color: "#64748b" }
  if (manifest.healthSource === "guardian-vault") {
    return health.vaultConfigured
      ? { label: "Vault live", color: "#4ade80" }
      : { label: "Vault key missing", color: "#fbbf24" }
  }
  if (manifest.healthSource === "task-guardian") {
    return health.taskGuardianEnabled
      ? { label: "Scheduler live", color: "#4ade80" }
      : { label: "Disabled", color: "#fbbf24" }
  }
  return { label: "API live", color: "#4ade80" }
}

function McpControlPlanePanel({ onClose }: { onClose: () => void }) {
  const ACCENT = "#22d3ee"
  const [health, setHealth] = useState<McpHealth>({
    loading: true,
    sparkbotApiLive: false,
    skillsCount: null,
    vaultConfigured: null,
    taskGuardianEnabled: null,
  })

  useEffect(() => {
    let cancelled = false
    async function loadHealth() {
      try {
        const [guardianRes, skillsRes] = await Promise.all([
          apiFetch("/api/v1/chat/guardian/status", { credentials: "include" }).catch(() => null),
          apiFetch("/api/v1/chat/skills", { credentials: "include" }).catch(() => null),
        ])
        const guardian = guardianRes?.ok ? await guardianRes.json().catch(() => null) : null
        const skills = skillsRes?.ok ? await skillsRes.json().catch(() => null) : null
        if (cancelled) return
        setHealth({
          loading: false,
          sparkbotApiLive: Boolean(guardianRes?.ok || skillsRes?.ok),
          skillsCount: Array.isArray(skills?.skills) ? skills.skills.length : null,
          vaultConfigured: typeof guardian?.vault_configured === "boolean" ? guardian.vault_configured : null,
          taskGuardianEnabled:
            typeof guardian?.task_guardian_enabled === "boolean" ? guardian.task_guardian_enabled : null,
        })
      } catch {
        if (!cancelled) {
          setHealth((prev) => ({ ...prev, loading: false, sparkbotApiLive: false }))
        }
      }
    }
    loadHealth()
    return () => {
      cancelled = true
    }
  }, [])

  const runtimeCounts = MCP_TOOL_MANIFESTS.reduce(
    (acc, manifest) => {
      acc[manifest.runtime] += 1
      return acc
    },
    { sparkbot: 0, "lima-robo-os": 0 },
  )

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        bottom: 0,
        width: 560,
        backgroundColor: "#07101e",
        borderLeft: `1px solid ${ACCENT}`,
        boxShadow: `-4px 0 32px ${ACCENT}22`,
        zIndex: 50,
        display: "flex",
        flexDirection: "column",
        fontFamily: "system-ui, sans-serif",
        overflow: "hidden",
        animation: "slideInPanel 0.2s ease-out",
      }}
    >
      <div
        style={{
          backgroundColor: `${ACCENT}18`,
          borderBottom: `1px solid ${ACCENT}33`,
          padding: "12px 16px",
          display: "flex",
          alignItems: "center",
          gap: 10,
          flexShrink: 0,
        }}
      >
        <Rocket size={15} style={{ color: ACCENT }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: ACCENT, letterSpacing: "0.06em", textTransform: "uppercase" }}>
            MCP Control Plane
          </div>
          <div style={{ fontSize: 10, color: "#6b7280", marginTop: 1 }}>
            Sparkbot command center and LIMA Robotics OS
          </div>
        </div>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border: "1px solid #1f2937",
            borderRadius: 4,
            cursor: "pointer",
            color: "#6b7280",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 28,
            height: 28,
          }}
          aria-label="Close MCP control plane"
        >
          <X size={14} />
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
        <p style={{ fontSize: 11, color: "#94a3b8", margin: 0, lineHeight: 1.65 }}>
          Sparkbot is the governed agentic assistant and command center. LIMA Robotics OS is the
          robotics and physical-world runtime exposed through MCP. This registry keeps both sets of
          tools under one policy and audit model.
        </p>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
          {[
            ["Sparkbot tools", String(runtimeCounts.sparkbot), health.sparkbotApiLive ? "API live" : health.loading ? "Checking" : "Offline"],
            ["Robo OS tools", String(runtimeCounts["lima-robo-os"]), "Replay/sim first"],
            ["Loaded skills", health.skillsCount == null ? "--" : String(health.skillsCount), "Drop-in plugins"],
          ].map(([label, value, detail]) => (
            <div key={label} style={{ border: `1px solid ${ACCENT}1f`, borderRadius: 8, backgroundColor: "#040d1a", padding: "10px 12px" }}>
              <div style={{ fontSize: 10, color: "#64748b", letterSpacing: "0.08em", textTransform: "uppercase", fontWeight: 700 }}>
                {label}
              </div>
              <div style={{ fontSize: 20, color: "#e2e8f0", fontWeight: 800, marginTop: 4 }}>{value}</div>
              <div style={{ fontSize: 10, color: ACCENT, marginTop: 2 }}>{detail}</div>
            </div>
          ))}
        </div>

        <div style={{ border: `1px solid ${ACCENT}1f`, borderRadius: 10, backgroundColor: "#040d1a", overflow: "hidden" }}>
          <div style={{ padding: "10px 12px", borderBottom: `1px solid ${ACCENT}1f`, fontSize: 10, color: ACCENT, letterSpacing: "0.1em", textTransform: "uppercase", fontWeight: 700 }}>
            Tool manifests and policy
          </div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            {MCP_TOOL_MANIFESTS.map((manifest) => {
              const healthState = manifestHealthLabel(manifest, health)
              const color = riskColor(manifest.riskLevel)
              return (
                <div key={manifest.id} style={{ padding: "11px 12px", borderBottom: "1px solid #0d1f35", display: "grid", gridTemplateColumns: "minmax(0, 1fr) 86px", gap: 10 }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <span style={{ fontSize: 12, color: "#e2e8f0", fontWeight: 700 }}>{manifest.name}</span>
                      <span style={{ fontSize: 9, color, border: `1px solid ${color}44`, borderRadius: 3, padding: "1px 6px", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                        {manifest.riskLevel}
                      </span>
                      <span style={{ fontSize: 9, color: healthState.color, border: `1px solid ${healthState.color}44`, borderRadius: 3, padding: "1px 6px", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                        {healthState.label}
                      </span>
                    </div>
                    <p style={{ fontSize: 10, color: "#94a3b8", lineHeight: 1.55, margin: "6px 0 0" }}>{manifest.description}</p>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 7 }}>
                      {manifest.policy.map((tag) => (
                        <span key={tag} style={{ fontSize: 9, color: "#7dd3fc", backgroundColor: "#0c1f35", borderRadius: 4, padding: "2px 6px", fontFamily: "monospace" }}>
                          {tag}
                        </span>
                      ))}
                    </div>
                    <div style={{ fontSize: 9, color: "#64748b", marginTop: 7 }}>
                      Secrets: {manifest.requiredSecrets.length ? manifest.requiredSecrets.join(", ") : "none"}
                    </div>
                  </div>
                  <div style={{ textAlign: "right", fontSize: 9, color: "#64748b", lineHeight: 1.5 }}>
                    <div>{manifest.owner}</div>
                    <div>{manifest.dryRunSupport}</div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div style={{ border: `1px solid ${ACCENT}1f`, borderRadius: 10, backgroundColor: "#040d1a", padding: "12px 14px" }}>
            <div style={{ fontSize: 10, color: ACCENT, letterSpacing: "0.1em", textTransform: "uppercase", fontWeight: 700, marginBottom: 8 }}>
              Dry run mode
            </div>
            <p style={{ fontSize: 11, color: "#94a3b8", lineHeight: 1.65, margin: 0 }}>
              Read-only tools can run directly. Writes, sends, destructive commands, secret use, and robot motion should produce an explain-plan first, then wait for the operator approval path.
            </p>
          </div>
          <div style={{ border: `1px solid ${ACCENT}1f`, borderRadius: 10, backgroundColor: "#040d1a", padding: "12px 14px" }}>
            <div style={{ fontSize: 10, color: ACCENT, letterSpacing: "0.1em", textTransform: "uppercase", fontWeight: 700, marginBottom: 8 }}>
              No hardware demos
            </div>
            <code style={{ display: "block", whiteSpace: "pre-wrap", color: "#cbd5e1", fontSize: 10, lineHeight: 1.6 }}>
              LIMA --replay run unitree-go2{"\n"}LIMA --simulation run unitree-go2-agentic-mcp{"\n"}LIMA run demo-camera
            </code>
          </div>
        </div>

        <div style={{ border: `1px dashed ${ACCENT}33`, borderRadius: 10, backgroundColor: "#040d1a", padding: "12px 14px" }}>
          <div style={{ fontSize: 10, color: ACCENT, letterSpacing: "0.1em", textTransform: "uppercase", fontWeight: 700, marginBottom: 8 }}>
            Universal run timeline
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {MCP_RUN_TIMELINE.map((step, index) => (
              <div key={step} style={{ display: "flex", gap: 9, alignItems: "center" }}>
                <span style={{ width: 18, height: 18, borderRadius: 999, backgroundColor: `${ACCENT}18`, border: `1px solid ${ACCENT}44`, color: ACCENT, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700 }}>
                  {index + 1}
                </span>
                <span style={{ fontSize: 11, color: "#cbd5e1" }}>{step}</span>
              </div>
            ))}
          </div>
        </div>

        <button
          type="button"
          onClick={() => window.open("https://github.com/armpit-symphony/LIMA-Robo-OS", "_blank", "noopener,noreferrer")}
          style={{
            alignSelf: "flex-start",
            display: "inline-flex",
            alignItems: "center",
            gap: 7,
            background: `${ACCENT}18`,
            border: `1px solid ${ACCENT}44`,
            borderRadius: 6,
            cursor: "pointer",
            color: ACCENT,
            fontSize: 11,
            padding: "7px 12px",
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            fontWeight: 700,
          }}
        >
          <ExternalLink size={12} />
          Open Robo OS README
        </button>
      </div>
    </div>
  )
}

interface TerminalDetailPanelProps {
  station: Station
  onClose: () => void
}

function TerminalDetailPanel({ station, onClose }: TerminalDetailPanelProps) {
  const { accentHex, label, id, shellType, host } = station
  const { sessionInfo, ws, error, connect, disconnect, listSessions } = useTerminalSession(id, {
    host: host || "localhost",
    shell: shellType === "zsh" ? "/bin/zsh" : shellType === "ssh" ? undefined : undefined,
  })
  const [activeSessions, setActiveSessions] = useState<import("@/types/terminal").TerminalSessionInfo[]>([])

  // Load active sessions on mount and whenever idle (to show resumable indicator)
  const isConnected = sessionInfo?.status === "connected"
  const isConnecting = sessionInfo?.status === "connecting"

  useEffect(() => {
    if (!isConnected && !isConnecting) {
      listSessions().then(setActiveSessions).catch(() => {})
    }
  }, [isConnected, isConnecting, listSessions])

  // Panel expands when connected to give the terminal room to breathe
  const panelWidth = isConnected ? 720 : 340

  const infoRowStyle: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "6px 0",
    borderBottom: "1px solid #0d1f35",
  }

  // Status label + color
  const statusLabel = sessionInfo?.status ?? "idle"
  const statusColor =
    isConnected ? accentHex : isConnecting ? "#fbbf24" : "#4b5563"

  const handleConnect = () => {
    connect().catch((e) => console.error("Terminal connect error:", e))
  }

  const localMachineLabel = host === "localhost" ? "This downloaded machine" : host ?? "localhost"

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        bottom: 0,
        width: panelWidth,
        backgroundColor: "#07101e",
        borderLeft: `1px solid ${accentHex}`,
        boxShadow: `-4px 0 32px ${accentHex}22`,
        zIndex: 50,
        display: "flex",
        flexDirection: "column",
        fontFamily: "monospace",
        overflow: "hidden",
        animation: "slideInPanel 0.2s ease-out",
        transition: "width 0.25s ease",
      }}
    >
      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div
        style={{
          backgroundColor: `${accentHex}18`,
          borderBottom: `1px solid ${accentHex}33`,
          padding: "12px 16px",
          display: "flex",
          alignItems: "center",
          gap: 10,
          flexShrink: 0,
        }}
      >
        <SquareTerminal size={15} style={{ color: accentHex }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 700,
              color: accentHex,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
            }}
          >
            {label}
          </div>
          <div style={{ fontSize: 10, color: "#6b7280", marginTop: 1 }}>
            {isConnected && sessionInfo?.sessionId
              ? sessionInfo.sessionId.slice(0, 16) + "…"
              : id}
          </div>
        </div>
        {/* Status badge */}
        <span
          style={{
            fontSize: 9,
            color: statusColor,
            border: `1px solid ${statusColor}44`,
            borderRadius: 3,
            padding: "1px 6px",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            flexShrink: 0,
          }}
        >
          {statusLabel}
        </span>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border: "1px solid #1f2937",
            borderRadius: 4,
            cursor: "pointer",
            color: "#6b7280",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 28,
            height: 28,
            flexShrink: 0,
          }}
          aria-label="Close panel"
        >
          <X size={14} />
        </button>
      </div>

      {/* ── Terminal area ──────────────────────────────────────────────────── */}
      {isConnected || isConnecting ? (
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          {/* xterm.js mounts here; always rendered so xterm element is stable */}
          <div
            style={{
              flex: 1,
              padding: "8px",
              overflow: "hidden",
              display: "flex",
              flexDirection: "column",
            }}
          >
            <Suspense fallback={<div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "#4b5563", fontSize: 11 }}>Loading terminal…</div>}>
              <XtermTerminal ws={ws} accentHex={accentHex} />
            </Suspense>
          </div>

          {/* Session info footer bar */}
          <div
            style={{
              flexShrink: 0,
              borderTop: `1px solid ${accentHex}22`,
              padding: "8px 16px",
              display: "flex",
              alignItems: "center",
              gap: 16,
              backgroundColor: "#040d1a",
            }}
          >
            <div style={{ display: "flex", gap: 12, flex: 1 }}>
              {[
                { k: "Host", v: host ?? "localhost" },
                { k: "Shell", v: shellType ?? "bash" },
              ].map(({ k, v }) => (
                <span key={k} style={{ fontSize: 10, color: "#4b5563" }}>
                  <span style={{ letterSpacing: "0.06em", textTransform: "uppercase" }}>{k}: </span>
                  <span style={{ color: "#9ca3af" }}>{v}</span>
                </span>
              ))}
            </div>
            <button
              onClick={disconnect}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 5,
                background: "none",
                border: "1px solid #374151",
                borderRadius: 4,
                cursor: "pointer",
                color: "#6b7280",
                fontSize: 10,
                padding: "4px 10px",
                letterSpacing: "0.06em",
                textTransform: "uppercase",
              }}
            >
              <PowerOff size={11} />
              Disconnect
            </button>
          </div>
        </div>
      ) : (
        /* ── Idle state ─────────────────────────────────────────────────── */
        <div style={{ display: "flex", flexDirection: "column", flex: 1, overflowY: "auto" }}>
          {/* Connect button — pinned at top so it's always visible */}
          <div style={{ padding: "16px 16px 8px" }}>
            <button
              onClick={handleConnect}
              disabled={isConnecting}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                width: "100%",
                padding: "12px 0",
                fontSize: 13,
                fontWeight: 700,
                color: isConnecting ? "#6b7280" : accentHex,
                border: `1px solid ${isConnecting ? "#1f2937" : accentHex}`,
                borderRadius: 8,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                background: isConnecting ? "none" : `${accentHex}18`,
                cursor: isConnecting ? "default" : "pointer",
              }}
              aria-label="Connect terminal session"
            >
              {isConnecting ? (
                <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} />
              ) : (
                <Power size={13} />
              )}
              {isConnecting ? "Connecting…" : activeSessions.some((s) => s.stationId === id) ? "Resume Session" : "Connect"}
            </button>
            {error && (
              <div style={{ marginTop: 8, padding: "8px 10px", backgroundColor: "#2d0a0a", border: "1px solid #7f1d1d", borderRadius: 6, fontSize: 10, color: "#fca5a5", lineHeight: 1.5 }}>
                {error}
              </div>
            )}
          </div>
          {/* Terminal screen preview (static, idle) */}
          <div style={{ padding: "0 16px 8px" }}>
            <div
              style={{
                marginBottom: 12,
                backgroundColor: "#0a1120",
                border: `1px solid ${accentHex}22`,
                borderRadius: 6,
                padding: "10px 12px",
              }}
            >
              <div
                style={{
                  fontSize: 10,
                  color: accentHex,
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  marginBottom: 4,
                  fontWeight: 700,
                }}
              >
                Local machine link
              </div>
              <p style={{ fontSize: 10, color: "#9ca3af", lineHeight: 1.6, margin: 0 }}>
                This desk connects to the machine running this Sparkbot download. Use it for local
                model installs, environment checks, logs, and normal shell work.
              </p>
            </div>
            <div
              style={{
                backgroundColor: "#030508",
                borderRadius: 6,
                border: `1px solid ${accentHex}22`,
                padding: "14px 16px",
                backgroundImage: SCANLINE_BG,
                boxShadow: "inset 0 2px 8px rgba(0,0,0,0.8)",
              }}
            >
              <div style={{ fontSize: 11, color: "#4ade80", marginBottom: 4, letterSpacing: "0.04em" }}>
                {host ?? "localhost"}:~$
              </div>
              <div style={{ fontSize: 10, color: "#374151", letterSpacing: "0.04em", lineHeight: 1.6 }}>
                <span style={{ color: "#1f2937" }}>▌</span>
                {" "}Session idle. Click Connect to begin.
              </div>
            </div>
          </div>

          {/* Session info rows */}
          <div style={{ padding: "8px 16px 16px" }}>
            <div
              style={{
                fontSize: 10,
                fontWeight: 700,
                color: "#4b5563",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                marginBottom: 10,
              }}
            >
              Session Info
            </div>
            <div
              style={{
                backgroundColor: "#0a1120",
                border: "1px solid #1a2235",
                borderRadius: 6,
                padding: "0 12px",
              }}
            >
              {[
                { key: "Host", value: localMachineLabel },
                { key: "Shell", value: shellType ?? "bash" },
                { key: "Status", value: statusLabel },
                {
                  key: "Session",
                  value: (() => {
                    const thisSession = activeSessions.find((s) => s.stationId === id)
                    if (thisSession) return `${thisSession.sessionId.slice(0, 12)}… (resumable)`
                    return activeSessions.length > 0 ? `${activeSessions.length} active (other stations)` : "—"
                  })(),
                },
              ].map(({ key, value }) => (
                <div key={key} style={infoRowStyle}>
                  <span style={{ fontSize: 10, color: "#4b5563", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                    {key}
                  </span>
                  <span style={{ fontSize: 11, color: "#9ca3af", letterSpacing: "0.04em" }}>
                    {value}
                  </span>
                </div>
              ))}
            </div>
          </div>

        </div>
      )}
    </div>
  )
}

// ─── LiveClock ────────────────────────────────────────────────────────────────

function LiveClock() {
  const [time, setTime] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  const pad = (n: number) => String(n).padStart(2, "0")
  return (
    <span style={{ color: PLASMA_SECONDARY, letterSpacing: "0.1em" }}>
      {pad(time.getHours())}:{pad(time.getMinutes())}:{pad(time.getSeconds())}
    </span>
  )
}

interface RoundTableStageProps {
  projectRoom: ProjectRoom
  eligibleStations: Station[]
  isSelected: boolean
  onOpen: () => void
  onPickSeat: (seatIndex: number) => void
  onLaunchMeeting: () => void
  launchingMeeting: boolean
  meetingLaunchError?: string | null
}

function RoundTableStage({
  projectRoom,
  eligibleStations,
  isSelected,
  onOpen,
  onPickSeat,
  onLaunchMeeting,
  launchingMeeting,
  meetingLaunchError,
}: RoundTableStageProps) {
  const participants = projectRoom.seats
    .map((seatId) => eligibleStations.find((station) => station.id === seatId) ?? null)
    .filter((station): station is Station => Boolean(station))
  const stagedCount = eligibleStations.filter((station) => station.status !== "empty").length
  const canLaunchMeeting = participants.length >= 2
  const chairAngles = [-148, -108, -62, -18, 18, 62, 108, 148]

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        borderRadius: 18,
        border: `1px solid ${isSelected ? "rgba(125,211,252,0.42)" : PLASMA_BORDER}`,
        background:
          "linear-gradient(180deg, rgba(8,14,28,0.96), rgba(10,17,32,0.94), rgba(79,70,229,0.08))",
        boxShadow: isSelected
          ? "0 0 0 1px rgba(125,211,252,0.16), 0 18px 48px rgba(15,23,42,0.62)"
          : "0 18px 48px rgba(15,23,42,0.52)",
        padding: "18px 20px",
        display: "flex",
        flexDirection: "column",
        gap: 16,
        textAlign: "left",
        fontFamily: "monospace",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(circle at center, rgba(99,102,241,0.16), transparent 42%), radial-gradient(circle at 50% 50%, rgba(125,211,252,0.08), transparent 58%)",
          pointerEvents: "none",
        }}
      />

      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 12,
          position: "relative",
          zIndex: 1,
        }}
      >
        <div>
          <div
            style={{
              fontSize: 10,
              color: ROUND_TABLE.accentHex,
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              fontWeight: 700,
            }}
          >
            Meeting Room
          </div>
          <div style={{ fontSize: 22, color: "#e5eef7", fontWeight: 700, marginTop: 6 }}>
            {ROUND_TABLE.label}
          </div>
          <p style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.7, margin: "8px 0 0" }}>
            Assign desks to any of the eight chairs, then launch the room into a live group chat.
          </p>
        </div>

        <button
          type="button"
          onClick={onOpen}
          style={{
            flexShrink: 0,
            border: "1px solid rgba(125,211,252,0.24)",
            borderRadius: 999,
            padding: "6px 10px",
            fontSize: 10,
            color: "#cbd5f5",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            backgroundColor: "rgba(10, 17, 32, 0.8)",
            cursor: "pointer",
          }}
        >
          {participants.length} / {ROUND_TABLE_SEAT_COUNT} seated
        </button>
      </div>

      <div
        style={{
          flex: 1,
          minHeight: 360,
          position: "relative",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 1,
        }}
      >
        {chairAngles.map((angle, index) => {
          const radians = (angle * Math.PI) / 180
          const x = Math.cos(radians) * 190
          const y = Math.sin(radians) * 136
          const station = projectRoom.seats[index]
            ? eligibleStations.find((candidate) => candidate.id === projectRoom.seats[index]) ?? null
            : null
          return (
            <button
              key={index}
              type="button"
              onClick={() => onPickSeat(index)}
              style={{
                position: "absolute",
                left: "50%",
                top: "50%",
                width: 108,
                minHeight: 62,
                marginLeft: -54 + x,
                marginTop: -31 + y,
                borderRadius: 18,
                border: station
                  ? `1px solid ${station.accentHex}44`
                  : "1px solid rgba(125,211,252,0.16)",
                backgroundColor: station
                  ? `${station.accentHex}12`
                  : "rgba(7, 13, 28, 0.84)",
                boxShadow: station
                  ? `0 0 0 1px ${station.accentHex}18, 0 16px 26px rgba(15,23,42,0.24)`
                  : "0 0 0 1px rgba(30,41,59,0.22)",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 4,
                padding: "10px 8px",
                cursor: "pointer",
              }}
            >
              <span
                style={{
                  fontSize: 9,
                  color: station ? "#cbd5f5" : "#64748b",
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                }}
              >
                Chair {index + 1}
              </span>
              <span
                style={{
                  fontSize: 11,
                  color: station ? "#f8fafc" : "#94a3b8",
                  fontWeight: 700,
                  textAlign: "center",
                  lineHeight: 1.3,
                }}
              >
                {station?.label ?? "Assign"}
              </span>
            </button>
          )
        })}

        <button
          type="button"
          onClick={onOpen}
          style={{
            width: 360,
            height: 360,
            borderRadius: "50%",
            border: "1px solid rgba(125,211,252,0.18)",
            background:
              "radial-gradient(circle at 50% 45%, rgba(99,102,241,0.18), rgba(15,23,42,0.9) 58%, rgba(8,12,24,0.96) 100%)",
            boxShadow:
              "inset 0 0 0 1px rgba(125,211,252,0.08), inset 0 -22px 48px rgba(15,23,42,0.68), 0 26px 48px rgba(0,0,0,0.34)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            position: "relative",
            cursor: "pointer",
          }}
        >
          <div
            style={{
              width: 220,
              height: 220,
              borderRadius: "50%",
              border: "1px solid rgba(245,158,11,0.2)",
              background:
                "radial-gradient(circle at 50% 38%, rgba(245,158,11,0.22), rgba(39,18,5,0.86) 68%, rgba(13,9,5,0.96) 100%)",
              boxShadow: "inset 0 0 0 1px rgba(245,158,11,0.08), 0 18px 34px rgba(15,23,42,0.28)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              textAlign: "center",
              padding: 24,
            }}
          >
            <div>
              <div
                style={{
                  fontSize: 10,
                  color: "#fbbf24",
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  fontWeight: 700,
                }}
              >
                Shared Project Room
              </div>
              <div style={{ fontSize: 18, color: "#f8fafc", fontWeight: 700, marginTop: 8 }}>
                Launch hub
              </div>
              <p style={{ fontSize: 11, color: "#cbd5e1", lineHeight: 1.65, margin: "10px 0 0" }}>
                Click the table for seat controls, or click any chair directly to assign a desk.
              </p>
            </div>
          </div>
        </button>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1.1fr 0.9fr",
          gap: 14,
          position: "relative",
          zIndex: 1,
        }}
      >
        <div
          style={{
            border: "1px solid rgba(125,211,252,0.14)",
            borderRadius: 12,
            backgroundColor: "rgba(7, 13, 28, 0.72)",
            padding: "12px 14px",
          }}
        >
          <div
            style={{
              fontSize: 10,
              color: "#c7d2fe",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              fontWeight: 700,
              marginBottom: 10,
            }}
          >
            Seated participants
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {participants.map((station) => (
              <span
                key={station.id}
                style={{
                  fontSize: 10,
                  color: "#e2e8f0",
                  border: `1px solid ${station.accentHex}33`,
                  borderRadius: 999,
                  padding: "4px 9px",
                  backgroundColor: `${station.accentHex}10`,
                  letterSpacing: "0.05em",
                }}
              >
                {station.label}
              </span>
            ))}
          </div>
        </div>

        <div
          style={{
            border: "1px solid rgba(125,211,252,0.14)",
            borderRadius: 12,
            backgroundColor: "rgba(7, 13, 28, 0.72)",
            padding: "12px 14px",
            display: "flex",
            flexDirection: "column",
            gap: 8,
            justifyContent: "space-between",
          }}
        >
          <div>
            <div
              style={{
                fontSize: 10,
                color: "#c7d2fe",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                fontWeight: 700,
              }}
            >
              Meeting rule
            </div>
            <p style={{ fontSize: 11, color: "#94a3b8", lineHeight: 1.65, margin: "8px 0 0" }}>
              {stagedCount} desks are staged on the floor. This room launches in turn-taking mode:
              one participant speaks at a time.
            </p>
          </div>
          <button
            type="button"
            onClick={onLaunchMeeting}
            disabled={!canLaunchMeeting || launchingMeeting}
            style={{
              border: "none",
              borderRadius: 10,
              padding: "10px 12px",
              background: canLaunchMeeting && !launchingMeeting
                ? "linear-gradient(135deg, rgba(245,158,11,0.94), rgba(249,115,22,0.88), rgba(125,211,252,0.42))"
                : "rgba(15, 23, 42, 0.92)",
              color: canLaunchMeeting && !launchingMeeting ? "#04101d" : "#64748b",
              cursor: canLaunchMeeting && !launchingMeeting ? "pointer" : "not-allowed",
              fontSize: 10,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
            }}
          >
            {launchingMeeting ? <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} /> : <Rocket size={13} />}
            {launchingMeeting ? "Launching…" : "Launch Meeting"}
          </button>
          {meetingLaunchError && (
            <p style={{ marginTop: 8, fontSize: 11, color: "#f87171", lineHeight: 1.5 }}>
              {meetingLaunchError}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── WorkstationPage (main export) ───────────────────────────────────────────

export default function WorkstationPage() {
  const navigate = useNavigate()

  // ── State ──────────────────────────────────────────────────────────────────
  const [panel, setPanel] = useState<PanelMode>(null)
  const [inviteModalTarget, setInviteModalTarget] = useState<Station | null>(null)
  const [projectRoom, setProjectRoom] = useState<ProjectRoom>(() => {
    const draft = loadMeetingDraft()
    return {
      roomName: draft.roomName,
      roomId: draft.roomId,
      seats: normalizeMeetingSeats(draft.seats),
    }
  })
  const [configuredInvites, setConfiguredInvites] = useState<Map<string, InviteConfig>>(() => {
    try {
      const raw = window.localStorage.getItem("sparkbot_invite_configs")
      if (!raw) return new Map()
      const entries = JSON.parse(raw) as Array<[string, InviteConfig]>
      return new Map(entries)
    } catch {
      return new Map()
    }
  })
  const [controlsConfig, setControlsConfig] = useState<SparkbotControlsConfig | null>(null)
  const [overview, setOverview] = useState<WorkstationOverview | null>(null)
  const [infoOpen, setInfoOpen] = useState(false)
  const [seatPicker, setSeatPicker] = useState<SeatPickerState | null>(null)
  const [launchingSparkBudId, setLaunchingSparkBudId] = useState<string | null>(null)
  const [launchingMeeting, setLaunchingMeeting] = useState(false)
  const [meetingLaunchError, setMeetingLaunchError] = useState<string | null>(null)
  const [showNewProject, setShowNewProject] = useState(false)
  const [newProjectName, setNewProjectName] = useState("")
  const [creatingProject, setCreatingProject] = useState(false)
  const [computerControlStatus, setComputerControlStatus] = useState<ComputerControlRoomStatus>({
    enabled: null,
    pinConfigured: null,
  })

  const fetchOverview = useCallback(async () => {
    try {
      const [configRes, overviewRes, guardianStatusRes] = await Promise.all([
        fetchControlsConfig(),
        apiFetch("/api/v1/chat/workstation/overview", { credentials: "include" }).then((r) =>
          r.ok ? r.json() : null
        ).catch(() => null),
        apiFetch("/api/v1/chat/guardian/status", { credentials: "include" }).then((r) =>
          r.ok ? r.json() : null
        ).catch(() => null),
      ])
      setControlsConfig(configRes)
      if (overviewRes) setOverview(overviewRes as WorkstationOverview)
      const bootRes = await apiFetch("/api/v1/chat/users/bootstrap", { method: "POST", credentials: "include" }).catch(() => null)
      const boot = bootRes?.ok ? await bootRes.json().catch(() => null) : null
      const roomId = typeof boot?.room_id === "string" ? boot.room_id : null
      let roomEnabled: boolean | null = null
      if (roomId) {
        const roomRes = await apiFetch(`/api/v1/chat/rooms/${roomId}`, { credentials: "include" }).catch(() => null)
        if (roomRes?.ok) {
          const room = await roomRes.json().catch(() => null)
          roomEnabled = typeof room?.execution_allowed === "boolean" ? room.execution_allowed : null
        }
      }
      setComputerControlStatus({
        enabled: roomEnabled,
        pinConfigured: typeof guardianStatusRes?.pin_configured === "boolean" ? guardianStatusRes.pin_configured : null,
      })
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    fetchOverview()
    const onFocus = () => fetchOverview()
    window.addEventListener("focus", onFocus)
    return () => window.removeEventListener("focus", onFocus)
  }, [fetchOverview])

  useEffect(() => {
    saveMeetingDraft({
      seats: projectRoom.seats,
      roomId: projectRoom.roomId,
      roomName: projectRoom.roomName,
    })
  }, [projectRoom])

  // ── Derived from config ────────────────────────────────────────────────────
  const companionModelStations = buildCompanionModelStations(controlsConfig)
  const resolvedInviteStations = INVITE_DESKS.map((station) =>
    resolveInviteStation(station, configuredInvites),
  )
  const localTerminalDesk = TERMINALS[0]
  const roomEligibleStations = [
    MAIN_DESK,
    ...companionModelStations.filter((station) => station.status !== "empty"),
    ...resolvedInviteStations.filter((station) => station.status !== "empty"),
    ...SPECIALTY_PLACEHOLDERS.filter((station) => station.status !== "empty"),
  ]
  const stackModelByStationId = {
    "stack-backup_1": controlsConfig?.stack.backup_1 ?? "",
    "stack-backup_2": controlsConfig?.stack.backup_2 ?? "",
    "stack-heavy_hitter": controlsConfig?.stack.heavy_hitter ?? "",
  }

  // ── Handlers ───────────────────────────────────────────────────────────────

  // Build seat meta for the 4 stack bots (used for auto-fill and task meetings)
  const buildStackSeatMeta = useCallback(
    (companionStations: Station[]): WorkstationMeetingSeatMeta[] => {
      const meta: WorkstationMeetingSeatMeta[] = [
        buildMeetingSeatMeta(MAIN_DESK, 0),
      ]
      companionStations.forEach((station, i) => {
        if (station.status !== "empty") {
          meta.push(buildMeetingSeatMeta(station, i + 1, stackModelByStationId[station.id as keyof typeof stackModelByStationId] || undefined))
        }
      })
      return meta
    },
    [stackModelByStationId],
  )

  const handleNavigate = useCallback(
    (route: string) => {
      if (route === "/dm?controls=open") {
        navigate({ to: "/dm", search: { controls: "open" } })
        return
      }
      navigate({ to: route })
    },
    [navigate],
  )

  const handleAddToRoom = useCallback((id: string) => {
    setProjectRoom((prev) => addStationToFirstOpenSeat(prev, id))
  }, [])

  const handleRemoveFromRoom = useCallback((id: string) => {
    setProjectRoom((prev) => removeStationFromSeats(prev, id))
  }, [])

  // Auto-fill the 4 stack bots into seats 1-4
  const handleAutoFillStack = useCallback(() => {
    const stackIds = [
      MAIN_DESK.id,
      "stack-backup_1",
      "stack-backup_2",
      "stack-heavy_hitter",
    ]
    const newSeats = normalizeMeetingSeats([])
    let seatIdx = 0
    for (const id of stackIds) {
      if (seatIdx >= ROUND_TABLE_SEAT_COUNT) break
      if (id === MAIN_DESK.id) {
        newSeats[seatIdx++] = id
      } else {
        const companion = companionModelStations.find((s) => s.id === id && s.status !== "empty")
        if (companion) newSeats[seatIdx++] = id
      }
    }
    setProjectRoom((prev) => ({ ...prev, seats: newSeats }))
  }, [companionModelStations])

  // Enter (or create) the meeting room for a guardian task
  const handleEnterTaskMeeting = useCallback(
    async (task: WorkstationTaskRecord) => {
      const existingRoomId = loadTaskMeetingLink(task.id)
      if (existingRoomId) {
        navigate({ to: "/meeting/$roomId", params: { roomId: existingRoomId } })
        return
      }
      const seatMeta = buildStackSeatMeta(companionModelStations)
      setLaunchingMeeting(true)
      setMeetingLaunchError(null)
      try {
        const meta = await launchTaskMeeting({ task, seats: seatMeta })
        saveTaskMeetingLink(task.id, meta.roomId)
        await fetchOverview()
        navigate({ to: "/meeting/$roomId", params: { roomId: meta.roomId } })
      } catch (e) {
        setMeetingLaunchError(e instanceof Error ? e.message : "Could not launch project meeting.")
      } finally {
        setLaunchingMeeting(false)
      }
    },
    [buildStackSeatMeta, companionModelStations, fetchOverview, navigate],
  )

  // Create a new project as a meeting room (no guardian task)
  const handleCreateProject = useCallback(async () => {
    if (!newProjectName.trim() || creatingProject) return
    setCreatingProject(true)
    try {
      const seatMeta = buildStackSeatMeta(companionModelStations)
      const meta = await launchMeetingRoom({ roomName: newProjectName.trim(), seats: seatMeta })
      setShowNewProject(false)
      setNewProjectName("")
      await fetchOverview()
      navigate({ to: "/meeting/$roomId", params: { roomId: meta.roomId } })
    } catch (e) {
      console.error("Could not create project:", e)
    } finally {
      setCreatingProject(false)
    }
  }, [buildStackSeatMeta, companionModelStations, creatingProject, fetchOverview, navigate, newProjectName])

  const handleAssignSeat = useCallback((seatIndex: number, stationId: string) => {
    setProjectRoom((prev) => assignStationToSeat(prev, stationId, seatIndex))
    setSeatPicker(null)
  }, [])

  const handleClearSeat = useCallback((seatIndex: number) => {
    setProjectRoom((prev) => {
      const nextSeats = normalizeMeetingSeats(prev.seats)
      nextSeats[seatIndex] = null
      return {
        ...prev,
        seats: nextSeats,
      }
    })
    setSeatPicker(null)
  }, [])

  const handleSaveInvite = useCallback((stationId: string, config: InviteConfig) => {
    setConfiguredInvites((prev) => {
      const next = new Map([...prev, [stationId, config]])
      try {
        window.localStorage.setItem("sparkbot_invite_configs", JSON.stringify([...next]))
      } catch {}
      return next
    })
    setInviteModalTarget(null)
  }, [])

  const handleClosePanel = useCallback(() => setPanel(null), [])

  const handleStationClick = useCallback(
    (station: Station) => {
      // Round Table → open project room panel
      if (station.type === "table") {
        setInfoOpen(false)
        setPanel((prev) => (prev?.kind === "table" ? null : { kind: "table" }))
        return
      }

      // Terminal → open terminal detail panel
      if (station.type === "terminal") {
        setPanel((prev) =>
          prev?.kind === "terminal" && prev.station.id === station.id
            ? null
            : { kind: "terminal", station },
        )
        return
      }

      // Unconfigured invite desk → open config modal
      if (station.isInviteSlot && !configuredInvites.has(station.id)) {
        setInviteModalTarget(station)
        return
      }

      // All other stations (main, configured invite, sparkbud)
      const resolved = resolveInviteStation(station, configuredInvites)
      setInfoOpen(false)
      setPanel((prev) =>
        prev?.kind === "station" && prev.station.id === resolved.id
          ? null
          : { kind: "station", station: resolved },
      )
    },
    [configuredInvites],
  )

  const handleBackToDm = useCallback(() => navigate({ to: "/dm" }), [navigate])
  const handleOpenInfo = useCallback(() => {
    setPanel(null)
    setSeatPicker(null)
    setInfoOpen((prev) => !prev)
  }, [])
  const handleOpenRoboOs = useCallback(() => {
    setInfoOpen(false)
    setSeatPicker(null)
    setPanel((prev) => (prev?.kind === "mcp" ? null : { kind: "mcp" }))
  }, [])

  const handleLaunchSparkBud = useCallback(
    async (station: Station, config: { prompt: string; agentName?: string }) => {
      const launchConfig = getSparkBudLaunchConfig(station.id)
      if (!launchConfig) return "Specialty launch is not available for this desk."
      if (!config.prompt.trim()) return "Enter a launch prompt before continuing."

      setLaunchingSparkBudId(station.id)
      try {
        if (launchConfig.launchMode === "builtin" && launchConfig.mentionName) {
          saveSparkBudChatLaunchDraft({
            text: buildSparkBudChatLaunchText(launchConfig.mentionName, config.prompt),
          })
          navigate({ to: "/dm" })
          return null
        }

        const agentName = (config.agentName ?? "").trim().toLowerCase()
        if (!agentName || !/^[a-z0-9_]+$/.test(agentName)) {
          return "Use a lowercase handle with letters, numbers, or underscores."
        }

        const response = await apiFetch("/api/v1/chat/agents", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            name: agentName,
            emoji: launchConfig.emoji,
            description: `${station.label} specialist launched from Workstation`,
            system_prompt: config.prompt.trim(),
          }),
        })

        if (!response.ok) {
          const errorPayload = await response
            .json()
            .catch(() => ({ detail: "Could not launch custom specialist." }))
          return String(errorPayload.detail ?? "Could not launch custom specialist.")
        }

        saveSparkBudChatLaunchDraft({ text: `@${agentName} ` })
        navigate({ to: "/dm" })
        return null
      } catch {
        return "Could not launch specialty desk."
      } finally {
        setLaunchingSparkBudId(null)
      }
    },
    [navigate],
  )

  const handleLaunchMeeting = useCallback(async () => {
    const assignedStations = getAssignedStationIds(projectRoom)
    if (assignedStations.length < 2 || launchingMeeting) return

    const assignedSeatMeta = normalizeMeetingSeats(projectRoom.seats)
      .map((stationId, seatIndex) => {
        if (!stationId) return null
        const station = roomEligibleStations.find((candidate) => candidate.id === stationId)
        if (!station) return null
        const inviteConf = station.isInviteSlot ? configuredInvites.get(station.id) : null
        const seatModelId =
          stackModelByStationId[station.id as keyof typeof stackModelByStationId] ||
          inviteConf?.modelId ||
          undefined
        return buildMeetingSeatMeta(station, seatIndex, seatModelId)
      })
      .filter((seat): seat is NonNullable<typeof seat> => Boolean(seat))

    setMeetingLaunchError(null)
    setLaunchingMeeting(true)
    try {
      const roomName = "Roundtable"
      const meetingMeta = await launchMeetingRoom({
        roomName,
        seats: assignedSeatMeta,
      })
      setProjectRoom((prev) => ({
        ...prev,
        roomId: null,
        roomName,
        seats: normalizeMeetingSeats([]),
      }))
      navigate({ to: "/meeting/$roomId", params: { roomId: meetingMeta.roomId } })
    } catch (error) {
      console.error(error)
      setMeetingLaunchError(error instanceof Error ? error.message : "Could not launch meeting. Check console.")
    } finally {
      setLaunchingMeeting(false)
    }
  }, [launchingMeeting, navigate, projectRoom, roomEligibleStations])

  const panelOpen = panel !== null
  const availableSeatCount = projectRoom.seats.filter((seatId) => !seatId).length
  const seatPickerAssignedStation = seatPicker
    ? roomEligibleStations.find((station) => station.id === projectRoom.seats[seatPicker.seatIndex]) ?? null
    : null
  const seatPickerAvailableStations = seatPicker
    ? roomEligibleStations.filter((station) => {
        const assignedSeatIndex = projectRoom.seats.findIndex((seatId) => seatId === station.id)
        return assignedSeatIndex === -1 || assignedSeatIndex === seatPicker.seatIndex
      })
    : []

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <>
      {/* Mobile fallback */}
      <div
        className="flex flex-col items-center justify-center gap-6 sm:hidden"
        style={{
          minHeight: "100dvh",
          backgroundColor: "#060a13",
          padding: 24,
          fontFamily: "monospace",
        }}
      >
        <Layers size={40} style={{ color: PLASMA_PRIMARY, filter: "drop-shadow(0 0 12px rgba(129,140,248,0.28))" }} />
        <div style={{ textAlign: "center" }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 700,
              color: PLASMA_PRIMARY,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              marginBottom: 8,
            }}
          >
            Workstation
          </div>
          <p style={{ fontSize: 12, color: "#6b7280", lineHeight: 1.6, maxWidth: 280, margin: 0 }}>
            Workstation view requires a larger screen. Please open Sparkbot on a desktop or tablet.
          </p>
        </div>
        <Button variant="outline" onClick={handleBackToDm}>
          Back to Sparkbot
        </Button>
      </div>

      {/* Full workstation — hidden at sm and below */}
      <div
        className="hidden sm:flex"
        style={{
          flexDirection: "column",
          minHeight: "100dvh",
          backgroundColor: "#060a13",
          backgroundImage: `
            repeating-linear-gradient(0deg, transparent, transparent 47px, rgba(0,210,255,0.04) 47px, rgba(0,210,255,0.04) 48px),
            repeating-linear-gradient(90deg, transparent, transparent 47px, rgba(0,210,255,0.04) 47px, rgba(0,210,255,0.04) 48px)
          `,
          fontFamily: "monospace",
          position: "relative",
          overflow: panelOpen ? "hidden" : undefined,
        }}
      >
        {/* Scanlines overlay */}
        <div
          style={{
            position: "fixed",
            inset: 0,
            backgroundImage: SCANLINE_BG,
            pointerEvents: "none",
            zIndex: 5,
          }}
        />

        {/* ─── Header bar ─────────────────────────────────────────────── */}
        <header
          style={{
            height: 56,
            borderBottom: `1px solid ${PLASMA_BORDER}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 20px",
            background:
              "linear-gradient(180deg, rgba(7,11,24,0.98), rgba(10,16,31,0.94))",
            flexShrink: 0,
            zIndex: 10,
            position: "relative",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Layers size={16} style={{ color: PLASMA_PRIMARY, filter: "drop-shadow(0 0 10px rgba(129,140,248,0.28))" }} />
            <span
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: PLASMA_PRIMARY,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
              }}
            >
              Sparkbot Workstation
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <SparkbotSurfaceTabs
              active={panel?.kind === "mcp" ? "robo_os" : infoOpen ? "info" : "workstation"}
              onChat={() => handleNavigate("/dm")}
              onWorkstation={() => handleNavigate("/workstation")}
              onControls={() => handleNavigate("/dm?controls=open")}
              onRoboOs={handleOpenRoboOs}
              onInfo={handleOpenInfo}
            />
            <Link
              to="/spine"
              style={{
                fontSize: 10,
                color: "rgba(203,213,245,0.6)",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                textDecoration: "none",
                whiteSpace: "nowrap",
              }}
            >
              Spine Ops →
            </Link>
            <div style={{ width: 1, height: 24, backgroundColor: "rgba(99,102,241,0.16)" }} />
            <LiveClock />
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span
                style={{
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
                  backgroundColor: PLASMA_SECONDARY,
                  boxShadow: "0 0 8px rgba(125,211,252,0.3)",
                  display: "inline-block",
                }}
              />
              <span
                style={{
                  fontSize: 10,
                  color: "#cbd5f5",
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                }}
              >
                Ready
              </span>
            </div>
          </div>
        </header>

        {/* ─── Main content ────────────────────────────────────────────── */}
        <main
          style={{
            flex: 1,
            padding: "10px 16px 16px",
            display: "flex",
            flexDirection: "column",
            gap: 12,
            position: "relative",
            zIndex: 6,
            paddingRight: panelOpen ? "336px" : 16,
            transition: "padding-right 0.2s ease",
          }}
        >
          <section
            style={{
              border: `1px solid ${PLASMA_BORDER}`,
              borderRadius: 20,
              background:
                "linear-gradient(180deg, rgba(7,11,24,0.96), rgba(8,14,28,0.96), rgba(11,17,33,0.98))",
              boxShadow: "0 18px 48px rgba(0,0,0,0.34)",
              padding: 18,
              display: "flex",
              flexDirection: "column",
              gap: 16,
              marginBottom: 16,
            }}
          >
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "280px minmax(0, 1fr) minmax(0, 1fr) 260px",
                gridTemplateRows: "minmax(198px, auto) minmax(480px, 1fr)",
                gap: 16,
                alignItems: "stretch",
              }}
            >
              <div style={{ gridColumn: "1", gridRow: "1" }}>
                <DeskCard
                  station={MAIN_DESK}
                  onClick={handleStationClick}
                  isSelected={panel?.kind === "station" && panel.station.id === MAIN_DESK.id}
                />
              </div>

              {companionModelStations.map((station, index) => (
                <div key={station.id} style={{ gridColumn: `${index + 2}`, gridRow: "1" }}>
                  <DeskCard
                    station={station}
                    onClick={handleStationClick}
                    isSelected={panel?.kind === "station" && panel.station.id === station.id}
                    compact
                  />
                </div>
              ))}

              <div
                style={{
                  gridColumn: "1",
                  gridRow: "2",
                  display: "flex",
                  flexDirection: "column",
                  gap: 12,
                }}
              >
                <div
                  style={{
                    padding: "0 4px",
                    fontSize: 10,
                    color: "#c7d2fe",
                    letterSpacing: "0.12em",
                    textTransform: "uppercase",
                    fontWeight: 700,
                  }}
                >
                  Invite Wing
                </div>
                {resolvedInviteStations.map((station) => (
                  <DeskCard
                    key={station.id}
                    station={station}
                    onClick={handleStationClick}
                    isSelected={panel?.kind === "station" && panel.station.id === station.id}
                    compact
                  />
                ))}
                <div
                  style={{
                    border: "1px dashed rgba(125,211,252,0.18)",
                    borderRadius: 12,
                    padding: "12px 14px",
                    backgroundColor: "rgba(7,13,28,0.56)",
                  }}
                >
                  <div
                    style={{
                      fontSize: 10,
                      color: "#c7d2fe",
                      letterSpacing: "0.1em",
                      textTransform: "uppercase",
                      fontWeight: 700,
                    }}
                  >
                    Invite staging
                  </div>
                  <p style={{ fontSize: 11, color: "#94a3b8", lineHeight: 1.65, margin: "8px 0 0" }}>
                    These desks are reserved for invited assistants or operators such as ChatGPT,
                    Claude, xAI Grok, or another future collaborator.
                  </p>
                </div>
                <DeskCard
                  station={localTerminalDesk}
                  onClick={handleStationClick}
                  isSelected={panel?.kind === "terminal" && panel.station.id === localTerminalDesk.id}
                  compact
                />
                {/* Computer Control hub card */}
                <button
                  onClick={() => setPanel(panel?.kind === "computercontrol" ? null : { kind: "computercontrol" })}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    background: panel?.kind === "computercontrol" ? "rgba(56,189,248,0.12)" : "rgba(7,13,28,0.56)",
                    border: panel?.kind === "computercontrol" ? "1px solid rgba(56,189,248,0.5)" : "1px solid rgba(56,189,248,0.18)",
                    borderRadius: 12,
                    padding: "10px 14px",
                    cursor: "pointer",
                    textAlign: "left",
                    width: "100%",
                  }}
                >
                  <MonitorCog size={15} style={{ color: "#38bdf8", flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#38bdf8", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                      Computer Control
                    </div>
                    <div style={{ fontSize: 10, color: "#64748b", marginTop: 1 }}>
                      Shell · Terminal · Browser
                    </div>
                  </div>
                  <span style={{ fontSize: 9, color: computerControlStatus.enabled ? "#4ade80" : "#fbbf24", border: `1px solid ${computerControlStatus.enabled ? "#4ade80" : "#fbbf24"}44`, borderRadius: 3, padding: "1px 6px", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                    {computerControlStatus.enabled ? "Always on" : "PIN gated"}
                  </span>
                </button>
                <button
                  onClick={handleOpenRoboOs}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    background: panel?.kind === "mcp" ? "rgba(34,211,238,0.12)" : "rgba(7,13,28,0.56)",
                    border: panel?.kind === "mcp" ? "1px solid rgba(34,211,238,0.5)" : "1px solid rgba(34,211,238,0.18)",
                    borderRadius: 12,
                    padding: "10px 14px",
                    cursor: "pointer",
                    textAlign: "left",
                    width: "100%",
                  }}
                >
                  <Rocket size={15} style={{ color: "#22d3ee", flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#22d3ee", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                      Robo OS
                    </div>
                    <div style={{ fontSize: 10, color: "#64748b", marginTop: 1 }}>
                      LIMA MCP registry
                    </div>
                  </div>
                  <span style={{ fontSize: 9, color: "#4ade80", border: "1px solid #4ade8044", borderRadius: 3, padding: "1px 6px", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                    Sim ready
                  </span>
                </button>
              </div>

              <div style={{ gridColumn: "2 / span 2", gridRow: "2" }}>
                <RoundTableStage
                  projectRoom={projectRoom}
                  eligibleStations={roomEligibleStations}
                  isSelected={panel?.kind === "table"}
                  onOpen={() => handleStationClick(ROUND_TABLE)}
                  onPickSeat={(seatIndex) => setSeatPicker({ seatIndex })}
                  onLaunchMeeting={handleLaunchMeeting}
                  launchingMeeting={launchingMeeting}
                  meetingLaunchError={meetingLaunchError}
                />
              </div>

              <div
                style={{
                  gridColumn: "4",
                  gridRow: "2",
                  display: "flex",
                  flexDirection: "column",
                  gap: 12,
                }}
              >
                <div
                  style={{
                    padding: "0 4px",
                    fontSize: 10,
                    color: "#c7d2fe",
                    letterSpacing: "0.12em",
                    textTransform: "uppercase",
                    fontWeight: 700,
                  }}
                >
                  Specialty Wing
                </div>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr",
                    gap: 12,
                  }}
                >
                  {SPECIALTY_PLACEHOLDERS.map((station) => (
                    <DeskCard
                      key={station.id}
                      station={station}
                      onClick={handleStationClick}
                      isSelected={panel?.kind === "station" && panel.station.id === station.id}
                      compact
                    />
                  ))}
                </div>
                <div
                  style={{
                    border: "1px dashed rgba(125,211,252,0.18)",
                    borderRadius: 12,
                    padding: "12px 14px",
                    backgroundColor: "rgba(7,13,28,0.56)",
                  }}
                >
                  <div
                    style={{
                      fontSize: 10,
                      color: "#c7d2fe",
                      letterSpacing: "0.1em",
                      textTransform: "uppercase",
                      fontWeight: 700,
                    }}
                  >
                    Public-safe posture
                  </div>
                  <p style={{ fontSize: 11, color: "#94a3b8", lineHeight: 1.65, margin: "8px 0 0" }}>
                    These SparkBud desks are shown as available specialists, but deeper internal
                    tooling remains hidden until it has clearer permissions and a cleaner product
                    story.
                  </p>
                </div>
              </div>
            </div>
          </section>

          {/* ─── Company Operations ────────────────────────────────────── */}
          <section
            style={{
              border: `1px solid ${PLASMA_BORDER}`,
              borderRadius: 20,
              background: "linear-gradient(180deg, rgba(7,11,24,0.96), rgba(8,14,28,0.96))",
              boxShadow: "0 8px 32px rgba(0,0,0,0.24)",
              padding: 18,
              display: "flex",
              flexDirection: "column",
              gap: 14,
            }}
          >
            {/* Section header */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Briefcase size={14} style={{ color: PLASMA_PRIMARY }} />
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    color: PLASMA_PRIMARY,
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                  }}
                >
                  Company Operations
                </span>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  onClick={() => fetchOverview()}
                  style={{
                    background: "none",
                    border: "1px solid #1f2937",
                    borderRadius: 4,
                    cursor: "pointer",
                    color: "#6b7280",
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                    padding: "4px 8px",
                    fontSize: 9,
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    fontFamily: "monospace",
                  }}
                >
                  <RefreshCw size={10} />
                  Refresh
                </button>
                <button
                  onClick={() => setShowNewProject((prev) => !prev)}
                  style={{
                    background: "none",
                    border: "1px solid rgba(139,147,255,0.3)",
                    borderRadius: 4,
                    cursor: "pointer",
                    color: "#8b93ff",
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                    padding: "4px 8px",
                    fontSize: 9,
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    fontFamily: "monospace",
                  }}
                >
                  <Plus size={10} />
                  New Project
                </button>
              </div>
            </div>

            {/* New Project form */}
            {showNewProject && (
              <div
                style={{
                  backgroundColor: "rgba(139,147,255,0.06)",
                  border: "1px solid rgba(139,147,255,0.2)",
                  borderRadius: 10,
                  padding: "12px 14px",
                  display: "flex",
                  gap: 8,
                  alignItems: "center",
                }}
              >
                <input
                  type="text"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") void handleCreateProject() }}
                  placeholder="Project name…"
                  autoFocus
                  style={{
                    flex: 1,
                    backgroundColor: "#030508",
                    border: "1px solid rgba(139,147,255,0.3)",
                    borderRadius: 6,
                    padding: "7px 10px",
                    fontSize: 12,
                    color: "#e2e8f0",
                    fontFamily: "monospace",
                    outline: "none",
                  }}
                />
                <button
                  onClick={() => void handleCreateProject()}
                  disabled={!newProjectName.trim() || creatingProject}
                  style={{
                    padding: "7px 14px",
                    fontSize: 11,
                    fontWeight: 700,
                    color: newProjectName.trim() && !creatingProject ? "#04101d" : "#374151",
                    backgroundColor: newProjectName.trim() && !creatingProject ? "#8b93ff" : "#1a2235",
                    border: "none",
                    borderRadius: 6,
                    cursor: newProjectName.trim() && !creatingProject ? "pointer" : "not-allowed",
                    fontFamily: "monospace",
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    whiteSpace: "nowrap",
                  }}
                >
                  {creatingProject ? "Creating…" : "Launch"}
                </button>
                <button
                  onClick={() => { setShowNewProject(false); setNewProjectName("") }}
                  style={{
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: "#6b7280",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    padding: 4,
                  }}
                >
                  <X size={14} />
                </button>
              </div>
            )}

            {/* Two-column: Active Tasks | Recent Meetings */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
              {/* Active Guardian Tasks */}
              <div>
                <div
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    color: "#c7d2fe",
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                    marginBottom: 10,
                  }}
                >
                  Guardian Tasks
                </div>
                {!overview?.tasks.length ? (
                  <div
                    style={{
                      padding: "10px 12px",
                      border: "1px dashed rgba(125,211,252,0.14)",
                      borderRadius: 8,
                      fontSize: 11,
                      color: "#4b5563",
                    }}
                  >
                    No tasks yet. Create tasks in Controls → Task Guardian.
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {overview.tasks.map((task) => {
                      const statusColor =
                        task.last_status === "success" ? "#4ade80"
                        : task.last_status === "failed" ? "#f87171"
                        : task.last_status === "running" ? "#fbbf24"
                        : "#4b5563"
                      const linkedRoomId = loadTaskMeetingLink(task.id)
                      return (
                        <div
                          key={task.id}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            padding: "8px 10px",
                            backgroundColor: "rgba(7,13,28,0.72)",
                            border: "1px solid rgba(125,211,252,0.1)",
                            borderRadius: 8,
                          }}
                        >
                          <span
                            style={{
                              width: 7,
                              height: 7,
                              borderRadius: "50%",
                              backgroundColor: statusColor,
                              boxShadow: task.last_status === "running" ? `0 0 6px ${statusColor}` : undefined,
                              flexShrink: 0,
                            }}
                          />
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div
                              style={{
                                fontSize: 11,
                                fontWeight: 700,
                                color: "#cbd5e1",
                                whiteSpace: "nowrap",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                fontFamily: "monospace",
                              }}
                            >
                              {task.name}
                            </div>
                            <div style={{ fontSize: 9, color: "#4b5563", marginTop: 1, fontFamily: "monospace" }}>
                              {task.tool_name}
                              {task.last_run_at ? ` · ${new Date(task.last_run_at).toLocaleDateString()}` : ""}
                            </div>
                          </div>
                          <button
                            onClick={() => void handleEnterTaskMeeting(task)}
                            disabled={launchingMeeting}
                            title={linkedRoomId ? "Re-enter meeting" : "Start project meeting"}
                            style={{
                              background: "none",
                              border: `1px solid ${linkedRoomId ? "rgba(245,158,11,0.4)" : "rgba(139,147,255,0.3)"}`,
                              borderRadius: 4,
                              cursor: launchingMeeting ? "not-allowed" : "pointer",
                              color: linkedRoomId ? "#f59e0b" : "#8b93ff",
                              display: "flex",
                              alignItems: "center",
                              gap: 4,
                              padding: "4px 7px",
                              fontSize: 9,
                              letterSpacing: "0.06em",
                              textTransform: "uppercase",
                              fontFamily: "monospace",
                              flexShrink: 0,
                            }}
                          >
                            <Play size={9} />
                            {linkedRoomId ? "Enter" : "Meet"}
                          </button>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>

              {/* Recent Meetings */}
              <div>
                <div
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    color: "#c7d2fe",
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                    marginBottom: 10,
                  }}
                >
                  Active Meetings
                </div>
                {!overview?.meetings.length ? (
                  <div
                    style={{
                      padding: "10px 12px",
                      border: "1px dashed rgba(125,211,252,0.14)",
                      borderRadius: 8,
                      fontSize: 11,
                      color: "#4b5563",
                    }}
                  >
                    No meetings yet. Launch one from the Roundtable or start a project above.
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {overview.meetings.map((meeting) => (
                      <button
                        key={meeting.id}
                        onClick={() => navigate({ to: "/meeting/$roomId", params: { roomId: meeting.id } })}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          padding: "8px 10px",
                          backgroundColor: "rgba(7,13,28,0.72)",
                          border: "1px solid rgba(125,211,252,0.1)",
                          borderRadius: 8,
                          cursor: "pointer",
                          textAlign: "left",
                          width: "100%",
                          transition: "border-color 0.15s",
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.borderColor = "rgba(245,158,11,0.3)" }}
                        onMouseLeave={(e) => { e.currentTarget.style.borderColor = "rgba(125,211,252,0.1)" }}
                      >
                        <span
                          style={{
                            width: 7,
                            height: 7,
                            borderRadius: "50%",
                            backgroundColor: "#f59e0b",
                            boxShadow: "0 0 5px rgba(245,158,11,0.5)",
                            flexShrink: 0,
                          }}
                        />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div
                            style={{
                              fontSize: 11,
                              fontWeight: 700,
                              color: "#cbd5e1",
                              whiteSpace: "nowrap",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              fontFamily: "monospace",
                            }}
                          >
                            {meeting.name}
                          </div>
                          {meeting.updated_at && (
                            <div style={{ fontSize: 9, color: "#4b5563", marginTop: 1, fontFamily: "monospace" }}>
                              <Clock size={8} style={{ display: "inline", verticalAlign: "middle", marginRight: 3 }} />
                              {new Date(meeting.updated_at).toLocaleDateString()}
                            </div>
                          )}
                        </div>
                        <ChevronRight size={12} style={{ color: "#374151", flexShrink: 0 }} />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {meetingLaunchError && (
              <p style={{ fontSize: 11, color: "#f87171", margin: 0 }}>{meetingLaunchError}</p>
            )}
          </section>
        </main>

        {/* ─── Side panels ─────────────────────────────────────────────── */}
        {panel?.kind === "station" && (
          <StationDetailPanel
            station={panel.station}
            onClose={handleClosePanel}
            onNavigate={handleNavigate}
            projectRoom={projectRoom}
            onAddToRoom={handleAddToRoom}
            onRemoveFromRoom={handleRemoveFromRoom}
            availableSeatCount={availableSeatCount}
            onLaunchSparkBud={handleLaunchSparkBud}
            launchingSparkBudId={launchingSparkBudId}
          />
        )}
        {panel?.kind === "table" && (
          <RoundTablePanel
            projectRoom={projectRoom}
            onClose={handleClosePanel}
            onAddToRoom={handleAddToRoom}
            onRemoveFromRoom={handleRemoveFromRoom}
            eligibleStations={roomEligibleStations}
            onPickSeat={(seatIndex) => setSeatPicker({ seatIndex })}
            onLaunchMeeting={handleLaunchMeeting}
            onAutoFillStack={handleAutoFillStack}
            launchingMeeting={launchingMeeting}
            meetingLaunchError={meetingLaunchError}
          />
        )}
        {panel?.kind === "terminal" && (
          <TerminalDetailPanel station={panel.station} onClose={handleClosePanel} />
        )}
        {panel?.kind === "computercontrol" && (
          <ComputerControlPanel
            onClose={handleClosePanel}
            onOpenTerminal={() => setPanel({ kind: "terminal", station: localTerminalDesk })}
            status={computerControlStatus}
          />
        )}
        {panel?.kind === "mcp" && (
          <McpControlPlanePanel onClose={handleClosePanel} />
        )}

        {/* ─── Invite config modal ────────────────────────────────────── */}
        {inviteModalTarget && (
          <InviteConfigModal
            station={inviteModalTarget}
            onSave={handleSaveInvite}
            onCancel={() => setInviteModalTarget(null)}
          />
        )}
        {seatPicker && (
          <SeatPickerModal
            seatIndex={seatPicker.seatIndex}
            assignedStation={seatPickerAssignedStation}
            availableStations={seatPickerAvailableStations}
            onAssign={(stationId) => handleAssignSeat(seatPicker.seatIndex, stationId)}
            onClear={() => handleClearSeat(seatPicker.seatIndex)}
            onClose={() => setSeatPicker(null)}
          />
        )}
        <SparkbotSurfaceInfoDialog
          open={infoOpen}
          title="Workstation"
          subtitle="A spatial office map around Sparkbot. Chat stays primary, Controls handles setup, and Roundtable launches focused group rooms from the floor."
          bullets={[
            "Workstation is the desktop map: desks, offices, and the central meeting table.",
            "Roundtable is the eight-seat launcher for staged desk participants.",
            "Sparkbot Chat remains the everyday home for normal prompting and conversations.",
            "Controls still manages providers, models, and safety/configuration settings.",
          ]}
          onClose={() => setInfoOpen(false)}
        />
      </div>

      {/* ─── Keyframe animations ──────────────────────────────────────────── */}
      <style>{`
        @keyframes statusPulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.6; transform: scale(0.85); }
        }
        @keyframes slideInPanel {
          from { transform: translateX(100%); opacity: 0; }
          to   { transform: translateX(0);    opacity: 1; }
        }
      `}</style>
    </>
  )
}
