import {
  Bot,
  Check,
  Copy,
  Loader2,
  Pause,
  Play,
  UserPlus,
  X,
} from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { apiFetch, getApiBase } from "@/lib/apiBase"
import {
  appBasePath,
  buildAgentInvite,
  buildGuestLink,
  type InvitedSeat,
  suggestSlug,
} from "@/lib/roundtableInvite"

interface SeatRow {
  id: string
  slug: string
  display_name: string
  kind: "agent" | "human"
  active: boolean
  role?: string | null
  // Runner pilot: agent seats only.
  presence?: "online" | "working" | "offline" | null
  working_note?: string | null
  pending_jobs?: number
}

const PRESENCE_POLL_MS = 5000
const PRESENCE_STYLE: Record<string, { color: string; text: string }> = {
  online: { color: "#4ade80", text: "online" },
  working: { color: "#facc15", text: "working…" },
  offline: { color: "#64748b", text: "offline" },
}

interface RoundtablePeoplePanelProps {
  roomId: string
  roomName: string
  canManage: boolean
  /** Called with the number of seats each time the list loads. */
  onSeatsLoaded?: (count: number) => void
}

const label: React.CSSProperties = {
  fontSize: 10,
  color: "#cbd5f5",
  letterSpacing: "0.1em",
  textTransform: "uppercase",
  fontWeight: 700,
}
const input: React.CSSProperties = {
  width: "100%",
  border: "1px solid rgba(125,211,252,0.18)",
  borderRadius: 8,
  backgroundColor: "rgba(7,13,28,0.72)",
  color: "#e2e8f0",
  fontSize: 12,
  padding: "8px 10px",
  boxSizing: "border-box",
}
const smallButton: React.CSSProperties = {
  borderRadius: 8,
  border: "1px solid rgba(125,211,252,0.22)",
  backgroundColor: "rgba(14,116,144,0.18)",
  color: "#bae6fd",
  padding: "7px 10px",
  fontSize: 11,
  fontWeight: 700,
  cursor: "pointer",
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
}

function serverUrl(): string {
  return (
    getApiBase() ||
    (typeof window !== "undefined" ? window.location.origin : "")
  )
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

export default function RoundtablePeoplePanel({
  roomId,
  roomName,
  canManage,
  onSeatsLoaded,
}: RoundtablePeoplePanelProps) {
  const [seats, setSeats] = useState<SeatRow[]>([])
  // Keep the latest callback without making `reload` change every render.
  const onSeatsLoadedRef = useRef(onSeatsLoaded)
  onSeatsLoadedRef.current = onSeatsLoaded
  const [loadError, setLoadError] = useState("")
  const [formOpen, setFormOpen] = useState(false)
  const [name, setName] = useState("")
  const [kind, setKind] = useState<"agent" | "human">("agent")
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState("")
  const [invited, setInvited] = useState<InvitedSeat | null>(null)
  const [copied, setCopied] = useState(false)
  const [confirmRevoke, setConfirmRevoke] = useState<string | null>(null)
  const [paused, setPaused] = useState(false)
  const [pauseBusy, setPauseBusy] = useState(false)

  const reload = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/v1/chat/rooms/${roomId}/seats`, {
        credentials: "include",
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const rows: SeatRow[] = await res.json()
      setSeats(rows)
      onSeatsLoadedRef.current?.(rows.length)
      setLoadError("")
      const stateRes = await apiFetch(
        `/api/v1/chat/rooms/${roomId}/roundtable/state`,
        {
          credentials: "include",
        },
      )
      if (stateRes.ok) setPaused(Boolean((await stateRes.json()).paused))
    } catch {
      setLoadError("Couldn't load seats.")
    }
  }, [roomId])

  useEffect(() => {
    void reload()
    // Keep online / working / offline dots and the pause state fresh.
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void reload()
    }, PRESENCE_POLL_MS)
    return () => window.clearInterval(timer)
  }, [reload])

  async function togglePause() {
    if (pauseBusy) return
    setPauseBusy(true)
    try {
      const res = await apiFetch(
        `/api/v1/chat/rooms/${roomId}/roundtable/pause`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ paused: !paused }),
        },
      )
      if (res.ok) setPaused(Boolean((await res.json()).paused))
      await reload()
    } finally {
      setPauseBusy(false)
    }
  }

  async function handleInvite(event: React.FormEvent) {
    event.preventDefault()
    const displayName = name.trim()
    if (!displayName || busy) return
    setBusy(true)
    setFormError("")
    try {
      // @handles are unique per server, so "Codex" in a second room becomes @codex-2.
      const base = suggestSlug(displayName)
      let data: Record<string, unknown> = {}
      for (let attempt = 1; attempt <= 9; attempt += 1) {
        const slug = attempt === 1 ? base : `${base.slice(0, 28)}-${attempt}`
        const res = await apiFetch(`/api/v1/chat/rooms/${roomId}/seats`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ display_name: displayName, slug, kind }),
        })
        data = await res.json().catch(() => ({}))
        if (res.ok) break
        if (res.status !== 409 || attempt === 9)
          throw new Error(
            typeof data.detail === "string"
              ? data.detail
              : `HTTP ${res.status}`,
          )
      }
      setInvited(data as unknown as InvitedSeat)
      setCopied(false)
      setName("")
      setFormOpen(false)
      await reload()
    } catch (err) {
      setFormError((err as Error).message || "Invite failed.")
    } finally {
      setBusy(false)
    }
  }

  async function handleRevoke(seatId: string) {
    if (confirmRevoke !== seatId) {
      setConfirmRevoke(seatId)
      return
    }
    setConfirmRevoke(null)
    await apiFetch(`/api/v1/chat/rooms/${roomId}/seats/${seatId}`, {
      method: "DELETE",
      credentials: "include",
    })
    if (invited?.id === seatId) setInvited(null)
    await reload()
  }

  const ctx = { serverUrl: serverUrl(), roomId, roomName }
  const inviteText = invited
    ? invited.kind === "agent"
      ? buildAgentInvite(invited, ctx)
      : buildGuestLink(
          window.location.origin,
          appBasePath(window.location.pathname),
          invited,
          ctx,
        )
    : ""

  return (
    <div
      data-testid="roundtable-people"
      style={{
        border: "1px solid rgba(125,211,252,0.14)",
        borderRadius: 12,
        padding: "12px 14px",
        backgroundColor: "rgba(10,17,32,0.72)",
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
        }}
      >
        <div style={label}>People &amp; agents</div>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            type="button"
            style={{ ...smallButton, padding: "7px 8px" }}
            onClick={() => void togglePause()}
            disabled={pauseBusy}
            title={
              paused
                ? "Let agents answer @mentions again"
                : "Stop agents from being woken in this room"
            }
          >
            {paused ? <Play size={13} /> : <Pause size={13} />}{" "}
            {paused ? "Resume" : "Pause"}
          </button>
          {canManage && !formOpen && (
            <button
              type="button"
              style={smallButton}
              onClick={() => setFormOpen(true)}
            >
              <UserPlus size={13} /> Invite
            </button>
          )}
        </div>
      </div>

      {paused && (
        <div
          aria-live="polite"
          style={{
            fontSize: 11,
            color: "#fde68a",
            border: "1px solid rgba(250,204,21,0.3)",
            backgroundColor: "rgba(161,98,7,0.15)",
            borderRadius: 8,
            padding: "7px 9px",
          }}
        >
          Paused: @mentions won't wake agents. Post /resume or press Resume.
        </div>
      )}

      <p style={{ fontSize: 11, color: "#94a3b8", lineHeight: 1.6, margin: 0 }}>
        Bring your own agents (Codex, Claude Code, …) or invite a person. They
        use their own subscriptions; Sparkbot needs no API keys. Seats can only
        read and post in this room.
      </p>

      {formOpen && (
        <form
          onSubmit={handleInvite}
          style={{ display: "flex", flexDirection: "column", gap: 8 }}
        >
          <input
            aria-label="Name"
            placeholder="Name, e.g. Codex or Dana"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={input}
            maxLength={100}
          />
          <div
            style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}
          >
            {(["agent", "human"] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setKind(option)}
                aria-pressed={kind === option}
                style={{
                  ...smallButton,
                  justifyContent: "center",
                  backgroundColor:
                    kind === option ? "rgba(59,130,246,0.28)" : "transparent",
                  color: kind === option ? "#e2e8f0" : "#94a3b8",
                }}
              >
                {option === "agent" ? "AI agent" : "Person"}
              </button>
            ))}
          </div>
          {formError && (
            <div style={{ fontSize: 11, color: "#fecaca" }}>{formError}</div>
          )}
          <div style={{ display: "flex", gap: 6 }}>
            <button
              type="submit"
              style={smallButton}
              disabled={busy || !name.trim()}
            >
              {busy ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <UserPlus size={13} />
              )}{" "}
              Create seat
            </button>
            <button
              type="button"
              style={{
                ...smallButton,
                backgroundColor: "transparent",
                color: "#94a3b8",
              }}
              onClick={() => {
                setFormOpen(false)
                setFormError("")
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {invited && (
        <div
          data-testid="roundtable-invite-result"
          style={{
            border: "1px solid rgba(250,204,21,0.25)",
            borderRadius: 10,
            padding: 10,
            backgroundColor: "rgba(161,98,7,0.12)",
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div style={{ fontSize: 11, color: "#fde68a", fontWeight: 700 }}>
              {invited.kind === "agent"
                ? `Paste this into ${invited.display_name}'s chat`
                : `Send this link to ${invited.display_name}`}
            </div>
            <button
              type="button"
              aria-label="Dismiss"
              onClick={() => setInvited(null)}
              style={{
                background: "none",
                border: "none",
                color: "#94a3b8",
                cursor: "pointer",
              }}
            >
              <X size={14} />
            </button>
          </div>
          <textarea
            readOnly
            value={inviteText}
            rows={invited.kind === "agent" ? 9 : 3}
            onFocus={(e) => e.currentTarget.select()}
            style={{
              ...input,
              fontFamily: "ui-monospace, monospace",
              fontSize: 10,
              resize: "vertical",
            }}
          />
          <button
            type="button"
            style={smallButton}
            onClick={async () => setCopied(await copyText(inviteText))}
          >
            {copied ? <Check size={13} /> : <Copy size={13} />}{" "}
            {copied ? "Copied" : "Copy"}
          </button>
          <div style={{ fontSize: 10, color: "#fcd34d", lineHeight: 1.5 }}>
            Shown once; it contains a private key. Send it only to{" "}
            {invited.display_name}. You can revoke the seat anytime.
          </div>
        </div>
      )}

      {loadError && (
        <div style={{ fontSize: 11, color: "#fecaca" }}>{loadError}</div>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {seats.length === 0 && !loadError && (
          <div style={{ fontSize: 11, color: "#64748b" }}>
            Nobody invited yet.
          </div>
        )}
        {seats.map((seat) => (
          <div
            key={seat.id}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              border: "1px solid rgba(125,211,252,0.12)",
              borderRadius: 8,
              padding: "7px 9px",
            }}
          >
            {seat.kind === "agent" ? (
              <Bot size={14} color="#7dd3fc" />
            ) : (
              <UserPlus size={14} color="#a5b4fc" />
            )}
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontSize: 12, color: "#e2e8f0", fontWeight: 700 }}>
                {seat.display_name}
              </div>
              <div style={{ fontSize: 10, color: "#64748b" }}>
                @{seat.slug} · {seat.kind === "agent" ? "AI agent" : "person"}
              </div>
              {seat.kind === "agent" && seat.presence && (
                <div
                  data-testid={`presence-${seat.slug}`}
                  title={seat.working_note ?? undefined}
                  style={{
                    fontSize: 10,
                    color: "#94a3b8",
                    display: "flex",
                    alignItems: "center",
                    gap: 5,
                    marginTop: 2,
                  }}
                >
                  <span
                    style={{
                      width: 7,
                      height: 7,
                      borderRadius: "50%",
                      backgroundColor:
                        PRESENCE_STYLE[seat.presence]?.color ?? "#64748b",
                    }}
                  />
                  {PRESENCE_STYLE[seat.presence]?.text ?? seat.presence}
                  {seat.pending_jobs ? ` · ${seat.pending_jobs} waiting` : ""}
                </div>
              )}
            </div>
            {canManage && (
              <button
                type="button"
                onClick={() => void handleRevoke(seat.id)}
                onBlur={() => setConfirmRevoke(null)}
                style={{
                  ...smallButton,
                  padding: "5px 8px",
                  fontSize: 10,
                  border: "1px solid rgba(248,113,113,0.22)",
                  backgroundColor:
                    confirmRevoke === seat.id
                      ? "rgba(127,29,29,0.5)"
                      : "rgba(127,29,29,0.18)",
                  color: "#fecaca",
                }}
              >
                {confirmRevoke === seat.id ? "Sure?" : "Remove"}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
