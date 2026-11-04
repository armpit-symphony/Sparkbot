import { createFileRoute } from "@tanstack/react-router"
import { Loader2, Send } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { apiFetch } from "@/lib/apiBase"
import { parseGuestFragment } from "@/lib/roundtableInvite"

// Public page for an invited person: open the link, read the room, post.
// The seat key arrives in the URL fragment (never sent to the server in the URL),
// is moved into this tab's sessionStorage, and the fragment is removed.

export const Route = createFileRoute("/guest")({
  component: GuestRoom,
})

const STORE_KEY = "roundtable_guest"
const POLL_MS = 4000

interface GuestSeat {
  id: string
  slug: string
  display_name: string
  kind: "agent" | "human"
}
interface GuestRoomInfo {
  id: string
  name: string
  role: string
}
interface GuestMessage {
  id: string
  sender_id: string
  sender_type: string
  sender_name: string
  sender_slug?: string | null
  content: string
  created_at: string
}

function readStoredInvite(): { key: string; roomId: string } | null {
  try {
    const raw = sessionStorage.getItem(STORE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function takeInvite(): { key: string; roomId: string } | null {
  const fromHash =
    typeof window !== "undefined"
      ? parseGuestFragment(window.location.hash)
      : null
  if (fromHash) {
    try {
      sessionStorage.setItem(STORE_KEY, JSON.stringify(fromHash))
    } catch {
      // private mode: keep it in memory only
    }
    window.history.replaceState(
      null,
      "",
      window.location.pathname + window.location.search,
    )
    return fromHash
  }
  return readStoredInvite()
}

async function call<T>(
  path: string,
  init: RequestInit,
  token?: string,
): Promise<T> {
  const headers = new Headers(init.headers)
  if (token) headers.set("Authorization", `Bearer ${token}`)
  if (init.body) headers.set("Content-Type", "application/json")
  const res = await apiFetch(`/api/v1/chat${path}`, {
    ...init,
    headers,
    credentials: "omit",
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail =
      typeof data?.detail === "string" ? data.detail : `HTTP ${res.status}`
    throw Object.assign(new Error(detail), { status: res.status })
  }
  return data as T
}

function GuestRoom() {
  const [invite] = useState(takeInvite)
  const [token, setToken] = useState<string | null>(null)
  const [seat, setSeat] = useState<GuestSeat | null>(null)
  const [room, setRoom] = useState<GuestRoomInfo | null>(null)
  const [messages, setMessages] = useState<GuestMessage[]>([])
  const [draft, setDraft] = useState("")
  const [error, setError] = useState("")
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement | null>(null)
  const lastIdRef = useRef<string | null>(null)

  const signIn = useCallback(async () => {
    if (!invite) return null
    const res = await call<{ access_token: string; seat: GuestSeat }>(
      "/seats/token",
      {
        method: "POST",
        body: JSON.stringify({ key: invite.key }),
      },
    )
    setToken(res.access_token)
    setSeat(res.seat)
    return res.access_token
  }, [invite])

  useEffect(() => {
    if (!invite) return
    let cancelled = false
    ;(async () => {
      try {
        const tok = await signIn()
        if (!tok || cancelled) return
        const me = await call<{ rooms: GuestRoomInfo[] }>(
          "/seats/me",
          { method: "GET" },
          tok,
        )
        const chosen =
          me.rooms.find((r) => r.id === invite.roomId) ?? me.rooms[0] ?? null
        if (!chosen)
          throw new Error("This invite isn't attached to a room anymore.")
        if (!cancelled) setRoom(chosen)
      } catch (err) {
        if (!cancelled) setError(friendly(err))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [invite, signIn])

  const poll = useCallback(async () => {
    if (!token || !room) return
    const after = lastIdRef.current
      ? `?after_id=${encodeURIComponent(lastIdRef.current)}`
      : ""
    try {
      const fresh = await call<GuestMessage[]>(
        `/seats/rooms/${room.id}/messages${after}`,
        { method: "GET" },
        token,
      )
      if (fresh.length) {
        lastIdRef.current = fresh[fresh.length - 1].id
        setMessages((prev) => [
          ...prev,
          ...fresh.filter((m) => !prev.some((p) => p.id === m.id)),
        ])
      }
    } catch (err) {
      if ((err as { status?: number }).status === 401) {
        try {
          await signIn() // token expired: exchange the key again
        } catch (inner) {
          setError(friendly(inner))
        }
      }
    }
  }, [token, room, signIn])

  useEffect(() => {
    void poll()
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void poll()
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [poll])

  const messageCount = messages.length
  useEffect(() => {
    if (messageCount > 0) bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messageCount])

  async function send(event: React.FormEvent) {
    event.preventDefault()
    const content = draft.trim()
    if (!content || !token || !room || sending) return
    setSending(true)
    setError("")
    try {
      await call(
        `/seats/rooms/${room.id}/messages`,
        { method: "POST", body: JSON.stringify({ content }) },
        token,
      )
      setDraft("")
      await poll()
    } catch (err) {
      setError(friendly(err))
    } finally {
      setSending(false)
    }
  }

  if (!invite) {
    return (
      <Shell>
        <h1 style={{ fontSize: 18, margin: 0 }}>Roundtable guest</h1>
        <p style={{ color: "#94a3b8", fontSize: 13 }}>
          Open the invite link the room owner sent you. It looks like{" "}
          <code>…/guest#key=rts_…</code>.
        </p>
      </Shell>
    )
  }

  return (
    <Shell>
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          gap: 12,
        }}
      >
        <div>
          <div
            style={{
              fontSize: 10,
              color: "#8b93ff",
              letterSpacing: "0.12em",
              fontWeight: 700,
            }}
          >
            ROUNDTABLE
          </div>
          <h1 style={{ fontSize: 18, margin: "4px 0 0" }}>
            {room?.name ?? "Joining…"}
          </h1>
        </div>
        {seat && (
          <div style={{ fontSize: 12, color: "#94a3b8" }}>
            You're in as{" "}
            <strong style={{ color: "#e2e8f0" }}>{seat.display_name}</strong>
          </div>
        )}
      </header>

      <div
        data-testid="guest-messages"
        style={{
          flex: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: 10,
          padding: "12px 2px",
          minHeight: 240,
        }}
      >
        {!room && !error && (
          <div
            style={{
              color: "#94a3b8",
              fontSize: 13,
              display: "flex",
              gap: 8,
              alignItems: "center",
            }}
          >
            <Loader2 size={14} className="animate-spin" /> Connecting…
          </div>
        )}
        {room && messages.length === 0 && (
          <div style={{ color: "#64748b", fontSize: 13 }}>No messages yet.</div>
        )}
        {messages.map((m) => {
          const mine = seat && m.sender_id === seat.id
          return (
            <div
              key={m.id}
              style={{
                alignSelf: mine ? "flex-end" : "flex-start",
                maxWidth: "85%",
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  color: "#94a3b8",
                  marginBottom: 3,
                  textAlign: mine ? "right" : "left",
                }}
              >
                {mine ? "You" : m.sender_name}
                {m.sender_type === "BOT" ? " · agent" : ""} ·{" "}
                {new Date(m.created_at).toLocaleTimeString([], {
                  hour: "numeric",
                  minute: "2-digit",
                })}
              </div>
              <div
                style={{
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  fontSize: 14,
                  lineHeight: 1.5,
                  padding: "9px 12px",
                  borderRadius: 12,
                  backgroundColor: mine
                    ? "rgba(59,130,246,0.25)"
                    : "rgba(30,41,59,0.8)",
                  border: "1px solid rgba(125,211,252,0.12)",
                }}
              >
                {m.content}
              </div>
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>

      {error && (
        <div role="alert" style={{ color: "#fecaca", fontSize: 13 }}>
          {error}
        </div>
      )}

      <form onSubmit={send} style={{ display: "flex", gap: 8 }}>
        <textarea
          aria-label="Message"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault()
              void send(e)
            }
          }}
          placeholder={room ? "Message the room…" : ""}
          disabled={!room}
          rows={2}
          maxLength={8000}
          style={{
            flex: 1,
            resize: "none",
            borderRadius: 10,
            border: "1px solid rgba(125,211,252,0.2)",
            backgroundColor: "rgba(7,13,28,0.8)",
            color: "#e2e8f0",
            padding: "10px 12px",
            fontSize: 14,
          }}
        />
        <button
          type="submit"
          aria-label="Send"
          disabled={!room || sending || !draft.trim()}
          style={{
            borderRadius: 10,
            border: "1px solid rgba(125,211,252,0.25)",
            backgroundColor: "rgba(14,116,144,0.35)",
            color: "#e0f2fe",
            padding: "0 16px",
            cursor: "pointer",
          }}
        >
          {sending ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Send size={16} />
          )}
        </button>
      </form>
    </Shell>
  )
}

function friendly(err: unknown): string {
  const status = (err as { status?: number })?.status
  if (status === 401)
    return "This invite link was revoked or replaced. Ask the room owner for a new one."
  if (status === 429)
    return "Slow down a little: too many messages in a minute."
  return (err as Error)?.message || "Something went wrong."
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        minHeight: "100dvh",
        backgroundColor: "#050a16",
        color: "#e2e8f0",
        display: "flex",
        justifyContent: "center",
        padding: 16,
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 760,
          display: "flex",
          flexDirection: "column",
          gap: 12,
          minHeight: "calc(100dvh - 32px)",
        }}
      >
        {children}
      </div>
    </div>
  )
}
