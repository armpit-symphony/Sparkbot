// ─── WorkstationPage.tsx ──────────────────────────────────────────────────────
// Retro pixel-art / hacker-lab visual workstation — pure React/CSS, no canvas.
// Route: /workstation
// Phase 3: Live terminal via xterm.js + WebSocket-backed PTY sessions.

import { useState, useCallback, useEffect } from "react"
import { useNavigate } from "@tanstack/react-router"
import {
  Bot,
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
} from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  type Station,
  type StationStatus,
  MAIN_DESK,
  INVITE_DESKS,
  ROUND_TABLE,
  SPARKBUDS,
} from "@/config/workstationStations"
import { useTerminalSession } from "@/hooks/useTerminalSession"
import { XtermTerminal } from "@/components/Terminal/XtermTerminal"

// ─── Types ────────────────────────────────────────────────────────────────────

type PanelMode =
  | { kind: "station"; station: Station }
  | { kind: "table" }
  | { kind: "terminal"; station: Station }
  | null

interface ProjectRoom {
  name: string
  participantIds: Set<string>
}

interface InviteConfig {
  label: string
  provider: string
  description: string
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
    status: "idle" as StationStatus,
    invitePrompt: undefined,
  }
}

// ─── Shared CSS strings ───────────────────────────────────────────────────────

const SCANLINE_BG =
  "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.08) 2px, rgba(0,0,0,0.08) 4px)"

const PUBLIC_WORKSTATION_BADGES = [
  "Desktop overview",
  "Chat-first workflow",
  "Advanced tools hidden by default",
]

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
  { value: "Google", label: "Google (Gemini)" },
  { value: "Ollama", label: "Ollama (Local)" },
  { value: "Custom", label: "Custom Provider" },
]

function InviteConfigModal({ station, onSave, onCancel }: InviteConfigModalProps) {
  const [label, setLabel] = useState(
    station.label === "Add Agent" ? "" : station.label,
  )
  const [provider, setProvider] = useState("OpenAI")
  const [description, setDescription] = useState("")

  const { accentHex } = station
  const canSave = label.trim().length > 0

  const handleSave = useCallback(() => {
    if (!canSave) return
    onSave(station.id, {
      label: label.trim(),
      provider,
      description: description.trim(),
    })
  }, [canSave, label, provider, description, station.id, onSave])

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
            <label style={labelStyle}>Description (optional)</label>
            <textarea
              style={{
                ...inputStyle,
                height: 64,
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
}

function StationDetailPanel({
  station,
  onClose,
  onNavigate,
  projectRoom,
  onAddToRoom,
  onRemoveFromRoom,
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
  const isInRoom = projectRoom.participantIds.has(id)
  const canToggleRoom = !isSparkbot && type !== "table" && type !== "terminal"

  const handleNavigate = useCallback(() => {
    if (route) onNavigate(route)
  }, [route, onNavigate])

  // Primary action
  let actionLabel = "Coming Soon"
  let actionDisabled = true
  let actionHandler: (() => void) | undefined

  if (route && isActive) {
    actionLabel = isSparkbot ? "Open Main Chat" : type === "sparkbud" ? "Launch Agent" : "Open Station"
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
          {isSparkbot ? (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "8px 10px",
                backgroundColor: "#0a1120",
                border: "1px solid #1a2235",
                borderRadius: 6,
              }}
            >
              <Check size={13} style={{ color: "#4ade80" }} />
              <span style={{ fontSize: 11, color: "#6b7280" }}>Always at the table</span>
            </div>
          ) : isInRoom ? (
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

      {/* Primary action button */}
      <div style={{ padding: 16, marginTop: "auto" }}>
        {actionDisabled ? (
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
  configuredInvites: Map<string, InviteConfig>
}

function RoundTablePanel({
  projectRoom,
  onClose,
  onAddToRoom,
  onRemoveFromRoom,
  configuredInvites,
}: RoundTablePanelProps) {
  const accentHex = ROUND_TABLE.accentHex

  // Stations that can be in the room (not terminals, not table)
  const eligibleStations = [
    MAIN_DESK,
    ...INVITE_DESKS.map((d) => resolveInviteStation(d, configuredInvites)).filter(
      (d) => d.status !== "empty",
    ),
    ...SPARKBUDS,
  ]

  const participants = eligibleStations.filter((s) => projectRoom.participantIds.has(s.id))
  const available = eligibleStations.filter((s) => !projectRoom.participantIds.has(s.id))

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
            {projectRoom.name}
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

      {/* Divider */}
      {available.length > 0 && (
        <>
          <div style={{ height: 1, backgroundColor: "#1a2235", margin: "14px 16px 0" }} />

          {/* Available section */}
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
              Add to Room
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {available.map((s) => (
                <button
                  key={s.id}
                  onClick={() => onAddToRoom(s.id)}
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
                  onMouseEnter={(e) => { e.currentTarget.style.borderColor = `${s.accentHex}44` }}
                  onMouseLeave={(e) => { e.currentTarget.style.borderColor = "#1a2235" }}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      backgroundColor: `${s.accentHex}44`,
                      border: `1px solid ${s.accentHex}66`,
                      flexShrink: 0,
                    }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: 11,
                        fontWeight: 700,
                        color: "#6b7280",
                        letterSpacing: "0.05em",
                        textTransform: "uppercase",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        fontFamily: "monospace",
                      }}
                    >
                      {s.label}
                    </div>
                    <div style={{ fontSize: 9, color: "#374151", marginTop: 1, fontFamily: "monospace" }}>
                      {s.subtitle}
                    </div>
                  </div>
                  <ChevronRight size={12} style={{ color: "#374151", flexShrink: 0 }} />
                </button>
              ))}
            </div>
          </div>
        </>
      )}

      {/* Phase 3 note */}
      <div
        style={{
          margin: "auto 16px 16px",
          padding: "10px 12px",
          backgroundColor: "#0a1120",
          border: "1px solid #1a2235",
          borderRadius: 6,
        }}
      >
        <p style={{ fontSize: 10, color: "#374151", margin: 0, lineHeight: 1.6 }}>
          Multi-agent task board, shared file drops, and live coordination wiring in Phase 3.
        </p>
      </div>
    </div>
  )
}

// ─── TerminalDetailPanel ──────────────────────────────────────────────────────
// Phase 3: Live xterm.js terminal backed by a WebSocket PTY session.

interface TerminalDetailPanelProps {
  station: Station
  onClose: () => void
}

function TerminalDetailPanel({ station, onClose }: TerminalDetailPanelProps) {
  const { accentHex, label, id, shellType, host } = station
  const { sessionInfo, ws, error, connect, disconnect } = useTerminalSession(id)

  const isConnected = sessionInfo?.status === "connected"
  const isConnecting = sessionInfo?.status === "connecting"

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
            <XtermTerminal ws={ws} accentHex={accentHex} />
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
          {/* Terminal screen preview (static, idle) */}
          <div style={{ padding: "16px 16px 8px" }}>
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
                { key: "Host", value: host ?? "localhost" },
                { key: "Shell", value: shellType ?? "bash" },
                { key: "Status", value: statusLabel },
                { key: "Session", value: "—" },
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

          {/* Error notice */}
          {error && (
            <div
              style={{
                margin: "0 16px 12px",
                padding: "10px 12px",
                backgroundColor: "#2d0a0a",
                border: "1px solid #7f1d1d",
                borderRadius: 6,
                fontSize: 10,
                color: "#fca5a5",
                lineHeight: 1.5,
              }}
            >
              {error}
            </div>
          )}

          {/* Connect button — live in Phase 3 */}
          <div style={{ padding: "0 16px 16px", marginTop: "auto" }}>
            <button
              onClick={handleConnect}
              disabled={isConnecting}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                width: "100%",
                padding: "10px 0",
                fontSize: 12,
                color: isConnecting ? "#6b7280" : accentHex,
                border: `1px solid ${isConnecting ? "#1f2937" : accentHex}44`,
                borderRadius: 6,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                background: isConnecting ? "none" : `${accentHex}0d`,
                cursor: isConnecting ? "default" : "pointer",
                transition: "background 0.15s ease, color 0.15s ease",
              }}
              aria-label="Connect terminal session"
            >
              {isConnecting ? (
                <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} />
              ) : (
                <Power size={13} />
              )}
              {isConnecting ? "Connecting…" : "Connect"}
            </button>
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
    <span style={{ color: "#4ade80", letterSpacing: "0.1em" }}>
      {pad(time.getHours())}:{pad(time.getMinutes())}:{pad(time.getSeconds())}
    </span>
  )
}

function WorkstationOverviewCard({ onNavigate }: { onNavigate: (route: string) => void }) {
  return (
    <section
      style={{
        border: "1px solid #0d1f35",
        borderRadius: 12,
        background:
          "linear-gradient(135deg, rgba(7,16,30,0.96), rgba(10,17,32,0.92), rgba(0,212,255,0.06))",
        boxShadow: "0 14px 38px rgba(0,0,0,0.32)",
        padding: "18px 20px",
        display: "grid",
        gridTemplateColumns: "1.35fr 0.95fr",
        gap: 18,
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div>
          <div
            style={{
              fontSize: 10,
              color: "#00d4ff",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              fontWeight: 700,
            }}
          >
            Workstation
          </div>
          <div
            style={{
              fontSize: 22,
              color: "#e5eef7",
              fontWeight: 700,
              letterSpacing: "0.03em",
              marginTop: 6,
            }}
          >
            Desktop overview for Sparkbot
          </div>
          <p style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.75, margin: "10px 0 0" }}>
            Workstation is a secondary surface for desktop users. Use it to jump into chat,
            open Controls, and understand which assistant tools are available on this install
            without treating the app like an internal console.
          </p>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {PUBLIC_WORKSTATION_BADGES.map((badge) => (
            <span
              key={badge}
              style={{
                fontSize: 10,
                color: "#9ccfe0",
                border: "1px solid #1f3b51",
                borderRadius: 999,
                padding: "5px 10px",
                letterSpacing: "0.05em",
                textTransform: "uppercase",
                backgroundColor: "rgba(8, 18, 32, 0.72)",
              }}
            >
              {badge}
            </span>
          ))}
        </div>
      </div>

      <div
        style={{
          border: "1px solid #12304a",
          borderRadius: 10,
          backgroundColor: "rgba(8, 18, 32, 0.82)",
          padding: "14px 16px",
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        <div style={{ fontSize: 10, color: "#4b5563", letterSpacing: "0.1em", textTransform: "uppercase", fontWeight: 700 }}>
          What belongs here
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {[
            "Everyday work still starts in Sparkbot Chat.",
            "Setup, providers, and channels stay in Controls.",
            "Advanced/operator tools stay hidden until they are explicitly ready.",
          ].map((item) => (
            <div
              key={item}
              style={{
                display: "flex",
                gap: 8,
                alignItems: "flex-start",
                fontSize: 11,
                color: "#cbd5e1",
                lineHeight: 1.55,
              }}
            >
              <span
                style={{
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
                  marginTop: 5,
                  backgroundColor: "#00d4ff",
                  boxShadow: "0 0 8px #00d4ff66",
                  flexShrink: 0,
                }}
              />
              <span>{item}</span>
            </div>
          ))}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: "auto" }}>
          <button
            onClick={() => onNavigate("/dm")}
            style={{
              padding: "10px 12px",
              borderRadius: 8,
              border: "none",
              backgroundColor: "#00d4ff",
              color: "#04101d",
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              cursor: "pointer",
              fontFamily: "monospace",
            }}
          >
            Open Chat
          </button>
          <button
            onClick={() => onNavigate("/dm?controls=open")}
            style={{
              padding: "10px 12px",
              borderRadius: 8,
              border: "1px solid #1f3b51",
              backgroundColor: "transparent",
              color: "#cbd5e1",
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              cursor: "pointer",
              fontFamily: "monospace",
            }}
          >
            Open Controls
          </button>
        </div>
      </div>
    </section>
  )
}

// ─── WorkstationNavStrip ─────────────────────────────────────────────────────

interface WorkstationNavStripProps {
  onNavigate: (route: string) => void
}

function WorkstationNavStrip({ onNavigate }: WorkstationNavStripProps) {
  const primaryLinks = [
    {
      label: "Workstation",
      hint: "Current room",
      route: "/workstation",
      icon: Layers,
      accentHex: "#00d4ff",
      active: true,
    },
    {
      label: "Sparkbot Chat",
      hint: "Main DM",
      route: "/dm",
      icon: Bot,
      accentHex: MAIN_DESK.accentHex,
      active: false,
    },
    {
      label: "Controls",
      hint: "Setup + config",
      route: "/dm?controls=open",
      icon: SlidersHorizontal,
      accentHex: "#f59e0b",
      active: false,
    },
  ]

  const buttonBaseStyle: React.CSSProperties = {
    backgroundColor: "#081220",
    border: "1px solid #1a2235",
    borderRadius: 8,
    padding: "10px 12px",
    display: "flex",
    alignItems: "center",
    gap: 10,
    textAlign: "left",
    cursor: "pointer",
    fontFamily: "monospace",
    transition: "border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease",
    minWidth: 0,
  }

  return (
    <section
      style={{
        border: "1px solid #0d1f35",
        borderRadius: 10,
        backgroundColor: "rgba(7, 16, 30, 0.86)",
        boxShadow: "0 10px 32px rgba(0,0,0,0.28)",
        padding: "12px 14px",
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <div>
          <div
            style={{
              fontSize: 10,
              color: "#00d4ff",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              fontWeight: 700,
            }}
          >
            Navigation
          </div>
          <div style={{ fontSize: 10, color: "#4b5563", marginTop: 3 }}>
            Move directly between the three public app surfaces without relying on browser history.
          </div>
        </div>
        <div
          style={{
            fontSize: 9,
            color: "#6b7280",
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            border: "1px solid #1f2937",
            borderRadius: 999,
            padding: "4px 8px",
            flexShrink: 0,
          }}
        >
          Chat is the primary home
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${primaryLinks.length}, minmax(0, 1fr))`,
          gap: 8,
        }}
      >
        {primaryLinks.map(({ label, hint, route, icon: Icon, accentHex, active }) => (
          <button
            key={route}
            onClick={() => {
              if (!active) onNavigate(route)
            }}
            aria-current={active ? "page" : undefined}
            style={{
              ...buttonBaseStyle,
              borderColor: active ? accentHex : "#1a2235",
              boxShadow: active ? `0 0 0 1px ${accentHex}, 0 0 18px 2px ${accentHex}22` : "none",
              cursor: active ? "default" : "pointer",
            }}
          >
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: 6,
                backgroundColor: `${accentHex}16`,
                border: `1px solid ${active ? accentHex : `${accentHex}33`}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <Icon size={14} style={{ color: accentHex }} />
            </div>
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  fontSize: 11,
                  color: active ? accentHex : "#d1d5db",
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  fontWeight: 700,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {label}
              </div>
              <div style={{ fontSize: 9, color: "#4b5563", marginTop: 2 }}>{hint}</div>
            </div>
          </button>
        ))}
      </div>

      <div
        style={{
          borderTop: "1px solid #132235",
          paddingTop: 10,
          fontSize: 10,
          color: "#64748b",
          lineHeight: 1.7,
        }}
      >
        Specialist desk previews and workstation terminal panels are intentionally hidden from the
        public surface until they have clearer permissions, stronger guardrails, and a cleaner
        first-run story.
      </div>
    </section>
  )
}

// ─── WorkstationPage (main export) ───────────────────────────────────────────

export default function WorkstationPage() {
  const navigate = useNavigate()

  // ── State ──────────────────────────────────────────────────────────────────
  const [panel, setPanel] = useState<PanelMode>({ kind: "station", station: MAIN_DESK })
  const [inviteModalTarget, setInviteModalTarget] = useState<Station | null>(null)
  const [projectRoom, setProjectRoom] = useState<ProjectRoom>({
    name: "Main Project",
    participantIds: new Set(["sparkbot"]),
  })
  const [configuredInvites, setConfiguredInvites] = useState<Map<string, InviteConfig>>(
    new Map(),
  )

  // ── Handlers ───────────────────────────────────────────────────────────────
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
    setProjectRoom((prev) => ({
      ...prev,
      participantIds: new Set([...prev.participantIds, id]),
    }))
  }, [])

  const handleRemoveFromRoom = useCallback((id: string) => {
    setProjectRoom((prev) => {
      const next = new Set(prev.participantIds)
      next.delete(id)
      return { ...prev, participantIds: next }
    })
  }, [])

  const handleSaveInvite = useCallback((stationId: string, config: InviteConfig) => {
    setConfiguredInvites((prev) => new Map([...prev, [stationId, config]]))
    setInviteModalTarget(null)
  }, [])

  const handleClosePanel = useCallback(() => setPanel(null), [])

  const handleStationClick = useCallback(
    (station: Station) => {
      // Round Table → open project room panel
      if (station.type === "table") {
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
      setPanel((prev) =>
        prev?.kind === "station" && prev.station.id === resolved.id
          ? null
          : { kind: "station", station: resolved },
      )
    },
    [configuredInvites],
  )

  const handleBackToDm = useCallback(() => navigate({ to: "/dm" }), [navigate])

  const panelOpen = panel !== null

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
        <Layers size={40} style={{ color: "#00d4ff", filter: "drop-shadow(0 0 10px #00d4ff88)" }} />
        <div style={{ textAlign: "center" }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 700,
              color: "#00d4ff",
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
            height: 48,
            borderBottom: "1px solid #0d1f35",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 20px",
            backgroundColor: "#060a13",
            flexShrink: 0,
            zIndex: 10,
            position: "relative",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Layers size={16} style={{ color: "#00d4ff", filter: "drop-shadow(0 0 6px #00d4ff88)" }} />
            <span
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: "#00d4ff",
                letterSpacing: "0.12em",
                textTransform: "uppercase",
              }}
            >
              Sparkbot Workstation
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <LiveClock />
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span
                style={{
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
                  backgroundColor: "#4ade80",
                  boxShadow: "0 0 6px 2px #4ade8066",
                  display: "inline-block",
                }}
              />
              <span
                style={{
                  fontSize: 10,
                  color: "#4ade80",
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                }}
              >
                Online
              </span>
            </div>
          </div>
        </header>

        {/* ─── Main content ────────────────────────────────────────────── */}
        <main
          style={{
            flex: 1,
            padding: "16px 16px 0",
            display: "flex",
            flexDirection: "column",
            gap: 12,
            position: "relative",
            zIndex: 6,
            paddingRight: panelOpen ? "336px" : 16,
            transition: "padding-right 0.2s ease",
          }}
        >
          <WorkstationNavStrip
            onNavigate={handleNavigate}
          />

          <WorkstationOverviewCard onNavigate={handleNavigate} />

          {/* ── Section 1: Public-ready desk + guidance cards ───────────────── */}
          <section
            style={{
              display: "grid",
              gridTemplateColumns: "1.35fr 0.95fr",
              gap: 12,
            }}
          >
            <DeskCard
              station={MAIN_DESK}
              onClick={handleStationClick}
              isSelected={panel?.kind === "station" && panel.station.id === MAIN_DESK.id}
            />
            <div
              style={{
                backgroundColor: "#0a1120",
                border: "1px solid #1a2235",
                borderRadius: 8,
                overflow: "hidden",
                boxShadow: "0 2px 8px rgba(0,0,0,0.6)",
                display: "flex",
                flexDirection: "column",
                fontFamily: "monospace",
              }}
            >
              <div
                style={{
                  backgroundColor: "rgba(245, 158, 11, 0.12)",
                  borderBottom: "1px solid rgba(245, 158, 11, 0.16)",
                  padding: "10px 12px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 8,
                }}
              >
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#f59e0b", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                    Advanced Tools
                  </div>
                  <div style={{ fontSize: 10, color: "#6b7280", letterSpacing: "0.04em", marginTop: 1 }}>
                    Deliberately restrained in the public view
                  </div>
                </div>
                <span
                  style={{
                    fontSize: 9,
                    color: "#f59e0b",
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    border: "1px solid rgba(245, 158, 11, 0.35)",
                    borderRadius: 3,
                    padding: "1px 5px",
                    flexShrink: 0,
                  }}
                >
                  Hidden by default
                </span>
              </div>

              <div style={{ padding: "14px 12px 12px", display: "flex", flexDirection: "column", gap: 10, flex: 1 }}>
                <p style={{ fontSize: 11, color: "#9ca3af", lineHeight: 1.7, margin: 0 }}>
                  Terminal panels, specialist desk previews, and other operator-style surfaces are
                  intentionally kept out of the everyday public workstation until they are easier
                  to explain and safer to expose by default.
                </p>

                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {["Not required for chat", "Operator-oriented", "Future advanced mode"].map((item) => (
                    <span
                      key={item}
                      style={{
                        fontSize: 9,
                        color: "#f59e0b",
                        border: "1px solid rgba(245, 158, 11, 0.25)",
                        borderRadius: 4,
                        padding: "3px 8px",
                        letterSpacing: "0.04em",
                        backgroundColor: "rgba(245, 158, 11, 0.06)",
                      }}
                    >
                      {item}
                    </span>
                  ))}
                </div>

                <div
                  style={{
                    marginTop: "auto",
                    backgroundColor: "#081220",
                    border: "1px solid #1f2937",
                    borderRadius: 6,
                    padding: "10px 12px",
                  }}
                >
                  <div style={{ fontSize: 10, color: "#e5eef7", fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 4 }}>
                    Public stance
                  </div>
                  <p style={{ fontSize: 10, color: "#94a3b8", lineHeight: 1.6, margin: 0 }}>
                    Chat is the everyday surface. Controls handles setup. Workstation shows the
                    desktop overview around those two.
                  </p>
                </div>
              </div>
            </div>
          </section>

          {/* ── Section 2: What users should expect from Workstation ───────── */}
          <section
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
              gap: 12,
              marginBottom: 16,
            }}
          >
            {[
              {
                title: "Chat first",
                body: "Sparkbot Chat remains the normal everyday home for prompts, reminders, file work, and conversations.",
              },
              {
                title: "Controls nearby",
                body: "Provider setup, model stack, channels, and Guardian settings stay one click away instead of being buried.",
              },
              {
                title: "Advanced later",
                body: "More experimental workstation surfaces stay out of the public path until they have a cleaner product story.",
              },
            ].map((card) => (
              <div
                key={card.title}
                style={{
                  backgroundColor: "#0a1120",
                  border: "1px solid #1a2235",
                  borderRadius: 8,
                  padding: "14px 16px",
                  boxShadow: "0 2px 8px rgba(0,0,0,0.6)",
                }}
              >
                <div style={{ fontSize: 10, color: "#00d4ff", letterSpacing: "0.1em", textTransform: "uppercase", fontWeight: 700 }}>
                  {card.title}
                </div>
                <p style={{ fontSize: 11, color: "#94a3b8", lineHeight: 1.7, margin: "10px 0 0" }}>
                  {card.body}
                </p>
              </div>
            ))}
          </section>
        </main>

        {/* ─── Footer bar ─────────────────────────────────────────────── */}
        <footer
          style={{
            height: 36,
            borderTop: "1px solid #0d1f35",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            backgroundColor: "#060a13",
            flexShrink: 0,
            zIndex: 10,
            position: "relative",
          }}
        >
          <span style={{ fontSize: 10, color: "#1e3a52", letterSpacing: "0.08em" }}>
            SparkPit Labs · Workstation is the desktop overview around Chat and Controls
          </span>
        </footer>

        {/* ─── Side panels ─────────────────────────────────────────────── */}
        {panel?.kind === "station" && (
          <StationDetailPanel
            station={panel.station}
            onClose={handleClosePanel}
            onNavigate={handleNavigate}
            projectRoom={projectRoom}
            onAddToRoom={handleAddToRoom}
            onRemoveFromRoom={handleRemoveFromRoom}
          />
        )}
        {panel?.kind === "table" && (
          <RoundTablePanel
            projectRoom={projectRoom}
            onClose={handleClosePanel}
            onAddToRoom={handleAddToRoom}
            onRemoveFromRoom={handleRemoveFromRoom}
            configuredInvites={configuredInvites}
          />
        )}
        {panel?.kind === "terminal" && (
          <TerminalDetailPanel station={panel.station} onClose={handleClosePanel} />
        )}

        {/* ─── Invite config modal ────────────────────────────────────── */}
        {inviteModalTarget && (
          <InviteConfigModal
            station={inviteModalTarget}
            onSave={handleSaveInvite}
            onCancel={() => setInviteModalTarget(null)}
          />
        )}
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
