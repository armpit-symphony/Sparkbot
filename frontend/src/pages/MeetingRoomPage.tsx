import { useEffect, useMemo, useState } from "react"
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

  useEffect(() => {
    setMeetingMeta(loadMeetingRoomMeta(roomId))
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
    const pollId = window.setInterval(loadRoomState, 3000)

    return () => {
      cancelled = true
      window.clearInterval(pollId)
    }
  }, [roomId])

  const seatedParticipants = useMemo(
    () => meetingMeta?.seats ?? [],
    [meetingMeta],
  )

  async function handleSendMessage(content: string) {
    if (!content.trim() || sending) return
    setSending(true)
    try {
      const response = await fetch(`/api/v1/chat/rooms/${roomId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ content: content.trim() }),
      })
      if (!response.ok) {
        throw new Error("Could not send meeting message.")
      }
      setInputValue("")
      const messagesRes = await fetch(`/api/v1/chat/rooms/${roomId}/messages`, {
        credentials: "include",
      })
      if (messagesRes.ok) {
        const messageData = await messagesRes.json()
        setMessages(messageData.messages ?? [])
      }
    } finally {
      setSending(false)
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
                <ChatInput
                  value={inputValue}
                  onChange={setInputValue}
                  onSubmit={handleSendMessage}
                  isLoading={sending}
                  placeholder="Send the next turn into the roundtable..."
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
