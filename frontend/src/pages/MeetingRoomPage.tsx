import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { ArrowLeft, Info, Loader2, Users } from "lucide-react"
import SparkbotSurfaceTabs from "@/components/Common/SparkbotSurfaceTabs"
import SparkbotSurfaceInfoDialog from "@/components/Common/SparkbotSurfaceInfoDialog"
import ChatInput from "@/components/chat/ChatInput"
import ChatWindow from "@/components/chat/ChatWindow"
import { loadMeetingRoomMeta, type WorkstationMeetingRoomMeta } from "@/lib/workstationMeeting"
import type { Message, User } from "@/lib/chat/types"

interface MeetingRoomPageProps {
  roomId: string
}

interface RoomDetail {
  id: string
  name: string
  description?: string
  meeting_mode_enabled: boolean
  meeting_mode_bots_mention_only: boolean
  meeting_mode_max_bot_msgs_per_min: number
}

interface RoomMemberMeResponse {
  user: User
}

export default function MeetingRoomPage({ roomId }: MeetingRoomPageProps) {
  const navigate = useNavigate()
  const [room, setRoom] = useState<RoomDetail | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [currentUser, setCurrentUser] = useState<User | null>(null)
  const [inputValue, setInputValue] = useState("")
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [infoOpen, setInfoOpen] = useState(false)
  const [meetingMeta, setMeetingMeta] = useState<WorkstationMeetingRoomMeta | null>(null)
  const [generatingNotes, setGeneratingNotes] = useState(false)
  const [latestArtifact, setLatestArtifact] = useState<{
    id: string
    content_markdown: string
    created_at: string
  } | null>(null)
  const [streamingToken, setStreamingToken] = useState("")
  const [streamingAgent, setStreamingAgent] = useState<string | null>(null)
  const [streamError, setStreamError] = useState("")
  const streamAbortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    setMeetingMeta(loadMeetingRoomMeta(roomId))
  }, [roomId])

  useEffect(() => {
    if (!roomId) return
    fetch(`/api/v1/chat/rooms/${roomId}/artifacts?type=notes&limit=1`, {
      credentials: "include",
    })
      .then((r) => (r.ok ? r.json() : []))
      .then((artifacts: Array<{ id: string; content_markdown: string; created_at: string }>) => {
        if (artifacts.length > 0) setLatestArtifact(artifacts[0])
      })
      .catch(() => {})
  }, [roomId])

  useEffect(() => {
    let cancelled = false

    async function loadRoomState() {
      try {
        const [roomRes, messagesRes, meRes] = await Promise.all([
          fetch(`/api/v1/chat/rooms/${roomId}`, { credentials: "include" }),
          fetch(`/api/v1/chat/rooms/${roomId}/messages`, { credentials: "include" }),
          fetch(`/api/v1/chat/rooms/${roomId}/members/me`, { credentials: "include" }),
        ])

        if (!cancelled && roomRes.ok) {
          setRoom(await roomRes.json())
        }

        if (!cancelled && messagesRes.ok) {
          const messageData = await messagesRes.json()
          setMessages(messageData.messages ?? [])
        }

        if (!cancelled && meRes.ok) {
          const membership = (await meRes.json()) as RoomMemberMeResponse
          setCurrentUser(membership.user ?? null)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    loadRoomState()

    return () => {
      cancelled = true
    }
  }, [roomId])

  const seatedParticipants = useMemo(
    () => meetingMeta?.seats ?? [],
    [meetingMeta],
  )

  const reloadMessages = async () => {
    const res = await fetch(`/api/v1/chat/rooms/${roomId}/messages`, { credentials: "include" })
    if (res.ok) {
      const data = await res.json()
      setMessages(data.messages ?? [])
    }
  }

  async function handleSendMessage(content: string) {
    if (!content.trim() || sending) return

    // Cancel any in-flight stream
    streamAbortRef.current?.abort()
    const abort = new AbortController()
    streamAbortRef.current = abort

    setSending(true)
    setStreamingToken("")
    setStreamingAgent(null)
    setStreamError("")
    setInputValue("")

    // Derive participant handles from seated agents (when no @mention present)
    const hasMention = /^@\w+/.test(content.trim())
    const participants = (!hasMention && seatedParticipants.length > 0)
      ? seatedParticipants.map((s) => s.label.toLowerCase().replace(/\s+/g, ""))
      : undefined

    try {
      const response = await fetch(`/api/v1/chat/rooms/${roomId}/messages/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        signal: abort.signal,
        body: JSON.stringify({ content: content.trim(), ...(participants ? { participants } : {}) }),
      })

      if (!response.ok || !response.body) {
        const errText = await response.text().catch(() => "")
        throw new Error(errText || "Could not send meeting message.")
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let accumulated = ""
      let streamDone = false

      while (!streamDone) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        for (const line of chunk.split("\n")) {
          if (!line.startsWith("data: ")) continue
          try {
            const evt = JSON.parse(line.slice(6))
            if (evt.type === "token") {
              accumulated += evt.token
              setStreamingToken(accumulated)
            } else if (evt.type === "agent_start") {
              // New agent starting — reset accumulated and update label
              accumulated = ""
              setStreamingToken("")
              setStreamingAgent(evt.label || evt.agent || null)
            } else if (evt.type === "agent_done") {
              accumulated = ""
              setStreamingToken("")
              setStreamingAgent(null)
              await reloadMessages()
            } else if (evt.type === "done") {
              streamDone = true
              break
            } else if (evt.type === "error") {
              const msg = typeof evt.error === "string" ? evt.error : "An error occurred."
              const friendly = msg.includes("guardrail") || msg.includes("data policy")
                ? "OpenRouter model unavailable (privacy policy). Check OpenRouter settings or switch model in Controls."
                : msg.includes("NotFoundError") || msg.includes("404")
                ? "Model not found. Please check your model settings in Controls."
                : msg.substring(0, 120)
              setStreamError(friendly)
              streamDone = true
              break
            }
          } catch {
            // malformed SSE line — ignore
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        console.error("Meeting stream error:", err)
        setStreamError((err as Error).message || "Stream error. Check console.")
      }
    } finally {
      setStreamingToken("")
      setStreamingAgent(null)
      setSending(false)
      await reloadMessages()
    }
  }

  async function handleGenerateNotes() {
    if (generatingNotes) return
    setGeneratingNotes(true)
    try {
      const res = await fetch(`/api/v1/chat/rooms/${roomId}/artifacts/generate`, {
        method: "POST",
        credentials: "include",
      })
      if (!res.ok) throw new Error("Could not generate notes")
      const artifact = await res.json()
      setLatestArtifact(artifact)
    } catch (err) {
      console.error("Generate notes error:", err)
    } finally {
      setGeneratingNotes(false)
    }
  }

  return (
    <>
      <div
        style={{
          minHeight: "100dvh",
          display: "flex",
          flexDirection: "column",
          background:
            "linear-gradient(180deg, rgba(6,10,19,1), rgba(8,14,28,1), rgba(11,17,33,1))",
        }}
      >
        <header
          style={{
            height: 56,
            borderBottom: "1px solid rgba(99,102,241,0.16)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 20px",
            background:
              "linear-gradient(180deg, rgba(7,11,24,0.98), rgba(10,16,31,0.94))",
            flexShrink: 0,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button
              type="button"
              onClick={() => navigate({ to: "/workstation" })}
              style={{
                width: 34,
                height: 34,
                borderRadius: 999,
                border: "1px solid rgba(99,102,241,0.16)",
                backgroundColor: "rgba(7, 13, 28, 0.72)",
                color: "#cbd5f5",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
              aria-label="Back to Workstation"
            >
              <ArrowLeft size={16} />
            </button>
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
                Meeting Room
              </div>
              <div style={{ fontSize: 16, fontWeight: 700, color: "#e2e8f0", marginTop: 4 }}>
                {room?.name ?? "Roundtable"}
              </div>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <SparkbotSurfaceTabs
              active={infoOpen ? "info" : undefined}
              onChat={() => navigate({ to: "/dm" })}
              onWorkstation={() => navigate({ to: "/workstation" })}
              onControls={() => navigate({ to: "/dm", search: { controls: "open" } })}
              onInfo={() => setInfoOpen((prev) => !prev)}
            />
            <div
              style={{
                border: "1px solid rgba(125,211,252,0.18)",
                borderRadius: 999,
                padding: "6px 10px",
                fontSize: 10,
                color: "#cbd5f5",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
              }}
            >
              One at a time
            </div>
          </div>
        </header>

        <main
          style={{
            flex: 1,
            padding: 16,
            display: "grid",
            gridTemplateColumns: "320px minmax(0, 1fr)",
            gap: 16,
          }}
        >
          <aside
            style={{
              border: "1px solid rgba(99,102,241,0.16)",
              borderRadius: 18,
              backgroundColor: "rgba(7, 13, 28, 0.68)",
              padding: 16,
              display: "flex",
              flexDirection: "column",
              gap: 14,
              alignSelf: "start",
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
                Roundtable
              </div>
              <p style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.7, margin: "8px 0 0" }}>
                Launched from Workstation. This MVP room uses turn-taking mode, so keep one speaker
                active at a time and hand the floor forward deliberately.
              </p>
            </div>

            <div
              style={{
                border: "1px solid rgba(125,211,252,0.14)",
                borderRadius: 12,
                padding: "12px 14px",
                backgroundColor: "rgba(10,17,32,0.72)",
              }}
            >
              <div
                style={{
                  fontSize: 10,
                  color: "#cbd5f5",
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  fontWeight: 700,
                  marginBottom: 10,
                }}
              >
                Seated participants
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {seatedParticipants.map((seat) => (
                  <div
                    key={seat.stationId}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      border: `1px solid ${seat.accentHex}22`,
                      borderRadius: 10,
                      padding: "9px 10px",
                      backgroundColor: `${seat.accentHex}10`,
                    }}
                  >
                    <span
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: "50%",
                        backgroundColor: seat.accentHex,
                        boxShadow: `0 0 10px ${seat.accentHex}55`,
                        flexShrink: 0,
                      }}
                    />
                    <div style={{ minWidth: 0 }}>
                      <div
                        style={{
                          fontSize: 11,
                          color: "#e2e8f0",
                          fontWeight: 700,
                          letterSpacing: "0.04em",
                          textTransform: "uppercase",
                        }}
                      >
                        Chair {seat.seatIndex + 1}: {seat.label}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <button
              type="button"
              onClick={() => navigate({ to: "/workstation" })}
              style={{
                border: "1px solid rgba(99,102,241,0.16)",
                borderRadius: 10,
                backgroundColor: "rgba(7, 13, 28, 0.72)",
                color: "#cbd5f5",
                padding: "10px 12px",
                cursor: "pointer",
                fontSize: 11,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                fontWeight: 700,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
              }}
            >
              <Users size={14} />
              Back to Workstation
            </button>

            {/* Meeting Notes */}
            <div
              style={{
                borderTop: "1px solid rgba(99,102,241,0.16)",
                paddingTop: 12,
                marginTop: 4,
              }}
            >
              <button
                type="button"
                onClick={handleGenerateNotes}
                disabled={generatingNotes}
                style={{
                  width: "100%",
                  borderRadius: 8,
                  border: "1px solid rgba(99,102,241,0.3)",
                  backgroundColor: "rgba(49,46,129,0.2)",
                  padding: "8px 12px",
                  fontSize: 11,
                  color: "#a5b4fc",
                  cursor: generatingNotes ? "not-allowed" : "pointer",
                  opacity: generatingNotes ? 0.5 : 1,
                  transition: "background 0.15s",
                  letterSpacing: "0.06em",
                }}
              >
                {generatingNotes ? "Generating notes…" : "Generate Meeting Notes"}
              </button>
              {latestArtifact && (
                <div
                  style={{
                    marginTop: 10,
                    borderRadius: 8,
                    border: "1px solid rgba(99,102,241,0.16)",
                    backgroundColor: "rgba(7,13,28,0.6)",
                    padding: 10,
                  }}
                >
                  <p
                    style={{
                      marginBottom: 6,
                      fontSize: 9,
                      fontWeight: 700,
                      letterSpacing: "0.1em",
                      textTransform: "uppercase",
                      color: "#64748b",
                    }}
                  >
                    Meeting Notes · {new Date(latestArtifact.created_at).toLocaleTimeString()}
                  </p>
                  <pre
                    style={{
                      maxHeight: 256,
                      overflowY: "auto",
                      whiteSpace: "pre-wrap",
                      fontSize: 11,
                      color: "#cbd5e1",
                      lineHeight: 1.6,
                      margin: 0,
                      fontFamily: "inherit",
                    }}
                  >
                    {latestArtifact.content_markdown}
                  </pre>
                </div>
              )}
            </div>
          </aside>

          <section
            style={{
              border: "1px solid rgba(99,102,241,0.16)",
              borderRadius: 18,
              backgroundColor: "rgba(7, 13, 28, 0.68)",
              overflow: "hidden",
              display: "flex",
              flexDirection: "column",
              minHeight: 0,
            }}
          >
            <div
              style={{
                padding: "14px 16px",
                borderBottom: "1px solid rgba(99,102,241,0.12)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
              }}
            >
              <div>
                <div style={{ fontSize: 16, fontWeight: 700, color: "#e2e8f0" }}>
                  {room?.name ?? "Roundtable"}
                </div>
                <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 4 }}>
                  Turn-taking mode is active. One participant speaks at a time.
                </div>
              </div>
              <button
                type="button"
                onClick={() => setInfoOpen(true)}
                style={{
                  width: 34,
                  height: 34,
                  borderRadius: 999,
                  border: "1px solid rgba(99,102,241,0.16)",
                  backgroundColor: "rgba(7, 13, 28, 0.72)",
                  color: "#cbd5f5",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
                aria-label="Meeting room info"
              >
                <Info size={16} />
              </button>
            </div>

            {loading ? (
              <div className="flex flex-1 items-center justify-center">
                <Loader2 className="size-8 animate-spin text-slate-500" />
              </div>
            ) : (
              <>
                <ChatWindow
                  messages={messages}
                  currentUser={currentUser}
                  isLoading={false}
                  typingUsers={[]}
                  className="flex-1"
                />
                {streamError && (
                  <div
                    style={{
                      padding: "8px 16px",
                      margin: "0 0 2px",
                      fontSize: 12,
                      color: "#f87171",
                      borderTop: "1px solid rgba(248,113,113,0.20)",
                      background: "rgba(248,113,113,0.06)",
                    }}
                  >
                    ⚠ {streamError}
                  </div>
                )}
                {streamingToken && (
                  <div
                    style={{
                      padding: "8px 16px",
                      margin: "0 0 2px",
                      fontSize: 13,
                      color: "#a5b4fc",
                      borderTop: "1px solid rgba(99,102,241,0.10)",
                      whiteSpace: "pre-wrap",
                      lineHeight: 1.6,
                      fontStyle: "italic",
                    }}
                  >
                    {streamingAgent && (
                      <span style={{ fontWeight: 700, fontStyle: "normal", marginRight: 8, fontSize: 11, color: "#7dd3fc" }}>
                        {streamingAgent}
                      </span>
                    )}
                    {streamingToken}
                    <span style={{ animation: "blink 1s step-end infinite", opacity: 0.7 }}>▌</span>
                  </div>
                )}
                <div
                  style={{
                    padding: "4px 16px 2px",
                    fontSize: 10,
                    color: "#475569",
                    letterSpacing: "0.05em",
                  }}
                >
                  {seatedParticipants.length > 0
                    ? `Call on a participant: ${seatedParticipants.map((s) => `@${s.label.toLowerCase().replace(/\s+/g, "")}`).join("  ")}`
                    : "Type your message and the roundtable moderator will respond."}
                </div>
                <ChatInput
                  value={inputValue}
                  onChange={setInputValue}
                  onSubmit={handleSendMessage}
                  isLoading={sending}
                  placeholder="Send the next turn into the roundtable…"
                />
              </>
            )}
          </section>
        </main>
      </div>

      <SparkbotSurfaceInfoDialog
        open={infoOpen}
        title="Roundtable Meeting Room"
        subtitle="This room was launched from Workstation as the live group chat version of the central table."
        bullets={[
          "Roundtable is the live room spawned from the eight-seat table in Workstation.",
          "The current protocol is one at a time: keep a single active speaker and hand the floor forward.",
          "Use Workstation to reseat desks, change the table, or launch again after reconfiguring chairs.",
          "Chat remains the everyday home. This room is the focused collaboration surface.",
        ]}
        onClose={() => setInfoOpen(false)}
      />
    </>
  )
}
