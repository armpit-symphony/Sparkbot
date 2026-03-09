// ─── WorkstationPage.tsx ──────────────────────────────────────────────────────
// Retro pixel-art / hacker-lab visual workstation — pure React/CSS, no canvas.
// Route: /workstation
// Phase 2: Round Table participant management, invite desk config modal,
//          SparkBud routes wired, terminal detail panel.

import { useState, useCallback, useEffect } from "react"
import { useNavigate } from "@tanstack/react-router"
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
  Monitor,
  SquareTerminal,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  type Station,
  type StationStatus,
  MAIN_DESK,
  INVITE_DESKS,
  ROUND_TABLE,
  TERMINALS,
  SPARKBUDS,
  STATION_BY_ID,
} from "@/config/workstationStations"

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

const CHAIR_ANGLES = [0, 60, 120, 180, 240, 300]

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

// ─── RoundTable sub-component ─────────────────────────────────────────────────

interface RoundTableProps {
  station: Station
  onClick: (station: Station) => void
  isSelected: boolean
  chairColors: (string | null)[]
}

function RoundTable({ station, onClick, isSelected, chairColors }: RoundTableProps) {
  const [hovered, setHovered] = useState(false)
  const handleClick = useCallback(() => onClick(station), [onClick, station])
  const handleMouseEnter = useCallback(() => setHovered(true), [])
  const handleMouseLeave = useCallback(() => setHovered(false), [])
  const { accentHex } = station
  const borderColor = isSelected ? accentHex : hovered ? `${accentHex}88` : "#1a2235"
  const shadowStr = isSelected
    ? `0 0 0 1px ${accentHex}, 0 0 28px 6px ${accentHex}44`
    : hovered
      ? `0 0 0 1px ${accentHex}66, 0 0 18px 4px ${accentHex}22`
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
        cursor: "pointer",
        transition: "transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease",
        transform: hovered ? "translateY(-2px) scale(1.005)" : "none",
        boxShadow: shadowStr,
        display: "flex",
        flexDirection: "column",
        fontFamily: "monospace",
        height: "100%",
        overflow: "hidden",
      }}
      role="button"
      tabIndex={0}
      aria-pressed={isSelected}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") handleClick()
      }}
    >
      {/* Header strip */}
      <div
        style={{
          backgroundColor: `${accentHex}14`,
          borderBottom: `1px solid ${accentHex}22`,
          padding: "10px 14px",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <StatusLight status={station.status} hex={accentHex} />
        <div style={{ flex: 1 }}>
          <div
            style={{
              fontSize: 12,
              fontWeight: 700,
              color: accentHex,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
            }}
          >
            {station.label}
          </div>
          <div style={{ fontSize: 10, color: "#4b5563", letterSpacing: "0.04em", marginTop: 1 }}>
            {station.subtitle}
          </div>
        </div>
        {/* Participant count badge */}
        <span
          style={{
            fontSize: 9,
            color: accentHex,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            border: `1px solid ${accentHex}44`,
            borderRadius: 3,
            padding: "1px 5px",
          }}
        >
          {chairColors.filter(Boolean).length} / {chairColors.length}
        </span>
      </div>

      {/* Table area */}
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 24,
          position: "relative",
          backgroundImage: `
            ${SCANLINE_BG},
            repeating-linear-gradient(90deg, transparent, transparent 23px, ${accentHex}08 23px, ${accentHex}08 24px),
            repeating-linear-gradient(0deg, transparent, transparent 23px, ${accentHex}08 23px, ${accentHex}08 24px)
          `,
        }}
      >
        <div style={{ position: "relative", width: 180, height: 180 }}>
          {/* Chair dots — colored by participant */}
          {CHAIR_ANGLES.map((angle, i) => {
            const rad = (angle - 90) * (Math.PI / 180)
            const r = 95
            const cx = 90 + r * Math.cos(rad)
            const cy = 90 + r * Math.sin(rad)
            const chairColor = chairColors[i]
            const isOccupied = chairColor !== null
            const isOperator = i === 0
            const dotSize = isOperator ? 14 : 10
            return (
              <div
                key={angle}
                style={{
                  position: "absolute",
                  width: dotSize,
                  height: dotSize,
                  borderRadius: "50%",
                  backgroundColor: isOccupied ? chairColor! : "#0f172a",
                  border: `1px solid ${isOccupied ? chairColor! : "#1f2937"}`,
                  boxShadow: isOccupied ? `0 0 8px 2px ${chairColor!}66` : undefined,
                  left: cx - dotSize / 2,
                  top: cy - dotSize / 2,
                  transition: "background-color 0.3s, box-shadow 0.3s",
                }}
              />
            )
          })}

          {/* Inner circle (the table) */}
          <div
            style={{
              position: "absolute",
              top: 18,
              left: 18,
              right: 18,
              bottom: 18,
              borderRadius: "50%",
              border: `2px solid ${accentHex}`,
              boxShadow: `0 0 20px 4px ${accentHex}33, inset 0 0 30px rgba(0,0,0,0.5)`,
              backgroundColor: `${accentHex}08`,
              backgroundImage: `
                repeating-linear-gradient(45deg, transparent, transparent 8px, ${accentHex}06 8px, ${accentHex}06 9px)
              `,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 4,
            }}
          >
            <Users
              size={22}
              style={{ color: accentHex, filter: `drop-shadow(0 0 6px ${accentHex}88)` }}
            />
            <div
              style={{
                fontSize: 9,
                color: accentHex,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                textAlign: "center",
                lineHeight: 1.3,
              }}
            >
              Round
              <br />
              Table
            </div>
          </div>
        </div>
      </div>

      {/* Capability tags */}
      <div
        style={{
          padding: "8px 14px 12px",
          display: "flex",
          gap: 6,
          flexWrap: "wrap",
          borderTop: `1px solid ${accentHex}18`,
        }}
      >
        {station.capabilities.slice(0, 3).map((cap) => (
          <span
            key={cap}
            style={{
              fontSize: 9,
              color: accentHex,
              border: `1px solid ${accentHex}33`,
              borderRadius: 3,
              padding: "2px 6px",
              letterSpacing: "0.05em",
              backgroundColor: `${accentHex}08`,
            }}
          >
            {cap}
          </span>
        ))}
      </div>
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
                  Commands and Help
                </div>
                <p style={{ fontSize: 10, color: "#9ca3af", lineHeight: 1.6, margin: 0 }}>
                  Slash commands live in Sparkbot DM. Open chat and type <span style={{ color: accentHex }}>/help</span> for the current command surface.
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
                  Operational Controls
                </div>
                <p style={{ fontSize: 10, color: "#9ca3af", lineHeight: 1.6, margin: 0 }}>
                  Token Guardian, Task Guardian, room execution gate, provider keys, and bridge settings remain in the Sparkbot DM controls drawer today.
                </p>
              </div>

              <div
                style={{
                  backgroundColor: "#0a1120",
                  border: "1px dashed #1f2937",
                  borderRadius: 6,
                  padding: "10px 12px",
                }}
              >
                <div
                  style={{
                    fontSize: 10,
                    color: "#6b7280",
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    marginBottom: 4,
                    fontWeight: 700,
                  }}
                >
                  Future Hook
                </div>
                <p style={{ fontSize: 10, color: "#6b7280", lineHeight: 1.6, margin: 0 }}>
                  Breakglass and admin entry points can attach here once those workstation-native routes are exposed.
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

interface TerminalDetailPanelProps {
  station: Station
  onClose: () => void
}

function TerminalDetailPanel({ station, onClose }: TerminalDetailPanelProps) {
  const { accentHex, label, id, shellType, host } = station

  const infoRowStyle: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "8px 0",
    borderBottom: "1px solid #0d1f35",
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
        <SquareTerminal size={15} style={{ color: accentHex }} />
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
            {label}
          </div>
          <div style={{ fontSize: 10, color: "#6b7280", marginTop: 2 }}>{id}</div>
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

      {/* Terminal screen preview */}
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
            {" "}Session idle. Connect to begin.
          </div>
        </div>
      </div>

      {/* Session info */}
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
            { key: "Status", value: "idle" },
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

      {/* xterm.js note */}
      <div
        style={{
          margin: "0 16px 16px",
          padding: "12px 14px",
          backgroundColor: `${accentHex}0a`,
          border: `1px solid ${accentHex}22`,
          borderRadius: 6,
        }}
      >
        <div
          style={{
            fontSize: 10,
            fontWeight: 700,
            color: accentHex,
            letterSpacing: "0.07em",
            textTransform: "uppercase",
            marginBottom: 6,
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <Monitor size={11} />
          Phase 3 — Live Terminal
        </div>
        <p style={{ fontSize: 10, color: "#6b7280", margin: 0, lineHeight: 1.6 }}>
          xterm.js integration and WebSocket shell backend are planned for Phase 3.
          This panel is the connection point — no changes needed to wire it in.
        </p>
      </div>

      {/* Connect button (placeholder) */}
      <div style={{ padding: "0 16px 16px", marginTop: "auto" }}>
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
          }}
        >
          Connect (Phase 3)
        </div>
      </div>
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

  // ── Resolved invite desks (merge configured data) ─────────────────────────
  const resolvedInviteDesks = INVITE_DESKS.map((d) =>
    resolveInviteStation(d, configuredInvites),
  )

  // ── Participant chair colors for RoundTable visual ─────────────────────────
  const participantList = [
    "sparkbot",
    ...[...projectRoom.participantIds].filter((id) => id !== "sparkbot"),
  ]
  const chairColors = CHAIR_ANGLES.map((_, i): string | null => {
    const pid = participantList[i]
    if (!pid) return null
    return STATION_BY_ID.get(pid)?.accentHex ?? "#f59e0b"
  })

  // ── Handlers ───────────────────────────────────────────────────────────────
  const handleNavigate = useCallback(
    (route: string) => navigate({ to: route }),
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
          {/* ── Section 1: Top row — desk cards ─────────────────────── */}
          <section
            style={{
              display: "grid",
              gridTemplateColumns: "1.3fr 1fr 1fr 1fr",
              gap: 12,
            }}
          >
            <DeskCard
              station={MAIN_DESK}
              onClick={handleStationClick}
              isSelected={panel?.kind === "station" && panel.station.id === MAIN_DESK.id}
            />
            {resolvedInviteDesks.map((desk) => (
              <DeskCard
                key={desk.id}
                station={desk}
                onClick={handleStationClick}
                isSelected={panel?.kind === "station" && panel.station.id === desk.id}
              />
            ))}
          </section>

          {/* ── Section 2: Middle — Round Table + Terminals/SparkBuds ── */}
          <section
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 220px",
              gap: 12,
              flex: 1,
              minHeight: 0,
            }}
          >
            {/* Left: Round Table */}
            <div style={{ minHeight: 320 }}>
              <RoundTable
                station={ROUND_TABLE}
                onClick={handleStationClick}
                isSelected={panel?.kind === "table"}
                chairColors={chairColors}
              />
            </div>

            {/* Right: Terminals + SparkBuds */}
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {/* Terminals */}
              {TERMINALS.map((term) => (
                <DeskCard
                  key={term.id}
                  station={term}
                  onClick={handleStationClick}
                  isSelected={panel?.kind === "terminal" && panel.station.id === term.id}
                  compact
                />
              ))}

              {/* SparkBuds 2×2 grid */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 8,
                  flex: 1,
                }}
              >
                {SPARKBUDS.map((bud) => (
                  <DeskCard
                    key={bud.id}
                    station={bud}
                    onClick={handleStationClick}
                    isSelected={panel?.kind === "station" && panel.station.id === bud.id}
                    compact
                  />
                ))}
              </div>
            </div>
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
            SparkPit Labs · AI Workstation v2
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
